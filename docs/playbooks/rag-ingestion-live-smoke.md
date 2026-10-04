# Knowledge ingestion live embedding smoke

This optional smoke sends one short synthetic string to the explicitly configured OpenAI embedding
provider. It is excluded from CI and the autonomous gate, requires `OPENAI_API_KEY`, and may incur
provider charges. It does not submit a document, write to the database, or publish a worker job.

Run it only after explicitly confirming the cost and setting `KNOWLEDGE_EMBEDDING_PROVIDER=openai`:

```powershell
python scripts/check_rag_ingestion_live.py --confirm-cost
```

The command reports only a safe pass/fail result; it never prints the API key, document text,
vectors, raw provider response, or provider error body.
