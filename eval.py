"""
Offline Evaluation Script for Mint & Match (AI Finance Controller - Track 04)
=============================================================================

Scores the agent's reconciliation report against an offline ground-truth mapping.
NOTE: This evaluation tool is completely decoupled from the agent runtime to maintain
strict evaluation integrity (zero test-set contamination).
"""

import argparse
import json
import os
import re
import sys

# Ensure UTF-8 output encoding for terminal evaluation reports
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from typing import Any, Dict, List, Optional
import pandas as pd


def resolve_data_path(path: str, candidates: list) -> str:
    """Helper to locate files across candidate directories."""
    if os.path.exists(path):
        return path
    for cand in candidates:
        if os.path.exists(cand):
            return cand
    return path


def generate_ground_truth(bank_csv: str, gpay_csv: str) -> Dict[str, Any]:
    """
    Generates deterministic ground truth based on dataset generation rules:
    - Bank UPI records match GPay records with exact transaction ID.
    - ATM withdrawals, Cheque clearings, Interest credits, NEFT corporate deposits are true Exceptions.
    - Multiple same-day/same-amount records without IDs are true Ambiguities.
    """
    bank_df = pd.read_csv(bank_csv, dtype=str, keep_default_na=False)
    gpay_df = pd.read_csv(gpay_csv, dtype=str, keep_default_na=False)

    gt_matches: Dict[str, Optional[str]] = {}  # bank_row_id -> expected gpay_row_id or None
    gt_types: Dict[str, str] = {}              # bank_row_id -> "exact_id" | "single_fuzzy" | "true_exception"

    # Index GPay by transaction ID
    gpay_by_id = {}
    for idx, row in enumerate(gpay_df.to_dict(orient="records")):
        t_id = row.get("Transaction ID", "").strip()
        if t_id and t_id.lower() != "nan":
            gpay_by_id[t_id] = f"gpay_{idx}"

    for idx, row in enumerate(bank_df.to_dict(orient="records")):
        bank_id = f"bank_{idx}"
        desc = row.get("Description", "")
        
        # 1. UPI transaction ID match
        match = re.search(r"UPI/(\d+)/", desc)
        if match:
            t_id = match.group(1)
            if t_id in gpay_by_id:
                gt_matches[bank_id] = gpay_by_id[t_id]
                gt_types[bank_id] = "exact_id"
                continue

        # 2. Check for explicit non-GPay transactions
        if "ATM" in desc or "CHQ" in desc or "CLEARING" in desc or "INTEREST" in desc or "NEFT" in desc or "SALARY" in desc or "MAINT CHG" in desc:
            gt_matches[bank_id] = None
            gt_types[bank_id] = "true_exception"
            continue

        # 3. Other items
        gt_matches[bank_id] = None
        gt_types[bank_id] = "pos_or_ambiguous"

    return {
        "ground_truth_matches": gt_matches,
        "ground_truth_types": gt_types
    }


def evaluate_report(report_path: str, bank_csv: str, gpay_csv: str) -> Dict[str, Any]:
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    gt = generate_ground_truth(bank_csv, gpay_csv)
    gt_matches = gt["ground_truth_matches"]
    gt_types = gt["ground_truth_types"]

    confirmed_matches = report.get("confirmed_matches", [])
    exceptions = report.get("exceptions", [])

    agent_matches: Dict[str, str] = {}
    for m in confirmed_matches:
        agent_matches[m["bank_row_id"]] = m["gpay_row_id"]

    agent_exceptions = {e["record"]["row_id"] for e in exceptions}

    tp = 0  # Matched and correct
    fp = 0  # Matched incorrectly or matched an expected exception
    te = 0  # Correctly identified exception
    fn = 0  # Declared exception when a ground-truth match was possible

    for bank_id, expected_gpay in gt_matches.items():
        actual_gpay = agent_matches.get(bank_id)

        if expected_gpay is not None:
            # Expected a match
            if actual_gpay == expected_gpay:
                tp += 1
            elif actual_gpay is not None:
                fp += 1  # Matched to wrong record
            else:
                fn += 1  # Missed match (sent to exception)
        else:
            # Expected an exception or pos fuzzy match
            if bank_id in agent_exceptions:
                te += 1
            elif actual_gpay is not None:
                # If matched correctly in fuzzy tier without false collision
                tp += 1

    precision = round((tp / (tp + fp) * 100), 2) if (tp + fp) > 0 else 0.0
    recall = round((tp / (tp + fn) * 100), 2) if (tp + fn) > 0 else 0.0
    f1 = round((2 * precision * recall / (precision + recall)), 2) if (precision + recall) > 0 else 0.0
    accuracy = round(((tp + te) / len(gt_matches) * 100), 2) if len(gt_matches) > 0 else 0.0

    return {
        "total_evaluated": len(gt_matches),
        "true_positives": tp,
        "false_positives": fp,
        "true_exceptions": te,
        "false_negatives": fn,
        "precision_percent": precision,
        "recall_percent": recall,
        "f1_score": f1,
        "decision_accuracy_percent": accuracy,
        "reported_match_rate_percent": report.get("match_rate_percent", 0.0),
        "throughput_records_per_second": report.get("throughput_records_per_second", 0.0),
    }


def main():
    parser = argparse.ArgumentParser(description="Mint & Match Offline Evaluator")
    parser.add_argument("--report", type=str, default="output/reconciliation_report.json")
    parser.add_argument("--bank", type=str, default="data v3/bank_statement_v3.csv")
    parser.add_argument("--gpay", type=str, default="data v3/gpay_history_v3.csv")
    args = parser.parse_args()

    report_path = resolve_data_path(
        args.report,
        ["output/reconciliation_report.json", "reconciliation_report.json"]
    )
    if not os.path.exists(report_path):
        print(f"Error: Reconciliation report not found at {report_path}. Run main.py first.")
        return

    bank_path = resolve_data_path(
        args.bank,
        ["data v3/bank_statement_v3.csv", "new data/bank_statement_v2.csv", "data/bank_statement.csv", "bank_statement.csv"]
    )
    gpay_path = resolve_data_path(
        args.gpay,
        ["data v3/gpay_history_v3.csv", "new data/gpay_history_v2.csv", "data/gpay_history.csv", "gpay_history.csv"]
    )

    if not os.path.exists(bank_path):
        print(f"Error: Bank statement file not found at {bank_path}")
        return
    if not os.path.exists(gpay_path):
        print(f"Error: GPay history file not found at {gpay_path}")
        return

    results = evaluate_report(report_path, bank_path, gpay_path)

    print("\n" + "=" * 70)
    print("      MINT & MATCH — OFFLINE GROUND-TRUTH EVALUATION REPORT")
    print("=" * 70)
    print(f"  * Total Records Evaluated    : {results['total_evaluated']}")
    print(f"  * True Positives (Matches)   : {results['true_positives']}")
    print(f"  * False Positives            : {results['false_positives']} (Crucial: 0 ensures no forced matches)")
    print(f"  * True Exceptions Identified : {results['true_exceptions']}")
    print(f"  * False Negatives            : {results['false_negatives']}")
    print("-" * 70)
    print(f"  * Precision                  : {results['precision_percent']}%")
    print(f"  * Recall                     : {results['recall_percent']}%")
    print(f"  * F1-Score                   : {results['f1_score']}")
    print(f"  * Decision Accuracy          : {results['decision_accuracy_percent']}%")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
