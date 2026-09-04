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

## Patch notes · 2026-09-05 · marketplace, work lamps, mandate rail, WEB operator

What GitHub had until this push (`269f430`, 4 Sep 2026): 60 Hz TMOG meters, live spectrum, FM dial, a MARKETPLACE *tab* between CRYPTO and TMOG, BufferMark on frames that wait, GROK TUI default.

What landed on top of that (this is the full `269f430` → HEAD delta, not only the mandate/WEB slice):

**MARKETPLACE is a catalog.** Pages CATALOG / REGISTER / RECEIPT / ELEMENTS / LIVES / ACTIVITY. Listings are ELEMENT, SUBSTANCE or OBJECT. Periodic elements mint as paper receipts (`list_element`). Objects carry composition (parts + mass) and previous lives; `rebirth_item` mints a new object that inherits those parts. Identity-hash stays on paper buy; state-hash moves. Merkle catalog, paper/testnet only, authority NONE. No nested MARKETPLACE GgFrame.

**Colored work lamps.** Chat footer has five dots — CPU (green), GPU (purple when present), NET (gold), DISK (red), CHAT (silver). They blink from the same 60 Hz `tmogPulse` when that resource is actually working. CHAT also follows GROK TUI I/O (`chatIoActive`) without double-stepping the pulse. Composer Send becomes a marching BufferMark + Stop while busy. TMOG DISK card has a red lamp on the hanging legend when disk I/O is live. GgFrame BufferMark still only shows when that frame is waiting.

**TMOG list pages are real rows.** SYSTEM / USERS / CONNECTIONS / DISK / FREQ / STARTUP / APPS / SERVICES fill with dict rows, not bare strings. `TmogRow` for lists, `TmogRail` hanging legends, right-click copy, scroll inside the frame. IPv4/IPv6 decode, `core_count`, `gpu_busy`, RAPL energy. Disk fill bar and spring-damped net/disk sparks stay.

**Mandate rail.** AUTHORITY stays NONE. TOOLS stay GREEN TYPED, WRITE stays YELLOW CURRENT. A new **MANDATE** row shows NONE, WAIT, or TASK_SCOPED after `/approve-mandate`. Yellow/red work needs an explicit human yes; it is never a standing red tool belt. Machine graph is 54 nodes / 165 edges (call-102–105).

**Visible WEB operator.** Agent web actions (OPEN, SNAPSHOT, CLICK, TYPE, RELOAD, BACK) run in the workspace **WEB** tab, not a hidden browser. Password fields are blocked. You type one.com / wp-admin logins yourself in that pane.

**Site import drop.** Drop a zip in the local `site-import/` folder; it unpacks into the local SITE copy and skips `wp-config.php`.

**SFTP plan.** `sftp_operator` builds BatchMode get/put for `robots.txt` and `gg-site-completion.php` using `ssh-agent`. No password in config. Live PUT stays red until you unlock the agent.

**MEDIA / UTILITIES chrome.** `MEDIA / UTILITIES` and `RADIO · NO RF` hang on the strip frame like the other GgFrames.

**Screenshot.** `docs/gg-ai-desktop.png` is the desk capture for this drop: mandate row, WEB host, hanging MEDIA/UTILITIES legends, GROK TUI. Marketplace pages and the work lamps are in the tree the screenshot sits on.

Unchanged: GROK TUI as motor, no GGUF in git, `GENERAL_ACTION_AUTHORITY` NONE. Python host edits still need a desktop restart; QML often RELOAD.

## Patch notes · 2026-09-04 · 60 Hz TMOG + live spectrum

What GitHub had until this push (`6bdf2a8`, 2 Sep 2026): GROK TUI default chat, PTY GUI-spin fix, 18-dot spectrum, 1 s radio buffer.

What this patch changes on top of that:

**TMOG is 60 Hz live meters.** Summary/performance/list are Loaders (only the open page exists). Sparks paint `Canvas.Immediate` with antialiasing. `tmogPulse()` is a cheap ~0.3 ms tick; the process table still snapshots about once a second. nvme/pch hwmon stays off the live path.

**Spectrum follows the audio.** FFT bands pump on their own (~125 Hz), not behind a status IPC. The strip paints every 8 ms. Each of the 120 columns is its own LED stack: punch up, fall LED by LED. SPECTRUM/CLIAMP labels and extra buffer marks are gone so the meters get the width. `playing` comes from the live pulse, so LEDs light while you hear the station.

**FM dial.** 87.5–108 MHz under the LEDs. Click snaps to the nearest SR preset. `probe_rf_frontend` is `NO RF` on this HP (RTL8822BE is 2.4/5 GHz WiFi, not FM). An RTL-SDR (`0bda:2838`) or `/dev/radio0` is the real RF path; do not pretend WiFi can demodulate broadcast radio.

**MARKETPLACE** sits between CRYPTO and TMOG. Buffer marks on frames that are actually waiting.

**Screenshot.** `docs/gg-ai-desktop.png` is this drop: TMOG 60 Hz meters, live spectrum, FM dial, MARKETPLACE, MEDIA/UTILITIES, CRYPTO, GROK TUI.

Unchanged: GROK TUI as motor, no GGUF in git, ACTION_AUTHORITY NONE, network NONE. Python host edits still need a desktop restart; QML often RELOAD.

## Patch notes · 2026-09-02 · lag pass

What GitHub had until this push (`fd6e733`, earlier 2026-09-02):

- DRAW desk, interactive desktop, MEDIA/UTILITIES strip, CRYPTO, ledger chrome, shell load
- GROK TUI on a native grid, but it was not guaranteed to be the chat from the first frame
- Typing and clicks inside this program could lag 0.25–0.5 s while other apps stayed fine

What this patch changes on top of that:

**GROK TUI is the default chat.** Start the program and Grok is already in the terminal. QWEN and GROK WORKER are opt-in. Chromium/WebEngine does not boot with the process.

**PTY no longer pegs the GUI thread.** Qt6 `QSocketNotifier.activated` was overwriting the terminal id with `Type.Read`, so the PTY never drained and the main thread spun ~80 % CPU. Keys and clicks waited on that loop.

**Spectrum is LED dots again.** 120 columns × 18 stacked LEDs, color by height — not solid bars that recolor as a whole.

**Radio.** Stream buffer is 1 s (3 s was audible lag; 750 ms underran). The bottom MEDIA/UTILITIES strip follows RADIO when you start a station in the workspace.

Still open: the desk is not fully AAA or lag-free. Function first, visualization as a cheap overlay.

## Patch notes · 2026-09-02 · DRAW / media strip

What GitHub had until that push (`7ca8453`, 27 Aug 2026):

- Workspace hosts CODE, TERMINAL, WEB, EXTERNAL, SITE, **MEDIA**, **CRYPTO**, **TMOG**
- GROK TUI on a native terminal grid (not Chromium)
- Screenshot of that drop (`docs/gg-ai-desktop.png`)
- Control plane, Safe Tools, Limited Write, task-bound autonomy as before

What this patch adds on top of that:

**DRAW.** New workspace host. Built-in sketch pad (brush, eraser, shapes, layers, undo, PNG) plus real desks when they are on PATH: Krita, GIMP, Inkscape, darktable, KolourPaint. Chat intents like `rita`, `draw`, `gimp` switch to DRAW.

**Interactive desktop.** Settings → Layout → Interactive desktop. The window goes frameless, stays below other windows, and fills the work area. SETTINGS in the header, DESKTOP there to return to a normal window.

**MEDIA / UTILITIES strip.** The bottom bar is a real player, not a reserved placeholder. MUSIC / RADIO / TV / GAME / FETCH, transport, volume, 120-bar spectrum with peak hold, 10-band EQ, seek when duration is known. Radio uses cliamp. TV/video stays in the workspace hole. GAME uses libretro in-hole for GB/GBC/GBA/NES plus the user's own files under `~/ROMs/`.

**CRYPTO desk.** Live Lightweight Charts, watch-only Solana pubkey, paper books GG / STOCH+RSI / DCA / DCA+SWING, flash-arb lab, trader lots on the local test validator. Telemetry rail shows CRYPTO holdings. Mainnet stays `MAINNET_NOT_ARMED`.

**Ledger chrome.** Stock Qt Fusion buttons, switches, sliders, checkboxes and fields are replaced by `GgButton`, `GgSwitch`, `GgSlider`, `GgCheck`, `GgField` and an interactive `GgScrollBar`. Settings, Live Aid, DRAW, WEB address, crypto pubkey and the terminal line use the same language as the frames.

**Shell load.** Startup walks the real QML dependency graph. No fake timer, no unrelated vendor dump in the load queue. RELOAD still uses `shellNonce`.

Unchanged: GROK TUI as motor, no GGUF in git, no `/shell` or `/exec`, network authority NONE, ACTION_AUTHORITY NONE.

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

- `GgFrame.qml`, `GgButton.qml`, `GgSwitch.qml`, `GgSlider.qml`, `GgCheck.qml`, `GgField.qml`, `GgScrollBar.qml`
- `ActivityStrip.qml`
- `ChatNode.qml`
- `WorkObject.qml`
- `WorkspaceSurface.qml`
- `TelemetryRail.qml`
- `ContextComposer.qml`
- `UtilitySurface.qml`, `MediaSurface.qml`, `CryptoSurface.qml`, `TmogSurface.qml`, `DrawSurface.qml`

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
