# Product

<!-- impeccable:product-schema 1 -->

> **Author's note (Impeccable init substitution).** Fields below were lifted from
> [specs/002-web-ui/spec.md](../../specs/002-web-ui/spec.md) and from the user's explicit
> brief ("UI com login e senha, usando a identidade visual da Getnet", confirmed through
> `/speckit.clarify`). No separate init interview was run; items marked **(inferred)** come
> from the spec, not a direct answer in this session.

## Platform

web

## Stack

React 18 + Vite 5 + TypeScript strict, served by nginx inside the project's existing
`docker-compose.yml`. The backend (FastAPI + LangGraph) is reused from the 001 feature; the
UI only adds a thin accounts / sessions layer. Playwright drives end-to-end tests; Vitest +
Testing Library drive component tests.

## Users

Three audiences share the same application; the role in the signed-in session decides which
screens they see.

- **Lojista** (primary). The Getnet merchant using a card machine or online checkout. Jobs:
  ask about a product (fees, receivables advance, link de pagamento), check the state of a
  terminal or an unpaid settlement, talk to a human when the automated answer is not enough,
  review a past conversation, keep the account under control (reset password, delete data).
  Context: at a store counter, often on mobile, sometimes between other tasks.
- **Operador**. The human handler of the escalated conversations. Jobs: see the queue ordered
  by priority and SLA, open a ticket with its summary and context, reply, approve or reject
  a pending action (open_dispute). Context: at a desk, several concurrent tickets, keyboard
  heavy.
- **Admin**. The platform operator. Jobs: invite operators and other admins, link a merchant
  account to a seeded establishment, deactivate an account, read the queue overview and the
  audit log. Context: desk; rare use but high-stakes actions.

## Product Purpose

Give a merchant immediate answers through the Getnet multi-agent system of the 001 feature,
and give operators and admins the tools to supervise and intervene when the AI delegates
back to a human.

Success is three measurable outcomes already recorded in `spec.md`:

1. A merchant goes from zero to the first useful answer in under 3 minutes, including the
   e-mail confirmation (SC-001).
2. The first agent_step reaches the chat within 1 s of the message being sent; an operator's
   reply reaches the merchant within 5 s (SC-002).
3. Zero cross-role or cross-user data access in the full test matrix (SC-004).

## Positioning

Most AI support surfaces either hide the automation (and lose trust the first time it is
wrong) or expose it unfiltered (and overwhelm the user). This UI shows **just enough of the
agent reasoning for the merchant to trust the answer**: the agent_step badges tell them which
specialist is on the question, the sources panel shows the Getnet pages the answer is drawn
from, and the handoff banner makes the transition to a human visible without the merchant
having to ask again. **(inferred)**

## Content

- The chat response, agent_step events and sources come from the 001 backend. The UI
  renders them as text (`textContent`) regardless of what the model emitted — no markdown,
  no HTML parsing — because the message channel is also a trust boundary (FR-012).
- All UI copy is bilingual (pt-BR primary, en secondary; FR-029). The automated answer still
  follows the merchant's message language, as the 001 already does.

## Voice

Direct, calm, practical. Short sentences. No marketing adjectives. Error states tell the
user what the next action is, not what the system did wrong. **(inferred)**

## Operating Context

- Browsers: last two versions of Chrome, Edge, Firefox, Safari — desktop and mobile.
- Minimum viewport: 360 px wide, no horizontal scroll required (SC-007).
- Streaming is Server-Sent Events over the same origin via nginx (research §8), so a modern
  browser with cookies and JS is required; the UI does not pretend to work without them.
- Network: production assumes HTTPS; local dev runs over http://localhost (session cookies
  degrade to `Secure=false` only in dev).

## Accessibility commitments

- WCAG 2.2 AA across every page (SC-005).
- Keyboard-first operator queue (operator jobs favour speed).
- SSE arrivals are announced via a polite ARIA live region, so a screen-reader hears each
  agent_step and the final answer.
- Error states always carry a visible message, never only a colour change.

## Internationalisation

Portuguese (pt-BR) is the default and the UI language the user picks is persisted in the
account. English (en) is the only alternate. The spec explicitly scopes other languages out
(spec.md Assumptions).

## Brand commitments

The visual world is a limited redesign anchored on the public Getnet offers page
(`site.getnet.com.br/ofertas/`), the same site the RAG index crawls. Decisions below are
**commitments**, not preferences; the surface brief in DESIGN.md expands them.

- **Signature colour**: `#EC0000` (the Getnet red observed on the site) is the brand accent.
  Text sits on neutral greys (`#282828`, `#454C52`, `#66707A`, `#E1E6EB`, `#F5F7FA`).
- **Logo**: the Getnet PNG from the public site is bundled at
  `apps/web/public/brand/logo-getnet.png` and attributed in `NOTICE.md`. Usage is scoped to
  this challenge; the file is replaced with a brand-owner version before any public
  deployment.
- **Type**: the Getnet site uses the proprietary Santander family. We **cannot** embed it,
  so Inter (SIL OFL) stands in. The substitution is explicit, not silent. **(inferred)**
- **Shape**: 8 px rounded corners are the default radius, matching the dominant value on
  the Getnet site.
- The redesign preserves product truth; it does not try to clone the Getnet marketing site
  pixel-for-pixel because the site has no analogue for chat, queues or admin forms.

## Legal and licence posture

- The Getnet logo is a third-party asset, licensed to its owner. See
  [apps/web/NOTICE.md](NOTICE.md) for the restrictive use scope and the Inter OFL note.
- The rest of this subproject is covered by the repository's top-level licence.
- No personal data of real customers is used; the demo seeds the DB with mock merchants.

## Evidence / Proof

The 001 feature already runs the agents, the sources panel, the HITL flow, and the RAG index
over the Getnet site. The UI only exposes those surfaces; it does not invent new product
claims. (The challenge brief is itself the proof the project needed: the whole repository
was built to pass it.) **(inferred)**

## Out of scope

- Social login, two-factor auth, SSO.
- Real e-mail provider; local dev uses Mailpit (FR-002a).
- Native mobile apps, admin skins per merchant, user-defined branding.
- Multi-tenant isolation beyond the one merchant ↔ one account constraint (FR-021).

## Open decisions

- The brand owner may replace `logo-getnet.png` with an SVG without touching any screen.
- The admin seed e-mail defaults to `admin@getnet.local` and the password is generated once
  by `scripts/create_demo_admin.py` and shown on stdout; a different convention is a
  configuration change, not a code one.
- An EN seed of the Getnet site does not exist yet (R-17 of the 001 research). PT remains the
  primary surface language and the automated answer bridges EN questions back to PT content.
