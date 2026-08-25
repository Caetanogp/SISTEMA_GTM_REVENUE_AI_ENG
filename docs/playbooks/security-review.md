# Playbook: security review (agentic)

Focused review for this system. Full rules: `docs/security/AGENT_SECURITY_RULES.md`.
Run it when a change touches prompts, tools, context assembly, auth, external calls or data.

## Automated first

```bash
gitleaks detect --no-git
semgrep --config auto .
bandit -r packages apps -q
pip-audit
pytest tests/adversarial -q
```

Automation catches the known shapes. The list below is for what it cannot see.

## Prompt injection

- Is external content (web, RAG, email body, lead reply, tool output) fenced and labelled as
  untrusted in the prompt?
- Could content inside that fence plausibly change the tool allowlist, raise a permission, lower a
  risk level, skip HITL, or extract the system prompt? Try it — write the attack as a test case.
- Are tool arguments derived from untrusted content re-validated against domain rules, not just the
  schema?
- Does a new content source have a matching case in `tests/adversarial/`?

## Tool safety

- Deny by default? Is the new tool on an explicit allowlist for a specific agent/env/role?
- Risk level correct — does it have an irreversible or external effect?
- Full validation chain before the side effect: schema → domain rules → authorization → risk?
- Idempotency key on writes? What happens if the retry fires twice?
- In `DEMO_MODE`, does it hit the sandbox, the outbound allowlist and the quota?

## Authorization and isolation

- Is `organization_id` filtered at the repository level, not in the handler?
- Can a user approve an action they could not have taken directly?
- Does a specialist agent get scopes beyond what its job needs?

## Data

- Any new PII in logs, traces, eval datasets or fixtures? Redacted?
- Any real customer data anywhere? It must be synthetic.
- Is the audit trail written on every path, including failure and rejection? Still append-only?

## Secrets and dependencies

- New env var: is it in `.env.example` with a placeholder, and absent from every committed file?
- New dependency: maintained, pinned, audited?
- New MCP server: scanned with `mcp-scan` and recorded in `docs/tooling/RESEARCH.md`?

## Output

Report findings ordered by severity, each with file:line and a concrete failure scenario — what
input, in what state, produces what damage. A finding without a scenario is a style opinion.
