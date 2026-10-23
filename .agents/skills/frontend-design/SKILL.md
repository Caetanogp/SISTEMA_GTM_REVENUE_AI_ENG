---
name: frontend-design
description: Apply Anthropic's Frontend Design guidance when building or substantially changing UI, pages, dashboards, or components. Pair it with this repository's frontend-screen playbook and product design brief.
---

# Frontend Design (Codex adapter)

Use the vendored Anthropic skill at `.claude/skills/frontend-design/SKILL.md` as the visual-design method. Then read and follow `docs/playbooks/frontend-screen.md`, which contains this product's approved design direction and implementation constraints.

The product brief and user instructions take precedence over generic aesthetic suggestions. Do not re-ask the product owner to confirm the already stated minimalist direction. Treat reversible choices of color, typography, spacing, and layout as design work within that brief; ask only when a missing decision would change product scope or user-visible behavior.

Before implementing a new substantial screen, briefly define its purpose, audience, design direction, and key layout. Then build, inspect the rendered result when a browser is available, and verify accessibility, responsive behavior, and required UI states.
