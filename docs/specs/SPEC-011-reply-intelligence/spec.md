# SPEC-011: Reply Intelligence

- **Status:** agreed
- **Owner:** Product and engineering
- **Roadmap phase:** 2/3
- **Created:** 2026-10-10

## Problem

The platform can research accounts and prepare grounded outreach, but it cannot turn an
authenticated inbound reply into a bounded, auditable recommendation. Operators need a tenant-safe
classification, explicit uncertainty handling, and immutable correction history before later specs
can automate follow-up work.

## User stories

- As a representative, I want to register an authenticated English or Portuguese reply, so that it can be classified without accepting tenant identity from the request body.
- As a representative, I want a typed category, evidence, confidence, and recommended next action, so that I can understand the result before acting.
- As an operator, I want uncertain classifications marked for review, so that the system does not silently infer intent from ambiguous text.
- As a reviewer, I want corrections appended to an immutable feedback history, so that later evals can measure regression without rewriting the original result.

## In scope

- Nine categories: `interested`, `not_interested`, `objection`, `question`, `out_of_office`, `wrong_person`, `unsubscribe`, `automatic_response`, and `unknown`.
- English and Portuguese current-message classification through an authenticated API.
- Tenant-safe account/contact resolution through the existing canonical resolver.
- Structured evidence offsets, limitations, confidence, and deterministic next-action mapping.
- Review-required results for low confidence, ambiguity, incompatible language, or invalid evidence.
- Explicit unsubscribe precedence over commercial intent for conservative English/Portuguese guards.
- Dedicated low-risk `classify_reply` tool and `reply-intelligence.v1` checkpointed graph.
- Immutable replies, classification requests, results, and correction feedback with idempotency.
- Offline synthetic dataset with five examples per category and language, contract and baseline evals.
- API result and feedback endpoints, adversarial coverage, restart coverage, and PDF traceability.

## Out of scope

- Mailbox or inbox connectors, polling, webhooks, or provider-specific credentials.
- Sending email, scheduling meetings, CRM mutation, bulk actions, or automatic sequences.
- Thread history, attachments, HTML rendering, or messages above 8,000 characters.
- Draft generation, task proposal, automatic training, or online model fine-tuning.
- Frontend screens, async workers, multi-agent routing, new dependencies, and provider quality claims from live evaluation.

## Acceptance criteria

1. Authenticated users can create and read an organization-scoped reply with account/contact relationship validation, language validation, bounded text, and replay-safe idempotency.
2. A classification request reserves one run atomically with its start event before model execution; same-key replays do not create duplicate replies, runs, or feedback records.
3. The dedicated graph returns one typed category, confidence, evidence offsets, limitations, and mapped next action; invalid or uncertain results are `review_required`.
4. Explicit unsubscribe intent wins over conflicting commercial language in English and Portuguese, and classification never updates contacts or other CRM records.
5. Cross-tenant, mismatched-account/contact, unauthorized-run, malformed-output, prompt-injection, fake-evidence, and PII-log cases are rejected or sanitized deterministically.
6. Checkpoint restart and terminal result reads do not invoke the model a second time; result reads use the artifact reader without graph construction, provider initialization, or RAG I/O.
7. Feedback appends a correction and optional comment while preserving the original classification; history is organization-scoped and linked to the run.
8. The synthetic offline dataset contains at least five examples per category per language; contract evaluation is 1.00 and the deterministic baseline reaches accuracy >=0.85, macro-F1 >=0.80, and unsubscribe recall 1.00.
9. Every new tool has a strict schema, low-risk allowlist entry, unit test, and eval case; audit records contain graph/prompt versions and per-call usage without raw reply text.
10. The full verification gate passes with twelve acceptance-evidence mappings recorded as file:line references, and no existing SPEC-009/010 behavior regresses.

## Tools and risk

| Tool | Type | Risk | HITL |
|---|---|---|---|
| `classify_reply` | read/analysis | low | no |

## Data model impact

Additive tables for replies, classification requests, and feedback. Use organization-scoped keys, foreign keys, indexes, and idempotency constraints. Do not drop or rewrite existing data.

## Security considerations

Reply text is untrusted data and may contain prompt injection, PII, or fake evidence. Tenant identity, authorization, risk, and allowlists remain deterministic. Raw text is stored only in the authorized reply record; events, logs, checkpoints, and eval artifacts contain identifiers and sanitized output.

## Eval impact

Add a synthetic 90-example bilingual dataset, contract cases, nine-class metrics, unsubscribe recall, and adversarial cases. Live evaluation is optional and requires explicit cost approval; it is not part of the launch gate.

## Risks and open questions

- Text-only classification can be ambiguous; the explicit review state is the safety boundary.
- Provider confidence is not calibrated and must not alone authorize an external action.
- No product questions remain for the approved scope. Any new public contract, dependency, destructive migration, or non-dominant architecture choice requires a deliberate design pass.
