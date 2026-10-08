# Knowledge retrieval live smoke

The mandatory retrieval contract is offline and deterministic. This optional smoke only sends one
synthetic query to the explicitly configured OpenAI embedding provider to verify live configuration
and response shape. It does not query a tenant corpus, write to the database, or measure semantic
quality.

It is excluded from CI and the autonomous gate, requires `OPENAI_API_KEY`, and may incur provider
charges. Run it only after explicitly confirming the cost and setting
`KNOWLEDGE_EMBEDDING_PROVIDER=openai`:

```powershell
python scripts/check_rag_retrieval_live.py --confirm-cost
```

Without `--confirm-cost` or the explicit live provider configuration, the command refuses to make a
network call. It reports only a safe pass/fail result and never prints the API key, query, vector,
or raw provider response.
