# Playbook: add an agent tool

A tool is how the agent touches the world. It is not done until it has all six pieces below —
partial tools are how agents send emails they should not have sent.

## The six pieces

### 1. Contract (application layer)

`packages/core/revops/application/tools/<name>.py`:

```python
class SendEmailArgs(BaseModel):
    contact_id: UUID
    subject: str = Field(max_length=200)
    body: str = Field(max_length=5000)
    model_config = ConfigDict(extra="forbid")   # reject anything the LLM invents
```

`extra="forbid"` is not optional. An LLM that hallucinates a `bypass_approval=true` field must fail
validation, not have it silently dropped.

### 2. Risk level (domain layer)

Register it in the risk matrix in `domain/policies/`:

| Level | Meaning | Examples |
|---|---|---|
| `low` | reads, no side effect | `get_account`, `search_accounts`, `get_pipeline_metrics` |
| `medium` | internal writes | `create_task`, `update_opportunity` |
| `high` | external writes, irreversible, or bulk | `send_email`, `schedule_meeting` |

`high` always routes through HITL. So does anything below the confidence threshold.

### 3. Allowlist entry

Deny by default. Add the tool to the allowlist for the specific agent, environment and role that
needs it. In `DEMO_MODE`, external-write tools point at the sandbox implementation with the outbound
allowlist and quota applied.

### 4. Port + adapter

Port (`application/ports.py`) declares what the tool needs; the adapter in `infrastructure/external/`
implements it. The use case never imports the adapter — that is what keeps the tool testable.

### 5. Validation chain

Before any side effect, in this order:

1. schema (Pydantic)
2. domain rules — quotas, opt-out, suppression list, blocked domains, valid state transition
3. authorization — this user, this org, this role, this scope
4. risk → HITL if high or low confidence

Then: idempotency key, timeout, retry with exponential backoff and jitter, and an `agent_actions`
row written whatever the outcome — success, failure or rejection.

### 6. Tests and evals

- unit: valid args, invalid args, each domain rule that can reject, authorization failure
- adversarial: an injection attempt in the arguments (`tests/adversarial/`)
- eval: at least one case in `evals/datasets/tool_selection.jsonl` — the agent should pick this tool
  when appropriate, and *not* pick it when it should not. Unnecessary-tool rate matters as much as
  accuracy.

## Checklist

- [ ] Pydantic args schema with `extra="forbid"`
- [ ] Risk level registered in the risk matrix
- [ ] Allowlist entry per agent/environment/role
- [ ] Port + adapter, sandboxed variant for demo mode
- [ ] Full validation chain, in order
- [ ] Idempotency, timeout, retry/backoff
- [ ] `agent_actions` audit row on every path
- [ ] Unit + adversarial tests
- [ ] Eval case, positive and negative
- [ ] Docstring stating what the tool does, its risk level and its side effects — this text is what
      the model reads to decide whether to call it, so write it for the model, not for a human
