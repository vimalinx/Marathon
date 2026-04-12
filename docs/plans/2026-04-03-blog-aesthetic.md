# Core Web UI Design: The Editorial Aesthetic (2026-04-03)

## Theme & Objective
Re-skin the entire `Marathon Core` Local Operator Console (`host/static/*`) to feel like a high-end personal publishing platform or an intimate developer logbook, instead of a traditional corporate IT dashboard.

## Scope
- Global redesign of `app.css`.
- Layout migration of `index.html`, `new.html`, `agents.html`, `sandboxes.html` into the unified `container-blog-page` paradigm, which previously only existed on `container.html`.

## Constraints & Invariants Preserved
- No functional changes to the application routing or underlying system calls.
- Preserved complete boundary separation from `Marathon Site` (public site projection remains unaffected in `host/static/site/`).
- Maintained responsive structure where needed but sticking to a "desktop-first" priority as per constraints in `AGENTS.md`.

## Key Aesthetic Directions
1. **Typography First**: Heavy usage of readable max-width columns (e.g. `1180px` max, `760px` reading column), sans-serif (Inter, Avenir Next) for UI, and high-contrast styling for headings vs body copy.
2. **"Paper" Containers**: Removing tight grey borders in favor of soft elevated shadows and pale creamy/off-white backgrounds (`#f5f1e8` or similar "parchment/canvas" tones) that feel welcoming.
3. **Micro-animations**: Subtle hover lifts, color transitions (140ms ease) on cards and buttons.  
4. **Rich Form Controls**: Form fields that feel like inline textual elements rather than thick boxed inputs when possible, or elegantly styled input blocks with soft focus rings.

## Implementation Steps
This design will be executed in a single pass over `app.css` and the `.html` structural files. Verification involves manually inspecting the UI against local Python server.
