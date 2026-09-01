"""
State definitions for the Mint & Match LangGraph Reconciliation Pipeline.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Record(BaseModel):
    source: str
    row_id: str
    date: str
    time: Optional[str] = None
    amount: float
    transaction_id: Optional[str] = None
    merchant: Optional[str] = None
    category: Optional[str] = None
    currency: str = "INR"
    payment_method: Optional[str] = None
    raw_description: str

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class ConfirmedMatch(BaseModel):
    bank_row_id: str
    gpay_row_id: str
    tier: str  # "tier_1_exact_id" | "tier_2_amount_date"
    bank_record: Dict[str, Any]
    gpay_record: Dict[str, Any]
    matched_at: str

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class UnresolvedRecord(BaseModel):
    bank_record: Dict[str, Any]
    candidates_considered: List[Dict[str, Any]] = Field(default_factory=list)
    candidate_count: int = 0

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class ExceptionRecord(BaseModel):
    record: Dict[str, Any]
    candidates_considered: List[Dict[str, Any]] = Field(default_factory=list)
    candidate_count: int = 0
    reason: str

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class ReconciliationStats(BaseModel):
    total_bank_records: int = 0
    total_gpay_records: int = 0
    tier1_exact_matches: int = 0
    tier2_fuzzy_matches: int = 0
    total_confirmed_matches: int = 0
    unresolved_exceptions: int = 0
    match_rate_percent: float = 0.0
    processing_time_seconds: float = 0.0
    throughput_records_per_second: float = 0.0
    start_time: float = 0.0
    end_time: float = 0.0

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class ReconciliationState(BaseModel):
    bank_records: List[Dict[str, Any]] = Field(default_factory=list)
    gpay_records: List[Dict[str, Any]] = Field(default_factory=list)
    claimed_gpay_ids: List[str] = Field(default_factory=list)
    confirmed_matches: List[Dict[str, Any]] = Field(default_factory=list)
    probable_matches: List[Dict[str, Any]] = Field(default_factory=list)
    unresolved_records: List[Dict[str, Any]] = Field(default_factory=list)
    exceptions: List[Dict[str, Any]] = Field(default_factory=list)
    stats: Dict[str, Any] = Field(default_factory=dict)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)
