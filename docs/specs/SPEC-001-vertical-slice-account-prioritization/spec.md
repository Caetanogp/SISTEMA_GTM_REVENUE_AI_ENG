# SPEC-001: Vertical slice — account prioritization with human-approved follow-up

- **Status:** agreed
- **Owner:** Caetano
- **Roadmap phase:** 1 — Code-first MVP
- **Created:** 2026-08-25

## Problem

Sales/RevOps teams spend their day deciding which accounts deserve attention, digging for context,
and writing follow-ups. Simple automation is brittle at exactly the parts that need judgement, and
an agent with unrestricted autonomy is worse: it can pick the wrong tool, invent arguments, or send
something it should not have sent.

This spec builds the thinnest path that proves the whole architecture works end to end. It is
deliberately narrow: one useful command, exercised through every layer, with a human in the loop
before anything leaves the building.

## User stories

- As a **sales rep**, I want to ask in plain language which accounts need attention today, so that I
  can start with the right ones instead of guessing.
- As a **sales rep**, I want the agent to draft a follow-up task with its reasoning and evidence, so
  that I can approve, edit or reject it instead of writing it from scratch.
- As a **RevOps lead**, I want every agent step, tool call and approval recorded, so that I can
  audit what the system did and why.

## In scope

- One natural-language entry point: *"which accounts need attention today?"*
- CRM read path: accounts, contacts, opportunities, recent interactions, for one organization.
- Deterministic prioritization signals + one LLM reasoning step producing **structured output**
  (score, tier, reasons, evidence) — never free text.
- Two tools: `search_accounts` (read, low risk) and `create_task` (write, medium risk).
- Policy layer: schema validation → domain rules → authorization → risk classification.
- HITL: `create_task` pauses for Approve / Edit / Reject; the graph resumes from its checkpoint.
- Audit trail: `agent_runs`, `agent_actions`, `approvals` persisted and queryable.
- Minimal API surface: start a run, stream progress over SSE, list runs, submit an approval decision.
- Synthetic seed data for one demo organization.

## Out of scope

Deliberately not in this slice — each has its own later spec:

- RAG, pgvector, any knowledge corpus (SPEC-002, phase 2)
- External research, email sending, calendar scheduling (high-risk tools, phase 3)
- Redis/Celery, background jobs, batch scoring (phase 4)
- Next.js UI — this slice is verified through the API and tests (a minimal UI follows in SPEC-003)
- Multi-agent anything
- Deduplication and ingestion pipelines
- Multi-tenant beyond a single demo organization with the isolation filter in place

## Acceptance criteria

1. Given a seeded demo organization, when an authenticated user posts a prioritization request, then
   the API returns an `agent_run_id` and streams progress events over SSE.
2. Given the run completes, then it returns a ranked list of accounts, each with a numeric score, a
   tier, and at least one evidence item referencing real CRM data — validated against a Pydantic
   schema before it leaves the graph.
3. Given the agent proposes a `create_task` action, then execution **pauses** and no row is written
   until a human decides.
4. Given the user approves, then the task is created, the `agent_actions` row records `approved_by`
   and `executed_at`, and the graph resumes from its checkpoint.
5. Given the user edits the payload, then the **edited** payload is what executes and what is
   stored in `approvals`.
6. Given the user rejects, then nothing is written to the CRM and the rejection is recorded.
7. Given the process is restarted between the interrupt and the decision, then the run still
   resumes correctly from the persisted checkpoint.
8. Given an LLM output that fails schema validation, then the run retries a bounded number of times
   and then fails cleanly — never executing an invalid payload.
9. Every run records `graph_version`, `prompt_version`, model config, latency and token cost.
10. A user from another organization cannot read or act on this organization's accounts (403, and
    no rows leaked).

## Tools and risk

| Tool | Type | Risk | HITL |
|---|---|---|---|
| `search_accounts` | read | low | no |
| `get_account_context` | read | low | no |
| `create_task` | write | medium | **yes** (in this slice, all writes are approved) |

`create_task` is medium risk and would normally be automatic; it goes through HITL here because
this slice exists to prove the approval path works.

## Data model impact

New tables: `organizations`, `users`, `accounts`, `contacts`, `opportunities`, `interactions`,
`tasks`, `agent_runs`, `agent_actions`, `approvals`, plus the LangGraph checkpoint tables.

Indexes: `organization_id` on every tenant-scoped table; `accounts(domain)` unique per org;
`contacts(email)` unique per org; foreign keys throughout. Audit tables are append-only.

## Security considerations

- No external content enters the context in this slice — the injection surface is limited to the
  user's own prompt, which is still fenced and treated as untrusted.
- `organization_id` is filtered at the repository level, not in the handler.
- The adversarial suite starts here with: a prompt trying to make the agent skip approval, one
  trying to make it call `create_task` for a different organization, and one trying to extract the
  system prompt.
- No PII beyond synthetic demo data. Traces redact email addresses.

## Eval impact

Creates `evals/datasets/tool_selection.jsonl` and `lead_scoring.jsonl` with a first small set of
cases, plus the initial thresholds. Baseline is recorded, not enforced strictly, until there are
enough cases for the numbers to mean something — and that is stated in the eval report rather than
quietly assumed.

## Risks and open questions

- **Scoring quality is not the point of this slice.** A simple, explainable heuristic plus one LLM
  reasoning pass is enough; sophistication comes after evals exist to measure it.
- LangGraph checkpoint persistence across a process restart is the riskiest technical unknown —
  test it early (acceptance criterion 7), not at the end.
- Provider keys are not configured yet; the LLM gateway needs a fake implementation so unit tests
  and CI can run without them.
