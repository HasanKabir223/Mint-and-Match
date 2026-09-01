# AGENTS.md — Working Protocol for Mint & Match

This file governs how AI coding agents (Antigravity) operate on this repository. Read this before touching any code.

---

## 0. Source of Truth

`docs/Mint&Match_PRD.md` is the authoritative specification. If anything in your plan or code contradicts it, the PRD wins — stop and reconcile the conflict explicitly rather than silently picking one.

---

## 1. Plan Before You Build — Always

Do not write implementation code in response to a feature request until a plan has been presented and explicitly approved.

For any non-trivial task (new module, new graph node, new script, schema change), the required sequence is:

1. **Restate the task** in your own words — what is being asked, and what is explicitly out of scope.
2. **Propose a plan**: files to be created/changed, function/node signatures, data shapes in/out, and any assumptions being made that the PRD does not cover.
3. **Flag open questions** — if the PRD is ambiguous or silent on something the task needs, ask rather than guessing. Silent assumptions are strictly prohibited.
4. **Wait for explicit go-ahead** before writing code ("looks good", "yes", "go", etc.).
5. **Implement exactly the approved plan** — if mid-implementation changes are needed, stop and re-confirm.

---

## 2. Scope Discipline & Non-Goals

- Build only what the current task asks for. Do not add unrequested features, extra files, extra abstraction layers, or speculative robustness (retry logic, config systems, CLI flags).
- If something seems missing or broken outside the current task, mention it as a suggestion — do not silently fix it inline.
- Re-read Section 7 ("Explicit Non-Goals") in `Mint&Match_PRD.md` before proposing any plan:
  - **No RAG, vector databases, or embeddings.**
  - **No two-tower / dual-encoder retrieval models.**
  - **No multi-format ingestion** (fixed CSV schema only).
  - **No many-to-one / bundled settlement matching** (1:1 transactions only).
  - Candidate pool is small (~50-60 records); brute-force filtering on amount + date is deliberate.

---

## 3. Architecture Boundaries

- **Normalization is deterministic** and runs before the agent graph (it is NOT a LangGraph node).
- **Tier 1 (Exact ID) and Tier 2 (Fuzzy, single candidate) matching are deterministic rule logic.** No ML, no LLM calls.
- **The LLM (Groq, `llama-3.3-70b-versatile`) is used ONLY for Tier 3 exception-reason generation.** Do not route matching decisions through the LLM. Do not use tool-calling/function-calling for matching tiers.
- **Agent orchestration is LangGraph**, structured as the node graph defined in PRD Section 5. Do not collapse it into a single monolithic function or introduce competing frameworks.

---

## 4. Data Handling & Evaluation Integrity

- Treat `bank_statement.csv` and `gpay_history.csv` (and their normalized outputs) as fixed schema for v1.
- Hidden ground-truth mapping (when present) is strictly for offline evaluation. Matching logic must never read from or be influenced by ground truth at runtime.

---

## 5. When the PRD Doesn't Say

- Propose a specific, reasoned default as part of the plan.
- Mark it clearly as an assumption, not a spec requirement.
- Surface it in the plan for review before building.

---

## 6. Honesty Over Impressiveness

- Do not report a match as confirmed unless it strictly meets Tier 1/2 criteria. Never force low-confidence matches to inflate accuracy metrics.
- Generate honest, specific exception reasons reflecting actual record data and structural limitations (e.g. absence of bank time data).
- Suspiciously perfect results (e.g., 100% match rate) must be treated as a signal to double check logic.

---

## 7. Summary checklist before any implementation

- [ ] Have I stated the plan and gotten explicit approval?
- [ ] Does this stay within the PRD's scope (and out of its non-goals)?
- [ ] Does this respect the deterministic-matching / LLM-only-for-exceptions boundary?
- [ ] Have I flagged assumptions instead of silently making them?
- [ ] Am I building only what was asked, not what seemed like a nice addition?

---

## 8. Backend Development: Mentorship & User-Authored Code (FastAPI)

For all backend / FastAPI development in this repository:
- **Default Mode is Mentorship / Pair Guide**: The user writes the code. The agent provides conceptual explanations, endpoint blueprints, step-by-step milestones/assignments, and debug hints.
- **Do Not Generate Code Unprompted**: The agent must NOT write or overwrite backend implementation files unless the user explicitly asks with phrases like *"write this for me"*, *"generate this code"*, or *"implement this file"*.
- **Role of the Agent**:
  1. Break down backend requirements into manageable learning assignments.
  2. Explain FastAPI concepts (routers, Pydantic request/response schemas, file uploads, dependency injection, async execution, CORS).
  3. Review the user's code for bugs, edge cases, and compliance with the PRD reconciliation engine.
  4. Help troubleshoot exceptions, server issues, or test failures.
