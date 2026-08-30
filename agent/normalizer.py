"""
Normalization Layer for Mint & Match (Deterministic Pre-Agent Processing)
==========================================================================
Reads the raw CSV sources (bank statements, GPay histories) and reshapes
each row into the canonical Record schema:

    {
        "source": "bank" | "gpay",
        "row_id": str,              # stable identifier e.g. "bank_0", "gpay_0"
        "date": "YYYY-MM-DD",
        "time": "HH:MM" or None,   # bank NEVER has time -> always None (structural)
        "amount": signed float,     # negative = money out, positive = money in
        "transaction_id": str or None,
        "raw_description": str      # original description string
    }

Output: two pandas DataFrames (normalized_bank, normalized_gpay).
"""

import os
import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
import pandas as pd


# ---------- Bank statement normalization ----------

def normalize_bank_row(row: Dict[str, Any], index: int) -> Dict[str, Any]:
    # Date: "02/08/2026" -> "2026-08-02"
    date_raw = str(row.get("Date", "")).strip()
    try:
        date_obj = datetime.strptime(date_raw, "%d/%m/%Y")
        date_iso = date_obj.strftime("%Y-%m-%d")
    except Exception:
        date_iso = date_raw

    # Amount: Withdrawal -> negative, Deposit -> positive
    withdrawal = str(row.get("Withdrawal", "")).strip()
    deposit = str(row.get("Deposit", "")).strip()
    
    amount = 0.0
    if withdrawal:
        try:
            amount = -abs(float(withdrawal.replace(",", "")))
        except ValueError:
            amount = 0.0
    elif deposit:
        try:
            amount = abs(float(deposit.replace(",", "")))
        except ValueError:
            amount = 0.0

    # Transaction ID: embedded in description like "UPI/808117155426/Name/Payment"
    # Not present on non-UPI rows (POS, ATM, interest, cheque, charges) -> None
    txn_id = None
    desc = str(row.get("Description", "")).strip()
    match = re.search(r"UPI/(\d+)/", desc)
    if match:
        txn_id = match.group(1)

    return {
        "source": "bank",
        "row_id": f"bank_{index}",
        "date": date_iso,
        "time": None,  # bank statements never capture time -- structural, not missing data
        "amount": round(amount, 2),
        "transaction_id": txn_id,
        "raw_description": desc,
    }


# ---------- GPay history normalization ----------

def normalize_gpay_row(row: Dict[str, Any], index: int) -> Dict[str, Any]:
    # Date: "Aug 02, 2026" -> "2026-08-02"
    date_raw = str(row.get("Date", "")).strip()
    try:
        date_obj = datetime.strptime(date_raw, "%b %d, %Y")
        date_iso = date_obj.strftime("%Y-%m-%d")
    except Exception:
        date_iso = date_raw

    # Time: "4:20 PM" -> "16:20"
    time_raw = str(row.get("Time", "")).strip()
    time_str = None
    if time_raw:
        try:
            time_obj = datetime.strptime(time_raw, "%I:%M %p")
            time_str = time_obj.strftime("%H:%M")
        except Exception:
            time_str = time_raw

    # Amount: GPay already stores it signed ("-680.66" / "+150.99")
    amount_raw = str(row.get("Amount", "0.0")).replace(",", "").strip()
    try:
        amount = float(amount_raw)
    except ValueError:
        amount = 0.0

    # Transaction ID: always present in GPay, already a clean column
    txn_raw = str(row.get("Transaction ID", "")).strip()
    txn_id = txn_raw if txn_raw else None

    return {
        "source": "gpay",
        "row_id": f"gpay_{index}",
        "date": date_iso,
        "time": time_str,
        "amount": round(amount, 2),
        "transaction_id": txn_id,
        "raw_description": str(row.get("Description", "")).strip(),
    }


# ---------- Main normalization entry point ----------

def normalize_bank_csv(path: str) -> pd.DataFrame:
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    rows = [normalize_bank_row(r, idx) for idx, r in enumerate(raw.to_dict(orient="records"))]
    return pd.DataFrame(rows)


def normalize_gpay_csv(path: str) -> pd.DataFrame:
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    rows = [normalize_gpay_row(r, idx) for idx, r in enumerate(raw.to_dict(orient="records"))]
    return pd.DataFrame(rows)


def normalize_sources(
    bank_csv_path: str = "data/bank_statement.csv",
    gpay_csv_path: str = "data/gpay_history.csv",
    save_outputs: bool = True
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    # Fallback to root directory if data/ paths do not exist
    if not os.path.exists(bank_csv_path) and os.path.exists("bank_statement.csv"):
        bank_csv_path = "bank_statement.csv"
    if not os.path.exists(gpay_csv_path) and os.path.exists("gpay_history.csv"):
        gpay_csv_path = "gpay_history.csv"

    normalized_bank = normalize_bank_csv(bank_csv_path)
    normalized_gpay = normalize_gpay_csv(gpay_csv_path)

    if save_outputs:
        out_dir = os.path.dirname(bank_csv_path) or "data"
        if not os.path.exists(out_dir) and out_dir:
            os.makedirs(out_dir, exist_ok=True)
        
        out_bank = os.path.join(out_dir, "normalized_bank_statements.csv") if out_dir else "normalized_bank_statements.csv"
        out_gpay = os.path.join(out_dir, "normalized_gpay_history.csv") if out_dir else "normalized_gpay_history.csv"
        
        normalized_bank.to_csv(out_bank, index=False)
        normalized_gpay.to_csv(out_gpay, index=False)

    return normalized_bank, normalized_gpay
