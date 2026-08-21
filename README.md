# GG AI Desktop

![GG AI Desktop](docs/gg-ai-desktop.png)

Public repo: [github.com/GoldGoblins/GG](https://github.com/GoldGoblins/GG)

This directory **is** the program. GROK TUI (Grok 4.6) is the intended motor.
Local Qwen GGUF files are not in git and are not required for GROK TUI.

```text
git clone https://github.com/GoldGoblins/GG.git
cd GG
chmod +x run-gg-ai-desktop.sh
./run-gg-ai-desktop.sh
```

Needs: Python 3, PySide6 + Qt WebEngine, Grok Build CLI, `grok login`.
Update: `git pull`. Push new features from this tree after they land here.

## Control & Bootstrap Plane v1

The Workbench now has a typed local control plane. Control commands are parsed
before the single-process busy gate, so an active model or runner can always be
inspected or stopped without waiting for normal chat routing.

```text
/help | /commands
/status [TASK_ID]
/tasks
/inspect TASK_ID
/stop [TASK_ID]
/logs TASK_ID [TAIL]
/diff TASK_ID
/resume TASK_ID
/cleanup TASK_ID
/doctor
/context
```

`/stop` is also exposed as a real composer button. It sends TERM and schedules
a KILL fallback after 3000 ms. A stop with no active work is idempotent. The
small critical section used for an already approved atomic file replacement is
deliberately not interruptible; its rollback contract must finish.

Bootstrap development reuses the existing task-bound `SELFDEV_MAIN_PY_V1`
candidate engine:

```text
/bootstrap GOAL
/diff TASK_ID
/approve-task TASK_ID CANDIDATE_SHA256 BASE_HEAD
/reject-task TASK_ID CANDIDATE_SHA256
```

`/bootstrap` may change only the runtime candidate for
`projects/gg-ai-desktop/main.py`. The model cannot select a path, executable,
command, environment, network target, authority or approval. Its semantic
grammar is finitely bounded to prevent an unclosed WHY field from consuming the
entire prediction budget. Persistent apply requires the exact task id,
candidate SHA-256 and base HEAD; the apply runner then revalidates the clean
repository, all bound hashes, Python compilation and the fixed regression
suite before an atomic replacement. It has no commit authority.

There is intentionally no `/shell`, `/exec`, arbitrary argv/path authority or
network authority.

This source slice extends the contract-locked GG AI Desktop product baseline.
The local chat bridge, fixed GREEN Safe Tools, explicit current-QML Limited
Write, task-bound autonomy and the typed control plane are connected. Network,
the external orchestrator, Operator Terminal input, arbitrary commands and
arbitrary paths remain disconnected.

## Canonical product grammar

```text
CHAT
= UNIVERSAL OPERATIONAL STREAM

WORKSPACE
= VISUAL MULTI-OBJECT SURFACE

PRIMARY INPUT
= USER INTENT
```

The UI is intent-native. Chat owns conversation, operational context and
contextual work objects. Workspace owns visual objects being viewed or edited.

## Real UI state versus synthetic fixture

Two provenance classes are mandatory:

```text
REAL_UI_STATE
SYNTHETIC_UI_FIXTURE
```

A real composer submission is `REAL_UI_STATE`. It inserts the user's message
into the local UI stream together with the deterministically resolved
workspace target.

The Local Chat Bridge emits only validated runner output. If the local runner
cannot produce a bound response, the next real UI node reports the blocker
truthfully:

```text
LOCAL CHAT BRIDGE · RESPONSE VALIDATION FAILED
runner evidence retained locally
```

No synthetic model answer is generated.

`SYNTHETIC_UI_FIXTURE` exists only to demonstrate future CODE, TERMINAL,
RUNNER, Live Aid and workspace renderers. Every fixture is visibly marked
`DEMO / SAMPLE` and may not claim real execution, real authority, real PASS,
or fabricated progress.

## Composer / future bridge seam

Composer submit already carries:

```text
text
resolved_context_reference
resolved_workspace_object_id
```

This is the stable seam used by the connected local bridge handler.

## Workspace objects and @current

Workspace tabs have stable object IDs. The selected object determines
`@current`. A tab change is real local UI state even when the displayed
renderer content is a sample fixture.

## Activity grammar

`GG_NEVER_SILENT_WHILE_BUSY=TRUE`

Supported states:

```text
IDLE
QUEUED
STARTING
RUNNING
STREAMING
GENERATING
WAITING
WAITING_FOR_USER
BLOCKED
STOPPING
PASS
FAIL
CANCELLED
TIMED_OUT
```

`FAKE_PROGRESS=FORBIDDEN`.

A percentage is displayed only when a real percentage is known. Otherwise the
UI uses an indeterminate activity indicator plus phase, elapsed time and last
activity when those real values exist.

## Visual language

The first theme is `GG Obsidian / Ledger`:

- dark neutral graphite surfaces;
- thin silver/grey borders;
- editorial monospace labels;
- restrained semantic accents;
- border legends as component syntax;
- compact peripheral telemetry;
- no neon dashboard treatment.

## Safety boundary

```text
THINKING_AUTHORITY != ACTION_AUTHORITY

GENERAL_ACTION_AUTHORITY=NONE
NETWORK_AUTHORITY=NONE
MODEL_INTEGRATION=ENABLED_LOCAL_CHAT
ORCHESTRATOR_INTEGRATION=DISABLED
OPERATOR_TERMINAL_PROCESS=DISABLED
REAL_COMMAND_EXECUTION=FIXED_GREEN_SAFE_TOOLS_ONLY
ARBITRARY_EXEC_AUTHORITY=NONE
SHELL_AUTHORITY=NONE
```

The published local model runner remains byte-frozen and is reachable only
through the validated local chat request/response contract.

## Phase lifecycle

This source is Phase A only:

```text
PHASE A
source/config/tests
→ Code Gate
→ offscreen runtime
→ implementation commit
→ STOP

PHASE B
separate visible Wayland preview
→ operator evidence
→ STOP

PHASE C
SYSTEMSTATUS COMPLETE_LOCAL
→ separate closure commit
```

`COMPLETE_LOCAL` is intentionally not asserted by this source slice. Visible
preview evidence is required first.

## Source layout

The QML entrypoint remains `qml/Main.qml`. Reusable product grammar now lives
under `qml/components/`:

- `GgFrame.qml`
- `ActivityStrip.qml`
- `ChatNode.qml`
- `WorkObject.qml`
- `WorkspaceSurface.qml`
- `TelemetryRail.qml`
- `ContextComposer.qml`

The frozen local-AI contract, schemas and published model runner remain
unchanged.

## Current functional path

```text
LOCAL CHAT BRIDGE
→ LOCAL MODEL IN REAL CHAT
→ FIXED GREEN SAFE TOOLS
→ EXPLICIT LIMITED WRITE
→ TASK-BOUND AUTONOMY / BOOTSTRAP
→ TYPED CONTROL, STOP, RESUME AND EXACT APPROVAL
→ OBSERVE → REPAIR → VERIFY
```
