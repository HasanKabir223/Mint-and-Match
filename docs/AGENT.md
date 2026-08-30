# AGENT.md — Working Protocol for Mint & Match

This file governs how an AI coding agent (e.g. Antigravity) should operate on this repo. Read this before touching any code.

---

## 0. Source of truth

`Mint_and_Match_PRD.md` is the spec. If anything in your plan or code contradicts it, the PRD wins — stop and reconcile the conflict explicitly rather than silently picking one.

---

## 1. Plan before you build — always

Do not write implementation code in response to a feature request until a plan has been presented and explicitly approved.

For any non-trivial task (new module, new graph node, new script, schema change), the required sequence is:

1. **Restate the task** in your own words — what's being asked, and what's explicitly out of scope for it.
2. **Propose a plan**: files to be created/changed, function/node signatures, data shapes in/out, and any assumptions you're making that the PRD doesn't cover.
3. **Flag open questions** — if the PRD is ambiguous or silent on something the task needs, ask rather than guessing. Silent assumptions are the main failure mode this file exists to prevent.
4. **Wait for explicit go-ahead** before writing code. "Looks good," "yes," "go" count. Silence does not.
5. Only then implement — and implement exactly the approved plan. If you discover mid-implementation that the plan needs to change, stop and re-confirm rather than improvising a fix and continuing.

This applies even to "obvious" changes. Obvious to the agent is not the same as approved by the user.

---

## 2. Scope discipline

- Build only what the current task asks for. Do not "helpfully" add extra features, extra files, extra abstraction layers, or extra robustness (retry logic, config systems, CLI flags) that weren't asked for or planned.
- If you notice something that seems missing or broken but is outside the current task, name it at the end of your plan or output as a suggestion — do not silently fix it inline.
- Re-read Section 7 ("Explicit Non-Goals") in the PRD before proposing any plan. If a plan starts drifting toward a non-goal (RAG, embeddings, two-tower models, multi-format ingestion, many-to-one settlement matching), stop and flag it rather than building it "since it might help."

---

## 3. Respect the architecture boundaries already decided

These are decided, not open for re-litigation without explicit discussion:

- **Normalization is deterministic and happens before the agent graph runs.** It is not a LangGraph node.
- **Tier 1 (exact ID) and Tier 2 (fuzzy, single-candidate) matching are deterministic rule logic. No ML, no LLM calls here.**
- **The LLM (Groq, `openai/gpt-oss-120b`) is used ONLY for Tier 3 exception-reason generation.** Do not route matching decisions through the LLM. Do not add tool-calling/function-calling for the matching tiers — they don't need it.
- **No RAG, no embeddings, no vector search, no two-tower/dual-encoder model anywhere in this pipeline.** The candidate pool is small (~50-60 records); brute-force filtering on amount+date is the deliberately chosen approach, not a placeholder for something fancier.
- **Agent orchestration is LangGraph**, structured as the node graph described in PRD Section 5. Don't collapse it back into a single function, and don't introduce a second framework alongside it.

If a task seems to require violating one of these, stop and raise it explicitly rather than proceeding.

---

## 4. Data handling

- Treat `bank_statement.csv` and `gpay_history.csv` (and their normalized outputs) as fixed schema for v1. Don't add speculative support for other formats/columns "just in case."
- The hidden ground-truth mapping (once `EVAL.md` exists) is for evaluation only. The agent's matching logic must never read from or be influenced by ground truth at runtime — it exists purely to score the agent's output after the fact. If you're not sure whether something counts as "peeking," ask before wiring it in.

---

## 5. When the PRD doesn't say

If a needed decision isn't covered in the PRD (e.g., exact confidence-score thresholds, exact LangGraph state field names, error handling for a malformed CSV row):

- Propose a specific, reasoned default as part of your plan.
- Mark it clearly as an assumption, not a spec requirement.
- Don't bury it in code comments as the only record of the decision — surface it in the plan so it can be corrected before it's built.

---

## 6. Honesty over impressiveness

This project's whole premise is that honest, measured output beats cherry-picked or inflated numbers. That standard applies to you too:

- Don't report a match as confirmed if it doesn't actually meet the Tier 1/2 criteria.
- Don't write exception reasons as generic templates — but also don't fabricate specific-sounding detail that isn't actually derivable from the record and its candidates.
- If a test run produces a suspiciously perfect result (e.g. 100% match rate), treat that as a signal to double check the logic, not a result to report proudly.

---

## 7. Summary checklist before any implementation

- [ ] Have I stated the plan and gotten explicit approval?
- [ ] Does this stay within the PRD's scope (and out of its non-goals)?
- [ ] Does this respect the deterministic-matching / LLM-only-for-exceptions boundary?
- [ ] Have I flagged assumptions instead of silently making them?
- [ ] Am I building only what was asked, not what seemed like a nice addition?
