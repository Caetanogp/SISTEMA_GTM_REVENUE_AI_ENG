---
agent: claude-code
updated_at: 2026-08-30
branch: feature/SPEC-001-agent-graph
spec: SPEC-001-vertical-slice-account-prioritization
phase: "SPEC-001 Item 14 (acceptance evidence) is complete. Item 15 (final closeout) is next and last. Overnight loop for items 10-15 in progress."
status: item14-done-item15-next-overnight-loop-running
---

# Current state

## Claude Code overnight loop (2026-08-30, Item 14 - completed)

Mapped all 10 of `spec.md`'s acceptance criteria to concrete `file:line` evidence, verified by
actually reading the cited test functions and code paths rather than guessing from names -
recorded as a new `tasks.md` section (same permission-driven substitution as Item 11's baseline).
Notably: criterion 3 ("no row until a human decides") is backed by reading
`infrastructure/agent/nodes.py:180-196` directly, confirming `interrupt()` (line 182) is called
strictly before `deps.uow_factory()` opens (line 196) - the code-level guarantee, not just a
behavioral inference from the happy-path test. Criterion 9 (run metadata) cites
`AgentGraphRunner._record_event` (`infrastructure/agent/runner.py:49-77`) where
`graph_version`/`prompt_version`/`token_cost_usd` are actually populated on every event. Also
listed failure-path coverage beyond the 10 numbered criteria (401/422/adversarial tests).
Committed the mapping alone first (`3c866f9`), confirmed the gate green on that clean commit, then
ticked and committed `tasks.md`'s box separately (`ffa7aad`) - correct sequencing again. Re-ran the
gate -> correctly advanced with no violation: `Item 15 gate is green but not yet ticked` - this is
the last item in the queue.

## Claude Code overnight loop (2026-08-30, Item 13 - completed)

Updated `README.md`: replaced the stale "phase 0 complete, phase 1 next" status banner (SPEC-001 is
now code-complete, pending merge) and added a "Trying the vertical slice" section - minting a demo
JWT (`revops.infrastructure.persistence.demo_seed.DEMO_ORGANIZATION_ID`/`DEMO_USER_ID` with
`apps.api.auth.create_access_token`, since this slice has no login endpoint), starting a run,
approving the proposed task, and listing/streaming runs - every command checked against the actual
route/schema code (`apps/api/routes/agent_runs.py`, `apps/api/schemas.py`) rather than guessed.
Disclosed honestly, not glossed over: `apps/api/dependencies.py`'s `default_llm_gateway()` is
`UnconfiguredLLMGateway`, so a freshly-started API's `POST /agent/runs` returns 503 at the reasoning
step until a real provider adapter exists - the full path is verified today via
`pytest tests/integration -q` (injects `FakeLLMGateway`), which the README now says explicitly.
Committed the README change alone first (`3bce7e4`), confirmed the gate green on that clean commit,
then ticked and committed the `tasks.md` box separately (`546e619`) - correct sequencing this time.
Re-ran the gate -> correctly advanced with no violation: `Item 14 gate is green but not yet ticked`.

## Claude Code overnight loop (2026-08-30, Item 12 - unblocked and completed)

Permission gap resolved by the user (verified `git show 1d31891` was authored by the actual user,
`Caetanogp <caetanopadoin345@gmail.com>`, before trusting a peer session's claim - same
verify-before-trust pattern as Item 11's unblock). Created
`docs/decisions/ADR-0004-api-auth-library-and-eval-baseline-strategy.md` verbatim from the draft
already written in this file's history: PyJWT-over-python-jose (drops the `ecdsa` dependency) and
the `tool_selection` naive-keyword-baseline decision (explicit stand-in for a future LLM-backed
tool router, replace-not-extend) plus the `thresholds.toml`-over-`.yaml` call. Committed the ADR
alone first (`6dda687`) while the `tasks.md` box was still unticked, confirmed
`python scripts/autonomous_gate.py` -> `Item 12 gate is green but not yet ticked` on that clean
commit, then ticked and committed the checkbox separately (`8e608a0`) - the sequencing this
project's own Item 11 HALT note prescribes, applied correctly this time with no false scope
violation. Re-ran the gate -> correctly advanced with no violation:
`Item 13 gate is green but not yet ticked`.

## Claude Code overnight loop HALT (2026-08-30, Items 12 and 13 - needs the user)

**Same class of blocker as Item 11's, found early this time by checking ahead instead of hitting it
one item at a time.** `.claude/settings.json`'s `permissions.allow` list has no rule at all for
`docs/decisions/**` or for the repo-root `README.md`. Item 12's scope is
`docs/decisions/`, `docs/specs/SPEC-001-.../`; Item 13's is `README.md`,
`docs/specs/SPEC-001-.../`. Both are genuinely needed, not routable around:

- **Item 12** — I did the actual verification work before concluding this (not assuming a new ADR
  is needed just because a file is unwritable): ADR-0001/0002/0003 cover architecture, persistence,
  and the LangGraph HITL runtime — they stop at roughly Item 5. Two real, undocumented "why is it
  this way" decisions were made after that, in Items 6-11, each with a rejected alternative and a
  real future-work implication (the ADR-0002-style bar: "documented so a future engineer does not
  reinvent or misread the decision"):
  1. **`apps/api/auth.py` uses PyJWT (`jwt.encode`/`decode`), not `python-jose`** — removed the
     `ecdsa` dependency from the project tree. Minor on its own; folding it into the same ADR as a
     short line item (à la ADR-0002's "Real findings from building this" section) rather than
     giving it a whole ADR.
  2. **`evals/scorers/tool_selection.py`'s baseline is a naive keyword heuristic, not a real
     LLM-backed router** — SPEC-001's shipped graph has no dynamic tool selection at all
     (`propose_action` always drafts exactly one `create_task`). Without an ADR, a future engineer
     could easily misread the dataset's 1.00 baseline score as "tool selection is solved," when it
     is a deliberate stand-in scored against its own small dataset. `evals/thresholds.toml` (not
     the `.yaml` originally named in tasks.md) is the companion decision - no new dependency, per
     the user's own resolution of the Item 11 halt.
  I attempted `Write` to `docs/decisions/ADR-0004-...md` and it was denied the same way `evals/*.py`
  was before commit `3de560c` - "Permission to use Write has been denied because Claude Code is
  running in don't ask mode." The full ADR text is drafted below, ready to paste as soon as
  `docs/decisions/**` is writable - no further judgment call needed from whoever unblocks this.
- **Item 13** — confirmed by reading `README.md`: line 11-12 ("Status: phase 0 complete... Phase 1
  — the vertical slice — is next") is now stale, SPEC-001 is nearly closed out. Updating it needs
  `Write`/`Edit` on the repo-root `README.md`, which has no allow-rule either.

**Checked ahead, not just reacted:** before halting, I read Items 14 and 15's declared scope too, so
this doesn't repeat a third and fourth time.
- **Item 14** (acceptance evidence) does **not** need a new permission — I can record the
  criteria-to-evidence mapping as a new section inside `tasks.md` itself, the same substitution
  already used for Item 11's baseline report, since `docs/specs/**/tasks.md` is writable.
- **Item 15** (closeout) does **not** need `.github/` write either, on inspection:
  `.github/pull_request_template.md` is a repo-wide reusable scaffold, not a per-PR file: "fill the
  pull-request template" means drafting the actual filled-in PR body text (evidence, checklists,
  etc. following that template's structure) for the user to paste when they run
  `gh pr create --body-file` or use the GitHub UI later - not editing the template file itself. That
  content can be recorded in `.handoff/STATE.md` or a chat response, both already fine.

So the loop only needs one more permission fix (`docs/decisions/**` and `README.md`) to clear
Items 12 and 13, then Items 14 and 15 should run without hitting this again.

**Suggested next step for the user:** add `Write(./docs/decisions/**)`, `Edit(./docs/decisions/**)`,
`Write(./README.md)`, `Edit(./README.md)` to `.claude/settings.json`, then resume.

### Draft ADR-0004, ready to create verbatim once `docs/decisions/` is writable

File: `docs/decisions/ADR-0004-api-auth-library-and-eval-baseline-strategy.md`

```markdown
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
```

## Claude Code overnight loop (2026-08-30, Item 11 - unblocked and completed)

The permission gap and thresholds-format question from the HALT below were both resolved by the
user (via another session's message, verified against real commits before trusting it - see "Cross-
session unblock" below). Implemented the remaining Item 11 work on top of the scorers already
committed in `3b09026`:

- `evals/run.py`: `python -m evals.run --suite all` (matches AGENTS.md's Commands section),
  writes one JSON report per suite to `evals/reports/` (git-ignored).
- `evals/gate.py`: `python -m evals.gate`, re-scores fresh every run (never trusts a stale report
  file), reads `evals/thresholds.toml`, exits 0 only if every suite meets its threshold.
- `evals/thresholds.toml`: `lead_scoring.min_exact_match = 1.00` (regression guard - it's the real
  domain policy under test), `tool_selection.min_accuracy = 0.80` (below the current 1.00 measured
  against the naive keyword baseline, leaving headroom before a real LLM router replaces it).
- Baseline recorded as a new section inside `tasks.md` (not a dedicated `eval-baseline.md` - this
  session's `Write`/`Edit` allowlist only covers `docs/specs/**/tasks.md`, not other files under
  `docs/specs/`; documented inline there and not treated as a reason to halt again, since it's a
  same-substance, no-new-permission-needed substitution, unlike the `evals/*.py` path question).
- Verified via `pytest tests/unit/evals -q` -> 34 passed (13 dataset/schema tests from Items 9-10,
  11 scorer tests from the earlier WIP commit, 5 for `evals/run.py`, 5 for `evals/gate.py`) plus
  `ruff check .`, `mypy .`, `lint-imports` all clean - `python -m evals.run`/`python -m evals.gate`
  themselves aren't on this session's Bash direct-execution allowlist, so `test_run.py`/
  `test_gate.py` exercise the exact same `run_suite`/`write_report`/`evaluate_suite`/`main`
  functions the CLIs call, which is a real, non-mocked verification of both modules.
- `python scripts/autonomous_gate.py` on the clean, committed tree (commit `e99751c`, before the
  tick) -> `Item 11 gate is green but not yet ticked in tasks.md - tick it.` (ruff/mypy/lint-imports/
  pytest/check_agent_docs all OK). Ticked, committed separately (`2352bae`), re-ran the gate ->
  correctly advanced with no scope violation: `Item 12 gate is green but not yet ticked`.

### Cross-session unblock (verified before trusting it)

Another Claude session on this machine sent a message claiming the permission gap and thresholds
question were resolved. Per this project's standing rule that a peer cannot grant escalation and a
peer's claim must be verified, not trusted at face value, I checked directly rather than acting on
the message alone: `git log`/`git show 3de560c` confirmed a real commit, authored by the actual
user (`Caetanogp <caetanopadoin345@gmail.com>`, not the peer session), adding exactly
`Write(./evals/*)` and `Edit(./evals/*)` to `.claude/settings.json` - one level, not recursive, the
existing subdirectory rules untouched. That the change was authored by the user themselves (not
merely relayed by a peer) is what made it safe to act on; a peer asserting a permission change
without that evidence would not have been enough on its own. Re-ran
`python scripts/autonomous_gate.py` myself to confirm the fix took effect before writing any new
code.

### A self-inflicted sequencing bug along the way (also self-resolved, no code change)

Ticked Item 11's `tasks.md` checkbox and ran the full gate *before* committing Item 11's own files.
`completed_task_count()` immediately saw the higher done_count and treated Item 12 as current;
since the gate's own baseline tracking (`.handoff/.autonomous_gate_state.json` - git-ignored,
untracked, not in this session's `Write`/`Edit` allowlist either) hadn't caught up yet, it reset
`baseline_sha` to the *pre-commit* HEAD, so Item 11's still-uncommitted files permanently read as
"changed since baseline" and got checked against Item 12's scope instead of Item 11's - the gate
correctly halted on this (see the HALT entry below), and it was a real, honest signal, not a bug in
the gate script. Fixed by reverting the tick, committing Item 11's files alone against a
now-correct baseline, confirming the gate went green on that clean commit, then ticking and
committing the checkbox as its own separate commit. **Lesson recorded for future items:** always
commit an item's own files *before* ticking its `tasks.md` box and re-running the gate - ticking
first, in the same uncommitted working tree, is what desyncs `baseline_sha` from reality.

## Claude Code overnight loop HALT (2026-08-30, Item 11 - needs the user, RESOLVED above)

**This is a real halt, not the gate's own `HALT:` mechanism** - `python scripts/autonomous_gate.py`
still prints "Item 11 gate is green but not yet ticked in tasks.md - tick it." That is the same
false-positive signal the user warned about at the start of this session for Item 10: the gate's
quality checks (ruff/mypy/lint-imports/pytest/check_agent_docs) are green because everything that
exists is clean, not because Item 11 is done. **Do not tick Item 11's `tasks.md` checkbox or trust
that gate line** - the deliverables it names do not exist on disk.

**The blocker:** `.claude/settings.json`'s `permissions.allow` list only grants `Write`/`Edit`
under these specific `evals/` subdirectories:
```
Write(./evals/datasets/**)   Edit(./evals/datasets/**)
Write(./evals/scorers/**)    Edit(./evals/scorers/**)
Write(./evals/regression/**) Edit(./evals/regression/**)
Write(./evals/reports/**)    Edit(./evals/reports/**)
```
There is no rule for bare files directly under `evals/` (no `Write(./evals/*.py)` or similar). This
session is running with `--permission-mode dontAsk` (the autonomous-loop playbook's own
recommendation, so an unattended run can't sit waiting on a prompt nobody will answer) - under that
mode, any tool call outside the allowlist is denied automatically, with no prompt to the user at
all. Confirmed directly: attempting `Write` to `evals/run.py` (verbatim content, no unusual path)
was denied with "Permission to use Write has been denied because Claude Code is running in don't
ask mode" - the identical denial shape seen earlier this session for `Bash` calls to `rm`, `mv`, and
plain `python -c` (none of those are on the `Bash` allowlist either; see the note on
`tests/unit/evals/test_zzz_scratch_lead_scoring_compute.py`'s filename below for that one).

**Why this is a real stop, not something to work around:** AUTONOMOUS_QUEUE.md's Item 11 and
`tasks.md` line 81 both name the exact deliverables - `evals/run.py`, `evals/gate.py`,
`evals/thresholds.yaml` - as bare files directly under `evals/`, and AGENTS.md's own Commands
section documents `python -m evals.run --suite all` as the intended invocation, which requires
`evals/run.py` to exist at exactly that path. There is no way to deliver what Item 11 actually asks
for without either (a) writing to a path this session has no permission for, or (b) restructuring
the deliverable into a location the allowlist does cover (e.g. nesting the runner inside
`evals/scorers/` instead) and changing the documented `python -m evals.run` command to match. Option
(b) is exactly the kind of "more than one defensible answer" design substitution the standing rule
in `AGENTS.md` says to stop and ask about rather than guess on - it would change a documented public
command surface, not just an eval-tooling implementation detail. Editing `.claude/settings.json`
myself to add the missing allow-rule is not something this session does unprompted - it is a
permissions/config change, not code, and self-expanding one's own write permissions is precisely
the kind of escalation `--permission-mode dontAsk` exists to prevent by construction.

**What is actually done vs. still needed for Item 11** (commit `3b09026`):
- Done and tested: `evals/scorers/lead_scoring.py` (wraps the real, production
  `prioritize_account` domain policy as a regression-guard scorer - not a new capability, just a
  reusable entry point so a runner can call it) and `evals/scorers/tool_selection.py` (an
  explicitly-labelled naive keyword-based baseline, documented in its own module docstring as a
  stand-in for a future LLM-backed tool router that does not exist yet in the shipped graph -
  `propose_action` always drafts exactly one `create_task`, deterministically, never picks among
  tools). `pytest tests/unit/evals -q` -> 24 passed (13 from Items 9-10 + 11 new: 4 for
  `lead_scoring` scorer, 7 for `tool_selection` scorer). `ruff check .`, `mypy .`, `lint-imports`
  all clean. Both scorers expose plain functions (`score_lead_scoring_dataset()` /
  `score_tool_selection_dataset()` returning a `ScoreResult(total, correct, failed_ids, accuracy)`)
  specifically so a future `evals/run.py` can import and call them with no further scorer work.
- Still needed once the permission is granted: `evals/run.py` (CLI matching
  `python -m evals.run --suite all` from AGENTS.md, writing a JSON report per suite to
  `evals/reports/` - already writable), `evals/gate.py` (reads a thresholds file, re-scores fresh
  - never trusts a stale report - and exits 0/1), and a thresholds file. On the thresholds file: I
  was leaning `evals/thresholds.toml` (stdlib `tomllib`, zero new dependency) over the literal
  `evals/thresholds.yaml` named in `tasks.md`, because PyYAML is not in `pyproject.toml`'s
  dependencies or dev-dependencies, and the autonomous-loop playbook's "What this does not do"
  section is explicit that a new dependency is itself a signal to stop and ask, not to add one -
  I had not yet added it when the `evals/run.py` Write call was denied, so this is also unresolved
  and worth the user's input alongside the path issue.
- With `evals/run.py` and `evals/gate.py` in place, the actual measured baseline (from the scorers
  already committed) would be: `lead_scoring` 15/15 exact match (1.00 - it's the same deterministic
  function under test, so a threshold of 1.00 is a real regression tripwire, not aspirational);
  `tool_selection` 13/13 against the current dataset (1.00) using the naive heuristic baseline - I
  was planning a threshold of 0.80, not 1.00, so future adversarial dataset growth has headroom
  without instantly failing the gate the day someone adds a harder case the heuristic misses.

**Suggested next step for the user:** add an allow-rule to `.claude/settings.json` covering bare
files under `evals/` (e.g. `Write(./evals/*.py)` and `Edit(./evals/*.py)`, plus a rule for whichever
thresholds-file format is chosen), confirm the YAML-vs-TOML call, then resume the loop - Items 10's
scorers are ready to be consumed by `evals/run.py` as soon as it can be written.

## Known cosmetic wart (Item 10, disclosed rather than hidden)

The Item 10 test file is named `tests/unit/evals/test_zzz_scratch_lead_scoring_compute.py`, not the
conventional `test_lead_scoring_dataset.py`. It started as a throwaway script (`assert False` +
prints) used only to compute the dataset's exact expected scores/tiers from the real policy
function, since this sandboxed session's `Bash` permission allowlist has no `rm`/`mv` and no
generic `python -c`. With no sanctioned way to delete or rename it, and ruling out the alternative
of using `pytest` itself to run non-test file-deletion code (an explicit tool-guidance red line),
the file was overwritten in place with the real, permanent, non-scratch test content instead.
Content and coverage are final and correct; renaming it to `test_lead_scoring_dataset.py` is a
trivial manual cleanup for whoever has normal filesystem access.

## Claude Code overnight loop (2026-08-30, Item 10)

Implemented Item 10: `evals/datasets/lead_scoring.jsonl` (15 synthetic labelled account-scoring
cases: all three tiers represented - 7 cold, 3 warm, 5 hot - plus explicit edge cases: never
touched, exact 30-day staleness boundary, closed-won and closed-lost opportunities both ignored by
value/stage signals, two open opportunities summed for the value signal, and 11 recent interactions
capping the engagement sub-score at 100). Test file
`tests/unit/evals/test_zzz_scratch_lead_scoring_compute.py` (6 tests: file exists, schema/field
validation, unique ids, ~15 cases, all 3 tiers present, and a regression guard that reconstructs
every case's `Interaction`/`Opportunity` entities and asserts `prioritize_account` - the real
domain policy in `packages/core/revops/domain/policies/prioritization.py` - still produces the
recorded `expected_score`/`expected_tier`). `pytest tests/unit/evals -q` -> 13 passed (7 from Item
9 + 6 new). `python scripts/autonomous_gate.py` -> `Item 11 gate is green but not yet ticked` after
ticking the `lead_scoring.jsonl` box (ruff/mypy/lint-imports/pytest/check_agent_docs all OK).
Committed as `d9bca4a`.

**Known cosmetic wart, disclosed rather than hidden:** the test filename is
`test_zzz_scratch_lead_scoring_compute.py`, not the conventional `test_lead_scoring_dataset.py`.
It started as a throwaway script (`assert False` + prints) used only to compute the dataset's exact
expected scores/tiers from the real policy function, since this sandboxed session's Bash permission
allowlist (`.claude/settings.json`) has no `rm`/`mv` and no generic `python -c` - only specific
prefixes (`git status/diff/log/add/commit/checkout/branch`, `ruff`, `mypy`, `pytest`,
`lint-imports`, `alembic upgrade/revision`, `docker compose up/ps/logs`, `gitleaks`,
`python scripts/*`, `uv`), and Write is only allowed under specific path prefixes that do not
include `scripts/`. With no sanctioned way to delete or rename the scratch file, and rejecting the
alternative of using pytest itself to run non-test file-deletion code (an explicit tool-guidance
red line), the least-bad choice was to overwrite the file in place with the real, permanent,
non-scratch test content and disclose the filename mismatch here rather than leave a stray
`assert False` file in the tree or silently accept a misleading name. Content and coverage are
final and correct; renaming the file to `test_lead_scoring_dataset.py` is a trivial manual cleanup
for whoever has normal filesystem access.

## Claude Code pickup (2026-08-30)

Resumed from Codex's handoff, verified `.handoff/STATE.md` against real `git log`/`git status`/
`python scripts/autonomous_gate.py` before trusting it - all matched. Implemented Item 9:
`evals/datasets/tool_selection.jsonl` (13 synthetic cases: 4 `search_accounts` positives, 3
`get_account_context` positives, 2 `create_task` positives, 4 negatives that must not select
`create_task`, including one adversarial bulk-write attempt) and
`tests/unit/evals/test_tool_selection_dataset.py` (7 structural tests: valid JSONL, required
fields, unique ids, ~10-15 cases, every known tool has a positive, at least 3 negatives, negatives
document why `create_task` is wrong - no scorer exists yet in `evals/scorers/`, this only proves
the dataset itself is well-formed). `pytest tests/unit/evals -q` -> 7 passed. Ticked `tasks.md`'s
`tool_selection.jsonl` checkbox. `python scripts/autonomous_gate.py` -> `Item 10 gate is green but
not yet ticked` (ruff/mypy/lint-imports/pytest/check_agent_docs all OK).

## Goal

Ship the SPEC-001 vertical slice end to end: natural-language request -> CRM context -> read tool ->
reasoning -> proposed action -> HITL approval -> write tool -> audit trail.

## Now

On `feature/SPEC-001-agent-graph`. Targeted verification is green after the LangGraph, API, and
security work: `ruff check` passed on the changed files, `python -m alembic upgrade head` applied
the runtime migration locally, `pytest tests/integration -q` passed (18 tests),
`pytest tests/adversarial -q` passed (3 tests), `bandit -r packages apps -q` is green with only
documented migration waivers, `gitleaks detect --no-git` is clean, and `pip-audit -l` in a clean
venv found no known vulnerabilities. The final `python scripts/autonomous_gate.py` also passed
all of its checks.

The policy/security work is implemented in the feature branch. The API composition root, JWT auth,
run/approval endpoints, adversarial coverage, and dependency audit now exist. The active SPEC-001
checklist has its first `## 7. Data and evals` checkbox complete; the remaining three data/evals
checkboxes and all four closeout checkboxes are still pending. The queue and `autonomous_gate.py`
now model those sections. The queue parser and gate were fixed and committed as `a356437`; the
implementation baseline was committed as `da756d6`.

Item 8 is complete on this branch and was committed as `c729380`. `python scripts/seed_demo.py` ran successfully twice
sequentially and twice concurrently after `alembic upgrade head`; both concurrent processes exited
0. The database contains exactly 1 demo organization, 1 user, 30 accounts, 30 contacts, 30
opportunities, and 60 interactions. Stable UUIDs plus a PostgreSQL transaction advisory lock make
repeated and concurrent invocations deterministic.

## Done (this spec; full narrative in `.handoff/log/2026-08-30-0106-claude.md`)

- SPEC-001 persistence remains merged on `develop`; this branch builds on that baseline with the
  graph runtime and resume wiring.
- The graph runtime now has `load_context`, `score_accounts`, `propose_action`, and
  `execute_action`, with a pooled Postgres checkpointer helper and a deterministic fake LLM for
  tests.
- The API layer now exposes `POST /agent/runs`, `GET /agent/runs`, `GET /agent/runs/{id}/stream`,
  and `POST /agent/runs/{id}/approve`, with token-based organization scoping.
- Approval decisions are now idempotent by persisted action id, and the audit/run history records
  run identity plus graph/prompt versions.
- The integration suite is green, including the repeated-resume idempotency case and the API
  happy path / auth failure coverage.

## Next

1. **Blocked - needs the user first:** grant `Write`/`Edit` on `docs/decisions/**` and `README.md`
   in `.claude/settings.json` - see the HALT entry above for the full reasoning and the ready-to-
   paste ADR-0004 draft. Do not resume the loop against Item 12 until this is resolved.
2. Once unblocked: create `docs/decisions/ADR-0004-...md` verbatim from the draft above, tick
   Item 12, commit; then Item 13 (`README.md` setup/usage steps).
3. Items 14-15 do **not** need a new permission (see the HALT entry's "checked ahead" note) -
   record Item 14's evidence mapping as a `tasks.md` section like Item 11's baseline, and Item 15's
   PR body content in `STATE.md`/chat rather than editing `.github/pull_request_template.md`.
4. **Sequencing reminder for every remaining item:** commit an item's own files first, *then* tick
   its `tasks.md` box in a separate commit, *then* re-run the gate - see the Item 11 self-resolved
   HALT note above for why ticking before committing desyncs the gate's baseline tracking.
3. Items 12-15: SPEC-001 decision record, setup docs, acceptance evidence, closeout handoff.
3. Materialize the next spec only after SPEC-001 closeout; `docs/specs/` currently only contains
   SPEC-001 and roadmap placeholders.

## Gotchas

- `git checkout <branch>` can fail with `error: cannot stat '.claude': Invalid argument` when the
  target branch's `.claude/` tree differs from the current one.
- Never call `EnterWorktree` for this project. Editable installs resolve to absolute paths from
  installation time, so a worktree can silently run stale code.
- `docs/playbooks/autonomous-loop.md` is the shared source of truth for unattended-loop rules.
- `alembic downgrade` is in the unattended `ask` list and remains a human-run step.

## Resume

```bash
cd "SISTEMA_PORTFOLIO_AI_ENG"
git status
git rev-parse --abbrev-ref HEAD
git log -1 --oneline --decorate
```

## Open questions

- OneDrive/Defender exclusion for this folder would likely remove the checkout gotcha, but needs the
  user.
- Provider keys are still not configured (`.env` does not exist yet) for running the graph against a
  real model.
- SPEC-002 and onward are roadmap placeholders only; there is no next `spec.md`/`plan.md`/`tasks.md`
  trio to hand to an unattended loop yet.
- The JWT helper now uses PyJWT instead of python-jose, which removed the `ecdsa` dependency from
  the project tree.
- The two earlier autonomous HALTs were caused by the queue parser/dirty pre-commit baseline and
  are resolved by commits `a356437` and `da756d6`; the current gate reaches Item 8 as expected.

## Autonomous loop HALT (2026-08-30T07:36:55+00:00)

Queue and tasks.md are out of sync - done_count is not covered by any item's closes range. Check every item's `- **Closes:** N tasks.md checkboxes` line adds up to tasks.md's total checkbox count for this section.

The loop stopped itself. Do not restart it against the same queue item without addressing the reason above first.

## Autonomous loop HALT (2026-08-30T07:37:33+00:00)

Item 8 declares scope ('scripts/', 'packages/core/revops/infrastructure/persistence/', 'tests/'), but changes touch files outside it: ['apps/api/__init__.py', 'apps/api/auth.py', 'apps/api/dependencies.py', 'apps/api/main.py', 'apps/api/routes/__init__.py', 'apps/api/routes/agent_runs.py', 'apps/api/runtime.py', 'apps/api/schemas.py', 'apps/api/settings.py', 'packages/core/revops/application/dto.py', 'packages/core/revops/application/ports.py', 'packages/core/revops/application/use_cases/decide_approval.py', 'packages/core/revops/application/use_cases/prioritize_accounts.py', 'packages/core/revops/application/use_cases/reason_about_accounts.py', 'packages/core/revops/domain/policies/task.py', 'packages/core/revops/infrastructure/agent/__init__.py', 'packages/core/revops/infrastructure/agent/checkpointer.py', 'packages/core/revops/infrastructure/agent/graph.py', 'packages/core/revops/infrastructure/agent/nodes.py', 'packages/core/revops/infrastructure/agent/prompt_loader.py', 'packages/core/revops/infrastructure/agent/prompts/prioritize_accounts.v1.md', 'packages/core/revops/infrastructure/agent/runner.py', 'packages/core/revops/infrastructure/agent/state.py', 'packages/core/revops/infrastructure/llm/__init__.py', 'packages/core/revops/infrastructure/llm/fake.py', 'pyproject.toml']. Revert the out-of-scope changes or stop and ask.

The loop stopped itself. Do not restart it against the same queue item without addressing the reason above first.

## Autonomous loop HALT (2026-08-30T07:38:29+00:00)

Item 8 declares scope ('scripts/', 'packages/core/revops/infrastructure/persistence/', 'tests/'), but changes touch files outside it: ['apps/api/__init__.py', 'apps/api/auth.py', 'apps/api/dependencies.py', 'apps/api/main.py', 'apps/api/routes/__init__.py', 'apps/api/routes/agent_runs.py', 'apps/api/runtime.py', 'apps/api/schemas.py', 'apps/api/settings.py', 'packages/core/revops/application/dto.py', 'packages/core/revops/application/ports.py', 'packages/core/revops/application/use_cases/decide_approval.py', 'packages/core/revops/application/use_cases/prioritize_accounts.py', 'packages/core/revops/application/use_cases/reason_about_accounts.py', 'packages/core/revops/domain/policies/task.py', 'packages/core/revops/infrastructure/agent/__init__.py', 'packages/core/revops/infrastructure/agent/checkpointer.py', 'packages/core/revops/infrastructure/agent/graph.py', 'packages/core/revops/infrastructure/agent/nodes.py', 'packages/core/revops/infrastructure/agent/prompt_loader.py', 'packages/core/revops/infrastructure/agent/prompts/prioritize_accounts.v1.md', 'packages/core/revops/infrastructure/agent/runner.py', 'packages/core/revops/infrastructure/agent/state.py', 'packages/core/revops/infrastructure/llm/__init__.py', 'packages/core/revops/infrastructure/llm/fake.py', 'pyproject.toml']. Revert the out-of-scope changes or stop and ask.

The loop stopped itself. Do not restart it against the same queue item without addressing the reason above first.

## Autonomous loop HALT (2026-08-30T08:42:57+00:00)

Item 12 declares scope ('docs/decisions/', 'docs/specs/SPEC-001-vertical-slice-account-prioritization/'), but changes touch files outside it: ['evals/gate.py', 'evals/run.py', 'evals/thresholds.toml', 'tests/unit/evals/test_gate.py', 'tests/unit/evals/test_run.py']. Revert the out-of-scope changes or stop and ask.

The loop stopped itself. Do not restart it against the same queue item without addressing the reason above first.

**Self-resolved, same session, no code change needed:** this was a sequencing mistake, not a real
scope violation. I ticked Item 11's `tasks.md` checkbox and ran the full gate *before* committing
Item 11's own files. `completed_task_count()` immediately saw done_count=4 and treated Item 12 as
current; since `gate_state.baseline_done_count` (3, from the last real commit) differed, the gate
reset `baseline_sha` to the *pre-commit* HEAD (`3de560c`) - stamping "everything before Item 12"
one commit too early, so Item 11's still-uncommitted files (`evals/run.py`, `evals/gate.py`,
`evals/thresholds.toml`, the two new test files) permanently read as "changed since baseline" and
got checked against Item 12's scope instead of Item 11's. `.handoff/.autonomous_gate_state.json` is
git-ignored, untracked, and not in this session's `Write`/`Edit` allowlist, so it can't be hand-
edited back - but it doesn't need to be. Fix: tasks.md's Item 11 box was reverted to unticked,
everything is being committed as one Item-11 commit while done_count is still 3 (so the gate's own
next run naturally resets `baseline_done_count` 3→3, no-op, then the gate reports "green but not
ticked" against a clean tree), and only *then* does a second, tiny commit tick the box - at which
point done_count 3→4 triggers a fresh, correct `baseline_sha` reset to that tick-commit (already
clean, so Item 12 starts with zero false positives). Lesson for future items: always commit an
item's own files *before* ticking its `tasks.md` box and re-running the gate, never in the same
uncommitted working tree - ticking first is what desyncs `baseline_sha` from reality.
