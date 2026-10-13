# Reply classification offline evaluation

`evals/datasets/reply_classification.jsonl` contains 90 synthetic cases: five examples for each
of the nine reply categories in English and Portuguese. Each record uses the repository-wide
`id`, `input`, `expected`, and `metadata` dataset shape; metadata states the declared language and
that the content is synthetic.

`evals/scorers/reply_classification.py` is an independent, deterministic lexical baseline. It does
not invoke the production reply policy or an LLM. The gate requires accuracy of at least 0.85,
macro-F1 of at least 0.80, and unsubscribe recall of 1.00.

`evals/datasets/reply_classification_contract.jsonl` and its scorer exercise the approved safety
contract: mapped actions, the inclusive confidence boundary, language mismatch, missing evidence,
and unsubscribe precedence. This contract suite must score 1.00.

Run the reproducible offline gate with:

```powershell
python -m evals.gate
```
