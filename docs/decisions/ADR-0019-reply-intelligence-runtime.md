# ADR-0019: Bounded Reply Intelligence Runtime

- **Status:** accepted
- **Date:** 2026-10-10
- **Scope:** SPEC-011

## Decision

Reply intelligence uses a dedicated fixed-tool `reply-intelligence.v1` graph with a low-risk `classify_reply` operation. It stores an immutable reply, reserves a classification request and agent run atomically, executes one bounded structured classification, and persists a sanitized typed artifact. Confidence below `0.80`, ambiguity, incompatible language, or invalid evidence becomes `review_required` and `manual_review`; the fixed next-action mapping is part of the approved contract. Uncertainty uses a correction API, not an external write approval.

## Context

The platform needs bilingual reply interpretation while keeping external content untrusted, tenant identity deterministic, and existing SPEC-009/010 runtimes stable. The result is analysis only; no mailbox, CRM, email, calendar, or sequence side effect is authorized.

## Consequences

The graph and reply-specific unit of work add code and tables, but make checkpoint/replay and evidence boundaries explicit. The 90-case offline dataset and three metrics establish a measurable baseline. Provider confidence remains informational, and explicit human review handles ambiguity.

## Alternatives rejected

An LLM router, mailbox connector, automatic CRM mutation, thread-wide context, shared ingestion UoW, and multi-agent split were rejected because they expand risk or scope without evidence of benefit.

## Traceability

The decision covers PDF reply intelligence and structured next-action behavior (PDF-02-010), feedback linkage (PDF-05-008), measurable reply metrics (PDF-10-002), and synthetic reply data (PDF-10-003).
