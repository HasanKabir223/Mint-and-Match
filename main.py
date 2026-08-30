"""
Main CLI Entry Point for Mint & Match (AI Finance Controller - Track 04)
========================================================================

Executes the multi-source reconciliation loop across bank statements and
GPay payment histories using LangGraph and Groq exception reasoning.
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, Union

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
        default="data/bank_statement.csv",
        help="Path to bank statement CSV (default: data/bank_statement.csv)",
    )
    parser.add_argument(
        "--gpay",
        type=str,
        default="data/gpay_history.csv",
        help="Path to GPay payment history CSV (default: data/gpay_history.csv)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="reconciliation_report.json",
        help="Path for output reconciliation report JSON (default: reconciliation_report.json)",
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
    
    print("\n📊 1. RECONCILIATION METRICS & THROUGHPUT")
    print("-" * 80)
    print(f"  • Total Bank Records Processed : {stats.get('total_bank_records', 0)}")
    print(f"  • Total GPay Records Loaded    : {stats.get('total_gpay_records', 0)}")
    print(f"  • Tier 1 Exact Matches (ID)    : {stats.get('tier1_exact_matches', 0)}")
    print(f"  • Tier 2 Fuzzy Matches (Amt/Dt): {stats.get('tier2_fuzzy_matches', 0)}")
    print(f"  • Total Confirmed Matches      : {stats.get('total_confirmed_matches', 0)}")
    print(f"  • Unresolved Exceptions (Tier3): {stats.get('unresolved_exceptions', 0)}")
    print(f"  • Overall Match Rate           : {stats.get('match_rate_percent', 0.0):.2f}%")
    print(f"  • Total Processing Time        : {stats.get('processing_time_seconds', 0.0):.4f} seconds")
    print(f"  • System Throughput            : {stats.get('throughput_records_per_second', 0.0):.2f} records/sec")
    print("-" * 80)

    print("\n🔍 2. SAMPLE CONFIRMED MATCHES (Top 5)")
    print("-" * 80)
    print(f"{'Bank Row':<10} | {'GPay Row':<10} | {'Tier':<22} | {'Date':<10} | {'Amount':<10} | {'Description'}")
    print("-" * 80)
    for m in confirmed[:5]:
        bank = m.get("bank_record", {})
        print(
            f"{m.get('bank_row_id', ''):<10} | "
            f"{m.get('gpay_row_id', ''):<10} | "
            f"{m.get('tier', ''):<22} | "
            f"{bank.get('date', ''):<10} | "
            f"{bank.get('amount', 0.0):<10.2f} | "
            f"{bank.get('raw_description', '')[:30]}"
        )
    if len(confirmed) > 5:
        print(f"  ... and {len(confirmed) - 5} more confirmed matches.")

    print("\n⚠️ 3. HONEST EXCEPTION LIST (Tier 3 - Unresolved Transactions)")
    print("-" * 80)
    if not exceptions:
        print("  None. All transactions were reconciled.")
    else:
        for idx, exc in enumerate(exceptions, 1):
            rec = exc.get("record", {})
            cand_count = exc.get("candidate_count", 0)
            reason = exc.get("reason", "")
            print(f"\n  [{idx}] Record ID: {rec.get('row_id')} | Date: {rec.get('date')} | Amount: {rec.get('amount'):.2f}")
            print(f"      Description: {rec.get('raw_description')}")
            print(f"      Candidates Considered in Payment History: {cand_count}")
            print(f"      Reason: {reason}")
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


def resolve_data_path(path: str, fallback_filename: str) -> str:
    """Helper to locate files in data/ directory or root directory."""
    if os.path.exists(path):
        return path
    root_fallback = os.path.join(os.getcwd(), fallback_filename)
    if os.path.exists(root_fallback):
        return root_fallback
    data_fallback = os.path.join(os.getcwd(), "data", fallback_filename)
    if os.path.exists(data_fallback):
        return data_fallback
    return path


def main():
    args = parse_args()
    
    if args.groq_model:
        os.environ["GROQ_MODEL"] = args.groq_model

    bank_path = resolve_data_path(args.bank, "bank_statement.csv")
    gpay_path = resolve_data_path(args.gpay, "gpay_history.csv")

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

    # Save output report JSON
    report = build_final_report(final_state)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"[✓] Reconciliation report successfully exported to {args.output}")


if __name__ == "__main__":
    main()
