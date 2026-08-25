# Playbook: build a front-end screen

`apps/web` — Next.js (App Router), React, TypeScript, Tailwind, shadcn/ui. This is the public demo;
a recruiter judges the whole project by it.

## Before writing JSX

Decide the design direction first: purpose, audience, and a specific aesthetic. Left to defaults, an
agent produces the same generic card grid with a purple gradient — that look now reads as
"unreviewed AI output" and costs the project credibility. Reuse the existing tokens and components;
a new screen should look like it belongs to the same product.

If the `frontend-design` plugin is installed, use it here.

## Rules

- Server components by default; `"use client"` only where interactivity actually requires it.
- Data fetching through a typed API client; no `fetch` scattered in components.
- Every async surface has three states: loading, empty and error. The empty state is where most
  demos fall apart — an empty CRM should still explain itself.
- Agent progress streams over SSE. Show the steps as they happen; that visible progress is a large
  part of what makes the demo convincing.
- Accessibility is not optional: real labels, keyboard reachable, visible focus, AA contrast.
- Responsive down to a phone. Recruiters open links on phones.

## The screens that carry the portfolio

- **AI Assistant** — the natural-language entry point, streaming its work.
- **HITL approval** — must show the full proposed action: recipient, payload, reason, risk level and
  the evidence behind it. Approve / Edit / Reject. Approving something you cannot inspect is not
  approval, and reviewers notice.
- **Agent Activity** — the audit trail as a product surface: steps, tools, inputs/outputs, duration,
  approval, result. This is the screen that proves the system is observable.
- **Dashboards** — task success, latency p50/p95, cost per run, tool failure rate, feedback.

## Checklist

- [ ] Uses existing design tokens and components
- [ ] Loading / empty / error states
- [ ] Keyboard accessible, labelled, AA contrast
- [ ] Responsive
- [ ] No secret or internal id leaked into the client bundle
- [ ] `npm run build` and `npm run lint` pass
- [ ] Verified in a real browser (Playwright MCP, if installed) — not assumed
