"""
General Normalization Layer for Mint & Match (Deterministic Pre-Agent Processing)
==================================================================================
Reads raw CSV sources (v1 and v2 bank statements & GPay histories) and reshapes
each row into the canonical Record schema:

    {
        "source": "bank" | "gpay",
        "row_id": str,                  # stable identifier e.g. "bank_0", "gpay_0"
        "date": "DD-MM-YYYY",
        "time": "HH:MM" or None,       # bank NEVER has time -> always None (structural)
        "amount": signed float,         # negative = money out, positive = money in
        "transaction_id": str or None,  # 12-digit UPI reference ID or None
        "merchant": str or None,        # Counterparty / Merchant name
        "category": str or None,        # Expense / income category
        "currency": str,                # 'INR'
        "payment_method": str or None,  # 'UPI', 'Card', 'GPay Balance', etc.
        "raw_description": str          # original description string
    }

Output: two pandas DataFrames (normalized_bank, normalized_gpay).
"""

import os
import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
import pandas as pd


# ---------- Feature Extraction Helpers ----------

def extract_transaction_id_from_desc(description: str) -> Optional[str]:
    """Extracts 12-digit UPI transaction reference ID from description."""
    if not isinstance(description, str) or not description.strip():
        return None
    
    # Check regex pattern: UPI/<12-digit ID>/...
    match = re.search(r"UPI/(\d{12})/", description)
    if match:
        return match.group(1)
    
    # Secondary regex: any 12 continuous digits after UPI/
    match = re.search(r"UPI/(\d+)/", description)
    if match and len(match.group(1)) == 12:
        return match.group(1)
        
    # Fallback: token scan
    for token in description.split("/"):
        clean = token.strip()
        if len(clean) == 12 and clean.isdigit():
            return clean
            
    return None


def extract_merchant_from_desc(description: str) -> Optional[str]:
    """Extracts merchant/counterparty name from description."""
    if not isinstance(description, str) or not description.strip():
        return None
    
    desc = description.strip()
    
    # Pattern 1: UPI/<id>/<Merchant>/Payment
    if desc.startswith("UPI/"):
        parts = desc.split("/")
        if len(parts) >= 3:
            return parts[2].strip()
        elif len(parts) == 2:
            return parts[1].strip()
            
    # Pattern 2: POS/<Merchant>/RETAIL or POS/<Merchant>
    if desc.startswith("POS/"):
        parts = desc.split("/")
        if len(parts) >= 2:
            return parts[1].strip()
            
    # Pattern 3: NEFT CR/<TYPE>/<Company> or NEFT/<Company>
    if desc.startswith("NEFT"):
        parts = desc.split("/")
        return parts[-1].strip()
        
    # Pattern 4: CHQ DEP CLEARING/<ID>
    if "CHQ" in desc.upper() or "CHEQUE" in desc.upper():
        return "Cheque Clearing"
        
    # Pattern 5: ATM WDL/<Location>/<Branch>
    if "ATM" in desc.upper():
        parts = desc.split("/")
        if len(parts) >= 2:
            return f"ATM ({parts[1].strip()})"
        return "ATM Withdrawal"

    # Pattern 6: Paid to <Merchant> / Received from <Merchant>
    if desc.lower().startswith("paid to "):
        return desc[8:].strip()
    if desc.lower().startswith("received from "):
        return desc[14:].strip()

    return None


def parse_date_to_iso(date_str: Any) -> str:
    """Converts dates like '02/08/2026' or 'Aug 02, 2026' or '2026-08-02' to ISO 'YYYY-MM-DD'."""
    if not date_str or pd.isna(date_str):
        return ""
    
    clean_date = str(date_str).strip()
    for fmt in ("%d/%m/%Y", "%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(clean_date, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return clean_date


def parse_time_to_hhmm(time_str: Any) -> Optional[str]:
    """Converts times like '4:20 PM' or '16:20' to 'HH:MM'."""
    if not time_str or pd.isna(time_str):
        return None
    
    clean_time = str(time_str).strip()
    if not clean_time or clean_time.lower() == "none" or clean_time.lower() == "nan":
        return None
        
    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(clean_time, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return clean_time


def parse_signed_amount(
    withdrawal_val: Any = None,
    deposit_val: Any = None,
    amount_val: Any = None
) -> float:
    """
    Computes signed float amount:
    - Withdrawal -> negative float
    - Deposit -> positive float
    - Single signed amount column (GPay) -> parsed directly
    """
    # Check withdrawal
    if withdrawal_val is not None and not pd.isna(withdrawal_val):
        w_str = str(withdrawal_val).replace(",", "").strip()
        if w_str and w_str.lower() != "nan":
            try:
                return -abs(float(w_str))
            except ValueError:
                pass

    # Check deposit
    if deposit_val is not None and not pd.isna(deposit_val):
        d_str = str(deposit_val).replace(",", "").strip()
        if d_str and d_str.lower() != "nan":
            try:
                return abs(float(d_str))
            except ValueError:
                pass

    # Check single amount column
    if amount_val is not None and not pd.isna(amount_val):
        a_str = str(amount_val).replace(",", "").strip()
        if a_str and a_str.lower() != "nan":
            try:
                return float(a_str)
            except ValueError:
                pass

    return 0.0


# ---------- Bank statement normalization ----------

def normalize_bank_row(row: Dict[str, Any], index: int) -> Dict[str, Any]:
    date_iso = parse_date_to_iso(row.get("Date"))
    
    amount = parse_signed_amount(
        withdrawal_val=row.get("Withdrawal"),
        deposit_val=row.get("Deposit"),
        amount_val=row.get("Amount")
    )
    
    desc = str(row.get("Description", "")).strip()
    
    # Extract transaction ID from explicit column if present, else regex from description
    txn_col = str(row.get("Transaction ID", "")).strip()
    txn_id = txn_col if (txn_col and txn_col.lower() != "nan" and txn_col.lower() != "none") else extract_transaction_id_from_desc(desc)
    
    # Extract merchant
    merchant_col = str(row.get("Merchant", "")).strip()
    merchant = merchant_col if (merchant_col and merchant_col.lower() != "nan") else extract_merchant_from_desc(desc)
    
    # Category and Currency
    category = row.get("Category")
    if pd.isna(category) or not str(category).strip() or str(category).lower() == "nan":
        category = None
    else:
        category = str(category).strip()
        
    currency = str(row.get("Currency", "INR")).strip() or "INR"

    return {
        "source": "bank",
        "row_id": f"bank_{index}",
        "date": date_iso,
        "time": None,  # bank statements never capture time -- structural, not missing data
        "amount": round(amount, 2),
        "transaction_id": txn_id,
        "merchant": merchant,
        "category": category,
        "currency": currency,
        "payment_method": row.get("Payment Method"),
        "raw_description": desc,
    }


# ---------- GPay history normalization ----------

def normalize_gpay_row(row: Dict[str, Any], index: int) -> Dict[str, Any]:
    date_iso = parse_date_to_iso(row.get("Date"))
    time_str = parse_time_to_hhmm(row.get("Time"))
    
    amount = parse_signed_amount(amount_val=row.get("Amount"))
    
    # Transaction ID
    txn_raw = str(row.get("Transaction ID", "")).strip()
    txn_id = txn_raw if (txn_raw and txn_raw.lower() != "nan" and txn_raw.lower() != "none") else None
    
    desc = str(row.get("Description", "")).strip()
    
    # Merchant
    merchant_col = str(row.get("Merchant", "")).strip()
    merchant = merchant_col if (merchant_col and merchant_col.lower() != "nan") else extract_merchant_from_desc(desc)
    
    payment_method = row.get("Payment Method")
    if pd.isna(payment_method) or not str(payment_method).strip() or str(payment_method).lower() == "nan":
        payment_method = "UPI"
    else:
        payment_method = str(payment_method).strip()

    category = row.get("Category")
    if pd.isna(category) or not str(category).strip() or str(category).lower() == "nan":
        category = None
    else:
        category = str(category).strip()

    currency = str(row.get("Currency", "INR")).strip() or "INR"

    return {
        "source": "gpay",
        "row_id": f"gpay_{index}",
        "date": date_iso,
        "time": time_str,
        "amount": round(amount, 2),
        "transaction_id": txn_id,
        "merchant": merchant,
        "category": category,
        "currency": currency,
        "payment_method": payment_method,
        "raw_description": desc,
    }


# ---------- Main normalization entry points ----------

def normalize_bank_csv(path: str) -> pd.DataFrame:
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    rows = [normalize_bank_row(r, idx) for idx, r in enumerate(raw.to_dict(orient="records"))]
    return pd.DataFrame(rows)


def normalize_gpay_csv(path: str) -> pd.DataFrame:
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    rows = [normalize_gpay_row(r, idx) for idx, r in enumerate(raw.to_dict(orient="records"))]
    return pd.DataFrame(rows)


def normalize_sources(
    bank_csv_path: str = "new data/bank_statement_v2.csv",
    gpay_csv_path: str = "new data/gpay_history_v2.csv",
    save_outputs: bool = True
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    # Fallback to other standard locations if paths do not exist
    if not os.path.exists(bank_csv_path):
        for candidate in ["data/bank_statement.csv", "bank_statement.csv", "new data/bank_statement_v2.csv"]:
            if os.path.exists(candidate):
                bank_csv_path = candidate
                break
                
    if not os.path.exists(gpay_csv_path):
        for candidate in ["data/gpay_history.csv", "gpay_history.csv", "new data/gpay_history_v2.csv"]:
            if os.path.exists(candidate):
                gpay_csv_path = candidate
                break

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


if __name__ == "__main__":
    bank_p = "new data/bank_statement_v2.csv" if os.path.exists("new data/bank_statement_v2.csv") else "bank_statement.csv"
    gpay_p = "new data/gpay_history_v2.csv" if os.path.exists("new data/gpay_history_v2.csv") else "gpay_history.csv"
    
    nb, ng = normalize_sources(bank_p, gpay_p, save_outputs=True)
    print(f"[✓] Normalized {len(nb)} Bank rows & {len(ng)} GPay rows.")
    print("\nSample Normalized Bank Row:")
    print(nb.iloc[0].to_dict())
    print("\nSample Normalized GPay Row:")
    print(ng.iloc[0].to_dict())
