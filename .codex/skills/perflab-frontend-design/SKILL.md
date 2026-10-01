---
name: perflab-frontend-design
description: Design, implement, or review PerfLab frontend pages and components using the project's quiet, data-dense observability-console design system. Use for changes under frontend/ that affect layout, visual styling, navigation, forms, tables, charts, feedback, responsiveness, or theming.
---

# PerfLab Frontend Design

Create a precise engineering console for comparing AI-system performance. Take cues from Langfuse's restrained observability UI—semantic tokens, compact information architecture, thin borders, neutral surfaces, and lucid data views—without copying its branding or page layouts.

## Product character

Use the visual direction **Quiet Observatory**:

- Calm, technical, and trustworthy; never promotional or futuristic.
- Dense enough for repeated operational use, but grouped so the eye can scan quickly.
- Light theme is the primary art direction; dark theme has equal semantic contrast.
- Neutral surfaces carry the layout. Cobalt identifies the primary action or current focus, not every interactive element.
- Data, status, and comparison are the visual interest. Avoid decorative gradients, glows, glass effects, oversized type, and dashboard-card wallpaper.

## Before changing UI

1. Inspect the relevant component and the shared styles in `frontend/src/index.css`.
2. Preserve product behavior, API payloads, localization, and ECharts semantics unless the request explicitly changes them.
3. Read [references/visual-system.md](references/visual-system.md) before a material styling or theming change.
4. For a page, navigation, form flow, table, or dashboard change, also read [references/page-patterns.md](references/page-patterns.md).
5. Prefer extending shared primitives/tokens over adding page-local visual exceptions.

## Core interface rules

- Use a persistent, compact left navigation on desktop and a deliberate mobile navigation treatment; do not turn the sidebar into a decorative brand panel.
- Page headers state the task in one line. Put context, filters, and the primary action alongside or immediately below the title.
- Prefer one dominant content plane. Use bordered sections, tables, and split panes instead of nesting many floating cards.
- CRUD index pages use a toolbar plus table/list. Creation and editing belong in a modal, side sheet, or focused detail pane; do not reserve half the page for an empty form.
- Use sentence case in Chinese and English UI. Do not use repeated uppercase eyebrow labels as the main hierarchy.
- Use a consistent vector icon family. Prefer Lucide when an icon dependency is in scope; never use Unicode symbols or emoji as structural icons.
- Keep controls compact: 32 px utility controls, 36 px standard inputs/buttons, 40–44 px data rows. Preserve at least 44 px hit areas for icon-only controls where touch use is plausible.
- Use tabular numerals for metrics and monospace only for IDs, endpoints, code, and log content.
- Use color with a second cue: status dot + label, icon + message, or line style + legend. Color alone is insufficient.

## Implementation boundaries

- Keep the current React + Vite + TypeScript + Tailwind v4 + ECharts stack.
- Do not introduce a component framework merely to imitate Langfuse. Small reusable primitives are preferable to a wholesale migration.
- Use semantic CSS custom properties. Components must not introduce raw theme colors when a semantic token exists.
- Keep charts driven by the shared chart palette and theme tokens; do not independently hard-code light/dark chart colors.
- Motion is functional and subtle: 120–180 ms color/opacity transitions, no layout-shifting hover transforms, and respect `prefers-reduced-motion`.
- Preserve keyboard focus, native semantics, labels, disabled behavior, loading feedback, and screen-reader names.

## Required verification

For implementation work:

1. Run `npm run build` from `frontend/`.
2. Inspect the changed flow in both light and dark themes.
3. Check at approximately 1440 px, 1024 px, 768 px, and 375 px widths.
4. Verify empty, loading, success, warning, error, disabled, hover, focus, and selected states that the changed surface supports.
5. Confirm dense data remains readable without horizontal clipping; tables may scroll when preserving columns is more useful than collapsing them.
6. Compare the result against the anti-patterns in the visual-system reference before delivery.

## Design intent test

The result should feel like a serious instrument an engineer can leave open all day: quiet at rest, explicit under failure, fast to scan, and rich only where the data demands it.
