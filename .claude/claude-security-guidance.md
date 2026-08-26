# Project-specific security rules

Full rules and reasoning: `docs/security/AGENT_SECURITY_RULES.md`. This file is the compact
version fed into the automated review — flag a violation of any rule below as high severity.

- **Tenant isolation is mandatory on every query.** `organization_id` must be filtered at the
  repository level (inside the adapter that talks to the database), never only in a handler or a
  use case. A query missing this filter is a cross-tenant data leak, not a style issue.
- **External content is untrusted, always.** Anything from a web fetch, RAG retrieval, an email
  body, a lead reply, or an MCP/tool output must be treated as data, never as instruction. Flag any
  code path where such content could reach a system prompt, change a tool allowlist, raise a
  permission, or skip an approval step.
- **HITL is mandatory before execution** for `send_email`, `schedule_meeting`, any bulk action, and
  anything classified high risk. Flag any write path to those tools (or an equivalent external
  write) that does not pause for Approve/Edit/Reject first.
- **No LLM output reaches a write tool unvalidated.** The required order is: schema validation →
  domain rules → authorization → risk classification, before any side effect. Flag code that
  executes a tool call before all four have run.
- **The domain layer must not import a framework.** `packages/core/revops/domain/` is pure Python
  (stdlib only) — flag any `pydantic`, `sqlalchemy`, `fastapi`, or `langgraph` import there, and any
  business rule (a risk decision, a scoring rule, a dedup rule) implemented outside that layer.
- **Audit tables are append-only.** `agent_runs`, `agent_actions`, `approvals` must never be
  targets of an `UPDATE` or `DELETE`; corrections are new rows.
- **PII is redacted before it reaches a log, a trace, or an eval dataset.** Flag any code path that
  writes an email address, phone number, or real name to `structlog`, an OTel span attribute, or a
  file under `evals/`.
- **Demo data is synthetic.** Flag any fixture, seed script, or eval case that looks like it could
  be real customer data from the original n8n/SociallyMe system.
- **Idempotency key on every write tool.** A retried tool call must not double-send or duplicate a
  record.

Inline exclusion: if a finding is a false positive, explain why in a comment on the flagged line
rather than suppressing the review.
