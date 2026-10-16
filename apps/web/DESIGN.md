# Design

<!-- impeccable:design-schema 1 -->

> **Author's note (Impeccable new-work substitution).** Written from
> [PRODUCT.md](PRODUCT.md) and the brand constraints already recorded in
> [specs/002-web-ui/spec.md](../../specs/002-web-ui/spec.md). No separate concept-seed
> round was dealt; the brand commitments pin the world tightly enough that a tournament
> would have been performative. If any item below conflicts with the brand owner's own
> guide, replace the token in `src/design/tokens.ts` — do not rework the components.

## 1. World

**Mode**: operate (chat, queue, forms, admin). The site this UI inherits from
(`site.getnet.com.br`) is marketing, so its vertical rhythm, hero banners and large product
tiles do not translate. We keep the signature red, the sharp lower-case headings and the
8 px shape vocabulary, and we invent everything the site has no analogue for (chat
transcript, agent-step badges, operator queue, pending-action approval dialog, admin tables).

**Posture**: calm and factual. Dense but not cramped. Red is the signal colour, used for
state (handoff open, error) and for the single primary action per screen; never as
decoration. **Shadows are low**: this is a working surface, not a card gallery.

## 2. Tokens

The single source of truth is `src/design/tokens.ts`. The Tailwind config is generated from
it; `features/**` can never import a Tailwind utility that encodes a raw colour. These
tables mirror the exported values.

### Colour

A 7-step neutral ramp plus two accents (brand and support). Each token documents the one
job it has.

| Token          | Hex       | Job                                                       |
|----------------|-----------|-----------------------------------------------------------|
| `color.brand`             | `#EC0000` | Primary action, selected tab, destructive confirmation.  |
| `color.brand.hover`       | `#D00000` | Hover of a brand element.                                 |
| `color.brand.pressed`     | `#B40000` | Pressed state.                                            |
| `color.brand.soft`        | `#FBE4E4` | Tag or badge background to signal brand state.           |
| `color.support`           | `#005CB9` | Informational accent (links, info banners). Rare.         |
| `color.ink.900`           | `#111318` | Headings.                                                 |
| `color.ink.700`           | `#282828` | Body text.                                                |
| `color.ink.500`           | `#454C52` | Secondary text, labels.                                   |
| `color.ink.400`           | `#66707A` | Captions, timestamps.                                     |
| `color.surface.100`       | `#FFFFFF` | Page background.                                          |
| `color.surface.200`       | `#F5F7FA` | Card background, resting input.                           |
| `color.surface.300`       | `#E1E6EB` | Divider, muted button.                                    |
| `color.state.success`     | `#117A2B` | "resolved" status.                                        |
| `color.state.warning`     | `#B45309` | "awaiting_human" and SLA warnings.                        |
| `color.state.danger`      | `#B40000` | Error banner, "expired" status.                           |

Dark mode is intentionally **not** shipped in this release. The chat is a working
surface; a theme switch is a distraction without a confirmed user demand (recorded under
"Open decisions" in PRODUCT.md).

### Typography

Inter, with the native stack as fallback. Four roles cover every screen:

| Role          | Size (px) | Line  | Weight | Used for                                |
|---------------|-----------|-------|--------|-----------------------------------------|
| `display`     | 28        | 36    | 700    | Page title (login, admin landings).     |
| `heading`     | 20        | 28    | 600    | Section header, dialog title.           |
| `body`        | 15        | 24    | 400    | Default running text, chat messages.    |
| `label`       | 13        | 20    | 500    | Form labels, badge text, timestamps.    |

Tabular numbers are enabled by default in `label` so queue timers and prices do not jitter.

### Spacing

A single 4 px step, exposed as `space.1` through `space.10`. Component spec never mixes
scales; `space.3` (12 px) is the base gutter and `space.4` (16 px) is the default stack rhythm.

| Token | px | Where it shows up                                         |
|-------|----|-----------------------------------------------------------|
| `space.1` | 4  | Icon ↔ text inside a button.                          |
| `space.2` | 8  | Gap between adjacent form controls.                    |
| `space.3` | 12 | Gutter inside cards and dialogs.                       |
| `space.4` | 16 | Default stack rhythm (vertical gap between blocks).    |
| `space.6` | 24 | Section rhythm.                                        |
| `space.8` | 32 | Page gutters on mobile.                                |
| `space.10`| 40 | Page gutters on desktop.                               |

### Radius

| Token | px | Jobs                                                        |
|-------|----|-------------------------------------------------------------|
| `radius.sm` | 4  | Inline tags, keyboard chips.                           |
| `radius.md` | 8  | **Default**. Buttons, inputs, cards, dialogs.          |
| `radius.lg` | 12 | Chat bubbles.                                          |

### Elevation

Working surface posture: two shadows, never more.

- `shadow.1`: `0 1px 2px rgba(17, 19, 24, 0.08)`. Resting cards, chat bubble.
- `shadow.2`: `0 8px 24px rgba(17, 19, 24, 0.12)`. Dialog, popover, overflow menu.

### Motion

- `motion.duration.fast`: 120 ms. Button hover, chip selection.
- `motion.duration.slow`: 220 ms. Dialog open, toast enter/exit.
- `motion.ease.standard`: `cubic-bezier(0.2, 0, 0, 1)`.

All motion respects `prefers-reduced-motion`: components fall through to a 1 ms crossfade.

### Focus

A single, unmistakable focus ring on every interactive element: 2 px solid
`color.support` with a 2 px outer offset against the current background. **Never** removed.

## 3. Composition rules

- **One primary action per screen.** The brand red is reserved for it.
- **One intent per screen.** No sidebar nav on the lojista's chat — the goal is to answer
  the question, not to tour the app.
- **Density scales with role.** The operator queue is denser than the lojista's chat; both
  obey the 4 px step.
- **Status is always a label plus a colour**, never only a colour (WCAG 2.2 AA, SC-005).
- **Numbers are tabular** everywhere they count — queue timers, retry-after countdowns, SLA
  minutes.
- **No icon-only buttons** (SC-005 again). Every icon carries a visible label or an
  `aria-label`, and every label can stand alone.

## 4. Patterns

### Button

Three sizes (`sm`, `md`, `lg`) × three intents (`primary`, `secondary`, `ghost`). Minimum
hit area 44×44 px on mobile. Loading state is a spinner on the left of the label, with the
label kept visible so the width does not jump.

### Input

Label stacked above, 2 px underline for the field edge, help text below (truncated at
80 chars). Error state swaps the help text for an error message and tints the underline red
without touching the label colour.

### Dialog

Centred on desktop, bottom sheet on mobile widths (< 480 px). Scrim is `rgba(17, 19, 24, 0.5)`
on light surfaces. First focusable element gets focus on open; Esc closes; the trigger gets
focus back on close.

### Toast

Lives in a single bottom-left region. Three variants (`success`, `warning`, `danger`), each
with an ARIA role (`status`, `status`, `alert`). Auto-dismiss at 5 s, pausable on hover and
on focus.

### Chat message

Lojista bubble on the right (ink text on `surface.200`), assistant on the left (ink text on
`surface.100` with a 1 px `surface.300` border). Agent-step badges stack vertically above
the assistant message as small `label` chips (`space.1` gap). Fonte list is a plain list
below the message, each item linking to the source URL in a new tab with `rel="noopener"`.

### Handoff banner

Pinned above the input. States map to the backend events:

- `awaiting_human` — soft brand background, badge label "aguardando atendente", a ticker
  shows the remaining SLA.
- `sla_breached` — warning foreground, label "atendimento está demorando", the ticker
  switches to "+N min atrasado".
- `resolved` — success tint, label "respondido", stays for 10 s then collapses.
- `expired` — danger tint, label "encerrado por tempo", suggests sending a new message.

### Queue row (operator)

One row = one ticket. Columns: priority chip (`high`/`normal`), reason label, SLA ticker,
summary (truncated at 80 chars), merchant mask. Hover reveals a "abrir" button that is
focusable from the keyboard without hover.

## 5. Accessibility floor

- Every interactive element has a visible, 3:1 contrast focus ring (see Focus token).
- Text contrast ≥ 4.5:1 for `body` and `label` on every surface token.
- Minimum touch target 44×44 px on mobile, 32×32 px on desktop.
- No animation forced on `prefers-reduced-motion`.
- Live regions on SSE arrivals: `aria-live="polite"` for a new assistant message, `assertive`
  for a `sla_breached` or `handoff_expired` event.
- Lang attribute follows the UI language; the response from the agent carries its own
  `lang` on the message element so a screen-reader can switch voice if the merchant asked
  in English.

## 6. Open items the designer should resolve next

Each of these is a design question we can answer later without touching components:

- Admin table design (dense or airy). Current default is dense.
- Dark mode (not shipped; see Colour).
- Illustration style for empty states. Current fallback is a muted glyph + one-line copy.
- Favicon beyond the current PNG placeholder (`apps/web/public/brand/favicon.png.readme`).
