# Desktop Home And Journal Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rework the desktop homepage into a compact cover layout and convert the container journal into a collapsible round timeline.

**Architecture:** Keep the existing static HTML + client-side render model. Adjust homepage card rendering inside `dashboard.js`, reshape the container round renderer in `container.js`, and update shared desktop styling in `app.css` to support clickable cards, clamped card copy, and the new round timeline presentation.

**Tech Stack:** Static HTML, vanilla JavaScript, shared CSS, Python unittest smoke checks, local browser verification.

---

### Task 1: Lock in the desktop-facing static copy

**Files:**
- Modify: `host/static/index.html`
- Modify: `host/static/container.html`
- Test: `tests/test_web_ui.py`

**Step 1: Update homepage section copy**

- Keep the existing structure and ids.
- Adjust the section copy so the page reads like a desktop browsing cover instead of a raw console dashboard.

**Step 2: Update container page journal copy**

- Replace the long-form “每一轮按博客文章方式堆在这里” language with timeline language.
- Keep `blogList`, `traceList`, and other existing anchors used by JS.

**Step 3: Update static HTML tests**

Run:

```bash
python3 -m pytest tests/test_web_ui.py -k "StaticHtmlContentTests" -q
```

Expected: tests should pass after the copy changes.

**Step 4: Skip commit**

This workspace is not a Git repository. Do not try to commit.

### Task 2: Rebuild homepage cards into compact clickable cover cards

**Files:**
- Modify: `host/static/dashboard.js`
- Modify: `host/static/app.css`

**Step 1: Add clickable whole-card behavior**

- Make featured cards and regular browser cards navigate to `/container?container=...` when the user clicks empty space on the card.
- Keep nested links working for “基于此新建”.

**Step 2: Reduce homepage card payload**

- Featured cards should only show:
  - container name
  - status chips
  - one compact summary
  - one compact next-step teaser
  - a short metadata footer
- Browser cards should show:
  - container name
  - status chips
  - one short summary
  - one short next-step teaser
  - metadata footer

**Step 3: Restyle desktop card layout**

- Replace horizontal featured scrolling with a stable two-column desktop grid.
- Add card hover/focus styling.
- Clamp teaser copy to keep card heights stable.

**Step 4: Verify homepage manually**

Run:

```bash
./scripts/start_web_ui.sh --foreground
```

Then verify in browser automation that:

- featured cards stay compact
- browser cards stay compact
- clicking a card enters the container page

### Task 3: Convert container journal into a collapsible round timeline

**Files:**
- Modify: `host/static/container.js`
- Modify: `host/static/app.css`

**Step 1: Replace long stacked post rendering**

- Render each post as a round timeline entry.
- Latest post opens by default.
- Older posts stay collapsed by default.

**Step 2: Keep structured round content**

- Collapsed state shows round label, timestamp, run id, status, and a one-line preview.
- Expanded state shows the existing `Done / Next / Thought` blocks.
- Keep raw command/stdout/stderr inside nested details.

**Step 3: Add timeline styling**

- Introduce a visual rail/marker structure.
- Add an explicit end marker at the end of the list.
- Keep the existing paper-like palette.

**Step 4: Verify container page manually**

- Open a container with many rounds.
- Confirm latest round is open, older rounds are collapsed.
- Confirm the page has a clear start/end rhythm instead of a continuous long article.

### Task 4: Run regression checks

**Files:**
- Modify: `tests/test_web_ui.py`

**Step 1: Run static UI tests**

Run:

```bash
python3 -m pytest tests/test_web_ui.py -q
```

Expected: PASS

**Step 2: Run focused browser verification**

- Open homepage.
- Click a featured card.
- Confirm navigation to the corresponding container.
- Confirm no console errors.

**Step 3: Skip commit**

This workspace is not a Git repository. Do not try to commit.

