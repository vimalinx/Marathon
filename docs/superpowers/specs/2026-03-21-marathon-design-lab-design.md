# Marathon Design Lab Frontend Design

## Goal

Build a separate frontend experiment space for Marathon that compares multiple UI/UX directions for the host-side observation console without destabilizing the current Web UI.

The first iteration should provide:

1. A dedicated `design-lab` surface alongside the existing host Web UI.
2. Three design variants that present the same Marathon experiment data with different visual and interaction philosophies.
3. A consistent comparison flow so the user can inspect the same run through each variant and choose a winning direction.
4. A UI structure that emphasizes Marathon's real product goal: observing autonomous AI behavior and especially self-modification inside the experiment runtime.

## Current Problem

The current host Web UI is useful as an operational panel, but it is not yet a settled product interface for Marathon's core use case.

Today there are four practical gaps:

1. The current screen mixes container operations and observation into one interface, which makes the product identity less clear.
2. There is no safe place to explore multiple UI directions without directly rewriting the existing console.
3. The current presentation does not make AI self-modification the most visually important event, even though that is one of Marathon's primary research goals.
4. There is no structured way to compare multiple design approaches against the same underlying experiment data.

## Product Context

Marathon's primary mode is not task execution. Its primary mode is open self-play inside a constrained runtime.

For the first product line:

- the host side is the stable control and observation plane
- the runtime instance is the autonomous experiment zone
- the UI should optimize for observing what the AI is doing, what it changed, and whether it has started changing itself

This means the frontend should behave more like an experiment observation console than a generic devops dashboard or a ticket execution panel.

## Non-Goals

This iteration will not:

- replace the existing `host/static/index.html` production UI
- redesign Marathon around task-first workflows
- add a live skill runtime that dynamically generates pages on demand
- integrate Figma or Penpot as a required runtime dependency
- build a multi-model benchmark dashboard
- redesign host-nightly mode, container orchestration, or model execution behavior

## Recommended Approach

Add a separate `design-lab` frontend area that is intentionally experimental and comparison-oriented.

This lab should keep the current host UI untouched while introducing three distinct design variants that all consume the same Marathon data model.

Recommended variant set:

1. `design-consultation` inspired variant
   Positioning: experiment observation console
2. `ui-ux-pro-max` inspired variant
   Positioning: polished high-end product control cockpit
3. `penpot-uiux-design` inspired variant
   Positioning: low-cognitive-load information architecture and workflow console

This keeps implementation scope clear:

- one shared data contract
- three static frontend variants
- one comparison index page
- one later selection step that chooses what should influence the main UI

## Skill Roles

The project should treat skills as design inputs with different responsibilities rather than pretending every skill is a page generator.

### Design-Generating Inputs

- `design-consultation`
- `ui-ux-pro-max`
- `penpot-uiux-design`

These inform the three variant pages.

### Design Review Inputs

- `plan-design-review`
- `design-review`

These do not need their own pages. Their job is to critique the variants, identify weaknesses, and help select or refine the winning direction.

### QA / Presentation Inputs

- `browse`

This is used to open and inspect the pages, not to define the design itself.

## Alternatives Considered

### 1. Replace The Existing Host UI Directly

Implement one new design directly in `host/static/index.html`.

This is faster in the very short term, but it makes comparison difficult and increases the chance of destabilizing the current operational console before the design direction is proven.

### 2. One Page With Theme Switching Only

Build one page and let the user switch between several theme presets.

This reduces implementation work, but it weakens the experiment. The real differences between the variants are not only colors or spacing; they include hierarchy, navigation, density, and which signals are emphasized.

### 3. Let External Skills Generate Pages At Runtime

Attempt to invoke skills dynamically and treat each as a runtime page generator.

This sounds flexible, but it is the wrong first step. It would mix skill execution, frontend generation, and product comparison into one unstable system. The first version should hand-build a clean comparison lab based on skill-inspired design directions.

## Design

### 1. Separate Design Lab Surface

Add a dedicated surface for design comparison instead of modifying the current host UI in place.

Recommended structure:

- `host/static/design-lab/index.html`
- `host/static/design-lab/design-consultation.html`
- `host/static/design-lab/ui-ux-pro-max.html`
- `host/static/design-lab/penpot-uiux-design.html`

The current root page `/` should remain the operational Web UI. The design lab is a separate experiment area that can be visited explicitly.

### 2. Shared Data Contract

All three variants must consume the same data so the comparison stays honest.

The first version should read from the existing host API surface:

- `GET /api/overview`
- `GET /api/containers/<name>`
- `GET /api/runs/<run_id>`

The lab should prefer existing payloads over inventing a new backend contract unless the current payloads cannot express a required observation concept.

Shared modules that every variant must show:

- current instance identity
- current runtime state
- current round summary
- recent round timeline
- latest command and tool output
- workspace change summary
- self-modification summary
- basic control actions such as refresh and navigation back to the main console

Variant context should be URL-addressable.

Recommended query model:

- `?run_id=<run_id>` when a concrete run is selected
- `?container=<name>` when only a container is selected

If both are present, `run_id` wins. This makes variant switching deterministic and keeps the comparison tied to one experiment context.

### 3. Variant Pages

Each variant should express the same information using a different design philosophy.

#### Variant A: Observation Deck

Inspired by `design-consultation`.

Intent:

- feel like a research console
- present the system as an active experiment
- emphasize chronology and causal understanding

Recommended layout:

- top summary strip with experiment identity and state
- central timeline and current round focus
- right-side self-modification and workspace change rail

This is the expected strongest candidate for the main Marathon UI because it best aligns with the product's research-first identity.

#### Variant B: Control Cockpit

Inspired by `ui-ux-pro-max`.

Intent:

- feel like a premium, high-confidence control surface
- present Marathon as a polished product
- emphasize status cards, strong visual state, and high readability

Recommended layout:

- strong top status band
- KPI-style cards for run state and recent activity
- large live feed area
- lower information trays for output and file changes

This variant is most useful for harvesting visual language and product polish.

#### Variant C: Flow Desk

Inspired by `penpot-uiux-design`.

Intent:

- minimize cognitive load
- make navigation and state progression obvious
- emphasize structured information flow rather than visual drama

Recommended layout:

- left-side lifecycle navigation
- center context panel for current state and timeline
- right-side detail inspector for output, diff, and self-modification

This variant is most useful for harvesting information architecture and task-mode compatibility.

### 4. Shared Interaction Flow

The comparison flow must stay consistent across variants.

Recommended user flow:

1. Open `design-lab/index.html`
2. Read a short explanation of the three variants
3. Pick a variant while keeping one specific Marathon instance or run in focus
4. Land on that variant's page with the same selected data context
5. Inspect first-layer information within a few seconds
6. Drill down into timeline, command output, and diffs
7. Switch to another variant without losing the selected instance or run context

The critical rule is: switching variants must keep the same underlying experiment context whenever possible. Otherwise the user ends up comparing different data, not different UI.

The preferred implementation is to preserve the selected context in the URL query string instead of keeping it only in transient client memory.

### 5. Information Prioritization

The first screen of each variant must answer these questions immediately:

- what instance am I looking at
- is it running, stopped, failed, or stalled
- what is the current or latest round trying to do
- what changed most recently
- has the AI started modifying itself

This means the UI should default to recent changes and active signals, not to static configuration.

### 6. Self-Modification As A First-Class Signal

Self-modification is not a normal diff and should not be visually buried in generic file changes.

The lab should explicitly track and highlight changes to:

- prompt files
- `agent_tools.py`
- `agent_loop.py`
- model configuration inputs when observable
- newly created helper scripts that materially extend the agent's capabilities

Recommended dedicated section name:

- `Self-Modification`
- or `Self-Evolution Events`

Required presentation layers:

1. high-level event badge
2. one-line summary of what changed
3. expandable before/after or diff view

Required summary indicators:

- most recent self-modification round
- total self-modification count for the current run
- most recent self-modification category such as prompt, tool, or loop

Detection should stay simple in the first version.

Recommended rule set:

- treat explicit tracked file targets as authoritative when they appear in run detail payloads or derived file-change summaries
- if only before/after state summaries are available, detect these target paths heuristically from the latest known workspace and runtime metadata
- do not attempt semantic code analysis in the first version

If the current API payloads are too weak to derive a trustworthy summary, add one minimal derived server-side field for the lab instead of inventing a large new persistence format.

### 7. Empty States

Empty states should explain what has not happened yet instead of displaying generic placeholders.

Required empty states:

- no instances available
- instance exists but run has not started
- run exists but no rounds completed yet
- no self-modification observed yet
- no recent output available yet

Each state should describe what the user is waiting for or what must happen next.

### 8. Error And Degradation States

The lab must remain legible when the experiment misbehaves.

Required degraded states:

- model request failure
- command execution failure
- stalled run with no fresh rounds
- destroyed or missing runtime instance
- self-modification followed by runtime breakage

These states should be expressed in experiment language rather than generic admin language. For example:

- `cognition link interrupted` for model connectivity failures
- `action failed` for command execution failures
- `experiment entity missing` for destroyed runtimes while logs still exist

Self-modification followed by failure should be treated as a highest-priority event because it is one of Marathon's most important research cases.

### 9. Comparison Index Page

The index page should not be a marketing landing page. It should be a comparison control surface.

It should include:

- a short explanation of the design-lab purpose
- three cards describing the variants
- direct entry into each variant
- the same selected run or container context carried forward
- a compact rubric for later review

Recommended rubric dimensions:

- clarity of current activity
- clarity of self-modification events
- readability under failure
- information density
- overall fit for Marathon's identity

### 10. Main UI Integration Boundary

The first version must not rewrite `host/static/index.html`.

Instead:

- build the design-lab as a sidecar experience
- choose a winning direction after review
- then selectively merge the strongest ideas into the main UI

This keeps operational risk low and lets the design comparison stay honest.

## Data Flow

1. User opens the design-lab index.
2. The frontend reads `GET /api/overview` to populate available containers, runs, and defaults.
3. The user selects or carries forward a target container or run.
4. The selected context is encoded into the URL query string.
5. A variant page loads with the selected context.
6. The variant fetches `GET /api/containers/<name>` and/or `GET /api/runs/<run_id>` as needed.
7. The page derives shared modules such as current status, recent timeline, output, workspace changes, and self-modification markers.
8. The user switches between variants while preserving the same context.

## File Impact

Expected changes for implementation:

- add `host/static/design-lab/index.html`
- add `host/static/design-lab/design-consultation.html`
- add `host/static/design-lab/ui-ux-pro-max.html`
- add `host/static/design-lab/penpot-uiux-design.html`
- modify `host/web_ui.py` to serve `design-lab` static assets
- optionally add a small shared frontend script or stylesheet under `host/static/design-lab/`

The current root UI file:

- `host/static/index.html`

should remain unchanged in the first iteration except for an optional link into the design lab.

## Testing Strategy

The first implementation should prioritize functional frontend validation and comparison readiness.

Minimum coverage:

1. Static routes for the design-lab pages are served correctly.
2. Each variant can load the same run or container context.
3. Variant switching preserves the selected context.
4. Empty states render correctly for missing data.
5. Error states render correctly for failed or missing run details.
6. Self-modification summaries are visually distinct from ordinary file changes.

Browser verification should be part of completion, not an optional afterthought.

## Risks

### Design Drift Across Variants

If each page invents its own information model, the comparison becomes meaningless. The fix is to lock the shared module list before implementation.

### Over-Building The Experiment Surface

It would be easy to turn the design-lab into a second full product UI. The fix is to keep it scoped to comparison, not feature expansion.

### Weak Self-Modification Detection

If self-modification is derived too loosely, the UI may over-highlight trivial changes or miss important ones. The first version should use explicit file targets and simple heuristics.

### Ambiguous Product Identity

A product-polish-heavy variant could make Marathon look like a general operations console instead of an autonomy lab. The winning direction should be selected based on product truth, not only on visual flash.

## Success Criteria

This change is successful when:

- the project has a separate design-lab surface that does not replace the current Web UI
- three variants can display the same Marathon experiment context
- the user can compare the variants against the same data without losing context
- self-modification is clearly more visible than ordinary file changes
- the team can confidently choose what should inform the next main UI revision

## Note On Git

The brainstorming workflow expects the spec to be committed, but the Marathon workspace at the time of writing is not a Git repository.

For this iteration the acceptable output is:

- spec written to `docs/superpowers/specs/`
- spec reviewed
- user review requested before implementation planning

If Marathon is later initialized as a Git repository, this workflow step should resume using normal commits.
