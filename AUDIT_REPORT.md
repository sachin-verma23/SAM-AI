# Mark LVII (JARVIS) — Audit Report

**Repo:** https://github.com/FatihMakes/Mark-LVII (commit `752ff61`)
**Local copy:** `c:\Users\Lenovo\Desktop\Projects\SAM AI`
**Audit date:** 2026-11-24
**Scope:** All 106 tracked files (~56,600 lines). I read every entry point, `main.py` and the memory and config layer in full. For every other module I read its docstring and structure, and the parts that matter in detail. I also ran the project's own self-test and git checks, and used the app's logs from this session.

Companion document: [brain.md](brain.md) explains how everything works. This report covers what is **wrong**, what is **missing** and what **works**.

---

## 0. Summary

| | |
|---|---|
| Overall code quality | **High.** Unusually well commented, defensive, and built around "never claim a success you did not check". |
| Bundled self-test | `python -m providers._tests` → **99 passed, 0 failed** (run 2026-11-24). |
| Biggest problem | **About 22 plugins the README advertises are not in the repo** (WhatsApp driver, Gmail, Calendar, Telegram, screen agent, image generator, quiz, Pomodoro…). Several features silently fall back to weaker paths. |
| Biggest security problem | **`.gitignore` is broken.** Your Gemini API key file (`config/api_keys.json`) is **not** ignored. A `git add .` followed by a push would publish it. |
| Biggest data-safety problem | `memory/long_term.json` is written non-atomically. One crash mid-write, and the next save **wipes all stored memory**. |
| Runtime used here | Python **3.14.7** in `.venv`. That is above the 3.11–3.13 range the project is tested on. It starts and runs, but optional parts (wake word) are at risk. |
| Licence | **CC BY-NC 4.0 — non-commercial only.** You may customise it for personal use. You may not sell it or use it commercially. |

### Severity scale
- **CRITICAL**: can leak secrets or lose data now
- **HIGH**: a feature is broken or misleading, or a real security weakness
- **MEDIUM**: wrong behaviour in some situations
- **LOW**: cleanup, consistency, dead code, docs

---

## 1. Problems found

### CRITICAL

#### C1. `.gitignore` does not ignore your API key and other secrets
> **Status: FIXED** in this repo (2026-11-24). Comments were moved to their own lines and the missing paths added. Re-checked with `git check-ignore`.

**File:** [.gitignore](.gitignore)
**Verified with** `git check-ignore`:

| Path | Ignored? |
|---|---|
| `config/api_keys.json` (Gemini key, all credentials) | **NO** |
| `config/certs/` (dashboard TLS private key) | **NO** |
| `config/whatsapp_web/` (a linked WhatsApp session) | **NO** |
| `token*.json`, `client_secret*.json` (Google OAuth) | **NO** |
| `memory/routines.json`, `memory/tasks/`, `reports/`, `uploads/` | **NO** (the README says they are) |
| `memory/long_term.json`, `.venv/` | yes |

**Why:** git only treats `#` as a comment at the **start** of a line. Lines like
`config/api_keys.json          # your Gemini API key…` make the whole line, comment included, into the pattern, so it matches nothing.
**Impact:** `git status` already shows `?? config/api_keys.json`. If you push a fork, your key goes public.
**Fix:** put every comment on its own line, and add the missing paths: `memory/routines.json`, `memory/tasks/`, `reports/`, `uploads/`, `providers/voices/`, `config/*.broken-*`.

#### C2. Memory file can be wiped by one bad write
**File:** [memory/memory_manager.py](memory/memory_manager.py)
- `save_memory()` (line ~118), `save_session_summary()` (~431) and `pop_last_session()` (~457) write `long_term.json` **in place** with `write_text`. The config file uses a safe temp-file-plus-rename (`config_manager._write_config`); memory does not.
- `load_memory()` returns an **empty memory** when the file fails to parse (line ~71).
- `update_memory()` then saves that empty dict plus the one new fact, and **everything else is gone for good**.
- `update_memory()` also takes the lock twice, once in load and once in save, with a gap between. Two writers at the same moment lose one update. For example, a `save_memory` tool call can race the session-summary save at shutdown.

**Fix:** write atomically (tmp + `os.replace`), back up a file that will not parse instead of overwriting it, and hold one lock across load-modify-save.

---

### HIGH

#### H1. About 22 advertised plugins are missing from the repository
The README "Project Structure" lists these files under `plugins/`. **The repo contains only `plugins/__init__.py` and `plugins/_template.py`.**

Missing: `_whatsapp_core.py`, `whatsapp_call.py`, `whatsapp_guard.py`, `telegram_remote.py`, `chat_takeover.py`, `screen_agent.py`, `gmail_control.py`, `calendar_control.py`, `obsidian_vault.py`, `document_review.py`, `excel_writer.py`, `image_generator.py`, `upload_video.py`, `printer_control.py`, `home_assistant.py`, `shopping_list.py`, `pomodoro.py`, `water_reminder.py`, `quiz.py`, `spaced_repetition.py`, `calorie_counter.py`, `pushup_counter.py`. The code also mentions `cloud_agent.py`, which is missing too.

(`code_helper`, `dev_agent`, `game_updater`, `flight_finder` and `youtube_video` **do** exist, but in `actions/`, not `plugins/`. The README places them wrongly.)

Knock-on effects:
- **WhatsApp sending is "blind".** `actions/send_message.py:203` imports `plugins._whatsapp_core`, fails, and falls back to keystrokes with fixed sleeps. Nothing checks which window received them. **This happened in this session:** the log shows `WhatsApp driver unavailable … typing blind` and `status=unverified` for messages to "Kapendra UNIQUE MIS".
- **Orphaned code:** `core/cloud.py` (2,933 lines, the server "second body"), `core/screenview.py` (2,225) and `core/screenact.py` (1,039) are only reachable from the missing plugins. They are about 6,200 lines of unused code in this repo.
- **Unused dependencies in `requirements.txt`:** `tinytuya`, `paho-mqtt`, `google-api-python-client`, `google-auth-oauthlib`. No file imports them.
- The UI and prompt still mention features that are not there, for example `show_quiz`, `show_review`, `generate_image` in tool descriptions, and the `[FOLDER_UPLOADED]` flow.

**Fix:** either get the plugin files from the author (YouTube, Instagram or GitHub issues) or write your own. Meanwhile, update the README and requirements, and decide whether to keep `core/cloud.py`, `screenview.py` and `screenact.py`.

#### H2. The phone dashboard always runs, on your whole network, unencrypted by default
**Files:** [main.py:2720-2730](main.py#L2720-L2730), [dashboard/server.py](dashboard/server.py)
- It starts at **every launch**, even if you never press REMOTE. It binds to `0.0.0.0:8000`, which means every device on your Wi-Fi can reach it.
- HTTPS is **off** by default (`dashboard_https` must be set to `true`). Over plain HTTP the page cannot use WebCrypto, so commands, transcripts and file uploads cross the LAN **in clear text**.
- Mitigations already present: an 8-character one-time pairing key with a 10-minute expiry, login throttling, device tokens and revoke-all.
- The module docstring still says "TLS is required", but the code says the opposite.

**Fix:** start the server only when REMOTE is pressed, or add a `dashboard_enabled` setting. Use HTTPS on shared networks.

#### H3. Keystroke automation can type into the wrong window
**Files:** [actions/send_message.py:142-178](actions/send_message.py#L142-L178) (Telegram, Signal, Discord, Instagram, Messenger, and WhatsApp without its driver), parts of `actions/game_updater.py`
Fixed `time.sleep()` gaps followed by `pyautogui` keys. On a slow machine or with a pop-up, the text lands in whatever window has focus, which can be the wrong chat. The code is honest about it (it returns `unverified`), but the risk is real for messages.

#### H4. Python 3.14 is outside the supported range
`setup.py` declares tested range 3.11–3.13. The app starts on 3.14, but:
- `main.py:1168-1181` (`_ensure_executor`) reaches into private asyncio internals (`loop._default_executor`, `_executor_shutdown_called`). These are the first things to break on a new Python.
- The optional wake-word package (`openwakeword` and its runtime) may not have 3.14 wheels.

**Recommendation:** build the venv with Python 3.12 or 3.13 for daily use.

---

### MEDIUM

| # | Issue | Where | Detail |
|---|---|---|---|
| M1 | **"1007" treated as a bad API key** | [main.py:2991](main.py#L2991) | Any error containing `1007` opens the "re-enter your API key" screen. 1007 is the generic WebSocket "invalid payload" close code; `core/gemini.py` itself says unsupported modalities return 1007. `core.gemini.is_key_error()` (the correct check) is not used here. |
| M2 | Network-error detection by message text | [main.py:3002-3005](main.py#L3002-L3005) | It looks for words like `"TimeoutError"` and `"OSError"` inside `str(e)`. A bare `TimeoutError()` has an empty message, so it is not seen as a network error and the backoff never grows. |
| M3 | `user_data` silently falls back to **random fake data** | [actions/computer_control.py:659-666](actions/computer_control.py#L659-L666) | If your name or email is not in memory, it returns a random name or email as if it were yours. The model can type that into a real form. |
| M4 | Coding agent installs packages **into JARVIS's own venv** | [actions/dev_agent.py:265-293](actions/dev_agent.py#L265-L293) | Uses `sys.executable -m pip install <model-chosen names>`. A hallucinated or typo-squatted name gets installed, and a dependency conflict can break the assistant itself. |
| M5 | `_open_vscode` always "succeeds" | [actions/dev_agent.py:300-318](actions/dev_agent.py#L300-L318) | `Popen(..., shell=True)` returns as soon as a shell starts. That is the same false-success bug the project fixed in `open_app`. |
| M6 | Weather tool doesn't fetch weather | [actions/weather_report.py](actions/weather_report.py) | It only opens a Google search in the browser and says "Showing the weather". The README says "Live weather data". The assistant cannot speak the forecast. |
| M7 | Tool calls run one after another inside the receive loop | [main.py:2077-2086](main.py#L2077-L2086) | Several function calls in one turn run serially, so one slow tool (for example `close_app`, 6 s in this session's log) delays the others. |
| M8 | Unprompted speech is on all day by default | `memory/routines.json` | The news watch runs every 30 min from 00:00 to 23:59, plus a check-in after 15 idle minutes. Quiet hours are **off** by default. |
| M9 | Clipboard panel appears on every copy of 10+ characters | [gui/window.py:2841-2847](gui/window.py#L2841-L2847) | It shows the copied text on screen, including passwords from a password manager. Nothing is sent anywhere until you click an action. |

---

### LOW (cleanup, consistency, docs)

| # | Issue | Where |
|---|---|---|
| L1 | Hard-coded **"Sir"** in spoken errors, which ignores the user-name and address rules | `main.py:1374`, `core/plugin_loader.py:129`, `actions/weather_report.py:14,29,33`, `actions/code_helper.py:494`, `plugins/_template.py:58` |
| L2 | Dead legacy code from "MARK XL", never imported: `core/stt.py`, `core/tts.py`, `core/llm_client.py`, `core/installer.py` (~1,260 lines) | `core/` |
| L3 | `dashboard/static/crypto-js.min.js` (60 KB) is unused; `app.html` says it was replaced by WebCrypto | `dashboard/static/` |
| L4 | `JarvisUI("face.png")`: the file does not exist and the argument is unused | `main.py:3053` |
| L5 | Typo `self._asst_name = "JARVI    S"` (overwritten on first connect, so harmless) | `main.py:598` |
| L6 | A global `subprocess.Popen` monkey-patch drops every caller's `startupinfo` | `main.py:6-15` |
| L7 | `asyncio.create_task(self._dashboard.broadcast(...))` without keeping a reference (the project's own `_keep_task()` exists for this) | `main.py:2042, 2061` |
| L8 | Leftover `_get_api_key()` helpers are copied into several actions. Model calls do go through `core.gemini` correctly, but each copy re-reads `api_keys.json` on its own | `code_helper.py`, `computer_control.py`, `desktop.py`, `flight_finder.py`, `web_search.py`, `youtube_video.py`, `dev_agent.py` |
| L9 | README errors: plugin locations, "HTTP by default" vs the dashboard docstring, `setup.py` banner says "MARK LIV" | `readme.md`, `setup.py`, `dashboard/server.py` |
| L10 | API keys are stored in plain text (documented, but worth knowing) | `config/api_keys.json` |
| L11 | `manage_monitor` refuses crypto, finance and trading topics. This is a policy choice; remove it if you want those topics | `main.py:440`, `actions/background_monitor.py` |
| L12 | `setup.py` prints a broken pywin32 post-install path (`Scripts\Scripts\…`). I fixed it manually during install | `setup.py` |

---

## 2. Features — what actually works in this copy

✅ = code present and wired in · ⚠️ = present but limited · ❌ = advertised but missing

### Conversation and core
| Feature | Status | Notes |
|---|---|---|
| Real-time voice chat (Gemini Live, `gemini-3.1-flash-live-preview`) | ✅ | Falls back to `gemini-2.5-flash-native-audio-preview-12-2025` on quota errors |
| Text input box | ✅ | Same session as voice |
| Session resumption (reconnect keeps context) | ✅ | Handle kept in RAM only |
| Stall watchdog (30 s with no reply → reconnect) | ✅ | |
| Unlimited session length (sliding-window compression) | ✅ | |
| Barge-in by voice | ❌ disabled | Code exists in `core/echo.py` but is switched off; use the INTERRUPT button |
| Echo guard (does not answer itself) | ✅ | |
| Push-to-talk (Ctrl+Space) | ✅ | Global on Windows |
| Wake word "Hey Jarvis" | ⚠️ | One-click install; Python 3.14 risk |
| Proactive audio (ignores speech not aimed at it) | ✅ | Auto-disabled if the server rejects it |
| Local engine: Whisper + Ollama/LM Studio/OpenAI-compatible + Piper/System/ElevenLabs | ✅ | ⚙ → ENGINE & PROVIDERS |
| One-shot model ladder with cooldowns | ✅ | `core/gemini.py` |

### Memory and safety
| Feature | Status |
|---|---|
| Long-term memory (`save_memory` / `recall_memory`), memory panel | ✅ (see C2) |
| Session summary → "last time we talked about…" | ✅ |
| Undo for files and settings | ✅ |
| Confirmation gate (shutdown, restart, Wi-Fi) that the model cannot fake | ✅ |
| Untrusted-content wrapper for web pages and files | ✅ |
| Status vocabulary done / unverified / failed / started / ask | ✅ |

### Tools (`actions/`, 21 total: 13 file-backed + 8 inline)
| Tool | Status | What it does |
|---|---|---|
| `open_app` | ✅ | Launches without a shell; checks the process table |
| `computer_settings` | ✅ | Volume, brightness, media keys, windows, tabs, zoom, keys, lock, dark mode, Wi-Fi, restart, shutdown |
| `computer_control` | ✅ (M3) | Type, click, hotkeys, scroll, close app, screen find |
| `browser_control` | ✅ | Playwright; Chrome, Edge, Firefox, Opera, Brave, Vivaldi |
| `file_controller` | ✅ | List, create, delete (to the Recycle Bin), move, copy, rename, find, disk usage |
| `file_processor` | ✅ | Images, PDF, DOCX, CSV/XLSX, JSON, code, audio, video, ZIP, PPTX |
| `web_search` | ✅ | Gemini grounded search plus DuckDuckGo; modes search, news, research, price, compare |
| `weather_report` | ⚠️ (M6) | Opens Google only |
| `send_message` | ⚠️ (H1, H3) | Blind keystrokes on every platform in this copy |
| `reminder` | ✅ | OS scheduler (Windows Task Scheduler) **and** a spoken routine |
| `routines` | ✅ | Say, prompt or task; once, weekly, monthly or interval; startup, idle; quiet hours |
| `background_tasks` | ✅ | Background agents (`agents/*.md`), checkpointed, resumable |
| `video_player` | ✅ | Plays a file, URL or YouTube video on the HUD (yt-dlp) |
| `youtube_video` | ✅ | Play, summarise, info, trending |
| `code_helper` | ✅ | Write, edit, explain or run single files |
| `dev_agent` | ✅ (M4, M5) | Multi-file "build" or "improve folder" coding agent |
| `flight_finder` | ✅ | Scrapes Google Flights via the browser |
| `game_updater` | ✅ | Steam and Epic: list, update, install, schedule |
| `desktop_control` | ✅ | Wallpaper, organise or clean the desktop |
| Inline: `system_status`, `screen_process` (screen/webcam vision), `close_camera`, `manage_monitor`, `save_memory`, `recall_memory`, `undo`, `shutdown_jarvis` | ✅ | |

### Proactive and background
| Feature | Status |
|---|---|
| Opening briefing (greeting + news + last session) | ✅ |
| Idle check-in | ✅ |
| News-topic watch | ✅ |
| Hardware alerts (CPU, RAM, GPU, temperature) | ✅ |
| Deep research with quotes checked in code | ✅ |

### UI
| Feature | Status |
|---|---|
| Command-center HUD, 3-D reactor **or** holographic face with lip-sync | ✅ |
| Live theming (hue wheel), voice picker (5 voices), rename assistant and user | ✅ |
| Audio device picker with mic test | ✅ |
| Plugin manager and plugin settings panels | ✅ (but there are no plugins to manage) |
| Clipboard quick actions | ✅ (M9) |
| Auto-start with Windows (`HKCU\…\Run\JARVIS_AI`) | ✅ |
| Phone dashboard (QR pairing) | ✅ (H2) |

### Advertised but missing (H1)
❌ Verified WhatsApp sending, WhatsApp calls and call-guard · Telegram remote · Chat takeover · Screen agent · Gmail · Google Calendar · Obsidian · Document review UI · Excel writer · Image generation · YouTube upload · 3-D printer (MQTT) · Smart home (Tuya) · Shopping list · Pomodoro · Water reminder · Quiz · Flashcards · Calorie counter (webcam) · Push-up counter (webcam) · Cloud server body

---

## 3. Good practices already in the code (keep them when customising)
1. **Honest outcomes.** Tools return `done` only after checking. Keep using `core/outcome.py`.
2. **One model gateway.** `core/gemini.py` gives you timeouts, the ladder, cooldowns and the provider fallback.
3. **Threading rule.** Tools never touch Qt widgets; they go through `player.*` methods (see AGENTS.md).
4. **Atomic config writes and a lock** in `memory/config_manager.py`.
5. **SSRF guard** in `core/tasks/web.py`: background agents cannot fetch private or loopback addresses.
6. **Background agents can never act**, and web access and memory access never go to the same agent.
7. **Lazy imports.** Heavy libraries load only when used (`core/lazyimport.py`).

---

## 4. Recommended fix order
1. **Fix `.gitignore` (C1)** before any `git add`, and before you create your own repo.
2. **Make memory writes atomic (C2).**
3. Decide on the plugins (H1): ask the author for them, rebuild the ones you need (WhatsApp, Gmail, reminders UI), or remove the references.
4. Switch the venv to Python 3.12 or 3.13 (H4).
5. Gate the dashboard behind a setting (H2).
6. Fix the `1007` check (M1) and the weather tool (M6).
7. Clean up: dead code (L2, L3), remove unused requirements, replace "Sir" with the configured address form (L1).

---

## 5. Fix status after SAM v1.0 (2026-11-24)

| # | Issue | Status | How |
|---|---|---|---|
| C1 | `.gitignore` leaked secrets | ✅ Fixed | Comments on their own lines; personal data paths added |
| C2 | Memory wipe on a bad write | ✅ Fixed | Atomic writes, unreadable file kept as `.broken-<time>`, one lock across read-modify-write |
| H1 | 22 plugins missing | ⚠️ Partly | Their dead dependencies were removed; their features are still missing (WhatsApp sending stays blind) |
| H2 | Dashboard always on, LAN, HTTP | ✅ Fixed | Starts only on REMOTE (or `dashboard_enabled`); port 8765 (8000 collided with Laravel) |
| H3 | Blind keystrokes | ⚠️ Mitigated | Every message now needs CONFIRM first; typing is still unverified |
| H4 | Python 3.14 | ✅ Checked | All needed packages have 3.14 wheels; app, tests, Vosk, MediaPipe, Whisper, Piper all run |
| M1 | "1007" = bad key | ✅ Fixed | Uses `gemini.is_key_error` |
| M2 | Network errors by text | ✅ Fixed | Also matched by exception type |
| M3 | `user_data` fake data | ⏳ Open | |
| M4 | dev_agent installs into SAM's venv | ⚠️ Mitigated | Every install now needs CONFIRM |
| M5 | `_open_vscode` false success | ⏳ Open | |
| M6 | Weather only opens a browser | ⏳ Open | |
| M7 | Serial tool calls | ⏳ Open (by design of the Live loop) | |
| M8 | Noisy routines | ✅ Fixed | 30-min check-in, 2-hourly news 08–22, quiet hours 23–07 |
| M9 | Clipboard panel shows copied text | ⏳ Open | |
| L1 | Hard-coded "Sir" | ✅ Fixed | 56 strings neutralised |
| L2 | Dead MARK XL modules | ✅ Removed | |
| L3 | Unused crypto-js | ✅ Removed | |
| L5 | `"JARVI    S"` typo | ✅ Fixed | Now `"SAM"` |
| L9 | README errors | ✅ Fixed | New README; original kept in `docs/` |
| L12 | Wrong pywin32 path in setup | ✅ Fixed | `sysconfig` scripts path, checked in a fresh interpreter |
