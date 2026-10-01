# PerfLab page and interaction patterns

## Application shell

Desktop:

- 232–248 px persistent sidebar with the PerfLab wordmark, grouped navigation, and bottom utilities.
- Active navigation uses a quiet accent background plus clear text/icon contrast; avoid a glowing indicator.
- Main content owns the page scroll. The top utility bar is 48–56 px and contains only page-global controls.
- Content width may reach 1440–1560 px for charts and tables. Text/forms use narrower internal measures.

Mobile/tablet:

- Collapse the sidebar into a sheet or compact top navigation; do not squeeze seven equal nav buttons into a single row.
- Preserve page title and primary action. Move secondary filters into a popover or collapsible filter row.
- Keep tables horizontally scrollable when comparisons depend on columns; pin the primary identity column when feasible.

## Page header

Structure:

1. Optional compact breadcrumb.
2. Page title and one-sentence context.
3. Right-aligned primary action and utilities.
4. Filter/query toolbar immediately below when the page is data-driven.

Avoid decorative English eyebrows above Chinese titles. Product nouns and concise descriptions are sufficient hierarchy.

## Overview / active run

- Put the currently selected run and its status in the page header or first section.
- Use a compact KPI strip for success rate, QPS, P95/P99, and elapsed time.
- Present live scenario progress as a table or structured timeline, not a loose collection of status chips.
- Place the most decision-relevant comparison chart first. Secondary distributions follow under tabs or a clearly titled analysis section.
- Keep cancel/delete actions separated from normal run inspection.

## New benchmark run

- Treat creation as a focused workflow with clear sections: workload → targets → concurrency → review/run.
- Prefer a single readable form column plus a sticky summary on wide screens.
- Show the expanded scenario count before submission.
- Progressive disclosure: only show Dify query/dataset fields for Dify modes, audio fields for audio, and model-specific controls where relevant.
- Primary action states what will happen, e.g. “Start 12 scenarios,” rather than a generic arrow.

## Playground

- Use a resizable or responsive split pane: request builder on the left, response inspector on the right.
- Response toolbar contains status, duration, copy, wrap, and expand controls.
- JSON/code content uses monospace with stable scrolling and a neutral code surface.
- Empty state tells the user to select a service and send a request. Errors remain in the response pane so request context is not lost.

## Run history

- Use a real data table with status, name, type, scenarios, success, duration, and time.
- Put search/filter/date controls in a compact toolbar.
- Clicking a row opens or selects the run. Destructive actions live in a trailing overflow menu or explicit confirmation flow.
- IDs are secondary monospace metadata, not the visual title.

## Provider and Dify configuration

- Default view is a searchable list/table of configurations with type, endpoint, credential state, and last validation state.
- Put “Add provider” or “Add Dify configuration” in the page header.
- Create/edit in a modal or right-side sheet at a readable width; use a full detail page only when one configuration contains many models/credentials.
- Group fields into identity, endpoint, model, and credentials. Explain whether an empty secret preserves the existing value.
- Validate inline and keep entered values after remote validation fails.
- Empty state is a compact bordered section with one explanation and one action, not a half-screen blank card.

## API documentation

- Prefer a full-bleed documentation workspace below the page header.
- Keep “Open in new window” as a secondary action.
- Avoid wrapping the iframe in multiple padded cards; the documentation is already a complete surface.

## Alerts, confirmations, and remote failures

- A failed save shows a field-level or form-level error inside the editor, close to the submit action.
- A page banner is reserved for cross-page or persistent service conditions.
- Error copy should name the target and likely recovery, e.g. “Dify redirected the site root. Enter the API host; PerfLab will probe `/v1/datasets`."
- Confirm destructive actions with the object's name and consequence.
- Loading actions disable only the affected controls and retain the surrounding context.

## Responsive checkpoints

### 1440 px

- Sidebar visible; dashboard charts may use two columns.
- Forms remain bounded; avoid stretching inputs across the full workspace.

### 1024 px

- Sidebar may remain compact; charts collapse when labels or legends become cramped.
- Sheets/modals must not exceed the viewport.

### 768 px

- Navigation transitions away from the persistent sidebar.
- Page actions wrap intentionally; toolbars may become two rows.

### 375 px

- One primary column.
- Inputs and primary actions fill available width.
- No essential action depends on hover.
- Tables scroll rather than destroying column meaning.

## Review checklist by surface

For each changed page, verify:

- hierarchy is visible in grayscale;
- primary action is unique;
- empty space communicates grouping rather than unfinished layout;
- every icon has one meaning and one style;
- every status has text as well as color;
- error and loading states preserve user input;
- keyboard order matches visual order;
- light and dark themes express the same surface hierarchy;
- dense data remains legible at 100% browser zoom and 200% text zoom.
