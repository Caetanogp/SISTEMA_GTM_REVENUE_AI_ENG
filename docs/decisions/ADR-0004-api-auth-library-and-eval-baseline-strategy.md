# ADR-0004: API auth library and offline eval baseline strategy

- **Status:** accepted
- **Date:** 2026-08-30
- **Context spec:** SPEC-001

## Context

ADR-0001 through ADR-0003 cover the architecture, persistence, and LangGraph HITL runtime
decisions through roughly Item 5 of the SPEC-001 queue. Two further decisions were made building
Items 6 (API composition root, JWT auth) and 9-11 (eval datasets, offline runner, baseline) that
were not recorded anywhere durable - only in `.handoff/STATE.md`, which rolls forward and is not
the project's decision log.

## Decision: JWT library

`apps/api/auth.py` encodes and decodes access tokens with **PyJWT** (`jwt.encode`/`jwt.decode`),
not `python-jose`. `python-jose` pulls in `ecdsa` for its EC algorithm support, which this project
does not use (HS256 is sufficient for a single-service, shared-secret JWT); PyJWT covers the same
HS256 path with one fewer transitive dependency to audit and pin. **Revisit if:** the API ever
needs asymmetric JWT verification (e.g., a separate identity provider issuing RS256 tokens) -
PyJWT supports it too, so this is not expected to force a second migration.

## Decision: offline eval baseline strategy

SPEC-001's shipped graph has no dynamic tool router - `propose_action` always drafts exactly one
`create_task`, chosen deterministically by `PrioritizeAccounts`, never picked among tools by an
LLM. Item 11 (offline eval runner) still needed to produce a real, reproducible number for
`evals/datasets/tool_selection.jsonl`, without provider credentials (`.env` does not exist) and
without inventing a new agent capability outside this item's scope.

### Options considered

1. **Script a `FakeLLMGateway` per case to return the dataset's own expected answer.** Rejected:
   trivially circular (100% "accuracy" against a fixture that is scripted to be correct) with zero
   real signal - it would test that the fake gateway pattern works, not anything about tool
   selection.
2. **Wire a real LLM-backed tool router into the graph now**, to give the eval something real to
   score. Rejected: out of Item 11's declared scope (`evals/`, `tests/`, `docs/specs/`), requires
   provider credentials that do not exist in this environment, and is exactly the kind of new
   agent capability `AGENTS.md`'s complexity-flagging rule reserves for a deliberate design pass,
   not a side effect of building eval infrastructure.
3. **A small, explicit, rule-based keyword baseline** (chosen) - `evals/scorers/tool_selection.py`.
   No provider credentials needed, fully deterministic and reproducible, and honestly labelled in
   its own module docstring as a stand-in, not a claim about current agent behaviour.

**Decision:** option 3. `evals/thresholds.toml`'s `tool_selection.min_accuracy = 0.80` is set below
the baseline's current 1.00 measurement on purpose, so growing the dataset with harder adversarial
phrasing has headroom before it fails the gate on a heuristic that was never meant to be the final
answer. `lead_scoring`'s scorer (`evals/scorers/lead_scoring.py`) is different in kind, not just
degree: it wraps the real, shipped `prioritize_account` domain policy directly, so its dataset is a
regression guard (`min_exact_match = 1.00`), not a baseline-to-beat.

## Decision: thresholds file format

`evals/thresholds.toml`, not the `evals/thresholds.yaml` originally named in
`docs/specs/SPEC-001-.../tasks.md`. PyYAML is not a dependency of this project (`pyproject.toml`),
and the autonomous-loop playbook treats adding a new dependency as a signal to stop and ask, not to
add one unprompted. Python's stdlib `tomllib` (3.11+) parses TOML with zero new dependencies. The
user confirmed this call directly when this session halted on the question (see
`.handoff/STATE.md`'s Item 11 history); `tasks.md` and this ADR are the durable record of it.

## Consequences

**Easier:** one fewer transitive dependency to audit (`ecdsa` removed) · the eval gate has a real,
reproducible number today instead of nothing, with an explicit, documented floor for when a real
router replaces the baseline · no new dependency was added for a small, single-purpose config file.

**Harder:** the `tool_selection` baseline could be mistaken for real agent quality by someone who
does not read its docstring or this ADR - mitigated by labelling it explicitly in three places
(module docstring, `evals/thresholds.toml` comments, this ADR).

**Revisit if:** a real LLM-backed tool router is built - it should **replace**
`evals/scorers/tool_selection.py`, not extend the keyword baseline further; and if the API ever
needs asymmetric JWT verification, per the auth decision above.
