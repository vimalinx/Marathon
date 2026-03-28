# Host Nightly Runner Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a separate host-side nightly Marathon runner for real Git repositories, scheduled with `systemd --user`, with a fresh nightly branch and per-round commits.

**Architecture:** Keep the current LXC system untouched and add a parallel host-only path. Reuse the existing agent loop and single-command tool by making their sandbox, log-root, prompt-file, and tool-file paths configurable via environment variables, then build a host nightly runner around that shared runtime. Store host project config under `state/host_projects/` and host run logs under `host-runs/`.

**Tech Stack:** Python stdlib, shell scripts, `systemd --user`, Git, existing Marathon agent loop/tool code

---

## Chunk 1: Shared Runtime Configurability

### Task 1: Make `agent_tools.py` host-path configurable

**Files:**
- Modify: `container/agent_tools.py`
- Test: `tests/test_agent_tools.py`

- [ ] **Step 1: Write the failing test**

```python
def test_resolve_cwd_uses_marathon_sandbox_env():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_agent_tools -v`
Expected: FAIL because `resolve_cwd()` ignores the env override

- [ ] **Step 3: Write minimal implementation**

Add an env-driven sandbox path, for example `MARATHON_SANDBOX`, and make `resolve_cwd()` prefer it.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_agent_tools -v`
Expected: PASS

- [ ] **Step 5: Commit**

Skip in this workspace: `/home/vimalinx/Research/Marathon` is not a Git repository.

### Task 2: Make `agent_loop.py` host-path configurable

**Files:**
- Modify: `container/agent_loop.py`
- Test: `tests/test_agent_loop.py`

- [ ] **Step 1: Write the failing test**

Add tests covering env-driven overrides for:
- sandbox root
- log root
- prompt file
- tool file

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_agent_loop -v`
Expected: FAIL because the module still uses hard-coded container paths

- [ ] **Step 3: Write minimal implementation**

Refactor path constants into env-resolved helpers or env-backed defaults. Keep existing container defaults unchanged when env vars are absent.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_agent_loop -v`
Expected: PASS

- [ ] **Step 5: Commit**

Skip in this workspace: `/home/vimalinx/Research/Marathon` is not a Git repository.

## Chunk 2: Host Nightly Core

### Task 3: Add a focused host-nightly core module

**Files:**
- Create: `host/host_nightly.py`
- Create: `tests/test_host_nightly.py`

- [ ] **Step 1: Write the failing test**

Add tests for:
- slug generation from repo path
- nightly branch naming
- resolving default branch from `origin/HEAD`
- detecting dirty workspace
- checkpoint commit message generation
- deadline logic (`08:00`)

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_host_nightly -v`
Expected: FAIL because `host.host_nightly` does not exist

- [ ] **Step 3: Write minimal implementation**

Implement small pure functions first:
- `slugify_repo_path(...)`
- `nightly_branch_name(...)`
- `read_default_branch(...)`
- `should_stop_for_deadline(...)`
- `dirty_checkpoint_message()`

Then add Git command wrappers used by the runner.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_host_nightly -v`
Expected: PASS

- [ ] **Step 5: Commit**

Skip in this workspace: `/home/vimalinx/Research/Marathon` is not a Git repository.

### Task 4: Add the host nightly runner entrypoint

**Files:**
- Create: `host/host_nightly_runner.py`
- Modify: `host/host_nightly.py`
- Test: `tests/test_host_nightly_runner.py`

- [ ] **Step 1: Write the failing test**

Add tests covering:
- writing run metadata to `host-runs/<slug>/<run-id>/`
- creating a checkpoint commit when the repo is dirty
- creating a fresh nightly branch from the default branch
- stopping with `stopped_by_deadline`

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_host_nightly_runner -v`
Expected: FAIL because the runner entrypoint does not exist

- [ ] **Step 3: Write minimal implementation**

Implement the runner to:
- load one repo config
- fetch origin
- resolve default branch
- checkpoint dirty state if needed
- create a nightly branch
- run the shared agent loop in host mode using env overrides
- mirror run artifacts into `host-runs/...`
- stop after the deadline

Prefer a simple polling loop similar to the current host orchestrator, but do not depend on LXC.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_host_nightly_runner -v`
Expected: PASS

- [ ] **Step 5: Commit**

Skip in this workspace: `/home/vimalinx/Research/Marathon` is not a Git repository.

## Chunk 3: CLI Scripts And Project Config

### Task 5: Add host project config helpers and one-shot runner script

**Files:**
- Modify: `host/host_nightly.py`
- Create: `scripts/run_host_nightly_once.sh`
- Test: `tests/test_host_nightly_scripts.py`

- [ ] **Step 1: Write the failing test**

Add tests covering:
- one-shot script exists and is shell-valid
- project config file is written to `state/host_projects/<slug>.json`
- one-shot script invokes `host/host_nightly_runner.py`

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_host_nightly_scripts -v`
Expected: FAIL because the script/config path is missing

- [ ] **Step 3: Write minimal implementation**

Implement:
- config read/write helpers in `host/host_nightly.py`
- `scripts/run_host_nightly_once.sh <repo_path>` that resolves or creates project config and launches the runner

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_host_nightly_scripts -v`
Expected: PASS

- [ ] **Step 5: Commit**

Skip in this workspace: `/home/vimalinx/Research/Marathon` is not a Git repository.

### Task 6: Add `systemd --user` installer script

**Files:**
- Create: `scripts/setup_host_nightly.sh`
- Modify: `host/host_nightly.py`
- Test: `tests/test_host_nightly_scripts.py`

- [ ] **Step 1: Write the failing test**

Add tests for:
- installer script exists
- unit names use `marathon-nightly-<slug>`
- timer and service text include the right repo path and one-shot runner

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_host_nightly_scripts -v`
Expected: FAIL because installer output/rendering is missing

- [ ] **Step 3: Write minimal implementation**

Implement `setup_host_nightly.sh <repo_path>` to:
- create/update project config
- render service and timer units
- install them under the user's `systemd --user` unit dir
- reload `systemd --user`
- enable/start the timer

Do not guess unsupported environments silently; return clear errors if `systemctl --user` is unavailable.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_host_nightly_scripts -v`
Expected: PASS

- [ ] **Step 5: Commit**

Skip in this workspace: `/home/vimalinx/Research/Marathon` is not a Git repository.

## Chunk 4: Verification And Docs

### Task 7: Add host-nightly docs and full verification

**Files:**
- Modify: `README.md`
- Test: `tests/test_host_nightly.py`
- Test: `tests/test_host_nightly_runner.py`
- Test: `tests/test_host_nightly_scripts.py`

- [ ] **Step 1: Write the failing test**

If needed, add a documentation smoke assertion that the new scripts are referenced in `README.md`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL until docs or remaining behavior is wired up

- [ ] **Step 3: Write minimal implementation**

Document:
- what host nightly mode is
- how it differs from LXC mode
- how to install it
- how to trigger it manually
- where logs and config live

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS

- [ ] **Step 5: Run syntax verification**

Run: `python3 -m py_compile host/host_nightly.py host/host_nightly_runner.py host/web_ui.py host/orchestrator.py container/agent_loop.py container/agent_tools.py`
Expected: exit 0

- [ ] **Step 6: Run shell verification**

Run: `bash -n scripts/setup_host_nightly.sh scripts/run_host_nightly_once.sh scripts/setup_lxc_passwordless_sudo.sh scripts/clone_container.sh scripts/create_base_container.sh scripts/start_run.sh scripts/start_web_ui.sh scripts/stop_web_ui.sh`
Expected: exit 0

- [ ] **Step 7: Manual smoke**

Run against a temporary Git repo:
- create a temp bare repo + working repo
- point setup/once scripts at the working repo
- verify a nightly branch appears and at least one Marathon commit is created

- [ ] **Step 8: Commit**

Skip in this workspace: `/home/vimalinx/Research/Marathon` is not a Git repository.
