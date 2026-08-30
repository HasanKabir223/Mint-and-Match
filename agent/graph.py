"""
LangGraph StateGraph definition for the Mint & Match Reconciliation Pipeline.
"""

from typing import Any, Dict, List
from langgraph.graph import StateGraph, START, END

from .state import ReconciliationState
from .nodes import (
    load_normalized_records,
    attempt_exact_match,
    attempt_fuzzy_match,
    generate_exception_reason,
    compile_report,
)


def route_ambiguous(state: ReconciliationState) -> str:
    """
    Conditional routing edge:
    - If any bank records remain unresolved (0 or 2+ candidates), routes to generate_exception_reason.
    - If all records are resolved, routes directly to compile_report.
    """
    unresolved = state.get("unresolved_records", [])
    if unresolved and len(unresolved) > 0:
        return "generate_exception_reason"
    return "compile_report"


def create_reconciliation_graph():
    """
    Constructs and compiles the LangGraph reconciliation workflow.
    """
    workflow = StateGraph(ReconciliationState)

    # Register nodes
    workflow.add_node("load_normalized_records", load_normalized_records)
    workflow.add_node("attempt_exact_match", attempt_exact_match)
    workflow.add_node("attempt_fuzzy_match", attempt_fuzzy_match)
    workflow.add_node("generate_exception_reason", generate_exception_reason)
    workflow.add_node("compile_report", compile_report)

    # Register edges
    workflow.add_edge(START, "load_normalized_records")
    workflow.add_edge("load_normalized_records", "attempt_exact_match")
    workflow.add_edge("attempt_exact_match", "attempt_fuzzy_match")
    
    # Conditional routing after Tier 2
    workflow.add_conditional_edges(
        "attempt_fuzzy_match",
        route_ambiguous,
        {
            "generate_exception_reason": "generate_exception_reason",
            "compile_report": "compile_report",
        }
    )

    workflow.add_edge("generate_exception_reason", "compile_report")
    workflow.add_edge("compile_report", END)

    return workflow.compile()


def run_reconciliation(
    bank_records: List[Dict[Any, Any]],
    gpay_records: List[Dict[Any, Any]],
) -> ReconciliationState:
    """
    Executes the reconciliation graph on the provided normalized datasets.
    """
    graph = create_reconciliation_graph()
    initial_state = ReconciliationState(
        bank_records=bank_records,
        gpay_records=gpay_records,
    )
    final_state = graph.invoke(initial_state)
    return final_state
