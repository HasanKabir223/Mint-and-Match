# EVAL.md — Evaluation Methodology for Mint & Match

**Track:** Razorpay Buildathon 2026 — Track 04, AI Finance Controller (Multi-Source Reconciliation)  
**Evaluation Standard:** *"Throughput plus measured accuracy plus an honest exception list. One cherry-picked match proves nothing."*

---

## 1. Zero-Contamination Architecture

To preserve evaluation integrity, the matching agent at runtime has **zero access** to ground-truth labels. The pipeline operates purely on the input data:
1. `bank_statement.csv`
2. `gpay_history.csv`

The offline evaluation script ([eval.py](file:///c:/Users/Hasan/Projects/razorpay%20buildathon/Mint-and-Match/eval.py)) reads the exported [reconciliation_report.json](file:///c:/Users/Hasan/Projects/razorpay%20buildathon/Mint-and-Match/output/reconciliation_report.json) and compares it against expected ground-truth labels post-run.

---

## 2. Evaluation Metrics

| Metric | Target / Benchmark | Definition |
|---|---|---|
| **Precision** | > 98% (Zero tolerance for False Positives) | $\frac{\text{True Positives}}{\text{True Positives} + \text{False Positives}}$ |
| **Recall** | > 85% on clean reconcilable rows | $\frac{\text{True Positives}}{\text{True Positives} + \text{False Negatives}}$ |
| **F1 Score** | Balanced harmonic mean | $2 \times \frac{\text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}}$ |
| **False Positive Count** | 0 | A match confirmed when no true counterpart exists or when matched to the wrong transaction |
| **Throughput** | > 10 records / second | Batch size divided by total execution duration |
| **Honest Exception Quality** | 100% specific & non-generic | Specific explanations citing actual reasons (e.g. ATM/POS/Cheque/Interest, or structural missing timestamp collisions) |

---

## 3. Running Evaluation

Execute the end-to-end reconciliation pipeline:
```bash
python main.py
```

Run the offline evaluator:
```bash
python eval.py
```
