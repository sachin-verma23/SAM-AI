# SAM — Personal AI Assistant

**Owner:** Sachin Verma
**Platform:** Windows 10/11 (also runs on macOS and Linux)

SAM is a personal voice assistant for the desktop. It hears you (Hindi, English or Hinglish), answers out loud, controls your PC by voice, remembers what matters to you, and works both online (Google Gemini Live) and offline (Ollama + Whisper + Piper).

> Licence: **CC BY-NC 4.0** — personal and non-commercial use only. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

---

## Quick start

```powershell
git clone https://github.com/sachin-verma23/SAM-AI.git
cd SAM-AI
py -m venv .venv
.\.venv\Scripts\python.exe setup.py
.\.venv\Scripts\python.exe setup_sam.py
.\.venv\Scripts\python.exe main.py
```

`setup_sam.py` installs everything else SAM uses — Ollama and the `llama3.2:3b` model, Whisper, the Hindi/English voices, the "Hey Sam" and gesture models — and writes the tuned offline + auto settings. It is safe to run again; finished steps are skipped. Options: `--yes` (no questions), `--skip-ollama`, `--skip-models`.

On first launch, paste a free Gemini API key (from https://aistudio.google.com/apikey). It is saved locally in `config/api_keys.json`, which git ignores.

Self-tests (no network or key needed):
```powershell
.\.venv\Scripts\python.exe -m tests.sam_tests
.\.venv\Scripts\python.exe -m providers._tests
```

## What SAM does

| | |
|---|---|
| 🗣️ Voice | Hindi, English and Hinglish. Choose with "ab se Hinglish mein baat karo" or leave it on auto |
| 🌐 Online + offline | Gemini Live while online; Ollama (llama3.2:3b) + Whisper + Piper offline, switched automatically |
| 🎙️ Wake word | "Hey Sam" (offline, Vosk). Turn it on in ⚙ → CONTROLS → WAKE WORD |
| 🧠 Memory | Remembers facts and every conversation locally; view, edit, add and delete in the memory panel |
| 🖥️ PC control | Apps, files, volume, brightness, media, windows, browser, reminders, routines |
| ✅ Safety | Delete, overwrite, move, send message, shutdown and installs wait for your CONFIRM on screen |
| ✋ Gestures | Webcam hand gestures for media, volume and navigation (off by default) |
| 🛠️ Self-update | Ask SAM to add a feature or setting to itself; it codes, tests, and applies only after your CONFIRM (and can roll back) |
| 📊 HUD | Animated assistant with live AI / internet / mic / camera / wake-word status |

## Offline mode

`setup_sam.py` sets it up completely. On a 4-core laptop the offline model needs about a minute to warm up after a switch, then answers in 5–20 seconds. Online answers take about a second.

## Documentation

| File | What it covers |
|---|---|
| [brain.md](brain.md) | How the whole project works, every module and setting, and how to customise it |
| [AUDIT_REPORT.md](AUDIT_REPORT.md) | Known problems, feature status, fix history |
| [ROADMAP.md](ROADMAP.md) | SAM's development plan and progress |
| [AGENTS.md](AGENTS.md) | Rules for anyone (or any AI) writing code here |

## Your data

Everything stays on your PC: settings and keys in `config/api_keys.json`, memory in `memory/`, reports in `reports/`. None of it is committed to git. Online mode streams your voice to Google Gemini while a session is open; offline mode sends nothing anywhere.

## Licence

CC BY-NC 4.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
