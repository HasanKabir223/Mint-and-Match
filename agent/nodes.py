"""
Node implementations for the Mint & Match LangGraph Reconciliation Pipeline.
"""

import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

from .state import ReconciliationState

# Load environment variables
load_dotenv()


# ---------- Node 1: load_normalized_records ----------

def load_normalized_records(state: ReconciliationState) -> Dict[str, Any]:
    """
    Entry node: initializes tracking sets, match lists, and execution timer.
    """
    start_time = time.perf_counter()
    bank_records = state.get("bank_records", [])
    gpay_records = state.get("gpay_records", [])

    return {
        "bank_records": bank_records,
        "gpay_records": gpay_records,
        "claimed_gpay_ids": [],
        "confirmed_matches": [],
        "probable_matches": [],
        "unresolved_records": [],
        "exceptions": [],
        "stats": {
            "total_bank_records": len(bank_records),
            "total_gpay_records": len(gpay_records),
            "start_time": start_time,
        }
    }


# ---------- Node 2: attempt_exact_match (Tier 1) ----------

def attempt_exact_match(state: ReconciliationState) -> Dict[str, Any]:
    """
    Tier 1 Matching: Deterministic exact ID match on transaction_id.
    Matches bank rows that contain an extracted transaction_id with GPay rows.
    """
    bank_records = state.get("bank_records", [])
    gpay_records = state.get("gpay_records", [])
    claimed_gpay_ids = list(state.get("claimed_gpay_ids", []))
    confirmed_matches = list(state.get("confirmed_matches", []))

    # Index unclaimed GPay records by transaction_id
    gpay_by_txn_id: Dict[str, Dict[str, Any]] = {}
    for gpay in gpay_records:
        txn_id = gpay.get("transaction_id")
        if txn_id and gpay["row_id"] not in claimed_gpay_ids:
            gpay_by_txn_id[str(txn_id)] = gpay

    # Match bank records
    now_iso = datetime.now().isoformat()
    for bank in bank_records:
        bank_txn_id = bank.get("transaction_id")
        if bank_txn_id and str(bank_txn_id) in gpay_by_txn_id:
            gpay = gpay_by_txn_id[str(bank_txn_id)]
            
            # Ensure not already claimed in this batch
            if gpay["row_id"] not in claimed_gpay_ids:
                claimed_gpay_ids.append(gpay["row_id"])
                # Remove from lookup to avoid duplicate claiming
                del gpay_by_txn_id[str(bank_txn_id)]

                confirmed_matches.append({
                    "bank_row_id": bank["row_id"],
                    "gpay_row_id": gpay["row_id"],
                    "tier": "tier_1_exact_id",
                    "bank_record": bank,
                    "gpay_record": gpay,
                    "matched_at": now_iso,
                })

    return {
        "claimed_gpay_ids": claimed_gpay_ids,
        "confirmed_matches": confirmed_matches,
    }


# ---------- Node 3: attempt_fuzzy_match (Tier 2 & Filter for Tier 3) ----------

def attempt_fuzzy_match(state: ReconciliationState) -> Dict[str, Any]:
    """
    Tier 2 Matching: Deterministic candidate search on exact amount + date.
    - If exactly 1 candidate is found -> Confirmed Tier 2 match.
    - If 0 or 2+ candidates found -> Unresolved, routed to Tier 3 Exception Reasoner.
    """
    bank_records = state.get("bank_records", [])
    gpay_records = state.get("gpay_records", [])
    claimed_gpay_ids = list(state.get("claimed_gpay_ids", []))
    confirmed_matches = list(state.get("confirmed_matches", []))
    unresolved_records: List[Dict[str, Any]] = []

    # Identify bank records already matched in Tier 1
    matched_bank_ids = {m["bank_row_id"] for m in confirmed_matches}

    now_iso = datetime.now().isoformat()

    for bank in bank_records:
        if bank["row_id"] in matched_bank_ids:
            continue

        bank_date = bank.get("date")
        bank_amount = bank.get("amount", 0.0)

        # Search available GPay records for matching amount and date
        candidates = []
        for gpay in gpay_records:
            if gpay["row_id"] in claimed_gpay_ids:
                continue
            
            # Check exact date and exact amount (within floating point epsilon)
            if gpay.get("date") == bank_date and abs(gpay.get("amount", 0.0) - bank_amount) < 0.001:
                candidates.append(gpay)

        if len(candidates) == 1:
            # Single candidate -> Confident Tier 2 match
            gpay_match = candidates[0]
            claimed_gpay_ids.append(gpay_match["row_id"])
            confirmed_matches.append({
                "bank_row_id": bank["row_id"],
                "gpay_row_id": gpay_match["row_id"],
                "tier": "tier_2_amount_date",
                "bank_record": bank,
                "gpay_record": gpay_match,
                "matched_at": now_iso,
            })
        else:
            # 0 or 2+ candidates -> Tier 3 exception candidate
            unresolved_records.append({
                "bank_record": bank,
                "candidates_considered": candidates,
                "candidate_count": len(candidates),
            })

    return {
        "claimed_gpay_ids": claimed_gpay_ids,
        "confirmed_matches": confirmed_matches,
        "unresolved_records": unresolved_records,
    }


# ---------- Node 4: generate_exception_reason (Tier 3 Groq Reasoner) ----------

def _generate_fallback_reason(bank_rec: Dict[str, Any], candidates: List[Dict[str, Any]]) -> str:
    """Deterministic fallback reason if Groq API is unavailable."""
    desc = bank_rec.get("raw_description", "")
    date = bank_rec.get("date", "")
    amount = bank_rec.get("amount", 0.0)
    count = len(candidates)

    if count == 0:
        if "ATM" in desc.upper():
            return f"ATM cash withdrawal of {abs(amount):.2f} on {date} has no counterparty in UPI/payment history."
        if "POS" in desc.upper():
            return f"Point-of-sale card transaction of {abs(amount):.2f} on {date} does not correspond to any GPay UPI record."
        if "CHQ" in desc.upper() or "CHEQUE" in desc.upper():
            return f"Cheque clearing deposit of {abs(amount):.2f} on {date} is a direct bank operation with no UPI record."
        if "INT" in desc.upper() or "INTEREST" in desc.upper():
            return f"Bank interest credit of {abs(amount):.2f} on {date} is an internal bank entry without a payment app counterpart."
        return f"No corresponding GPay transaction of amount {amount:.2f} was found on date {date}."
    else:
        return f"Found {count} GPay transactions with identical amount {amount:.2f} on {date}; unable to disambiguate because bank statement lacks time timestamps."


def generate_exception_reason(state: ReconciliationState) -> Dict[str, Any]:
    """
    Tier 3 Reasoner: Calls Groq LLM to generate an honest, specific one-sentence
    explanation for every unresolved transaction.
    """
    unresolved_records = state.get("unresolved_records", [])
    exceptions: List[Dict[str, Any]] = []

    if not unresolved_records:
        return {"exceptions": exceptions}

    # Setup Groq client if API key is available
    groq_api_key = os.environ.get("GROQ_API_KEY", "").strip()
    groq_client = None
    if groq_api_key:
        try:
            from groq import Groq
            groq_client = Groq(api_key=groq_api_key)
        except Exception:
            groq_client = None

    # Preferred model: llama-3.3-70b-versatile or llama3-70b-8192 or user configured
    model_name = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    system_prompt = (
        "You are the exception reasoning engine of an automated financial reconciliation pipeline (Mint & Match).\n"
        "You are given an unresolved bank statement entry and its candidate matching payment records from GPay.\n"
        "Your task is to provide exactly ONE honest, concise, fact-based sentence explaining why reconciliation failed.\n\n"
        "Strict Guidelines:\n"
        "1. Never guess or hallucinate identities/facts not present in the record.\n"
        "2. If candidate count is 0: Explain that no matching transaction exists in the payment app on that date/amount. "
        "Reference if it is an ATM withdrawal, POS retail card payment, cheque deposit, interest credit, or bank charge.\n"
        "3. If candidate count is 2 or more: Explain that multiple transactions have the exact same amount and date, "
        "and resolution is impossible specifically because the bank statement lacks time timestamps to disambiguate them.\n"
        "4. Output ONLY the single sentence explanation without quotes or preamble."
    )

    for item in unresolved_records:
        bank_rec = item["bank_record"]
        candidates = item["candidates_considered"]
        count = item["candidate_count"]

        reason = None
        if groq_client:
            user_prompt = (
                f"Bank Record:\n"
                f"- Row ID: {bank_rec.get('row_id')}\n"
                f"- Date: {bank_rec.get('date')}\n"
                f"- Amount: {bank_rec.get('amount')}\n"
                f"- Description: {bank_rec.get('raw_description')}\n"
                f"- Time: None (bank does not record timestamps)\n\n"
                f"Matching Candidates Found in GPay: {count}\n"
            )
            if count > 0:
                for idx, c in enumerate(candidates, 1):
                    user_prompt += f"  Candidate {idx}: Time={c.get('time')}, Amount={c.get('amount')}, Desc='{c.get('raw_description')}', TxnID={c.get('transaction_id')}\n"

            try:
                # Primary model attempt
                response = groq_client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.1,
                    max_tokens=150,
                )
                reason = response.choices[0].message.content.strip()
            except Exception as e:
                # Fallback to llama3-8b-8192 or deterministic if model unavailable
                try:
                    fallback_response = groq_client.chat.completions.create(
                        model="llama-3.1-8b-instant",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.1,
                        max_tokens=150,
                    )
                    reason = fallback_response.choices[0].message.content.strip()
                except Exception:
                    reason = None

        if not reason:
            reason = _generate_fallback_reason(bank_rec, candidates)

        exceptions.append({
            "record": bank_rec,
            "candidates_considered": candidates,
            "candidate_count": count,
            "reason": reason,
        })

    return {"exceptions": exceptions}


# ---------- Node 5: compile_report ----------

def compile_report(state: ReconciliationState) -> Dict[str, Any]:
    """
    Terminal node: aggregates metrics, computes match rate & throughput,
    and structures the final output report.
    """
    end_time = time.perf_counter()
    stats = state.get("stats", {})
    start_time = stats.get("start_time", end_time)
    duration = max(0.0001, end_time - start_time)

    bank_records = state.get("bank_records", [])
    gpay_records = state.get("gpay_records", [])
    confirmed_matches = state.get("confirmed_matches", [])
    exceptions = state.get("exceptions", [])

    total_bank = len(bank_records)
    total_gpay = len(gpay_records)
    tier1_count = sum(1 for m in confirmed_matches if m.get("tier") == "tier_1_exact_id")
    tier2_count = sum(1 for m in confirmed_matches if m.get("tier") == "tier_2_amount_date")
    total_matches = tier1_count + tier2_count
    unresolved_count = len(exceptions)

    match_rate = round((total_matches / total_bank * 100), 2) if total_bank > 0 else 0.0
    throughput = round(total_bank / duration, 2)

    final_stats = {
        "total_bank_records": total_bank,
        "total_gpay_records": total_gpay,
        "tier1_exact_matches": tier1_count,
        "tier2_fuzzy_matches": tier2_count,
        "total_confirmed_matches": total_matches,
        "unresolved_exceptions": unresolved_count,
        "match_rate_percent": match_rate,
        "processing_time_seconds": round(duration, 3),
        "throughput_records_per_second": throughput,
        "start_time": start_time,
        "end_time": end_time,
    }

    return {"stats": final_stats}
