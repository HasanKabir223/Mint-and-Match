"""
Normalization Entry Point for Mint & Match
"""

import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from agent.normalizer import (
    normalize_sources,
    normalize_bank_csv,
    normalize_gpay_csv,
    normalize_bank_row,
    normalize_gpay_row,
    extract_transaction_id_from_desc,
    extract_merchant_from_desc,
)

__all__ = [
    "normalize_sources",
    "normalize_bank_csv",
    "normalize_gpay_csv",
    "normalize_bank_row",
    "normalize_gpay_row",
    "extract_transaction_id_from_desc",
    "extract_merchant_from_desc",
]

if __name__ == "__main__":
    bank_p = "new data/bank_statement_v2.csv" if os.path.exists("new data/bank_statement_v2.csv") else "bank_statement.csv"
    gpay_p = "new data/gpay_history_v2.csv" if os.path.exists("new data/gpay_history_v2.csv") else "gpay_history.csv"
    
    nb, ng = normalize_sources(bank_p, gpay_p, save_outputs=True)
    print(f"[+] Normalized {len(nb)} Bank rows & {len(ng)} GPay rows.")
    print("\nNormalized Bank (First 3):")
    print(nb.head(3).to_string())
    print("\nNormalized GPay (First 3):")
    print(ng.head(3).to_string())
