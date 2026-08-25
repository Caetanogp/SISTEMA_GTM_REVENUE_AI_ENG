# Playbook: add a LangGraph node or edge

LangGraph is infrastructure. The graph orchestrates; it does not decide business meaning.

## Where things live

- `infrastructure/agent/graph/` — graph definition, nodes, edges, checkpointer
- `infrastructure/agent/prompts/` — versioned prompt files, never string literals in a node
- `application/` — the use case the node calls. A node is a thin adapter: read state, call a use
  case, write state.

If you find yourself writing an `if` about business meaning inside a node, that branch belongs in
the domain and the node should be asking it a question.

## Adding a node

1. Define what it reads from and writes to the graph state. Keep the state minimal and typed —
   it is checkpointed, so everything you put there is persisted and replayed.
2. Call an application use case. Never a repository or an HTTP client directly.
3. Structured output only: the LLM returns a Pydantic model, validated before it reaches state.
4. Handle failure explicitly: a bounded schema retry, then a fallback path. Never let an invalid
   payload continue down the graph.
5. Bump `graph_version` and record it on the `agent_runs` row.

## Routing

Conditional edges route on **validated state**, never on raw model text. If routing depends on a
model judgement, that judgement is a structured field with an enum, produced and validated upstream.

## Interrupts and HITL

High-risk actions interrupt before execution. The checkpoint carries everything needed to resume:
proposed action, payload, reason, risk level, evidence. After Approve/Edit/Reject the graph resumes
from that checkpoint — with the *edited* payload if the user edited it.

Test resumability explicitly: interrupt, persist, restart the process, resume. A HITL flow that only
works in a warm process is not a HITL flow.

## Checklist

- [ ] Node calls a use case, not an adapter
- [ ] Prompt is a versioned file; `prompt_version` bumped if changed
- [ ] Structured output validated before entering state
- [ ] Bounded retry + fallback on invalid output
- [ ] Routing on validated fields only
- [ ] `graph_version` bumped and recorded
- [ ] Unit test with a fake LLM gateway; integration test for the resume path
- [ ] Eval suite re-run — prompt or graph changes require it
