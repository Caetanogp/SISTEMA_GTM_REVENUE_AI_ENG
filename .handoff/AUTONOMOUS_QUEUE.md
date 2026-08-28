# Autonomous work queue

The **only** source of work for an unattended loop session (`docs/playbooks/autonomous-loop.md`).
The loop does not decide what to do — it works this list, top to bottom, one item at a time, and
stops the moment it reaches an item marked `HALT` or runs out of items.

Each item declares the files it may touch (nothing outside that scope, ever) and a done
criterion a script can check without judgment. `scripts/autonomous_gate.py` is what actually
evaluates "done" — this file is the plan, that script is the referee.

Spec: `docs/specs/SPEC-001-vertical-slice-account-prioritization/`. Design already resolved in
that spec's `plan.md` — the loop implements it, it does not re-derive it.

---

## Item 1 — Application ports

- **Scope:** `packages/core/revops/application/ports.py`,
  `packages/core/revops/application/__init__.py`, `tests/unit/application/`
- **What:** `typing.Protocol` definitions: `AccountRepository`, `TaskRepository`, `AuditTrail`,
  `LLMGateway`, `Clock`, `UnitOfWork` — signatures only, per `plan.md`'s application section. No
  implementations here; those are infrastructure (out of scope for this queue).
- **Done when:** `ruff`, `mypy`, `lint-imports` (the "Application depends on no infrastructure
  library" contract must hold) and `pytest tests/unit -q` are all green, and every protocol named
  above exists in `ports.py`.

## Item 2 — DTOs

- **Scope:** `packages/core/revops/application/dto.py`, `tests/unit/application/test_dto.py`
- **What:** `CreateTaskArgs` and `AccountScore` as Pydantic models, `model_config =
  ConfigDict(extra="forbid")` on both (AGENTS.md: free text never reaches a write tool
  unvalidated — this is the schema that enforces it for `create_task`).
- **Done when:** gate green, plus a test proving an unknown field on each DTO raises
  `pydantic.ValidationError`.

## Item 3 — `PrioritizeAccounts` use case

- **Scope:** `packages/core/revops/application/use_cases/prioritize_accounts.py`,
  `packages/core/revops/application/use_cases/__init__.py`,
  `tests/unit/application/use_cases/test_prioritize_accounts.py`,
  `tests/unit/application/use_cases/__init__.py`
- **Depends on:** items 1-2, and the domain policy already built
  (`domain.policies.prioritization.prioritize_account`).
- **What:** assembles context from the repository ports, calls the domain policy, returns ranked
  `AccountScore` DTOs with evidence. No LLM call yet — that is infrastructure/graph territory.
- **Done when:** gate green, unit tests pass against fakes implementing the ports (no mocking of
  internals — `docs/playbooks/verify-before-done.md`).

## Item 4 — `ProposeTask` use case

- **Scope:** `packages/core/revops/application/use_cases/propose_task.py`,
  `packages/core/revops/application/use_cases/__init__.py`,
  `tests/unit/application/use_cases/test_propose_task.py`,
  `tests/unit/application/use_cases/__init__.py`
- **Depends on:** items 1-2, `domain.policies.risk`.
- **What:** builds the proposed `create_task` action and classifies its risk
  (`policies.risk.classify` / `requires_hitl`). Returns the proposal **unexecuted** — this use
  case never writes to a repository; `DecideApproval` (item 5) does, after a decision.
- **Done when:** gate green, unit tests cover: a low-confidence or otherwise flagged proposal
  requiring HITL, and the risk classification matching `domain.policies.risk`.

## Item 5 — `DecideApproval` use case

- **Scope:** `packages/core/revops/application/use_cases/decide_approval.py`,
  `packages/core/revops/application/use_cases/__init__.py`,
  `tests/unit/application/use_cases/test_decide_approval.py`,
  `tests/unit/application/use_cases/__init__.py`
- **Depends on:** items 1-2, 4.
- **What:** Approve / Edit / Reject on a proposed action. Approve or Edit executes the (possibly
  edited) payload through the repository ports and writes an audit row via `AuditTrail`; Reject
  writes the audit row and nothing else. Re-deciding an already-decided action raises — reuse or
  extend a domain error (`InvalidTransitionError` fits; do not invent a parallel one without
  checking `domain/errors.py` first).
- **Done when:** gate green, unit tests cover Approve, Edit (the edited payload is what gets
  persisted, not the original), Reject, and re-deciding raising.

## Item 6 — Context builder

- **Scope:** `packages/core/revops/application/context/builder.py`,
  `packages/core/revops/application/context/__init__.py`,
  `tests/unit/application/context/test_builder.py`,
  `tests/unit/application/context/__init__.py`
- **What:** assembles per-task context (account, recent interactions, relevant opportunities)
  under an explicit token budget. AGENTS.md: "never dump the whole CRM into a prompt."
- **Done when:** gate green, plus a test proving it truncates (drops lowest-priority context,
  documented order) rather than silently overflowing the budget.

---

## Item 7 — LangGraph node/checkpoint/interrupt wiring — **HALT: PLAN-MODE-REQUIRED**

- **Scope:** would touch `packages/core/revops/infrastructure/agent/` — do not create or edit
  anything here.
- **Why halted:** `spec.md`'s own words: *"LangGraph checkpoint persistence across a process
  restart is the riskiest technical unknown."* `AGENTS.md`'s standing rule (commit `0c7eddb`)
  requires flagging this kind of decision before implementing, not after. This is exactly that
  case — checkpoint shape, interrupt placement and the resume mechanism are real design choices
  with more than one defensible answer.
- **On reaching this item:** stop. Do not write code toward it. Write the halt reason and the
  state of everything before it to `.handoff/STATE.md`, and end the session. The user resumes
  this item deliberately, in Opus + plan mode, per `AGENTS.md`'s Spec Driven Development section.

---

## Rules for the loop

- Work items in order. Do not skip ahead even if a later item looks easier or independent — the
  order encodes real dependencies (items 3-6 all need items 1-2).
- Never touch a file outside an item's declared scope. If finishing an item genuinely requires
  touching something outside scope, that is itself a signal to stop and flag it, not to expand
  scope silently.
- **Worktree, once, at the very start — not per item.** A `--bg` session defaults to
  `bgIsolation: worktree`, which blocks every Write/Edit outside a worktree until one is entered.
  Call `EnterWorktree` exactly once, before Item 1, then `git branch -m` the auto-generated
  `worktree-<name>` branch to a `feature/`-prefixed name (`autonomous_gate.py` only checks the
  prefix, not the exact name). Do **all** queue items inside that one worktree/branch — do not
  re-enter or create a second worktree partway through.
- One commit per completed item, on that same `feature/`-prefixed branch, following the same
  commit and verification discipline as any other work in this repo (`AGENTS.md`).
- **Do not merge or reconcile the branch yourself.** Reconciling the worktree branch back into
  `feature/SPEC-001-application` (or wherever it needs to land) is a human/main-session step,
  done afterward — the loop's job ends at the last commit + a clean `STATE.md`.
- Tick the matching box in `docs/specs/SPEC-001-vertical-slice-account-prioritization/tasks.md`
  as each item completes.
- Update `.handoff/STATE.md` after every item — evidence, not claims, same as always.
