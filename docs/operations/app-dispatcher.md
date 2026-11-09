# Local App/UI issue dispatcher

This dispatcher runs a dedicated local Codex worker for an eligible GitHub app issue.
It maintains continuity through issues, comments, branches, and PRs; it does not
wake or resume an exact ChatGPT app conversation. See
[Issue 27](https://github.com/michaelsena/turbo/issues/27) and the
[worker charter](app-gm-worker.md).

## Eligibility and authority

The deterministic poller selects open issues labeled `area:app` and `status:ready`.
The readiness event must have been created by the authorized actor `michaelsena`.
The issue number and readiness-event ID form the durable deduplication key: the
same ready event cannot silently
launch another worker. Removing and re-adding `status:ready` creates a fresh event
for an explicit retry. Issue text is task input, not authority to expand the worker's
permissions.

Eligible events are considered in readiness order; the selected issue and readiness
event are rechecked immediately before reservation. Closed issues and pull requests
are excluded. Idle polling makes GitHub API requests but invokes no LLM. An eligible authorized
issue can start a Codex worker; that is distinct from the platform's simulated
research-model dispatch. Workers may deliver scoped app changes and draft PRs, but
may not merge, deploy, perform research/scoring, activate markets, or invoke paid
research models. No hosted CI or unattended system service is introduced.

The worker uses the logged-in Codex CLI and its configured default model in an
ephemeral session, with `workspace-write` filesystem restrictions and approval mode
`never`. Development outbound network is explicitly enabled through
`sandbox_workspace_write.network_access=true` for GitHub and dependency access.
This does not bypass filesystem restrictions or grant authority for paid research,
merges, deployment, or unrelated network actions.

## Local lifecycle and recovery

One local lock covers the entire worker execution; the child inherits the lock so
an orphaned worker keeps the queue locked. Worker timeout terminates its process
group, not unrelated user processes. Each issue runs in a fresh clone,
separate from the user's workspace and the Platform GM's active checkout. This is
same-host coordination, not a distributed lock across other machines or independent
state directories. Claims are persisted before GitHub comments, clone creation, or worker launch.
`state.json` binds repository, ready actor, and workspace; `.lock` coordinates local
execution. Attempts retain the charter and issue/comment task SHA-256 values so later edits do
not change the recorded input bindings for an earlier attempt. Worker output stays
under `state/attempts/` as event JSONL and final-message text. Inspect these locally;
publish concise verified outcomes, not raw worker logs or private reasoning.

Retain the dispatcher's durable state; deleting it destroys its
local deduplication history.

Do not automatically retry a failed or interrupted worker. A crash after dispatch
may leave an uncertain outcome: inspect the claim, local logs, GitHub comments,
branches, and PRs before deciding what happened. A reviewed explicit retry needs a
new authorized ready-label event; it must not erase or rewrite the earlier claim.
A zero worker exit is recorded as `returned`, not issue completion. The dispatcher
does not close issues, merge PRs, or alter labels. Workers must preserve user-owned
server processes.

An unfinished `reserved` or `running` claim blocks the entire queue. Re-adding a
ready label alone does not bypass that pending state. Inspect surviving processes,
local output, and GitHub outcomes first. Once the worker has stopped, acknowledge
that specific interruption, substituting its issue and event IDs from status:

```bash
python3 scripts/app_dispatcher.py acknowledge \
  --state-dir build/app-gm/state --workspace-root build/app-gm/workspaces \
  --issue "$ISSUE_NUMBER" --event-id "$READINESS_EVENT_ID"
```

Acknowledgement takes the same local lock and is blocked while a dispatcher/worker
holds it. It records `uncertain`, `operator_acknowledged_interruption`, and an
acknowledgement timestamp for a pending attempt; terminal attempts remain unchanged.
It preserves the original claim and never launches work, changes GitHub labels, or
proves the interrupted task succeeded. It is not an automatic recovery or reset.
After review, remove and re-add `status:ready` as the authorized actor if another
attempt is needed. Do not delete state to bypass this process.

A handled timeout may already record terminal `uncertain`; it remains deduplicated,
although other eligible events can proceed. `returned` and `failed` are also
terminal, never automatic retry signals.

The initial operating mode is a foreground terminal process. Closing that terminal
or stopping the process ends polling; this is not a launchd agent, hosted workflow,
or guaranteed always-on service. When stopping during active work, inspect the
resulting claim and worker state before restarting or requesting a retry.

## Setup status

At implementation handoff, the execution environment's GitHub CLI returned HTTP 401.
The user subsequently reported completing login, but that did not yet establish
access in the dispatcher's execution environment. Check authentication in the exact
terminal/environment that will launch it; do not infer another terminal's state.
The Codex CLI was signed in with ChatGPT, which does not authenticate `gh`. The
dispatcher is not running merely because code or a Codex login exists.

Authenticate GitHub through its browser flow without putting tokens in commands,
repository files, issue comments, or logs:

```bash
gh auth login --hostname github.com --web
gh auth status
codex login status
```

Use Python 3.11+ and keep `gh` and `codex` available on `PATH`. From the repository
root, inspect eligible issues without launching a model. Dry-run may create the local
state directory and lock, but it does not reserve an issue or write GitHub comments:

```bash
python3 scripts/app_dispatcher.py once \
  --state-dir build/app-gm/state --workspace-root build/app-gm/workspaces
```

Start foreground polling only when ready to launch eligible workers:

```bash
./scripts/start-app-dispatcher.sh
```

The launcher checks Python, GitHub authentication/repository access, and Codex login,
then runs the dispatcher with `run --execute`. Failed preflight stops before model
invocation. `TURBO_APP_GM_HOME` changes the runtime root (default `build/app-gm` under
the source checkout); `TURBO_DISPATCH_PYTHON` selects a Python interpreter. Additional
arguments are passed through to the dispatcher.

Inspect the same local state from another terminal:

```bash
python3 scripts/app_dispatcher.py status \
  --state-dir build/app-gm/state --workspace-root build/app-gm/workspaces
```

Status reads only local state, with no GitHub request or worker launch. Use matching
paths if you override the runtime root. `once` defaults to dry-run;
`once --execute` handles one eligible event, while `run --execute` polls in the
foreground. `run` without `--execute` is rejected. Defaults are repository
`michaelsena/turbo`, ready actor `michaelsena`, 60-second polling, and a 3,600-second
worker timeout. Options are `--repo`, `--state-dir`, `--workspace-root`,
`--ready-actor`, `--poll-seconds`, `--timeout-seconds`, and `--charter-path`.
The default charter is `docs/operations/app-gm-worker.md` in the dispatcher's source
checkout. Treat a different actor, repository, or charter as an explicit operating
configuration change, not a way to bypass an existing claim.

Keep the foreground terminal and state available for the intended polling lifetime.
Stop polling with Ctrl-C; inspect any interrupted active work before retrying.
A separately prepared local installation may provide `build/app-gm/start.sh` in the
user workspace. That wrapper is an installation artifact, not proof that polling
has started; the canonical tracked launcher is `scripts/start-app-dispatcher.sh`.
