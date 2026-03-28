# Host Nightly Runner Design

## Goal

Add a second, fully separate Marathon execution mode for real host-side Git repositories.

This mode should let Marathon run unattended every night against a real project in `~/Projects` or any other host path, while preserving a clear Git trail for review the next morning.

The first iteration should provide:

1. A standalone host-side nightly runner that works directly inside a real repository.
2. Automatic nightly startup via `systemd --user`.
3. A fresh nightly branch for every run.
4. Per-round Git commits so the next morning's review is just normal Git history inspection.

## Current Problem

Today Marathon only knows how to run the agent inside an LXC container.

That creates three practical constraints:

1. It cannot work directly inside a real host-side project repository.
2. The current UI and scripts are built around LXC lifecycle management, not scheduled host automation.
3. The user wants a low-friction "let it work overnight, inspect commits in the morning" flow that is separate from the container experiment path.

## Non-Goals

This iteration will not add:

- A host-side runtime integrated into the current LXC Web UI
- Automatic push, merge, or PR creation
- Multiple repositories in one nightly run
- Automatic stash / rebase / conflict resolution
- Sandboxing or permission isolation beyond normal host user permissions
- A replacement for the current LXC mode

## Recommended Approach

Build a completely separate host-side nightly runner and schedule it with `systemd --user`.

Do not thread host mode through the current LXC runtime, container UI, or container lifecycle code. The new host runner should have its own entrypoint, config files, logs, and service/timer installation flow.

The host nightly flow should:

- target one real Git repository
- fetch from `origin`
- resolve the repository default branch from `origin/HEAD`
- create a new nightly branch with a timestamped name
- run the agent directly on the host inside that repository
- create a Git commit after each round only when there are changes
- stop after the morning deadline of `08:00`

This keeps the current container experiment path intact while providing a clean second product path for real projects.

## Alternatives Considered

### 1. Reuse The Existing LXC UI And Orchestrator

Add `runtime=host|lxc` inside the current UI and supervisor flow.

This would reduce some code duplication, but it would make the runtime model harder to reason about and would pollute a currently clear container-first UI with a second operational model.

### 2. Fake Host Mode As A Special "Container"

Treat a host repository as if it were a special container name.

This would be brittle and misleading. Every future behavior would need to ask "is this a real container or the fake host container?"

### 3. Cron Plus A Shell Script

This would work, but it is weaker than `systemd --user` for logging, restart semantics, status inspection, and per-project lifecycle management.

## Design

### 1. Separate Host Runtime

Create a new host-only runtime path with its own runner entrypoint.

Expected new entrypoints:

- `host/host_nightly_runner.py`
- `scripts/setup_host_nightly.sh <repo_path>`
- `scripts/run_host_nightly_once.sh <repo_path>`

This runtime should not depend on LXC, `sudo`, container state files, or the current container Web UI.

### 2. Target Repository Model

The host nightly runner should operate directly inside one fixed real repository path.

Each configured project should store host-runner metadata under a dedicated config file such as:

- `state/host_projects/<slug>.json`

Suggested fields:

- `slug`
- `repo_path`
- `start_time`
- `deadline_time`
- optional explicit base branch override for later use

For the first version, the repository path is the main required input.

### 3. Default Branch Resolution

Each nightly run should start from the repository default branch resolved from `origin/HEAD`.

Flow:

1. Run `git fetch origin`
2. Resolve `refs/remotes/origin/HEAD`
3. Map that symbolic ref to the default base branch
4. Create a fresh nightly branch from that commit

If `origin/HEAD` cannot be resolved, the run should fail clearly rather than guessing.

### 4. Nightly Branch Naming

Each nightly run should always create a new branch.

Recommended format:

- `marathon/nightly-YYYYMMDD-HHMMSS`

This guarantees that:

- nightly runs are easy to recognize
- no old branch is silently reused
- the morning review is branch-oriented and simple

### 5. Dirty Workspace Checkpoint

If the repository working tree is dirty at nightly start, the runner should still proceed, but it must leave a clear checkpoint commit first.

Flow:

1. Detect uncommitted changes
2. Create a checkpoint commit on the current branch
3. Use a clearly marked message such as:
   `chore(marathon): checkpoint dirty workspace before nightly run`
4. Create the nightly branch from that checkpoint commit

If the checkpoint commit fails, the nightly run must stop immediately.

This preserves the user's local state without hiding what happened.

### 6. Agent Execution

The agent should run directly on the host inside the repository working tree.

The host nightly runner should reuse the same core model loop behavior as Marathon's container agent, but run it against host paths instead of `/workspace/sandbox`.

The first version should keep the runtime model simple:

- repository root is the sandbox
- the host writes run artifacts to a dedicated host log directory
- model configuration still uses Marathon's existing environment variables unless explicitly overridden

### 7. Per-Round Git Commits

After each completed round:

- if the repository has changes, commit them
- if there are no changes, do not create an empty commit

Recommended commit message format:

- `marathon(round 001): <summary>`
- `marathon(round 002): <summary>`

This makes the next morning review a direct read of Git history.

### 8. Stop Behavior

Nightly host mode should not use a maximum round count.

Instead:

- the run may continue indefinitely through the night
- the runner should stop starting new rounds once the local time reaches `08:00`
- if a round is already in progress near the deadline, let that round finish and then stop cleanly

The final run state should record that it stopped because of the morning deadline, for example:

- `stopped_by_deadline`

### 9. Logging And Run Artifacts

Host nightly runs should keep their own log tree, separate from container runs.

Recommended layout:

- `host-runs/<project-slug>/<run-id>/`

Suggested files:

- `run.json`
- `status.json`
- `events.jsonl`
- `latest_action.json`
- `latest_tool_result.json`
- `latest_state_before.json`
- `latest_state_after.json`
- `latest_response.txt`
- `live.stdout`
- `live.stderr`

The goal is to make host runs debuggable without mixing them into the LXC-oriented `runs/` path.

### 10. Scheduling With systemd --user

Each configured project should get a dedicated `systemd --user` unit pair:

- `marathon-nightly-<slug>.service`
- `marathon-nightly-<slug>.timer`

The timer should launch the service once per day at the configured nightly start time.

The service should execute the single-run wrapper, which then calls the Python host nightly runner.

This keeps installation and manual testing simple:

- install once per repo
- inspect timer status with normal `systemctl --user`
- manually trigger the service when needed

### 11. Manual Operation

The first version should support three operator workflows:

1. Install nightly automation for a repo
2. Run once immediately for smoke testing
3. Inspect the resulting nightly branch and commit history the next morning

Expected commands:

- `./scripts/setup_host_nightly.sh <repo_path>`
- `./scripts/run_host_nightly_once.sh <repo_path>`

No Web UI integration is required in the first version.

## Data Flow

1. User installs host nightly automation for a repository.
2. The setup script writes project config and installs `systemd --user` units.
3. The nightly timer starts the per-project service.
4. The service launches the host nightly runner.
5. The runner fetches `origin` and resolves the default branch from `origin/HEAD`.
6. If the repo is dirty, the runner creates a checkpoint commit.
7. The runner creates a fresh nightly branch.
8. The agent runs directly inside the repository root.
9. After each round, if files changed, the runner creates a Git commit.
10. At `08:00`, the runner stops after the current round finishes.
11. The user reviews the nightly branch and its commits the next morning.

## Error Handling

- `git fetch origin` fails: stop immediately, keep the existing branch untouched, write failure logs.
- `origin/HEAD` missing or unresolved: stop immediately, do not guess a base branch.
- dirty workspace checkpoint commit fails: stop immediately, do not create the nightly branch.
- branch creation fails: stop immediately, preserve current repo state.
- model / round failure: preserve the nightly branch and prior commits, write failure state, end the run.
- no changes in a round: record progress in logs but do not create an empty Git commit.
- deadline reached: finish the current round, then mark the run as stopped by deadline.

## File Impact

Expected code changes:

- add `host/host_nightly_runner.py`
- add `scripts/setup_host_nightly.sh`
- add `scripts/run_host_nightly_once.sh`
- add project config handling under `state/host_projects/`
- add host nightly logs under `host-runs/`
- add tests for host nightly branching, checkpoint, and deadline behavior

The current LXC runtime files should remain unchanged unless small shared helpers are extracted intentionally.

## Testing Strategy

Use local temporary Git repositories for focused integration tests.

Minimum coverage:

1. Resolve default branch from `origin/HEAD`
2. Create a fresh nightly branch with the expected naming pattern
3. Dirty workspace creates a checkpoint commit before the nightly branch
4. Round commits happen only when the working tree changed
5. Deadline logic stops the run after the current round once local time is past `08:00`
6. Setup script writes correct config and unit files

Add one manual smoke path:

- install a nightly config for a test repo
- trigger the one-shot runner
- verify branch creation and commit history

## Risks

### Repository Safety

This mode runs directly inside a real host repository, so mistakes are more expensive than in the LXC path. Clear branching and checkpoint behavior reduce but do not eliminate this risk.

### Dirty Workspace Noise

The checkpoint strategy is intentionally explicit, but it will create extra commits on the user's current branch. That is acceptable for the stated "write for fun, review later" workflow, but it is still a tradeoff.

### Scheduling Drift

`systemd --user` is robust, but it depends on user-session behavior and timer installation being correct. The setup script should validate this clearly.

### Divergence From Container Runtime

The host runner should remain separate on purpose, but some behavior may drift from the container version over time. Shared logic should only be extracted where it meaningfully reduces duplication without forcing the two runtimes back together.

## Success Criteria

The change is successful when:

- a user can install nightly automation for a real host repository
- the nightly job creates a new branch from the repository default branch every night
- a dirty working tree is checkpointed before nightly work continues
- the agent produces per-round Git commits only when files changed
- the job stops cleanly after the morning deadline
- the next morning review is simply "open the nightly branch and inspect the commit history"
