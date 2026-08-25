# Playbook: add an eval case or scorer

Evals are what let this system change safely. Without them, every prompt edit is a guess.

## Datasets

`evals/datasets/*.jsonl`, one JSON object per line:

| Dataset | Measures |
|---|---|
| `lead_scoring.jsonl` | agreement with golden labels, quality per score tier |
| `reply_classification.jsonl` | accuracy / F1 per class |
| `tool_selection.jsonl` | right tool chosen, and unnecessary-tool rate |
| `rag_questions.jsonl` | retrieval recall/relevance, then groundedness |
| `adversarial_security.jsonl` | injection resistance, policy compliance |

Each case carries: `id`, `input`, `expected`, `metadata` (why this case exists, which failure it came
from). Synthetic or anonymised data only.

## Adding a case

1. Write the case with the expected output **before** changing the code it tests.
2. Include negative cases. "Does not call `send_email` when the user only asked for a summary" is
   worth more than another happy path.
3. Cases promoted from real failures go in `evals/regression/` with a link to the `agent_run_id` and
   a one-line note on what went wrong.

## Scorers

- Deterministic first: exact match, set comparison, schema validity, business-rule validity,
  numeric tolerance.
- LLM-as-judge only for genuinely subjective criteria (tone, personalisation quality), and always
  paired with a deterministic check. A judge that agrees with everything is measuring nothing —
  validate it against a human-labelled subset before trusting it.
- Measure retrieval separately from generation. A bad answer from good chunks and a bad answer from
  bad chunks need different fixes.

## Thresholds and the gate

Thresholds live in `evals/thresholds.yaml` and are enforced by `.github/workflows/evals.yml`.
Raise a threshold when a change genuinely improves the score; **never lower one to make CI pass**.
If a change regresses a score, that is the eval doing its job — fix the change or argue the case
explicitly in the PR.

## When to re-run

Any change to a prompt, a model config, the graph, the retrieval pipeline, or a tool contract.
Record `prompt_version`, `graph_version`, model and dataset version with the result, so any score can
be traced back to what produced it.
