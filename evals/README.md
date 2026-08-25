# evals

Offline evaluation suite. CI blocks the merge when scores fall below the thresholds.

- `datasets/` golden JSONL: lead_scoring, reply_classification, tool_selection, rag_questions,
  adversarial_security. Synthetic or anonymised only — never real customer data.
- `scorers/` deterministic scorers first; LLM-as-judge only for genuinely subjective criteria, and
  always paired with a deterministic check.
- `regression/` cases promoted from real failures, after human triage.
- `reports/` generated output (git-ignored).

Datasets are versioned and hashed; `agent_runs` records the dataset version used, so any score can
be reproduced.
