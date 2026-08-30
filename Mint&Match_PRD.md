# Mint&Match — Product Requirements Document

**Track:** Razorpay Buildathon 2026 — Track 04, AI Finance Controller (Multi-source reconciliation)
**Scope of this doc:** Backend + workflow only. Frontend/dashboard is out of scope for v1.
**Agent orchestration:** LangGraph
**LLM provider:** Groq (`openai/gpt-oss-120b`) — used ONLY for exception-reason generation, not for matching decisions.

---

## 1. Problem Statement

Reconciling a bank statement against a UPI/GPay-style payment history is currently a manual, row-by-row process. The two sources describe the same transactions in structurally different ways (different name formats, different column layouts, different levels of detail), and a meaningful fraction of transactions cannot be matched with full certainty.

Mint&Match is an agent that ingests both sources, matches transactions across them with tiered confidence, and — critically — is honest about which transactions it could not resolve and why, rather than forcing low-confidence matches to inflate its own accuracy.

This directly targets the track's stated bar: *"Throughput plus measured accuracy plus an honest exception list. One cherry-picked match proves nothing."*

---

## 2. Inputs

Two CSV files, fixed schema for v1 (no multi-format support yet):

### 2.1 Bank Statement CSV
| Column | Type | Notes |
|---|---|---|
| Date | string, `DD/MM/YYYY` | |
| Description | string | UPI transactions embed a transaction ID: `UPI/<txn_id>/<Legal Name>/Payment`. Non-UPI entries (POS, ATM, interest, cheque, charges) have no embedded ID. |
| Withdrawal | string (numeric or blank) | Present only if money left the account |
| Deposit | string (numeric or blank) | Present only if money entered the account |

**Known real-world properties (from user's own reconciliation experience):**
- No time field exists at all — this is a structural absence, not missing data per row.
- Name shown is the account holder's legal/registered name (bank/KYC name), which frequently does NOT match the casual/contact name saved on the counterparty's device.

### 2.2 GPay/Payment History CSV
| Column | Type | Notes |
|---|---|---|
| Date | string, `MMM DD, YYYY` | |
| Time | string, `H:MM AM/PM` | Always present |
| Description | string | `Paid to <name>` or `Received from <name>` — name here is a casual/contact name, not the legal name |
| Transaction ID | string | Always present (per user's real data) |
| Amount | string, signed numeric | Negative = paid out, positive = received |

**Ground truth for dev/testing:** Since v1 data is synthetic, a hidden ground-truth mapping (bank row index ↔ gpay row index ↔ "should be exception") is maintained separately to measure true precision/recall of the matching pipeline. This mapping is NOT available to the agent at runtime — it exists only for our own evaluation.

---

## 3. Normalization Layer (pre-agent, deterministic, not part of the LangGraph graph)

Both CSVs are independently reshaped into one common record schema before the agent ever runs:

```json
{
  "source": "bank" | "gpay",
  "row_id": "<stable index into original file>",
  "date": "YYYY-MM-DD",
  "time": "HH:MM" or null,       // ALWAYS null for bank rows — structural, not missing
  "amount": <signed float>,       // negative = out, positive = in
  "transaction_id": "<string>" or null,
  "raw_description": "<original string, preserved for exception reasoning>"
}
```

Rules:
- Bank: `Withdrawal` → negative amount; `Deposit` → positive amount.
- Bank: transaction ID extracted via regex from description (`UPI/(\d+)/`); null if no match (POS/ATM/interest/cheque/charge rows).
- GPay: `Paid to` implies negative amount is already encoded in the `Amount` column's sign; used as-is.
- GPay: `Transaction ID` column used directly.
- Output: two separate DataFrames/record-lists, same schema, NOT merged. Merging/matching is the agent's job, not this layer's.

---

## 4. Matching Logic (the core decision tree the agent executes)

For each unresolved bank record, evaluated in order:

### Tier 1 — Exact ID Match (deterministic, no ML, no LLM)
Does `transaction_id` appear on both sides? If yes → **confirmed match**, no further processing needed for this row.

### Tier 2 — Fuzzy Match, Single Candidate (deterministic, no ML, no LLM)
No shared transaction ID (bank-side ID is null). Search the other source for rows matching on `amount` (exact) + `date` (exact) + same direction. If exactly **one** candidate found → **confident match**, tagged as "matched without ID, by amount+date."

### Tier 3 — Exception (requires the LLM reasoning step)
Triggered when:
- **Zero candidates** found on amount+date (e.g., ATM withdrawal, interest credit — genuinely has no counterpart in the other source), OR
- **Multiple candidates** found with identical amount+date, and no further signal exists to disambiguate (bank has no time field, so same-day/same-amount collisions cannot be resolved with certainty).

Every Tier 3 case is passed to the **Exception Reasoner** (Groq `openai/gpt-oss-120b`, plain chat completion, NOT a tool call) along with the unresolved record and its candidate list (possibly empty). The reasoner returns one specific, honest sentence explaining why resolution failed — referencing actual amounts/dates/candidate counts, and explicitly noting the "bank has no time data" structural limitation ONLY when it is actually the cause of the ambiguity.

**No two-tower model, no embeddings, no RAG, no vector search anywhere in this pipeline.** The candidate pool per row is small (≤60 records total), so brute-force filtering on amount+date is sufficient and is the deliberately-chosen, judge-defensible approach. A confidence-scoring classifier (logistic regression / gradient-boosted tree on features like amount_diff, date_diff, description similarity) is an optional v1.1 addition for Tier 2 cases with more than one candidate — NOT required for the base version.

---

## 5. Agent Orchestration (LangGraph)

The agent is expressed as a LangGraph state graph, not a single monolithic function, so each decision point is inspectable and independently testable.

**Proposed graph nodes:**
1. `load_normalized_records` — entry node, loads the two normalized record sets into shared state
2. `attempt_exact_match` — runs Tier 1 across all unresolved bank records
3. `attempt_fuzzy_match` — runs Tier 2 on records still unresolved after node 2
4. `route_ambiguous` — conditional edge: if a record has 0 or 2+ fuzzy candidates → route to `generate_exception_reason`; if exactly 1 candidate → mark confirmed and skip to `compile_report`
5. `generate_exception_reason` — calls the Groq-based reasoner for each Tier 3 record
6. `compile_report` — terminal node; computes match rate, throughput, and assembles the final exception list with reasons

**State object (shared across nodes):**
```json
{
  "bank_records": [...],
  "gpay_records": [...],
  "confirmed_matches": [...],
  "probable_matches": [...],
  "exceptions": [...],
  "stats": {
    "total_bank_records": <int>,
    "tier1_matches": <int>,
    "tier2_matches": <int>,
    "exceptions": <int>,
    "processing_time_seconds": <float>
  }
}
```

Why LangGraph specifically (vs. a plain function loop, which was the original leaner plan): explicit node/edge structure gives a visual, inspectable graph for the pitch demo ("here's exactly how the agent routes each record") and makes conditional routing (Tier 2 ambiguous vs. confirmed) declarative rather than nested if/else. This is a legitimate reason to use it — just note it adds a dependency and some boilerplate versus the original raw-Python plan discussed earlier in this project's design conversation.

---

## 6. Output / Report

Final deliverable, per the track's bar ("throughput plus measured accuracy plus an honest exception list"):

```json
{
  "match_rate_percent": <float>,
  "tier1_exact_matches": <int>,
  "tier2_fuzzy_matches": <int>,
  "unresolved_exceptions": <int>,
  "throughput_records_per_second": <float>,
  "exceptions": [
    {
      "record": {...},
      "candidates_considered": [...],
      "reason": "<LLM-generated honest explanation>"
    }
  ]
}
```

v1 output format: a JSON file + a clean terminal/CLI printout. Dashboard/visual UI is explicitly out of scope for this PRD.

---

## 7. Explicit Non-Goals (for this hackathon build)

- No RAG / vector database / embeddings — candidate pool is small enough for brute-force filtering.
- No two-tower or dual-encoder retrieval model.
- No support for file formats other than CSV.
- No many-to-one / bundled-settlement matching (one bank deposit = multiple gateway transactions) — explicitly deferred to a future version; current synthetic data is 1:1 only.
- No offense-capable functionality (this track requires defense-only tooling; irrelevant here since this isn't a fraud track, but noted for completeness).

---

## 8. Success Criteria (how we'll know it worked)

- Processes 50+ record batch successfully within a few seconds.
- Tier 1 + Tier 2 match rate is high on clean data (target: 85%+ of records resolved with confidence) — validated against the hidden ground-truth mapping during dev, NOT shown to the agent.
- Every Tier 3 exception has a specific, non-generic reason (spot-checked manually, not templated boilerplate).
- No forced/cherry-picked matches — a record either meets Tier 1/2 criteria cleanly or is honestly flagged.
