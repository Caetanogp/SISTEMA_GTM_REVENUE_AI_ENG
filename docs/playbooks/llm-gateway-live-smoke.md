# LLM gateway live smoke

The live smoke is optional and never runs in CI or the autonomous gate. It requires provider
credentials in the local environment and may incur provider charges.

Run it only after explicitly confirming the cost:

```powershell
python scripts/check_llm_gateway_live.py --provider all --confirm-cost
```

Use `--provider openai` or `--provider anthropic` to exercise one provider. The command uses one
minimal structured request per selected provider, does not print prompts or completions, and closes
the HTTP client after each call. It does not change CRM state or invoke provider tools.
