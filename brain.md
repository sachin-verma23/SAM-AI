# brain.md — Everything about SAM

> The complete map of **SAM** as it exists in this folder: what it is, how every piece works, where every setting lives, and how to customise it.
> Read this before changing anything. For the list of bugs and gaps, see [AUDIT_REPORT.md](AUDIT_REPORT.md).

---

## Table of contents
0. [SAM v1.0 — what changed](#0-sam-v10--what-changed)
1. [What this project is](#1-what-this-project-is)
2. [How to run it](#2-how-to-run-it)
3. [Big picture: architecture](#3-big-picture-architecture)
4. [Folder and file map](#4-folder-and-file-map)
5. [Startup sequence, step by step](#5-startup-sequence-step-by-step)
6. [The live conversation loop](#6-the-live-conversation-loop)
7. [Audio pipeline (mic → model → speakers)](#7-audio-pipeline)
8. [How the system prompt is built](#8-how-the-system-prompt-is-built)
9. [Tools: how the model acts](#9-tools-how-the-model-acts)
10. [Every tool, one by one](#10-every-tool-one-by-one)
11. [core/gemini.py: the model gateway and ladder](#11-coregeminipy-the-model-gateway-and-ladder)
12. [Memory system](#12-memory-system)
13. [Settings: `config/api_keys.json`](#13-settings-configapi_keysjson)
14. [Routines (scheduled and unprompted speech)](#14-routines)
15. [Background tasks and deep research](#15-background-tasks-and-deep-research)
16. [Safety layers](#16-safety-layers)
17. [Local engine: the `providers/` folder](#17-local-engine-the-providers-folder)
18. [The GUI (`gui/` + `ui.py`)](#18-the-gui)
19. [Phone dashboard](#19-phone-dashboard)
20. [Wake word, push-to-talk, echo guard, lip-sync](#20-wake-word-push-to-talk-echo-guard-lip-sync)
21. [Error handling and reconnect logic](#21-error-handling-and-reconnect-logic)
22. [Shutdown](#22-shutdown)
23. [Threads and concurrency rules](#23-threads-and-concurrency-rules)
24. [Data files created at runtime](#24-data-files-created-at-runtime)
25. [Dependencies](#25-dependencies)
26. [What is missing from this copy](#26-what-is-missing-from-this-copy)
27. [Customisation cookbook](#27-customisation-cookbook)
28. [Glossary](#28-glossary)

---

## 0. SAM v1.0 — what changed

SAM is SAM customised for **Sachin Verma**. Everything below is new or changed; the rest of this document describes the original architecture, which still applies. Progress and test results: [ROADMAP.md](ROADMAP.md).

### New files
| File | What it does |
|---|---|
| `core/connectivity.py` | Cached TCP probe of Gemini's host (no key, no quota). `is_online()`, `stable_online()` (2 good probes), `force()` for tests |
| `core/policy.py` | Which actions need the on-screen CONFIRM; `gate()` for tools, `approve_and_wait()` for background jobs |
| `core/offline_tools.py` | The short, curated tool list the local model gets (same tool names, short schemas) |
| `core/prompt_local.txt` | The short offline system prompt, with tool-call examples |
| `core/wake_sam.py` | Offline "Hey Sam" through Vosk with a grammar and word confidence |
| `core/gestures.py` | Webcam hand-gesture control (MediaPipe GestureRecognizer + swipe detection) |
| `memory/history.py` | Every conversation turn, one JSONL file per day in `memory/history/`, keyword search |
| `actions/sam_settings.py` | Voice tool: `set_language`, `set_mode`, `set_lite`, `get` |
| `actions/conversation_history.py` | Voice tool: search / recent / day of earlier conversations |
| `actions/gesture_control.py` | Voice tool: gestures on / off / status |
| `core/self_update.py` + `actions/self_update.py` | SAM changes its own code on request: CONFIRM → git branch `sam-self/<time>` → coding agent → compile + `tests.sam_tests` → CONFIRM → apply + restart; `rollback` reverts the last one |
| `setup_sam.py` | One-command setup after `setup.py`: offline packages, Ollama + model, voices, Whisper, Hey Sam and gesture models, tuned offline/auto settings, final report |
| `tests/sam_tests.py` | Self-test for every SAM change: `python -m tests.sam_tests` (89 checks) |
| `models/` (git-ignored) | `vosk-model-small-en-in-0.4/` (36 MB) and `gesture_recognizer.task` (8 MB) |

### Changed behaviour
| Area | Before | SAM v1.0 |
|---|---|---|
| Name | — | SAM, owner Sachin Verma, version "SAM v1.0" (`gui/theme.py`) |
| Memory writes | in place; a crash could wipe `long_term.json` | temp file + rename; an unreadable file is kept as `.broken-<time>` |
| Phone dashboard | always on, port 8000 | starts only when REMOTE is pressed (or `dashboard_enabled`); port `dashboard_port`, default 8765 |
| Routines | check-in after 15 min, news every 30 min round the clock | check-in after 30 min (max hourly), news every 2 h 08:00–22:00, quiet hours 23:00–07:00 |
| Language | "never mix languages" | `preferred_language`: auto / hindi / english / hinglish; Hinglish is one language; "aap" form |
| Engine | Gemini or pipeline, chosen by hand | plus `auto`: Gemini online, local pipeline offline / no key / out of quota |
| Offline AI | not set up | Ollama `llama3.2:3b`, Whisper `small` int8 CPU, Piper `hi_IN-rohan-medium` + `en_US-lessac-medium` |
| Confirmation | shutdown, restart, Wi-Fi | plus delete, overwrite, move, organise desktop, send message, package installs (close app: optional) |
| After CONFIRM / CANCEL | result only in the activity log | SAM is told the result and says it |
| Memory panel | view, delete | view, edit (✎), add (+), delete |
| Wake word | "Hey Sam" (openWakeWord) | "Hey Sam" (Vosk); `wake_engine: sam` brings the old one back |
| Footer | engine + mic | AI (online/offline + model), NET, MIC, CAM, WAKE — live |
| HUD | 30/20 Hz repaint | same, or 15/10 Hz with `ui_lite` |
| Error "1007" | opened the API-key screen | only a real bad-key message does (`gemini.is_key_error`) |
| Spoken errors | "Sir, …" hard-coded | neutral; the model addresses the user |

### How the offline engine works (and why it is built this way)
Measured on this laptop (i5-8250U, 8 GB, no GPU):
- Ollama reads a prompt at **~25 tokens/s** and generates at **~6.7 tokens/s** with `llama3.2:3b`. A prompt it has already read is cached: 1,229 tokens took **50 s cold and 0.8 s cached**.
- llama3.2's chat template re-inserts native tool definitions into **every** user turn, so native tools cost ~100 s per reply.

So offline SAM uses:
1. `core/prompt_local.txt` (~1.4k chars) instead of the full prompt (~15k).
2. `core/offline_tools.py`: 13 short tools in **prompt format** (`"tool_format": "prompt"` on the Ollama provider). They live in the system prompt, which Ollama caches.
3. **Warm-up**: when the local engine starts, `PipelineEngine._warm_llm()` makes the model read the system prompt once (45–70 s, in the background).
4. Replies that start with `{` are **held** until complete. If they are a tool call, nothing is spoken, including any "done" the model adds after the JSON.
5. Piper chooses the voice by the reply's **script**: Devanagari → Hindi voice, Latin → English voice.
6. Tools that need the internet (`web_search`, `browser_control`, `youtube_video`, `weather_report`, `background_tasks`, …) are withheld while offline.

Result (offline end-to-end test): warm-up ~65 s, then replies in **5–17 s**; "Volume 30 percent kar do" → `computer_settings volume_set 30`; "Notepad kholo" → `open_app Notepad`.

### Auto switching
`main._resolve_engine_caps()` asks `_auto_wants_local()` before every connect: no internet, no Gemini key, or every Live model cooling → local pipeline; otherwise Gemini Live. During a session, `_watch_connectivity()` checks every 15 s: offline while on Gemini → rebuild on local; back online (two good probes) while on local → rebuild on Gemini. A switch starts a fresh conversation (long-term memory and history are kept). One-shot model calls (`core/gemini.call`) skip all Gemini rungs while offline and go straight to the local provider.

### New settings in `config/api_keys.json`
| Key | Default | Meaning |
|---|---|---|
| `preferred_language` | `auto` | auto / hindi / english / hinglish |
| `providers.mode` | `auto` (set during setup) | gemini / pipeline / auto |
| `providers.creds["openai_compat@ollama"].tool_format` | `prompt` | prompt-format tools for the slow CPU |
| `dashboard_enabled` | false | start the phone dashboard at launch |
| `dashboard_port` | 8765 | HTTP port (HTTPS = +1) |
| `confirm_actions` | see `core/policy.py` | e.g. `{"move_files": false, "close_app": true}` |
| `wake_engine` | `sam` | sam (Vosk "Hey Sam") / sam (openWakeWord) |
| `wake_threshold` | 0.85 | Hey Sam word confidence; raise if it wakes by itself |
| `gestures_enabled` | false | webcam gestures |
| `gesture_actions` | see `core/gestures.py` | remap a gesture to any `computer_settings` action, `wake_sam`, or `""` |
| `ui_lite` | false | slower HUD repaint to save CPU |

### Gestures (when switched on)
✋ open palm = play/pause · ✊ fist = mute/unmute · 👍 / 👎 = volume ±10 (repeats while held) · ✌️ = next track · ☝️ = previous track · 🤟 = wake SAM · swipe ← / → = back / forward. A pose must be held ~0.5 s and then rests 1.5 s.

### Self-update (SAM changes its own code)
Say what you want added or changed ("apne andar ek nayi setting banao jo …"). SAM puts **CONFIRM #1** on screen; after it, the coding agent edits SAM's folder on a new branch `sam-self/<time>`. Every changed file must compile and `python -m tests.sam_tests` must pass, otherwise everything is thrown away. If it passes, SAM tells you what changed and shows **CONFIRM #2**; pressing it applies the change and restarts SAM. CANCEL keeps it waiting ("apply kar do" later, or "discard"). "Pichla code change wapas lo" reverts the last applied change and restarts. Requirements: online (uses the Gemini coding model), and no uncommitted edits in the folder. The `self_update` policy category can never be switched off.

### Voice commands added
- "ab se Hindi / English / Hinglish mein baat karo", "jo bhasha main bolun usi mein jawab do" → `sam_settings set_language`
- "offline mode", "online mode", "auto mode" → `sam_settings set_mode`
- "lite mode on karo" → `sam_settings set_lite`
- "kal humne kya baat ki thi?", "maine folder ka naam kya bataya tha?" → `conversation_history`
- "gestures on / off karo", "kaun se gestures hain?" → `gesture_control`
- "apne code mein … jodo / badlo", "apply kar do", "pichla code change wapas lo" → `self_update`

---

## 1. What this project is

- **Name:** **SAM**, owned by **Sachin Verma**. The assistant calls itself **SAM** by default; you can rename it. Licence and attribution: see `LICENSE` and `NOTICE`.
- **What it does:** a desktop voice assistant that **hears** (microphone), **speaks** (speakers), **sees** (screenshot or webcam, on request) and **controls the computer** (apps, keyboard, mouse, files, browser, settings), with long-term memory, reminders, routines and background research.
- **Brain:** Google **Gemini Live API**. One WebSocket carries your audio in and the model's audio out, both transcripts, and tool calls. Optionally, a **local pipeline** replaces it: Whisper (speech-to-text) → any OpenAI-compatible LLM (Ollama, LM Studio, Groq…) → Piper, system voice or ElevenLabs (text-to-speech).
- **Window:** PyQt6 "command-center" HUD with a 3-D reactor core or a holographic face that lip-syncs.
- **Platforms:** Windows, macOS and Linux (X11 works fully; Wayland blocks input and capture).
- **Licence:** CC BY-NC 4.0, so personal or non-commercial use only.
- **Size:** about 56,600 lines across 106 files. Biggest files: `main.py` (3,077), `gui/window.py` (2,960), `core/cloud.py` (2,933), `core/screenview.py` (2,225).

---

## 2. How to run it

```powershell
cd "c:\Users\Lenovo\Desktop\Projects\SAM AI"
.\.venv\Scripts\python.exe main.py
```
- `.venv` was created with **Python 3.14.7** (`py -3.14 -m venv .venv`) and filled with `setup.py`. Supported range: 3.11–3.13, so 3.12 or 3.13 is safer.
- `setup.py` runs `pip install -r requirements.txt` (with OS markers) and `python -m playwright install chromium firefox`, then checks `core/face_model.obj`.
- First launch: the setup overlay asks for a **Gemini API key** (from https://aistudio.google.com/apikey) and saves it to `config/api_keys.json`.
- Stop it by saying "shut down" or "goodbye" (`shutdown_sam` tool), by closing the window, or with Ctrl+C in the terminal.
- Self-test (no network or key needed): `.\.venv\Scripts\python.exe -m providers._tests`, which gives 99/99 passing.

---

## 3. Big picture: architecture

```
┌──────────────────────── Qt MAIN THREAD ───────────────────────────┐
│ ui.py  SamUI  ── wraps ──>  gui/window.py  MainWindow          │
│   (thread-safe methods: write_log, set_state, show_content, …     │
│    each just emits a pyqtSignal)                                  │
└───────────────▲───────────────────────────────────────────────────┘
                │ signals                    ▲ callbacks (text typed, buttons)
┌───────────────┴──── "runner" daemon THREAD: asyncio loop ─────────┐
│ main.py  SamLive.run()                                         │
│   ├─ Gemini Live session  (or providers/engine_pipeline.py)       │
│   ├─ TaskGroup per session:                                       │
│   │    _listen_audio  → out_queue → _send_realtime → session      │
│   │    _receive_audio ← session (audio, transcripts, tool calls)  │
│   │    _play_audio    ← audio_in_queue → speakers + lip-sync      │
│   │    _watch_stall, _watch_reconnect, _run_system_monitor,       │
│   │    _run_sleep_watch, _relay_phone_audio                       │
│   ├─ _execute_tool → inline tools / ActionRegistry / PluginRegistry│
│   └─ dashboard server (FastAPI/uvicorn) on the same loop          │
└──────────┬────────────────────────────────────────────────────────┘
           │ run_in_executor (ThreadPool "sam", 32 workers)
┌──────────▼──── WORKER THREADS ────────────────────────────────────┐
│ actions/*.py handlers, plugins/*.py run()                         │
│ core/gemini.py one-shot calls (Live throwaway session or REST)    │
└───────────────────────────────────────────────────────────────────┘
Other threads: routine engine tick, task engine workers, wake-word
detector, push-to-talk poller, metrics sampler, audio-device prefetch.
```

**Core idea:** `main.py` owns the conversation. Everything the model can *do* is a **tool** (function declaration). Tools are discovered automatically from `actions/` (bundled) and `plugins/` (drop-in). Results go back to the model as text, and it says them in your language.

---

## 4. Folder and file map

### Root
| File | Purpose |
|---|---|
| `main.py` | The heart: Live session, audio I/O, lip-sync extraction, tool dispatch, briefing, reconnect logic, shutdown. Class `SamLive`. |
| `ui.py` | `SamUI`, the object passed to every tool as `player`. Thin thread-safe wrapper over `gui/window.MainWindow`. Also sets UI scale and re-exports old names. |
| `setup.py` | OS-aware installer (pip + Playwright browsers + Python version check). |
| `requirements.txt` | Dependencies (see §25). |
| `AGENTS.md` | Rules for anyone (or any AI) writing code here: threading, plugins, model calls, GUI. **Read it before writing code.** |
| `readme.md` | Author's long changelog and feature list (partly out of date, see §26). |
| `LICENSE` | CC BY-NC 4.0. |
| `.gitignore` | **Broken**: does not ignore the API key (see AUDIT C1). |

### `actions/`: bundled tools (each has a `TOOL` dict and is auto-discovered)
| File | Tool name | Lines |
|---|---|---|
| `open_app.py` | `open_app` | 411 |
| `computer_settings.py` | `computer_settings` | 1360 |
| `computer_control.py` | `computer_control` | 781 |
| `browser_control.py` | `browser_control` | 1428 |
| `file_controller.py` | `file_controller` | 769 |
| `file_processor.py` | `file_processor` | 938 |
| `web_search.py` | `web_search` | 434 |
| `weather_report.py` | `weather_report` | 71 |
| `send_message.py` | `send_message` | 448 |
| `reminder.py` | `reminder` | 414 |
| `routines.py` | `routines` | 168 |
| `background_tasks.py` | `background_tasks` | 161 |
| `video_player.py` | `video_player` | 502 |
| `youtube_video.py` | `youtube_video` | 475 |
| `code_helper.py` | `code_helper` | 633 |
| `dev_agent.py` | `dev_agent` | 1665 |
| `flight_finder.py` | `flight_finder` | 405 |
| `game_updater.py` | `game_updater` | 1101 |
| `desktop.py` | `desktop_control` | 784 |
| `screen_processor.py` | (helpers) `_capture_screen`, `_capture_camera` used by inline `screen_process` | 187 |
| `system_monitor.py` | (helpers) `SystemMonitor`, `get_system_status` | 200 |
| `proactive.py` | (helper) `ProactiveEngine`, which builds check-in prompts | 131 |
| `background_monitor.py` | (helpers) topic watch for `manage_monitor` | 159 |

### `core/`: shared engine pieces
| File | Purpose |
|---|---|
| `gemini.py` | **The only place one-shot model calls should go.** Model ladders, timeouts, cooldowns, Live-as-text trick, provider fallback, JSON parsing. |
| `prompt.txt` | System prompt template with `{assistant_name}`, `{platform}`, `{capabilities}`, `{limits}` tokens. |
| `action_loader.py` | Discovers `actions/*.py` `TOOL` dicts → `ActionRegistry` (validate, dispatch by signature, `strip_meta`). |
| `plugin_loader.py` | Discovers `plugins/*.py` `PLUGIN` dicts → `PluginRegistry` (enable/disable, crash isolation, settings schemas). |
| `outcome.py` | Result vocabulary: `done()`, `unverified()`, `failed()`, `started()`, `ask()`, `untrusted()` wrapper, `unwrap()`. |
| `confirm.py` | Confirmation gate: a UI button issues the token, so the model cannot fake it. |
| `undo.py` | Shared undo stack: `push_undo(label, fn)`, `undo_last()`, `history()`. |
| `appidentity.py` | Which apps are running, matching what the user said, the assistant's own processes (never closed), polite close, focus. |
| `audio_devices.py` | Mic and speaker list (by **name**, not index), measure input, test tone, per-device volume. |
| `echo.py` | `EchoGuard`: tells your voice from the assistant's own echo. |
| `viseme.py` | Transcript → mouth shapes (language-independent via Unicode reduction). |
| `avatar.py`, `avatar_mesh.py`, `face_model.obj` | Software-rendered 3-D head (MediaPipe face mesh, Apache-2.0). |
| `hotkey.py` | Push-to-talk (Ctrl+Space). Global on Windows via `GetAsyncKeyState` polling. |
| `wake_word.py` | Local "Hey Sam" via `openwakeword` (optional install). |
| `platform_support.py` | Detects Wayland or missing macOS permissions; tells the user and the model. |
| `lazyimport.py` | `LazyModule` proxy so `pyautogui` and `playwright` load only when used. |
| `tls.py` | HTTPS trusts system roots **plus** certifi (fixes SSL errors on Windows). |
| `code_checks.py`, `_smoke_harness.py` | Coding agent's project analysis and post-write checks. |
| `tasks/` | Background-task engine (see §15). |
| `routines/` | Routine engine (see §14). |
| `cloud.py` | "Second body" server for a VPS with Telegram. **Not reachable:** its plugin `cloud_agent.py` is missing. Can be run as `python -m core.cloud`. |
| `screenview.py`, `screenact.py` | Accessibility-tree screen reading and clicking. **Orphaned:** used by the missing `screen_agent` plugin. |
| ~~`stt.py`, `tts.py`, `llm_client.py`, `installer.py`~~ | Dead legacy code — **removed in SAM**. |

### `gui/`: the window
| File | Purpose |
|---|---|
| `window.py` | `MainWindow`: layout, header, left/right columns, drawers, content panel, video/camera surface, quiz/review panels, all signals and slots. |
| `widgets.py` | Panels, gauges, sparkline, activity log, file drop zone, task and routine rows, buttons. |
| `overlays.py` | Setup (API key), Customise (name, voice, colour), Plugins, Plugin settings, Confirm banner, Audio devices, Memory panel, Clipboard panel, Remote QR. |
| `providers_panel.py` | ENGINE & PROVIDERS panel (form generated from provider declarations). |
| `hud.py` | Centre canvas: avatar or reactor, state line, waveform, lip-sync schedule. |
| `reactor.py` | 3-D reactor core (QPainter + numpy, cached layers, about 5 ms per frame). |
| `theme.py` | Palette class `C`, `APP_VERSION = "SAM"`, live re-theme. |
| `style.py` | Fonts (`hud_font`, `mono_font`, `px_font`), colour mixing, button CSS. |
| `metrics.py` | CPU, RAM, network, GPU (pynvml), temperature sampling for the HUD. |

### `memory/`
| File | Purpose |
|---|---|
| `config_manager.py` | Read and write `config/api_keys.json` (atomic, locked). Getter and setter for every setting. |
| `memory_manager.py` | `long_term.json`: facts, prompt formatting, search, session summaries. |
| `long_term.json`, `routines.json`, `tasks/` | Runtime data (see §24). |

### Others
| Folder | Purpose |
|---|---|
| `providers/` | Optional local or third-party engine (see §17). Never imported unless configured. |
| `dashboard/` | Phone remote control: `server.py` (FastAPI) plus `static/app.html` and `login.html`. |
| `agents/` | Background agent profiles: `general.md`, `researcher.md`. |
| `plugins/` | Drop-in skills. **Only `_template.py` is present.** |
| `config/` | `__init__.py` (OS helpers), `sam.ico`, `api_keys.json` (your settings and key). |

---

## 5. Startup sequence, step by step

1. **`main.py` top-level, before any import:**
   - On Windows, patches `subprocess.Popen` so every child process gets `CREATE_NO_WINDOW` (no flashing consoles).
   - Reconfigures stdout and stderr to UTF-8 (emoji in logs would otherwise crash non-UTF-8 consoles).
   - `core.tls.install()`: HTTPS trusts system plus certifi roots.
2. Imports: sounddevice, numpy, google-genai, `ui.SamUI`, memory, actions helpers, core modules.
3. **`main()`** (line 3052):
   - `ui = SamUI("face.png")`: sets the UI scale (`ui_scale` config or automatic from screen height on Windows), creates the **single** `QApplication`, builds `MainWindow` and shows it. If there is no key, the window shows the **SetupOverlay**.
   - Starts the daemon thread `runner()`, then `ui.root.mainloop()` (Qt event loop) blocks the main thread.
4. **`runner()`:**
   - `ui.wait_for_api_key()`: polls `MainWindow._ready` every 0.1 s until setup is done.
   - `SamLive(ui)` (line 592) constructor:
     - Sets up state (speaking flag, queues, vision flags, PTT, echo guard, lip-sync stream, resumption handle…).
     - Wires UI callbacks: `on_text_command`, `on_remote_clicked`, `on_interrupt`, `on_voice_change`, `on_audio_device_change`, `on_push_to_talk`, `ptt_hold`.
     - **`discover_actions(actions/)`** → `ActionRegistry` (names may not collide with the 8 inline tools).
     - **`discover_plugins(plugins/)`** → `PluginRegistry` (may not collide with inline tools or actions).
     - Exposes to plugins: `ui.get_plugins`, `ui.get_plugin_settings`, `ui.request_say` (speak mid-task), `ui.tool_catalog`, `ui.run_tool`.
     - `core.tasks.desktop.attach(ui)`: starts the task engine and **resumes interrupted tasks**.
     - `core.routines.desktop.attach(CallbackHost(...))`: starts the routine engine; on first run it seeds the built-in routines. If this fails, `_routines = None` and the old fixed schedules run instead.
     - Wake-word state (`wake_word_enabled`), push-to-talk restore.
   - `asyncio.run(sam.run())`.
5. **`SamLive.run()`** (line 2696):
   - Binds the confirm gate to the UI (`show_confirm` / `hide_confirm`), memory-trim notifier, audio device rates (16 kHz in, 24 kHz out), prefetches the device list.
   - Starts the **dashboard server** (always) and its command-relay task.
   - **Connect loop** (`while True`):
     1. `_ensure_executor()`: makes sure a 32-worker thread pool exists.
     2. `LIVE_MODEL = _gemini.live_model()`: first Live model not in cooldown.
     3. `_resolve_engine_caps()`: `None` means Gemini Live; otherwise it builds the local pipeline and checks vision support.
     4. If there is no Gemini key and no local engine, it logs a hint, shows SLEEPING, and retries every 5 s.
     5. `config = _build_config()` (see §8).
     6. `async with _open_session(...) as session, TaskGroup() as tg:`
        - Wraps `session.send_client_content` to arm the **stall watchdog** on every send.
        - Creates fresh queues (`audio_in_queue`, `out_queue` maxsize 200) and `_turn_done_event`; resets vision state.
        - Wake word: on the **first connect**, if enabled and the detector loads, it starts **asleep**.
        - Logs platform limits once.
        - Starts session tasks: `_watch_reconnect`, `_watch_stall`, `_send_realtime`, `_listen_audio`, `_receive_audio`, `_play_audio`, `_run_system_monitor`, `_run_sleep_watch`, plus `_relay_phone_audio` (if dashboard), plus `engine.warmup()` (local engine). The fallback schedules `_run_background_monitor` and `_run_proactive_mode` run only if routines failed to load.
        - `routines.session_started(awake)` triggers the **Opening briefing** routine.
     7. On an exception, see §21. Then `SLEEPING` state, back off, reconnect.

---

## 6. The live conversation loop

### Sending your voice
`_listen_audio` opens `sd.InputStream(16000 Hz, mono, int16, blocksize 1024)` on the chosen mic (by name; falls back to default). The callback runs on the audio thread and applies these gates **in order**:
1. **Wake-word asleep?** Feed the frame to the local detector only; nothing goes to Gemini.
2. **Assistant speaking?** Drop it. Barge-in is disabled.
3. **Echo tail active** (just stopped speaking, plus output latency plus 0.25 s)? Only pass the frame if `EchoGuard.is_user_speech()` says it is you.
4. **Push-to-talk on and key not held?** Drop it.
5. **Muted or phone mic active?** Drop it.
6. Otherwise, `out_queue.put_nowait({"data": pcm, "mime_type": "audio/pcm"})` and update the HUD waveform.

`_send_realtime` sends each item via `session.send_realtime_input(audio=types.Blob(...))`.

### Typed text
The input box calls `on_text_command(text)` → `_on_text_command` → `session.send_client_content(turns=[user text], turn_complete=True)`. It is ignored while asleep.

### Receiving
`_receive_audio` iterates `session.receive()`:
- **Any message** clears the stall deadline.
- `session_resumption_update` stores `new_handle` if `resumable`.
- `response.data` (24 kHz PCM) is sliced into 2400-byte (50 ms) chunks → `audio_in_queue` (discarded while `_interrupted`).
- `output_transcription` → de-duplicated → `out_buf` and the lip-sync text feed.
- `input_transcription` → `in_buf` and `_last_user_speech = now`.
- `turn_complete` → logs `You: …` and `SAM: …` to the activity log, `_session_log` (used for the end-of-session summary) and the dashboard; handles camera auto-close.
- `tool_call` → for each function call, `await _execute_tool(fc)` (serially), then `send_tool_response`, then `_flush_pending_vision()` (sends a captured image right after the tool response).

### Playing
`_play_audio` opens `sd.RawOutputStream(24000 Hz, mono, int16)` on the chosen speaker and reads the device latency (which sizes the echo tail). Loop:
- Get a chunk, set `speaking=True`, batch up to 9600 bytes (about 200 ms).
- Compute 20 ms lip-sync frames from the audio (`_pcm_visemes`: F1/F2 formant bands plus fricative hiss), fuse them with transcript visemes (`VisemeStream.frames`) and schedule them on the HUD at the exact time they will sound (`_play_cursor`).
- Feed `EchoGuard.note_output()` with what is playing.
- `stream.write()` in a thread.
- When the queue is empty and the turn is done, `speaking=False`, state goes back to LISTENING, and the echo tail starts.

### Interrupt
The INTERRUPT button calls `interrupt()`: drains the audio queue, sets `_interrupted`, resets lip-sync, stops a local engine's generation. Leftover audio from that turn is discarded until its `turn_complete`.

---

## 7. Audio pipeline

| | Rate | Format | Chunk |
|---|---|---|---|
| Mic → model | 16 kHz | mono int16 PCM | 1024 frames (~64 ms) |
| Model → speaker | 24 kHz | mono int16 PCM | queue slices of 2400 B (50 ms), writes ≤ 9600 B (200 ms) |
| Waveform level | RMS floor 60, full 2600 → 0..1 | | |
| Lip-sync frames | 20 ms hop, 1024-sample window | (level, openness, width) | |

Constants are in `main.py` lines 119-189 (`SEND_SAMPLE_RATE`, `RECEIVE_SAMPLE_RATE`, `CHUNK_SIZE`, `_STALL_LIMIT = 30`, `_TAIL_MARGIN = 0.25`, `WAKE_SLEEP_TIMEOUT = 120`).

---

## 8. How the system prompt is built

`_build_config()` (main.py line 1376) runs on **every connect**:

1. Reads `assistant_name` and `user_name` from config.
2. `load_memory()` → `format_memory_for_prompt()` (see §12).
3. Loads `core/prompt.txt`. If that is missing, it uses a one-line fallback.
4. Assembles the system instruction in this order:
   ```
   [CURRENT DATE & TIME]  "Right now it is: Tuesday, November 24, 2026 — 04:30 PM"
   [IDENTITY]             "Your name is X. ... ADDRESS: Always call the user 'Y'."
                          (or: use the respectful 'sir'-equivalent of the current language)
   [memory block]         identity + recent facts + [ALSO REMEMBERED] key index
   prompt.txt rendered    {assistant_name}, {platform} = "Windows 11",
                          {capabilities} = one line per tool (from live declarations, ≤150 chars each),
                          {limits} = generated limits (platform, vision, mic)
   ```
5. Tools = inline `TOOL_DECLARATIONS` plus action declarations plus plugin declarations, passed through `strip_meta` (removes the project's own `tier` and `brief` keys). If the engine cannot see, `screen_process` and `close_camera` are removed. If it cannot use tools, all are removed.
6. LiveConnectConfig:
   - `response_modalities=["AUDIO"]`, input and output transcription on.
   - `session_resumption(handle=...)`, `context_window_compression=sliding_window`.
   - Voice: `voice_name` (default **Charon**; choices Charon, Puck, Kore, Fenrir, Aoede).
   - `proactivity.proactive_audio=True` if `proactive_audio` is not disabled (uses API `v1alpha`).
   - Optional tuning (`_tuning_config`): `realtime_input_config` (turn detection, **off by default**), `media_resolution`, `thinking_config` (only if `thinking_enabled`).

**`prompt.txt` sections:** `[SELF]` (you have a face; image labels), `[WHAT YOU CAN DO]`, `[WHAT YOU CANNOT DO]`, `[JUDGEMENT]`, `[VOICE]` (personality: experienced operator, concrete, dry humour, no filler), `[ACKNOWLEDGE BEFORE A SILENCE]`, `[LANGUAGE]` (always reply in the language of the latest message), `[UNTRUSTED CONTENT]`, `[EXECUTION]` (call each tool once, save memory silently, undo, confirmation), `[TAGGED MESSAGES]` (`[TOOL_STARTING]`, `[FOLDER_UPLOADED]`, `[DEV_AGENT_DONE]`, `[SYSTEM_ALERT]`, `[STARTUP_BRIEFING]`, `[PROACTIVE_CHECK]`), `[SPEED]`.

---

## 9. Tools: how the model acts

### Three sources of tools
1. **Inline** (in `main.py`, `TOOL_DECLARATIONS` line 385). These are tied to live-session state: `system_status`, `screen_process`, `close_camera`, `manage_monitor`, `shutdown_sam`, `save_memory`, `recall_memory`, `undo`.
2. **Actions** (`actions/*.py` with a module-level `TOOL` dict):
   ```python
   TOOL = {
       "name": "open_app",                       # ^[a-zA-Z_][a-zA-Z0-9_]{0,63}$
       "description": "...",                     # what the model reads
       "parameters": {"type": "OBJECT", "properties": {...}, "required": [...]},
       "handler": open_app,                      # callable
       # optional: "tier": "core", "brief": "...", "scheduling"/NON_BLOCKING
   }
   ```
   The handler is called with `parameters` plus whichever of `player`, `speak`, `response` and `session_memory` its signature declares.
3. **Plugins** (`plugins/<name>.py`, no leading underscore):
   ```python
   PLUGIN = {"name": ..., "description": ..., "parameters": {"type": "OBJECT", ...}}
   def run(parameters: dict, player=None, session_memory=None) -> str: ...
   ```
   Rules: return a **short string**, **never raise**, return **within seconds** (put slow work on a thread and report through `player`), and treat `player` as possibly `None`. Enabled automatically; can be toggled in the Plugin Manager (`plugins_enabled` in config). Files starting with `_` are helper modules and are skipped.

### Dispatch (`_execute_tool`, main.py line 1574)
- Sets the HUD to THINKING, then:
- `save_memory` writes immediately and returns `{"result":"ok","silent":True}`.
- Inline branches. `screen_process` has a 4 s cooldown; the image is captured in a thread and attached right after the tool response.
- Action, run in the executor. Special cases: `file_processor` uses the uploaded file if no path is given; `dev_agent` uses the uploaded **folder** with mode=improve; `web_search` results are mirrored to the content panel.
- Plugin, run in the executor.
- Errors: `"Tool 'x' failed: …"`, plus a spoken error.
- Logs `📤 name (ms) → result[:80]`.
- Returns a `FunctionResponse`, optionally with `scheduling` for NON_BLOCKING tools.

### Result vocabulary (`core/outcome.py`)
`status=done` (checked) · `status=unverified` (requested, not confirmed; never to be called a success) · `status=failed` · `status=started` (running in the background, result later) · `status=ask` (needs the user). External content is wrapped in `<<<UNTRUSTED source=…>>> … <<<END UNTRUSTED>>>`.

---

## 10. Every tool, one by one

| Tool | Key parameters | Behaviour |
|---|---|---|
| **system_status** | none | CPU, RAM, GPU, temperature, uptime, process count (psutil, pynvml, wmi). |
| **screen_process** | `angle` screen/camera, `text` question | Captures with mss or OpenCV, compresses, sends the image into the same session labelled `[IMAGE SOURCE: SCREEN CAPTURE]` or `[IMAGE SOURCE: WEBCAM]`. The camera view stays on the HUD and auto-closes about 2 s after the answer. |
| **close_camera** | none | Closes the camera view. |
| **manage_monitor** | `action` add/remove/list, `topic` | News topics checked by the News-watch routine (DDG news, new-headline hash). Refuses crypto and finance topics. |
| **shutdown_sam** | none | Spoken goodbye plus session summary in parallel, stop the engines, exit the process. |
| **save_memory** | `category`, `key`, `value` (English) | Silent write to `long_term.json`. |
| **recall_memory** | `query` (empty = all) | Local keyword search over stored facts. |
| **undo** | `action` undo/list | Reverses the last change the assistant made (files and settings). |
| **open_app** | `app_name` (real name) | Resolves without a shell (Windows: path, Start-menu search, URI); returns `started` straight away and confirms in the background by watching for a new process. If the app is already open, its window is raised instead. |
| **computer_settings** | `action` (about 70 actions), `value`, `times`, `description` fallback | Volume set/up/down/mute (pycaw on Windows), brightness, media keys, seek, window snap/min/max, tabs, zoom, scroll (notches), copy/paste/undo, type text, press key, screenshot, lock, dark mode, **Wi-Fi / restart / shutdown (confirm gate)**. Pushes undo entries. |
| **computer_control** | `action` (type, click, hotkey, scroll, move, screenshot, close_app, screen_find, screen_click, random_data, user_data…) | Low-level pyautogui control. `close_app` matches running processes, closes politely and never closes the assistant itself. `screen_find` asks Gemini for coordinates. |
| **browser_control** | `action` (go_to, search, click, type, scroll, fill_form, smart_click, get_text, tabs, back, forward, reload, switch, list_browsers, close), `browser`, `url`, `query`… | Playwright sessions per browser (uses your real profile where possible); one call opens the browser. |
| **file_controller** | `action` (list, create_file, create_folder, delete, move, copy, rename, read, write, find, largest, disk_usage, organize_desktop, info), `path` (shortcuts: desktop, downloads, documents, home) | Delete goes to the Recycle Bin (send2trash); undo entries for move, create, write. |
| **file_processor** | `file_path` (or the uploaded file), `action`, `instruction`, format, size and trim options | Images, PDF, DOCX, TXT, CSV, XLSX, JSON, code, audio, video, ZIP, PPTX. Uses `gemini.call` with a 90 s timeout. |
| **web_search** | `query`, `mode` search/news/research/price/compare, `items`, `aspect` | Gemini grounded search (REST `SEARCH` ladder) plus DuckDuckGo (`ddgs`) in parallel, with a quota cooldown. |
| **weather_report** | `city` | Opens a Google weather search in the browser (does not fetch data). |
| **send_message** | `receiver`, `message_text`, `platform` | Background; WhatsApp tries `plugins/_whatsapp_core` (missing), otherwise blind keystrokes. Telegram, Signal, Discord: blind keystrokes. Instagram, Messenger: browser plus keystrokes. Result is `unverified`. |
| **reminder** | `date` YYYY-MM-DD, `time` HH:MM, `message` | Creates an OS scheduled notification (Windows Task Scheduler, macOS LaunchAgent, Linux systemd) **and** a spoken "say" routine. |
| **routines** | `action` add/list/update/remove/run/quiet…, `kind` say/prompt/task, timing fields | See §14. |
| **background_tasks** | `action` start/status/list/steer/finish/cancel, `task`, `agent`, `minutes`, `at`, `deliver`, `file_path`, `task_id`, `note` | See §15. |
| **video_player** | `action` play/stop/mute/unmute/forward/back/seek_to/pause/resume, `source`, `source_type`, `seconds`, `position` | Plays on the HUD (QtMultimedia); YouTube via yt-dlp (separate video and audio streams kept in sync); starts **muted**. Also shows pictures. |
| **youtube_video** | `action` play/summarize/get_info/trending, `query`, `url`, `region`, `save` | Opens or plays, summarises from the transcript (youtube-transcript-api) via Gemini. |
| **code_helper** | `action` write/edit/explain/run/build/auto, `description`, `language`, paths, `timeout` | Single-file coding with Gemini SMART (60 s). |
| **dev_agent** | `mode` build/improve/status, `description`, `folder`, `language`, `project_name` | Multi-file agent. *build* creates `Desktop/SamProjects/<name>`, plans, writes, installs dependencies, runs and fixes. *improve* scans a folder (reads AGENTS.md or CLAUDE.md), plans changes, writes, runs checks and tests (`core/code_checks.py`). Live progress in the panel. Uses `coding_provider` if set. |
| **flight_finder** | `origin`, `destination`, `date`, `return_date`, `passengers`, `cabin`, `save` | Opens Google Flights in Playwright, parses with Gemini, speaks the best options. |
| **game_updater** | `action` update/install/list/download_status/schedule…, `platform` steam/epic/both, `game_name`, `app_id`, `hour`, `minute`, `shutdown_when_done` | Finds Steam and Epic installs and manifests, drives the launchers, schedules daily updates. |
| **desktop_control** | `action` wallpaper/wallpaper_url/current_wallpaper/organize/clean/list/stats, `path`, `url`, `mode` | Wallpaper (verified and reversible), tidy desktop files. |

---

## 11. core/gemini.py: the model gateway and ladder

**Use it for every non-conversation model call:**
```python
from core import gemini
gemini.text(prompt, tier=gemini.FAST)                 # str or None
gemini.text(prompt, tier=gemini.SMART, timeout_ms=60_000)
gemini.as_json(prompt, tier=gemini.SMART)             # parsed JSON or None
gemini.call(contents, tier=..., config=..., timeout_ms=...)  # full response or None
```
- **Tiers:** `FAST` (classification), `SMART` (reasoning, code, documents, images), `SEARCH` (grounded, REST only).
- **`LIVE` rung first:** a throwaway Live session answers text through `output_transcription`, because the **Live quota is a separate pool** from the text quota (on the free tier the text pool runs out first). At most 3 concurrent side sessions (`_LIVE_SLOTS`); if no slot frees up within 3 s, the call falls through to REST.
- **Ladders** (line 168), tried left to right:
  - FAST: live → 3.5-flash-lite → flash-lite-latest → 3.1-flash-lite → 3.5-flash → 3.6-flash → 3.8-flash → flash-latest → 3-flash-preview → 2.5-flash-lite → 2.5-flash
  - SMART: live → 3.5-flash → 3.8-flash → 3.6-flash → flash-latest → 3.7-flash → 3.5-flash-lite → flash-lite-latest → 3.1-flash-lite → 3-flash-preview → 2.5-flash → 2.5-flash-lite
  - SEARCH: 3.5-flash → flash-latest → 3.8-flash → 3.6-flash → 2.5-flash → 2.5-flash-lite
- **Conversation models** (`LIVE_MODELS`, line 200): `gemini-3.1-flash-live-preview`, then `gemini-2.5-flash-native-audio-preview-12-2025`.
- **Cooldowns:** 429 quota → 5 min; 503/504 → 30 min; 404/403/"not supported" → 6 h; key errors rest nothing.
- **Timeouts:** default and minimum 10 s (the API rejects less).
- **Provider rung:** if ⚙ sets a "sidecar" provider (`prov:<id>`), it joins the ladder, optionally first (`sidecar_first`).
- `parse_json()` strips `<think>` blocks and ``` fences.

---

## 12. Memory system

**File:** `memory/long_term.json`
```json
{
  "identity":      {"name": {"value": "…", "updated": "2026-11-24"}, "language": {...}},
  "preferences":   {...}, "projects": {...}, "relationships": {...},
  "wishes":        {...}, "notes": {...},
  "sessions":      [{"date": "2026-11-24", "summary": "…", "language": "Hindi"}]
}
```
- **Write:** the model calls `save_memory(category, key, value)` silently. Values are English, truncated to 380 characters, stamped with an `updated` date.
- **Prompt block** (`format_memory_for_prompt`):
  1. Identity in full (name, age, birthday, city, job, language… "language" is phrased as a past observation).
  2. Most recently updated other facts, up to 900 characters, at most 6 per category.
  3. `[ALSO REMEMBERED]`: an index of the remaining **keys** (420 characters), so the model knows to call `recall_memory`.
- **Search:** `search_memory(query)` uses word scoring over category, key and value.
- **Limit:** 200,000 characters as a runaway guard; it trims the oldest entries and logs this to the activity log.
- **Session summaries:** at session end (≥ 3 log lines) Gemini SMART writes 1-2 sentences in your language (max 280 characters, keeps 3). The next Opening briefing **pops** the latest one ("yesterday we talked about…"), so it is never repeated.
- **UI:** the Memory panel lists every fact and lets you delete it (`forget`).
- To wipe everything, delete `memory/long_term.json`.
- ⚠️ Writes are not atomic (AUDIT C2).

---

## 13. Settings: `config/api_keys.json`

Written only through `memory/config_manager.py` (atomic tmp+rename plus a lock; an unreadable file is set aside as `.broken-<time>`). Current keys in your file: `gemini_api_key`, `local_only`, `os_system`. All recognised keys:

| Key | Default | Meaning |
|---|---|---|
| `gemini_api_key` | (setup) | Gemini key, stored **in plain text**. |
| `local_only` | false | true means never use Gemini. |
| `os_system` | auto | windows/mac/linux. |
| `assistant_name` | "SAM" | Its name (Customise panel). |
| `user_name` | "" | How it addresses you; empty means "sir"-equivalent. |
| `voice_name` | "Charon" | Charon, Puck, Kore, Fenrir or Aoede. |
| `ui_color` | `#00d4ff` | Accent colour (hue-linked palette). |
| `hud_style` | "face" | "face" (holographic head) or "core" (3-D reactor). |
| `ui_scale` | auto | 0.5–3 Qt scale override. |
| `wake_word_enabled` | false | "Hey Sam" gate. |
| `push_to_talk_enabled` | false | Hold Ctrl+Space. |
| `morning_brief_enabled` | true | Mirrors the Opening-briefing routine switch. |
| `proactive_audio` | true | Model ignores speech not aimed at it. |
| `thinking_enabled` | false | Live thinking budget -1. |
| `media_resolution` | default | default/low/medium/high for screenshots. |
| `turn_tuning` | `{enabled:false, silence_ms:550, prefix_ms:150, end_sensitivity:"high", start_sensitivity:"default"}` | Server-side end-of-turn detection. |
| `input_device`, `output_device` | "" (system default) | Device **names**. |
| `camera_index` | auto | Webcam index (auto-detected and saved). |
| `plugins_enabled` | {} | Per-plugin on/off. |
| `plugin_config` | {} | Per-plugin settings (namespaced). |
| `providers` | – | `{mode: "gemini"|"pipeline", pipeline: {stt, llm, tts}, <id>: {...creds}, sidecar, sidecar_first, coding}` |
| `dashboard_https` | false | Phone dashboard over HTTPS (self-signed). |
| `tasks_max_parallel` | – | Background task workers. |

---

## 14. Routines

**Engine:** `core/routines/engine.py` (tick every few seconds, on its own thread). **Store:** `memory/routines.json`. **Tool:** `routines`.

A routine has a **trigger** and a **kind**:
- Triggers: `time` (rule: `once {at_ts}`, `weekly {time, days[1=Mon..7]}`, `monthly {day 1-31 (31 = last), time}`, `interval {minutes, start, end, days}`), `startup` (once per run, first moment it can speak), `idle {minutes, cooldown}`.
- Kinds: `say` (speak fixed text, wrapped as `[REMINDER …]`), `prompt` (instruction executed with tools), `task` (start a background task), `builtin` (briefing, checkin, news_watch).
- **Lateness grace:** say ≤ 2 h, prompt ≤ 45 min, task ≤ 6 h. Past that it is skipped and logged.
- **Quiet hours:** one window (off by default). Routines marked `quiet` (check-in, news watch) are held back; exact-time reminders still ring.
- **Delivery needs:** session connected, awake, not speaking (`_routine_ready`).

**Your current routines** (seeded on first run):
| Name | Trigger | Notes |
|---|---|---|
| Opening briefing | startup | Greeting with the time, plus last-session line, plus news (`top world news today`) shown in the panel; `extra` lets you add tasks. |
| Check-in | idle 15 min, cooldown 20 | Three "focuses" (projects, wellbeing, interesting fact); quiet=true. |
| News watch | every 30 min, 00:00–23:59 | Checks `manage_monitor` topics; quiet=true. |

Examples by voice: "move the briefing to 08:30", "every Friday at 17:00 remind me to send the report", "don't talk to me between 23:00 and 07:00".

---

## 15. Background tasks and deep research

**Package:** `core/tasks/`. **Tool:** `background_tasks`. **Agents:** `agents/*.md`.

- **Agent file format:**
  ```markdown
  ---
  name: researcher
  title: Researcher
  description: one line
  mode: research          # optional; omit for an open loop
  tools: search_web, fetch_page, file_processor
  minutes: 10
  rounds: 300
  ---
  Instructions in plain words…
  ```
  Shipped: **general** (15 min, 40 rounds; tools: search_web, web_search, fetch_page, notes, write_file, file_processor) and **researcher** (10 min, 300 rounds, research mode).
- **Lifecycle:** queued/scheduled → running → (waiting_quota: sleeps 5 min) → done/failed/cancelled. **Every round is checkpointed** to `memory/tasks/<id>.json` and `<id>.turns.json` (atomic). Tasks resume after a restart; more than 3 interruptions fail the task. Finished tasks beyond the latest 100 are pruned.
- **Budgets:** minutes and rounds. When exhausted, or when you say "that's enough, write it up", the last round offers no tools and asks for the report.
- **Control by voice:** "how is it going" (status), "stop it" (cancel), "write it up" (finish), "also look at euro prices" (steer).
- **Output:** `reports/<slug>.md`, the content panel, and a spoken announcement in your language through `request_say`.
- **Research mode stages** (`research.py`): PLAN → INVESTIGATE (per sub-question: search, read the page in full, record a finding with an exact quote) → REVIEW (up to 2 gap cycles) → WRITE (from findings only) → VERIFY. **Quotes are checked in code** against the saved page text; citations are renumbered and a dangling one becomes `[?]`.
- **`brain.py`:** one tool-calling round on the Gemini REST ladder (no Live rung); the history is vendor-neutral, so a task can continue on a fallback provider.
- **Hard rules (`tools.py`):** no tool that acts on the computer; **web access and memory access are never given to the same agent**; files stay inside the task's folder.
- **`web.py`:** fetches pages and PDFs, **refuses private, loopback and link-local addresses**, follows redirects by hand and checks each hop.

---

## 16. Safety layers

| Layer | File | What it does |
|---|---|---|
| Confirmation gate | `core/confirm.py` + `core/policy.py` | `request(title, detail, fn)` shows a CONFIRM/CANCEL banner; the tool returns `[CONFIRMATION_PENDING]`; `fn` runs only after **you** press CONFIRM. Used for shutdown, restart, Wi-Fi and (SAM) delete, overwrite, move, organise desktop, send message, package installs. SAM is told the result. |
| Undo | `core/undo.py` | Actions push a reverse function. The `undo` tool runs the most recent; `list` shows the history. |
| Honest outcomes | `core/outcome.py` | done / unverified / failed / started / ask. |
| Untrusted wrapper | `core/outcome.untrusted()` + prompt | Web, document and screen text is marked as data; instructions inside it are reported, not obeyed. |
| Own-process protection | `core/appidentity.py` | `close_app` can never target the assistant's own processes. |
| No shell in open_app | `actions/open_app.py` | Prevents command injection. |
| Recycle Bin deletes | `file_controller` (send2trash) | Recoverable. |
| Background agents can't act | `core/tasks/tools.py` | See §15. |
| SSRF guard | `core/tasks/web.py` | No private addresses. |
| Platform honesty | `core/platform_support.py` | Tells the user and the model what Wayland or macOS blocks. |

---

## 17. Local engine: the `providers/` folder

Choose it in ⚙ → **ENGINE & PROVIDERS** → "MY OWN SETUP". Never imported in Gemini mode.

| File | Role |
|---|---|
| `base.py` | Contract: `Engine` (same 4 methods as a Live session: `send_realtime_input`, `send_client_content`, `send_tool_response`, `receive`), `LLM.chat`, `STT.transcribe`, `TTS.speak`, `Field` (form fields), caps. |
| `registry.py` | Lists providers by name, imports one on demand, caches built objects, `missing_fields()`. |
| `engine_pipeline.py` | STT → LLM → TTS wearing the Live interface. Voice-activity detection for the end of a turn (or the push-to-talk release), sentence streaming to TTS, `<think>` filtering, tool loop, interrupt, warmup. Expect 1.5–4 s per reply. |
| `llm_openai.py` | Any `/v1/chat/completions` endpoint: Ollama, LM Studio, llama.cpp, vLLM, OpenAI, Groq, DeepSeek, Mistral, xAI, OpenRouter, Together… Streaming tool calls, vision probe. |
| `stt_whisper.py` | faster-whisper on CPU (default) or a transcription API. Language detection. |
| `tts_piper.py` | Piper neural voices (~50 languages; voices downloaded to `providers/voices/`; follows the detected language). |
| `tts_system.py` | Windows SAPI (via PowerShell), macOS `say`, Linux espeak-ng. |
| `tts_elevenlabs.py` | ElevenLabs streaming (PCM 24 kHz on paid plans, MP3 fallback). |
| `schema.py` | Converts tool declarations between Gemini, OpenAI and Anthropic; **tool budget** (small models get core-first tools by count and size). |
| `audio.py` | Resample and convert between rates. |
| `_tests.py` | Self-test (99 checks). |

Other uses: **sidecar** (one-shot calls go to another model when Gemini's text quota runs out) and **coding provider** (which model `dev_agent` uses).

---

## 18. The GUI

- **One `QApplication`**, created in `SamUI.__init__`. Fusion style.
- **Layout (`MainWindow`):** header (logo, clock, state chip, buttons) · left column (ring gauges for CPU, RAM, GPU and temperature, network sparkline, identity rows, TASKS / ROUTINES panel) · centre HUD (avatar or reactor, waveform, state; also the video, picture and camera surface) · right column (activity log in transcript style, file drop zone, content panel) · input row (text box, send, mute, interrupt) · drawers (quick drawer and CONTROLS drawer) · status strip.
- **States:** `LISTENING`, `SPEAKING`, `THINKING`, `SLEEPING`.
- **Overlays:** Setup (API key) · Customise (assistant name, your name, voice, colour wheel or hex) · Plugin manager · Plugin settings · Confirm banner · Audio devices (pick, test meter, volume) · Memory panel · Remote QR · ENGINE & PROVIDERS · Clipboard panel (Translate / Summarise / Explain / Fix).
- **CONTROLS drawer toggles:** wake word (install, enable, wake now), push-to-talk, morning brief, HUD style face/core, autostart (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run` value `SAM_AI`), desktop shortcut, fullscreen.
- **Thread-safe API** (call from any thread through `player`): `write_log`, `set_state`, `show_content(title≤48, text≤4000)`, `show_code_job`, `show_quiz`, `hide_quiz`, `show_review`, `show_video`, `show_image`, `stop_video`, `set_video_muted`, `seek_video`, `pause_video`, `video_state`, `start_camera_stream`, `stop_camera_stream`, `show_camera_frame`, `show_confirm`, `hide_confirm`, `prompt_reconfig`, `push_visemes`, `set_audio_level`, `glance`, `request_say`, `tool_catalog`, `run_tool`, `muted`, `current_file`, `assistant_name`.
- **Pattern for a new cross-thread UI feature:** add a `pyqtSignal` to `MainWindow`, connect it in `__init__`, add a thin `SamUI` method that only emits it (copy `show_content` → `_content_sig` → `_show_content`).
- **Theme:** palette class `C` in `gui/theme.py` (BG `#00060a`, PRI `#00d4ff`, ACC `#ff6b00`, GREEN `#00ff88`, RED `#ff3355`, TEXT `#8ffcff`…). Stylesheets must use only these hex values so the live re-theme can swap them. Fonts come only from `gui/style.py` (Bahnschrift on Windows).

---

## 19. Phone dashboard

- `dashboard/server.py`: FastAPI plus uvicorn on the same asyncio loop. **SAM: starts only when REMOTE is pressed** (or `dashboard_enabled`). Binds to `0.0.0.0`, HTTP **:8765** by default (`dashboard_port`; HTTPS on the next port if `dashboard_https`).
- **Pairing:** press REMOTE to get a QR code and a one-time 8-character key (expires after 10 min) → `/auto-login?key=` → a device token (in memory). Login throttling; `/api/revoke-devices`.
- **Endpoints:** `/login`, `/`, `/auto-login`, `/api/device-login`, `/api/revoke-devices`, `/api/command` (text → session), `/api/wake`, `/ws/phone-audio` (phone mic → session; mutes the PC mic while streaming), `/api/upload`, `/api/files`, `/uploads/{file}`, `/ws` (live log and status broadcast).
- Commands are AES-256-GCM encrypted (PBKDF2 from the pairing key) **only over HTTPS**; plain HTTP sends them in clear.
- On Windows it may ask for admin rights to add firewall rules (only when you press REMOTE).

---

## 20. Wake word, push-to-talk, echo guard, lip-sync

- **Wake word** (`core/wake_word.py` → `core/wake_sam.py`): SAM listens for **"Hey Sam"** with Vosk (or the original openWakeWord "Hey Sam" with `wake_engine: sam`), on its own thread, mic frames pushed by a queue. While asleep **nothing is streamed** to Gemini. Wake by saying "Hey Sam", pressing WAKE NOW, holding the push-to-talk key, or a remote command. Auto-sleeps after 120 s with no speech. Installed with one click from CONTROLS.
- **Push-to-talk** (`core/hotkey.py`): Ctrl+Space; global on Windows (polls `GetAsyncKeyState` 30 times a second), window-only elsewhere. With a local engine, the key release ends the turn.
- **Echo guard** (`core/echo.py`): compares band energies of the mic against what is playing and calibrates itself. Used only for the echo tail; voice barge-in is disabled.
- **Lip-sync:** audio formants (timing and vowels) plus transcript visemes (`core/viseme.py`, which knows closures such as m, b and p), scheduled against the real playback time. About 50 shapes a second. Biased to lead the audio slightly, never lag.
- **Face as status:** looks away while thinking, eye contact while listening, eyelids down while asleep.

---

## 21. Error handling and reconnect logic

In `run()`'s `except BaseException`:
1. **`_ReconnectSignal`** (voice change, audio device change, stall): reconnect at once. A voice change drops the resumption handle (fresh conversation); the others keep it.
2. **Resumption handle rejected:** drop it and start fresh.
3. **`note_live_failure`** (429 quota, or 404/403): step to the next Live model; if every model is resting, wait 15 s.
4. **Tuning fields rejected** (INVALID_ARGUMENT, "Unknown name"…): turn `_tuned_live` off and reconnect.
5. **Proactive audio rejected:** turn `_enhanced_live` off (use API v1beta).
6. **"API key not valid" or "1007":** show the setup overlay and wait for a new key (the "1007" check is suspect, see AUDIT M1).
7. **Network words in the message:** exponential backoff 3 → 60 s, and the log says "a VPN may be required".
8. Otherwise back off 3 s.

`finally`: `session=None`; if the log has ≥ 3 lines, save the session summary. Then SLEEPING state, a dashboard status broadcast, sleep, retry.

**Stall watchdog:** 30 s after a send with no server message, the session is rebuilt (context kept).

---

## 22. Shutdown

- **By voice (`shutdown_sam`):** send "say a brief goodbye", wait for the turn to complete and the speaking to end (max 8 + 6 s), **and in parallel** save the session summary (max 12 s). Then `_stop_engines()` (routines stop; the running task stays "running" on disk and resumes next launch), then `_exit_process(0)` (atexit handlers, flush, `os._exit`).
- **By closing the window:** `mainloop` returns → `sam.finish()` (summary within 15 s, stop the engines) → `_exit_process(0)`.

---

## 23. Threads and concurrency rules

1. **Only the Qt main thread touches widgets.** Tools must never create a `QWidget`, `QApplication`, `QThread` or `QDialog` (AGENTS.md). Use `player.*`.
2. Tools run in the loop's ThreadPoolExecutor (32 workers, prefix `sam`).
3. The Live session, queues and `send_*` belong to the asyncio loop thread. From other threads use `asyncio.run_coroutine_threadsafe(..., self._loop)` (as `plugin_say`, `speak` and `_on_text_command` do).
4. `_speaking_lock` guards `_is_speaking`.
5. Config writes are locked and atomic; memory writes are locked but **not** atomic.
6. Fire-and-forget asyncio tasks should be kept with `self._keep_task(task)`.

---

## 24. Data files created at runtime

| Path | Contains | Safe to delete? |
|---|---|---|
| `config/api_keys.json` | Key and every setting | Deleting it means the setup screen again |
| `config/certs/` | Dashboard TLS key and certificate | Yes (regenerated) |
| `memory/long_term.json` | Facts about you and session summaries | Yes (forgets everything) |
| `memory/routines.json` | Routines and quiet hours | Yes (built-ins re-seeded) |
| `memory/tasks/` | Task checkpoints and saved pages | Yes |
| `reports/` | Task reports (Markdown) | Yes |
| `uploads/` | Phone uploads | Yes |
| `providers/voices/` | Piper voices | Yes (re-downloaded) |
| `%LOCALAPPDATA%\ms-playwright` | Chromium and Firefox for Playwright | Re-run `playwright install` |
| `Desktop/SamProjects/` | `dev_agent` build output | Yours |
| Windows Task Scheduler entries | Reminders and game-update schedules | Remove in Task Scheduler |

---

## 25. Dependencies

From `requirements.txt` (✓ = used; ✗ = no file imports it in this copy):
PyQt6 ✓ · sounddevice ✓ · numpy ✓ · google-genai ✓ · httpx ✓ · requests ✓ · certifi ✓ · beautifulsoup4 ✓ · playwright ✓ · yt-dlp ✓ · pyautogui ✓ · pyperclip ✓ · pillow ✓ · opencv-contrib-python ✓ · mediapipe ✓ (gestures) · mss ✓ · psutil ✓ · send2trash ✓ · python-pptx ✓ · fastapi ✓ · uvicorn ✓ · cryptography ✓ · python-multipart ✓ · qrcode ✓ · openpyxl ✓ · youtube-transcript-api ✓ · pygetwindow ✓ · ddgs ✓ · pdfplumber ✓ · PyPDF2 ✓ · python-docx ✓ · pynvml ✓ (deprecated; it warns) · Windows only: comtypes ✓, pycaw ✓, win10toast ✓, pywin32 ✓, wmi ✓, pywinauto ✓
**Removed in SAM (only the missing plugins used them):** google-api-python-client · google-auth-oauthlib · tinytuya · paho-mqtt. **Added:** mediapipe, opencv-contrib-python (replaces opencv-python). **Installed for SAM but optional:** vosk (Hey Sam), faster-whisper, piper-tts (offline voice).
**Optional, installed from the UI:** openwakeword (wake word), faster-whisper (local STT), piper-tts (local voice).

---

## 26. What is missing from this copy

The README describes ~22 plugins that **are not in the GitHub repo** (only `plugins/_template.py` exists): the WhatsApp core driver, calls and guard, Telegram remote, chat takeover, screen agent, Gmail, Calendar, Obsidian, document review, Excel writer, image generator, YouTube upload, printer, home assistant, shopping list, Pomodoro, water reminder, quiz, spaced repetition, calorie counter, push-up counter, and cloud_agent. Some UI and prompt hooks for them exist (`show_quiz`, `show_review`, `show_image`, `generate_image` mentions). Details are in AUDIT H1.

---

## 27. Customisation cookbook

| Want to… | Do this |
|---|---|
| **Rename the assistant / change how it calls you** | UI: Customise panel. Or set `assistant_name` and `user_name` in the config (through the panel, not by hand). |
| **Change its personality** | Edit `core/prompt.txt`, especially `[VOICE]`. Keep the `{tokens}`. Applies on the next connect. |
| **Make it always speak Hindi or Hinglish** | Add a line under `[LANGUAGE]` in `prompt.txt`, for example "Always reply in Hinglish (Hindi in Latin script) unless asked otherwise." The current rule is "reply in the language of the latest message". Also save `identity/language`. |
| **Change the voice** | Customise panel (Charon, Puck, Kore, Fenrir, Aoede). The list is `AVAILABLE_VOICES` in `memory/config_manager.py:147`. |
| **Change colours** | Customise colour wheel, or the defaults in class `C` in `gui/theme.py`. |
| **Change the default HUD (face/reactor)** | CONTROLS → HUD style (`hud_style`). |
| **Change the conversation model** | `LIVE_MODELS` in `core/gemini.py:200` (and `LIVE_MODEL` in `main.py:119`). |
| **Change side-call models** | `_LADDERS` in `core/gemini.py:168`. |
| **Add a new tool that controls the PC** | New `actions/my_tool.py` with a `TOOL` dict and a handler (copy the shape of `weather_report.py`). Return `core.outcome` strings. Restart. |
| **Add a skill that is not about PC control** | Copy `plugins/_template.py` to `plugins/my_skill.py`; fill in `PLUGIN` and `run()`. Restart; it is enabled automatically. |
| **Speak in the middle of a long plugin job** | `player.request_say("Tell the user X briefly.")` |
| **Show something on screen from a tool** | `player.show_content(title, text)`, `player.show_video(path)`, `player.show_image(path)` |
| **Ask a model from your tool** | `from core import gemini; gemini.text(...)`. Always handle `None`. |
| **Add a background agent** | New `agents/<name>.md` (frontmatter plus instructions). Allowed tools: search_web, web_search, fetch_page, notes, write_file, file_processor. |
| **Change the morning briefing** | By voice ("make the briefing about technology", "add the weather to the briefing") or edit `options` in `memory/routines.json` (news_topic, extra). |
| **Stop unprompted talking** | Say "turn off the check-in" or "set quiet hours 23:00–07:00", or disable routines in the ROUTINES panel. |
| **Run fully offline** | ⚙ → ENGINE & PROVIDERS → MY OWN SETUP: Whisper + Ollama (e.g. `qwen3`) + Piper; set `local_only`. |
| **Use another provider only when the Gemini text quota runs out** | ⚙ → ENGINE & PROVIDERS → background requests (sidecar). |
| **Change which apps open by nickname** | `ALIASES` in `core/appidentity.py`; the `app_name` description in `actions/open_app.py`. |
| **Add an inline tool that needs session state** | Add it to `TOOL_DECLARATIONS` (main.py:385) and a branch in `_execute_tool` (main.py:1574). |
| **Change wake-word sleep time** | `WAKE_SLEEP_TIMEOUT` (main.py:102). |
| **Change stall timeout** | `_STALL_LIMIT` (main.py:178). |
| **Phone dashboard** | Off by default in SAM; press REMOTE, or set `dashboard_enabled: true` to start it at launch. |
| **Add a UI signal** | See §18, "Pattern for a new cross-thread UI feature". |
| **Test changes to providers** | `python -m providers._tests` |

**Rules to keep while customising** (from AGENTS.md): never touch Qt from tools; never report success without checking; never send child-process output to DEVNULL without logging; write settings only through `config_manager`; use only libraries already in `requirements.txt` (or add them there).

---

## 28. Glossary

| Term | Meaning |
|---|---|
| **Mark** | Version number (LVII = 57). |
| **Live / Live API** | Gemini's real-time audio WebSocket. |
| **Rung / ladder** | One model in an ordered fallback list. |
| **Cooldown / resting** | A model temporarily skipped after an error. |
| **Inline tool** | A tool declared in `main.py`. |
| **Action** | A bundled tool in `actions/` (PC control). |
| **Plugin** | A drop-in skill in `plugins/`. |
| **player** | The `SamUI` object given to tools. |
| **Outcome** | The `status=…` result line for the model. |
| **Untrusted wrapper** | `<<<UNTRUSTED …>>>` markers around external text. |
| **Routine** | A scheduled or unprompted action. |
| **Task** | Background work done by an agent. |
| **Agent** | A Markdown profile in `agents/`. |
| **Pipeline engine** | The local STT → LLM → TTS replacement for Live. |
| **Sidecar** | A provider used for one-shot side calls. |
| **Viseme** | A mouth shape for lip-sync. |
| **Echo tail** | The short window after speaking when the speakers are still sounding. |
| **Resumption handle** | Server token that lets a reconnect keep the conversation. |
| **HUD** | The window's visual interface. |
