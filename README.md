# SAM — Personal AI Assistant

**Owner:** Sachin Verma
**Platform:** Windows 10/11 (also runs on macOS and Linux)

SAM is a personal voice assistant for the desktop. It hears you (Hindi, English or Hinglish), answers out loud, controls your PC by voice, remembers what matters to you, and works both online (Google Gemini Live) and offline (Ollama + Whisper + Piper).

> SAM is built on **[MARK LVII](https://github.com/FatihMakes/Mark-LVII) by FatihMakes** and keeps its licence, **CC BY-NC 4.0**: personal and non-commercial use only. The original README is kept in [docs/MARK-LVII-README.md](docs/MARK-LVII-README.md).

---

## Quick start

```powershell
git clone https://github.com/sachin-verma23/SAM-AI.git
cd SAM-AI
py -m venv .venv
.\.venv\Scripts\python.exe setup.py
.\.venv\Scripts\python.exe main.py
```

On first launch, paste a free Gemini API key (from https://aistudio.google.com/apikey). It is saved locally in `config/api_keys.json`, which git ignores.

Self-tests (no network or key needed):
```powershell
.\.venv\Scripts\python.exe -m tests.sam_tests
.\.venv\Scripts\python.exe -m providers._tests
```

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

CC BY-NC 4.0, inherited from MARK LVII by FatihMakes. See [LICENSE](LICENSE).
