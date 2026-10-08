# SPEC-010: Grounded Company Research and Follow-Up Preparation

- **Status:** agreed
- **Owner:** Product owner and platform engineering
- **Roadmap phase:** 2-3
- **Created:** 2026-10-07

## Problem

The platform can prioritize accounts, retrieve versioned knowledge, and propose a task, but it
cannot research a company or prepare a follow-up grounded in that company's CRM history and the
approved product knowledge. Users still have to collect evidence and write the message themselves.

The project guide requires external research with citations, personalized generation using CRM and
RAG, and conditional single-agent routing. This spec connects those capabilities into a bounded
single-company workflow that produces a reviewable result and preserves the existing approval path.

## Source requirements

The source of truth is `docs/Agentic_GTM_Revenue_Operations_Platform_Guia_Projeto.pdf`.

| PDF location | Requirement addressed | Traceability IDs |
|---|---|---|
| Pages 3-4, sections 1-2 | Company research and personalized follow-ups using commercial context | PDF-02-005, PDF-02-007, PDF-02-013 |
| Page 8, section 6 | Conditional generation routing and `research_company` / `prepare_followup` tools | PDF-06-002, PDF-06-005 |
| Page 9, section 7 | Budgeted CRM, RAG, prior tool outputs, source attribution, and data/instruction separation | PDF-07-001, PDF-07-002, PDF-07-005 |
| Pages 10-11, sections 8-9 | Least privilege, validation, injection protection, bounded external calls | PDF-08-001, PDF-08-002, PDF-08-003, PDF-09-001 |
| Page 12, section 10 | Groundedness, unsupported claims, tool choice, safety, and reproducibility | PDF-10-002, PDF-10-003 |
| Page 15, section 13 | Progress toward at least five real schema-validated tools | PDF-13-002 |

This spec addresses subsets of cross-cutting requirements. It does not mark the full platform,
production reliability, observability, or MVP complete.

## User stories

- As a Sales/RevOps user, I want to research an account using permitted external sources and see
  the supporting evidence, so that I can assess the result instead of trusting an unsupported summary.
- As a Sales/RevOps user, I want a follow-up draft grounded in CRM history and product knowledge,
  so that personalization reflects facts and approved commercial information.
- As a platform operator, I want bounded requests and attributable outputs, so that research and
  generation remain reproducible and safe to evaluate.
- As a security owner, I want web pages, CRM text, RAG passages, and prior tool results treated as
  untrusted data, so that they cannot change tenant identity, tool permissions, or approval policy.

## Confirmed product decisions

The product owner selected the recommendations below on 2026-10-07 and approved this scope and its
implementation plan on 2026-10-07.

1. Use public pages of the account's company website as the first external source. The deployment
   explicitly authorizes hosts and supported page locations. An account domain alone is not
   permission to fetch it. No search-provider subscription is required by this proposed scope.
   A research-provider API is deferred; adding one requires a separate scope/cost decision.
2. Prepare email drafts in English and Portuguese, with an explicitly selected output language.
   Other messaging channels require a scope revision. Email delivery remains with SPEC-017.
3. If the authorized company site is unavailable but tenant-scoped CRM and approved knowledge are
   sufficient, continue with an explicit source-unavailable limitation. Do not invent external
   company facts or silently treat CRM text as website evidence.
4. Compose a natural structured draft first, then run a second structured factual verifier over every
   claim. A verifier rejection is a bounded insufficient/contradictory result, not an endless retry.

## In scope

- Add exactly two capabilities to the existing single-agent catalog: `research_company` and
  `prepare_followup`, each with strict argument schemas, fixed risk, explicit allowlist entries,
  unit tests, and offline eval cases.
- Support one authenticated account per research/follow-up workflow. Resolve its canonical account
  and tenant ownership before CRM reads, retrieval, network access, or generation. If a contact is
  selected, verify both tenant membership and its relationship to that account.
- Implement a real, explicitly configured external-read adapter and a deterministic offline
  adapter. Offline fixtures are synthetic; an absent live configuration cannot silently enable
  arbitrary network access or return fabricated research as live evidence.
- Return structured research facts with source identifiers, permitted source URLs, retrieval time,
  content hashes, and supporting excerpts. Distinguish missing evidence, conflicting information,
  policy refusal, and provider failure instead of inventing company attributes.
- Reuse SPEC-008 retrieval for current platform/organization knowledge, preserving active revisions,
  ready-state filtering, organization overrides, compatible embedding spaces, and chunk provenance.
- Build follow-up context from the selected account, available relevant CRM history, retrieved
  product/playbook/voice knowledge, and optional validated research from the same account and run.
- Generate a structured draft containing subject, body, language, rationale, evidence references,
  and explicit limitations. Account-level drafts must not invent a recipient or contact details.
- Extend runtime routing and bounded prior-tool-result context so that research can inform a later
  follow-up. Enforce the existing five-tool-call and one-business-write limits across the run.
  External-read retries and generation calls also receive separate finite execution limits.
- Persist bounded research/draft artifacts and their provenance with the agent run and expose a
  typed, authenticated result read. Lifecycle evidence remains sanitized. Existing start, stream,
  task approval, and replay behavior remain compatible.
- Keep prompts, graph, provider configuration, RAG provenance, usage, and cost attributable to the
  run. New model calls must not discard the gateway's usage metadata.
- Add mandatory offline research/generation contract and groundedness evaluations, adversarial
  coverage, and a documented optional live smoke with explicit network/cost confirmation.

Exact limits, result endpoint shape, checkpoint fields, HTTP safety mechanism, and contracts are
fixed in `plan.md`; an implementation change to them requires a scope revision first.

## Out of scope

- Sending email, scheduling meetings, automatically enrolling contacts, or modifying CRM records
  as a consequence of research or draft generation. Existing `create_task` remains behind HITL.
- Bulk research, outreach sequences, scheduled follow-ups, or long-running/background orchestration;
  these remain owned by SPEC-018/019. This slice must finish or fail within a bounded run deadline.
- General web crawling, browser automation, login/paywall access, file downloads, arbitrary
  model-selected URLs, and additional providers beyond the agreed first source.
- Reply classification, frontend screens, MCP exposure, multi-agent delegation, cloud deployment,
  and platform-wide analytics or telemetry.
- New mutable long-term memory, corpus mutation from research, hybrid retrieval, or reranking.
- New dependencies or paid-service procurement as an implementation shortcut. If the source choice
  requires either, revise the scope and agree the resulting plan first.

Deferred capabilities retain their existing roadmap owners; they are not removed from the PDF scope.

## Acceptance criteria

1. Given an authenticated research or follow-up request for an account, when routed, then it selects
   an allowlisted capability; ambiguous account selection and unsupported channels fail without
   guessing an account, source, recipient, or new tool.
2. Given an account/contact from another tenant, a mismatched contact/account, or a tenant/provider/
   permission override in model arguments, when validated, then execution is refused before any
   external request, retrieval, generation, or business write.
3. Given a configured allowed company source, when research runs, then the real adapter can perform
   a bounded read and return typed evidence. Offline tests exercise the same boundary through a
   controlled HTTP transport; live mode never substitutes fictional facts after a failed read.
4. Given a disallowed scheme, host, port, destination address, or redirect, when access is attempted,
   then it is blocked. Tests cover loopback, private/link-local addresses, metadata destinations,
   credential-bearing URLs, and host/address changes during resolution and connection.
5. Given timeouts, rate limits, oversized content, unsupported content types, or malformed responses,
   when reading sources, then retries, response size, and overall execution stay bounded and expose
   only typed sanitized failures. Permanent policy failures are not retried as transient errors.
6. Given research evidence, when a structured summary is produced, then factual assertions reference
   sources actually acquired for that account and supporting excerpts. Missing, conflicting, or
   insufficient evidence is reported explicitly; fabricated sources and invalid references fail.
7. Given active RAG documents and tenant-specific overrides, when preparing context, then the existing
   retrieval rules apply and the result records the exact included chunks/revisions and CRM entities.
   Embedding incompatibility or retrieval failure is not silently replaced with generic generation.
8. Given the run's context budget, when assembling request, CRM, RAG, research, and prior results,
   then the complete assembled context is bounded and omissions are reported. Essential missing
   policy/product evidence produces an evidence-insufficient result rather than invented promises.
9. Given enough authorized evidence, when preparing a draft in either agreed language, then the
   result contains subject, body, language, rationale, and resolvable evidence references. Product,
   pricing, company, and relationship assertions remain within the available evidence; hypothetical
   benefits are distinguished from established facts.
10. Given a request only to research or prepare a follow-up, when it completes, then no email,
    meeting, enrollment, task, interaction, CRM mutation, or external write is created by those tools.
    Persisting the run artifact does not convert generation into a sent message.
11. Given web/CRM/RAG/tool text attempting to change policy, reveal secrets, redirect access, change
    tenants, or trigger a write, when routing and generation run, then deterministic controls still
    apply and adversarial cases cannot bypass the source allowlist or HITL.
12. Given a research-then-follow-up workflow, when tool results are reused, then only validated,
    budgeted results from the same tenant/account/run enter the next context. A sixth tool call is
    denied, and repeated reads do not consume or increase the one-business-write allowance.
13. Given a persisted run result, when read after a process restart, then an authorized same-tenant
    user can retrieve its structured artifact and provenance. Another tenant cannot retrieve it;
    raw HTML, credentials, full prompts, and unrestricted checkpoint state are not exposed.
14. Given a completed/refused/failed workflow, when lifecycle evidence is recorded, then events are
    append-only and sanitized, with graph/prompt/source versions and available per-call model
    configuration, tokens, latency, and cost. Draft content is an access-controlled artifact rather
    than an unrestricted log payload.
15. Given the synthetic offline datasets, when all suites run without network or credentials, then
    new deterministic contract/safety cases score 1.00 and controlled claim-support cases detect
    unsupported claims and invalid citations. Existing eval thresholds remain unchanged.
16. Given the original three tools, existing checkpoints, and task approve/edit/reject/replay flows,
    when full verification runs, then their contracts, isolation, audit invariants, and passing
    unit/integration/adversarial/eval baselines do not regress.

## Tools and risk

| Tool | Type | Risk | HITL |
|---|---|---|---|
| `research_company` | external read from explicitly authorized public sources | low within the agreed source restrictions | no; policy refusals stop access |
| `prepare_followup` | draft generation | low | no; this tool cannot send |
| `search_accounts` / `get_account_context` | existing reads | low | unchanged |
| `create_task` | existing business write | medium | yes, unchanged |

Research authorization is enforced outside the model. A draft is not authorization for a later
send. Broader external sources require separate risk review.

## Fixed execution and result limits

| Control | Limit |
|---|---|
| Tool calls per run | 5 |
| Business writes per run | 1, existing HITL write only |
| Research calls per run | 1, completed result reused |
| Follow-up calls per run | 1, completed result reused |
| Pages per research call | 3 |
| Response bytes per page | 256 KiB |
| Extracted characters per page | 12,000 |
| Attempts per page | 2, transient failures only |
| Research deadline | 30 seconds |
| Whole run deadline | 180 seconds |
| Logical LLM completions per run | 10 |
| LLM call budget | 20 seconds inside remaining deadline |
| Default context budget | 4,096 estimated tokens; hard ceiling 16,384 |
| Request objective | 500 characters |
| Subject/body | 160/6,000 characters |
| New persisted artifacts | 128 KiB total |

## Result endpoint

The authenticated `GET /agent/runs/{run_id}/result` endpoint returns only the typed research,
follow-up draft, provenance, status, and limitations for a same-tenant run. It never executes a
tool, network request, retrieval, or model call. A legacy run without a recorded artifact returns
an explicit `artifact_not_recorded` status. Raw checkpoints, prompts, HTML, secrets, and unrestricted
tool payloads are not public API data.

## Data model impact

Prefer existing PostgreSQL checkpoints and append-only run events for bounded artifacts and
provenance. This is a proposed no-new-table slice, subject to design verification in `plan.md`.
Result schemas and checkpoint additions must preserve compatibility with existing runs. No artifact
is automatically inserted into business interactions or RAG knowledge, and audit rows are not
updated or deleted. If durable retrieval cannot be supported safely by existing storage, raise the
decision before agreeing the plan; do not add a migration during an unattended item.

## Security considerations

External reads introduce an SSRF and prompt-injection boundary. Authorization must cover both the
source hostname and the actual network destination, with redirects and DNS changes constrained.
Research requests disclose only the minimal public company identity needed; private CRM/history
must not be sent to a website or third-party search endpoint.

CRM text and all retrieved sources remain data. Domain policy and authorization stay outside model
output. Validate schemas, business rules, tenant scope, and risk before invocation. Restrict source
retention, context sizes, and output sizes; redact PII/secrets before lifecycle logging. User-visible
drafts and their necessary evidence belong to tenant-protected result storage. Test malicious HTML,
source delimiter escapes, cross-tenant result reuse, fabricated references, and secret-shaped data.

## Eval impact

Keep retrieval evaluation separate from generation evaluation. Add synthetic English/Portuguese
research and draft cases, scripted model outputs, and controlled HTTP responses covering routing,
source authorization, factual support, RAG overrides, insufficient evidence, language, provenance,
budgets, data fencing, and absence of writes.

Reference integrity is deterministic; a valid citation alone does not prove semantic support.
Controlled golden cases must distinguish supported facts from contradicted or unsupported claims.
Offline generation contract scores are not represented as evidence of live model quality. Optional
live smoke results must report their own provider/source configuration, cost, and limitations.

## Risks and open questions

- Product decisions 1-4 above are confirmed. The complete scope and acceptance criteria are agreed.
- Website sources can be unavailable, outdated, or misleading; source provenance is not a guarantee
  of truth. Conflicting evidence and uncertainty must remain visible.
- The current runtime only passes sanitized tool-event summaries to subsequent decisions. The plan
  defines bounded same-run result reuse and explicit checkpoint boundaries.
- The current agent-run API did not expose a typed final artifact. This plan adds an authenticated
  result read while preserving existing start/stream/approval contracts.
- The current runtime can discard model usage metadata. This slice retains usage per model call
  without claiming platform-wide observability is complete.
- Source-safe HTTP connection, fact-support validation, output storage, and numeric execution
  limits are fixed in the agreed plan and ADR.
- Five registered tools demonstrated only with mocks do not prove the PDF's five-real-tools
  requirement. Traceability must distinguish implemented adapters from observed live evidence.

---

Implementation is authorized against the agreed `plan.md` and `tasks.md`. Autonomous queue
activation remains gated by the repository playbook and the verified pilot; it is not implied by
this document alone.
