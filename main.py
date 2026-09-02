"""
Main CLI Entry Point for Mint & Match (AI Finance Controller - Track 04)
========================================================================

Executes the multi-source reconciliation loop across bank statements and
GPay payment histories using LangGraph and Groq exception reasoning.
"""

import argparse
import csv
import json
import os
import sys
from typing import Any, Dict, List, Union

# Ensure UTF-8 output encoding for terminal dashboards
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from datetime import datetime
from dotenv import load_dotenv

# Ensure environment is loaded
load_dotenv()

from agent import normalize_sources, run_reconciliation, ReconciliationState


def parse_args():
    parser = argparse.ArgumentParser(
        description="Mint & Match — Multi-Source Reconciliation Agent (Razorpay Track 04)"
    )
    parser.add_argument(
        "--bank",
        type=str,
        default="data v3/bank_statement_v3.csv",
        help="Path to bank statement CSV (default: data v3/bank_statement_v3.csv)",
    )
    parser.add_argument(
        "--gpay",
        type=str,
        default="data v3/gpay_history_v3.csv",
        help="Path to GPay payment history CSV (default: data v3/gpay_history_v3.csv)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/reconciliation_report.json",
        help="Path for output reconciliation report JSON (default: output/reconciliation_report.json)",
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        default="output/reconciliation_report.csv",
        help="Path for output reconciliation report CSV (default: output/reconciliation_report.csv)",
    )
    parser.add_argument(
        "--groq-model",
        type=str,
        default=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        help="Groq model ID for Tier 3 exception reasoning",
    )
    return parser.parse_args()


def print_dashboard(final_state: Union[ReconciliationState, Dict[str, Any]]):
    stats = final_state.get("stats", {})
    confirmed = final_state.get("confirmed_matches", [])
    exceptions = final_state.get("exceptions", [])

    print("\n" + "=" * 80)
    print("           MINT & MATCH — RECONCILIATION AGENT DASHBOARD")
    print("           Track 04: AI Finance Controller (Multi-Source Reconciliation)")
    print("=" * 80)
    
    print("\n[+] 1. RECONCILIATION METRICS & THROUGHPUT")
    print("-" * 80)
    print(f"  * Total Bank Records Processed : {stats.get('total_bank_records', 0)}")
    print(f"  * Total GPay Records Loaded    : {stats.get('total_gpay_records', 0)}")
    print(f"  * Tier 1 Exact Matches (ID)    : {stats.get('tier1_exact_matches', 0)}")
    print(f"  * Tier 2 Fuzzy Matches (Amt/Dt): {stats.get('tier2_fuzzy_matches', 0)}")
    print(f"  * Total Confirmed Matches      : {stats.get('total_confirmed_matches', 0)}")
    print(f"  * Unresolved Exceptions (Tier3): {stats.get('unresolved_exceptions', 0)}")
    print(f"  * Overall Match Rate           : {stats.get('match_rate_percent', 0.0):.2f}%")
    print(f"  * Total Processing Time        : {stats.get('processing_time_seconds', 0.0):.4f} seconds")
    print(f"  * System Throughput            : {stats.get('throughput_records_per_second', 0.0):.2f} records/sec")
    print("-" * 80)

    print("\n[+] 2. SAMPLE CONFIRMED MATCHES (Top 5)")
    print("-" * 80)
    print(f"{'Bank Row':<10} | {'GPay Row':<10} | {'Tier':<22} | {'Date':<10} | {'Amount':<10} | {'Merchant / Description'}")
    print("-" * 80)
    for m in confirmed[:5]:
        bank = m.get("bank_record", {})
        merchant_or_desc = bank.get("merchant") or bank.get("raw_description", "")
        print(
            f"{m.get('bank_row_id', ''):<10} | "
            f"{m.get('gpay_row_id', ''):<10} | "
            f"{m.get('tier', ''):<22} | "
            f"{bank.get('date', ''):<10} | "
            f"{bank.get('amount', 0.0):<10.2f} | "
            f"{merchant_or_desc[:30]}"
        )
    if len(confirmed) > 5:
        print(f"  ... and {len(confirmed) - 5} more confirmed matches.")

    print("\n[!] 3. HONEST EXCEPTION LIST (Tier 3 - Unresolved Transactions)")
    print("-" * 80)
    if not exceptions:
        print("  None. All transactions were reconciled.")
    else:
        for idx, exc in enumerate(exceptions[:10], 1):
            rec = exc.get("record", {})
            cand_count = exc.get("candidate_count", 0)
            reason = exc.get("reason", "")
            cat_str = f" | Category: {rec.get('category')}" if rec.get('category') else ""
            print(f"\n  [{idx}] Record ID: {rec.get('row_id')} | Date: {rec.get('date')} | Amount: {rec.get('amount'):.2f}{cat_str}")
            print(f"      Description: {rec.get('raw_description')}")
            print(f"      Candidates Considered in Payment History: {cand_count}")
            print(f"      Reason: {reason}")
        if len(exceptions) > 10:
            print(f"\n  ... and {len(exceptions) - 10} more unresolved exceptions (see full list in exported report).")
    print("\n" + "=" * 80 + "\n")


def build_final_report(final_state: Union[ReconciliationState, Dict[str, Any]]) -> Dict[str, Any]:
    stats = final_state.get("stats", {})
    return {
        "match_rate_percent": stats.get("match_rate_percent", 0.0),
        "tier1_exact_matches": stats.get("tier1_exact_matches", 0),
        "tier2_fuzzy_matches": stats.get("tier2_fuzzy_matches", 0),
        "total_confirmed_matches": stats.get("total_confirmed_matches", 0),
        "unresolved_exceptions": stats.get("unresolved_exceptions", 0),
        "throughput_records_per_second": stats.get("throughput_records_per_second", 0.0),
        "processing_time_seconds": stats.get("processing_time_seconds", 0.0),
        "total_bank_records": stats.get("total_bank_records", 0),
        "total_gpay_records": stats.get("total_gpay_records", 0),
        "confirmed_matches": final_state.get("confirmed_matches", []),
        "exceptions": final_state.get("exceptions", []),
    }


def export_reconciliation_csv(final_state: Union[ReconciliationState, Dict[str, Any]], output_path: str):
    """
    Exports reconciliation results to a tabular CSV format with columns:
    date, merchant, tier, reason, amount, transaction_id
    """
    confirmed = final_state.get("confirmed_matches", [])
    exceptions = final_state.get("exceptions", [])
    
    rows: List[Dict[str, Any]] = []
    
    def get_order_key(row_id: str) -> int:
        if isinstance(row_id, str) and row_id.startswith("bank_"):
            try:
                return int(row_id.split("_")[1])
            except (IndexError, ValueError):
                pass
        return 999999

    for m in confirmed:
        bank = m.get("bank_record", {})
        gpay = m.get("gpay_record", {})
        tier = m.get("tier", "")
        reason = "Matched via exact UPI reference ID" if tier == "tier_1_exact_id" else "Matched via single candidate (date + amount)"
        rows.append({
            "order_key": get_order_key(bank.get("row_id", "")),
            "date": bank.get("date", ""),
            "merchant": bank.get("merchant") or gpay.get("merchant") or "",
            "tier": tier,
            "reason": reason,
            "amount": bank.get("amount", 0.0),
            "transaction_id": bank.get("transaction_id") or gpay.get("transaction_id") or "",
        })

    for exc in exceptions:
        bank = exc.get("record", {})
        rows.append({
            "order_key": get_order_key(bank.get("row_id", "")),
            "date": bank.get("date", ""),
            "merchant": bank.get("merchant") or "",
            "tier": "tier_3_exception",
            "reason": exc.get("reason", ""),
            "amount": bank.get("amount", 0.0),
            "transaction_id": bank.get("transaction_id") or "",
        })

    # Sort rows by original bank statement order
    rows.sort(key=lambda r: r["order_key"])
    for r in rows:
        r.pop("order_key", None)

    fieldnames = ["date", "merchant", "tier", "reason", "amount", "transaction_id"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def resolve_data_path(path: str, candidates: list) -> str:
    """Helper to locate files across new data/, data/, or root."""
    if os.path.exists(path):
        return path
    for cand in candidates:
        if os.path.exists(cand):
            return cand
    return path


def main():
    args = parse_args()
    
    if args.groq_model:
        os.environ["GROQ_MODEL"] = args.groq_model

    bank_path = resolve_data_path(
        args.bank,
        ["data v3/bank_statement_v3.csv", "new data/bank_statement_v2.csv", "data/bank_statement.csv", "bank_statement.csv"]
    )
    gpay_path = resolve_data_path(
        args.gpay,
        ["data v3/gpay_history_v3.csv", "new data/gpay_history_v2.csv", "data/gpay_history.csv", "gpay_history.csv"]
    )

    print(f"[*] Normalizing input sources:\n    - Bank: {bank_path}\n    - GPay: {gpay_path}")
    
    if not os.path.exists(bank_path):
        print(f"Error: Bank statement file not found at {bank_path}", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(gpay_path):
        print(f"Error: GPay history file not found at {gpay_path}", file=sys.stderr)
        sys.exit(1)

    bank_df, gpay_df = normalize_sources(bank_path, gpay_path, save_outputs=True)
    bank_records = bank_df.to_dict(orient="records")
    gpay_records = gpay_df.to_dict(orient="records")

    print(f"[*] Initializing LangGraph state graph with {len(bank_records)} bank records & {len(gpay_records)} GPay records...")
    final_state = run_reconciliation(bank_records, gpay_records)

    print_dashboard(final_state)

    # Ensure output directory exists
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    # Save output report JSON
    report = build_final_report(final_state)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"[+] Reconciliation JSON report successfully exported to {args.output}")

    # Save output report CSV
    export_reconciliation_csv(final_state, args.output_csv)
    print(f"[+] Reconciliation CSV report successfully exported to {args.output_csv}")


if __name__ == "__main__":
    main()
