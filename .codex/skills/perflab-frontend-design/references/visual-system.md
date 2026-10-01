# PerfLab visual system

## Direction: Quiet Observatory

PerfLab is a benchmarking instrument, not an AI marketing site. The interface should borrow the discipline of modern observability tools: restrained chrome, compact controls, stable geometry, strong data hierarchy, and semantic feedback.

Reference Langfuse at the level of principles:

- semantic shadcn-style theme roles rather than page-specific colors;
- neutral application shell and low-contrast dividers;
- data tables, filter bars, tabs, sheets, and charts as the core vocabulary;
- small typography with clear weight contrast;
- contextual actions revealed near the object they affect;
- dark and light themes derived from the same semantic roles.

Do not copy Langfuse branding, logo, proprietary layouts, or exact colors.

## Design dials

| Dial | Value | Consequence |
| --- | ---: | --- |
| Density | 8/10 | Compact toolbars, 36 px controls, 40–44 px rows |
| Visual variance | 3/10 | Repeated, predictable geometry; few hero moments |
| Motion | 3/10 | Short state transitions only |
| Decoration | 1/10 | No ambient gradients, glow, glass, or ornamental graphics |
| Contrast | 7/10 | Crisp content and focus; quiet secondary chrome |

## Token architecture

Use three layers where practical: primitive values → semantic roles → component aliases. Components consume semantic or component tokens, never primitives directly.

Recommended semantic roles:

```css
--background;
--foreground;
--surface;
--surface-subtle;
--surface-raised;
--muted;
--muted-foreground;
--border;
--border-strong;
--input;
--ring;
--primary;
--primary-hover;
--primary-foreground;
--accent;
--accent-foreground;
--success;
--success-subtle;
--warning;
--warning-subtle;
--destructive;
--destructive-subtle;
--info;
--info-subtle;
--chart-1 through --chart-6;
--sidebar;
--sidebar-foreground;
--sidebar-accent;
--sidebar-border;
```

### Light theme target

Use nearly neutral, slightly cool surfaces. The background and card should be visibly distinct without blue-tinted panels everywhere.

| Role | Target |
| --- | --- |
| App background | `#f8f9fb` |
| Main surface | `#ffffff` |
| Subtle surface | `#f3f4f6` |
| Raised surface | `#ffffff` |
| Primary text | `#171a21` |
| Secondary text | `#626977` |
| Border | `#e1e4e9` |
| Strong border/input | `#cbd0d8` |
| Primary cobalt | `#3157c8` |
| Primary hover | `#2848aa` |
| Focus ring | cobalt at visible 35–45% alpha |

### Dark theme target

Avoid navy gradients. Use a neutral graphite stack with slightly cool text.

| Role | Target |
| --- | --- |
| App background | `#111318` |
| Main surface | `#171a20` |
| Subtle surface | `#1d2129` |
| Raised surface | `#20242c` |
| Primary text | `#eef0f4` |
| Secondary text | `#9aa1ad` |
| Border | `#2a2f38` |
| Strong border/input | `#3a414d` |
| Primary cobalt | `#7896f5` |
| Primary hover | `#91a9f8` |

Exact values may be adjusted for contrast, but preserve the neutral hierarchy.

## Typography

- UI family: `Inter`, followed by the current CJK-safe system stack.
- Data/code family: `JetBrains Mono`, `SFMono-Regular`, `Consolas`, monospace.
- Default body: 13 px / 20 px on dense desktop surfaces; 14 px where reading length increases.
- Page title: 20–24 px, weight 600, tight but not display-like.
- Section title: 14–16 px, weight 600.
- Label and table header: 12 px, weight 500–600.
- Metadata: 11–12 px with adequate contrast; never use tiny low-contrast text to simulate sophistication.
- Metrics: 24–30 px with `font-variant-numeric: tabular-nums`; avoid bolding every value.
- IDs and endpoints use monospace and may truncate with a discoverable full-value affordance.

## Geometry and depth

- Base spacing unit: 4 px. Common gaps: 4, 8, 12, 16, 24, 32.
- App gutter: 24–32 px desktop, 16–20 px tablet, 12–16 px mobile.
- Radius: 6 px controls, 8 px cards/panels, 10 px dialogs. Pills only for filters, tags, and statuses.
- Borders: 1 px. Dividers and row boundaries do most of the grouping.
- Shadows: none for inline cards; a restrained shadow only for menus, dialogs, popovers, and sheets.
- Avoid large rounded white rectangles floating on tinted backgrounds. A page should read as one workspace, not a collection of tiles.

## Iconography

- Use one Lucide outline style with a consistent 1.5–2 px stroke.
- Sizes: 14 px inline, 16 px controls/navigation, 18 px top-level utility, 20 px only when visually isolated.
- An icon-only button needs an accessible label and a minimum 32 px visual box / 44 px hit target where touch applies.
- Do not use `◈`, arrows as text, globe characters, or emoji for application navigation and status.

## Components

### Buttons

- Primary: one per action cluster; cobalt fill, white text, subtle hover darkening.
- Secondary: surface fill or transparent with border.
- Ghost: no border until hover; use for row actions and toolbars.
- Destructive: neutral by default for low-risk row actions, red only on hover or confirmation; solid red reserved for confirmed destructive action.
- No gradients, glow, oversized text, or arrow glyph decoration.

### Inputs and selects

- Standard height 36 px; labels above, help/error below.
- Surface matches the main plane; border supplies affordance.
- Focus uses border + ring, not a color fill.
- Passwords, endpoints, IDs, and API keys receive concise contextual help.
- Validation stays near the field. A page-level alert summarizes only when multiple fields or a remote operation fail.

### Tables and lists

- Use tables for comparable repeated records and lists only for heterogeneous summaries.
- Header height about 36 px; row height 40–44 px.
- Sticky headers are appropriate for long result sets.
- Hover uses `surface-subtle`; selection adds a slim cobalt indicator or quiet accent background.
- Keep row actions at the end, normally ghosted until hover/focus while remaining keyboard reachable.

### Cards and panels

- Cards are for metrics or self-contained visualizations, not every section.
- Header, body, and footer align to a shared inset.
- Avoid card-in-card nesting. Use dividers, tabs, or split panes inside a panel.
- Empty panels should be compact unless the empty state is the page's primary onboarding task.

### Feedback and status

- Success, warning, error, and info each use icon/dot + text + subtle semantic background.
- Status badges are compact and quiet; running may animate only a small indicator.
- Errors should explain what happened and the next action. Avoid giant dark banners dominating the workspace.
- Toasts are for transient completion; persistent or actionable failures remain inline.
- Skeletons preserve final geometry. Spinners are for local indeterminate actions, not whole-page waiting.

## Data visualization

Use charts as analytic instruments:

- Palette order: cobalt, teal, violet, amber, rose, sky. Each series stays consistent across charts.
- Grid lines are low contrast; axis labels are readable; chart furniture never competes with the data.
- Line width around 2 px. Show point symbols on hover or when sparse, not on every dense sample.
- Tooltips use the raised surface, border, tabular numbers, and aligned label/value columns.
- Legends are compact and interactive when hiding a series helps comparison.
- Use semantic colors only for semantic data. Do not make the first arbitrary series green or red.
- Avoid gradients, 3D effects, heavy area fills, and rainbow palettes.
- Provide a useful empty explanation and preserve accessible chart labels.

## Motion

- Hover/focus/color transitions: 120–160 ms.
- Dialog/sheet enter: 160–200 ms; exit slightly faster.
- Progress may interpolate width, but do not fake progress.
- Avoid springy cards, scale-on-hover, parallax, or animated page decoration.
- Under `prefers-reduced-motion`, remove nonessential transitions and all pulsing except essential live-status indication.

## Anti-patterns

- Blue-on-blue or cyan-on-navy as the entire brand expression.
- Radial/mesh gradients behind the application.
- Glassmorphism, neon glow, and translucent cards.
- Uppercase tracking labels above every heading.
- Huge empty cards and permanent editor panels on CRUD pages.
- Emoji or Unicode symbols as icons.
- Every card having a shadow, every state having a colored border, or every control having a filled background.
- Low-contrast gray labels on light blue surfaces.
- Marketing-sized headings inside an operational dashboard.
- Adding shadcn wholesale without a component migration need.

