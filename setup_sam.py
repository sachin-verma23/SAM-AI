"""
setup_sam.py — everything SAM needs beyond `setup.py`, in one command.

Run it from the repo folder, with the project's virtual environment:

    .\\.venv\\Scripts\\python.exe setup.py        (Python packages, browsers)
    .\\.venv\\Scripts\\python.exe setup_sam.py    (this file)
    .\\.venv\\Scripts\\python.exe main.py         (first launch asks for the Gemini key)

What it does (each step is skipped when it is already done, so it is safe to
run again at any time):

    1. Python packages for offline voice and the wake word
       (faster-whisper, piper-tts, vosk) and an OpenCV conflict check
    2. Ollama: finds it, offers to install it with winget, starts the server,
       and downloads the llama3.2:3b model (~2 GB)
    3. Models: Piper voices (Hindi + English), Whisper "small", the "Hey Sam"
       wake-word model, the hand-gesture model
    4. Settings: offline + auto mode exactly as tuned on the main laptop
       (prompt-format tools, warm-up friendly limits)
    5. A final check, with a short report of what is ready

Options:
    --yes            answer "yes" to every question (non-interactive)
    --skip-ollama    do not install / start / pull Ollama
    --skip-models    do not download voices or models
    --model NAME     the Ollama model to use (default llama3.2:3b)

It never prints or changes your Gemini API key.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "llama3.2:3b"
VOICES = ("hi_IN-rohan-medium", "en_US-lessac-medium")
WHISPER_SIZE = "small"
EXTRA_PACKAGES = {"faster_whisper": "faster-whisper", "piper": "piper-tts", "vosk": "vosk"}

RESULTS: list[tuple[str, bool, str]] = []


# ── helpers ──────────────────────────────────────────────────────────────────

def say(msg: str) -> None:
    print(msg, flush=True)


def step(title: str) -> None:
    say(f"\n━━ {title} " + "━" * max(3, 60 - len(title)))


def record(name: str, ok: bool, note: str = "") -> None:
    RESULTS.append((name, ok, note))
    say(f"   {'✅' if ok else '❌'} {name}" + (f" — {note}" if note else ""))


def ask(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    try:
        return input(f"   {question} [Y/n] ").strip().lower() in ("", "y", "yes", "haan", "ha")
    except EOFError:
        return False


def pip(*args: str) -> bool:
    r = subprocess.run([sys.executable, "-m", "pip", *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-3:]
        say("   pip: " + " | ".join(tail))
    return r.returncode == 0


def retry(fn, attempts: int = 3, wait: float = 10.0):
    """Run fn() until it returns a falsy error string; flaky Wi-Fi is common."""
    err = ""
    for i in range(attempts):
        err = fn()
        if not err:
            return ""
        if i + 1 < attempts:
            say(f"   … {err} — retrying in {wait:.0f} s")
            time.sleep(wait)
    return err


def http_ok(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


# ── 0. environment ───────────────────────────────────────────────────────────

def check_environment() -> None:
    step("0. Environment")
    v = sys.version_info
    record("Python", v >= (3, 11), f"{v.major}.{v.minor} at {sys.executable}")
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    record("Virtual environment", in_venv,
           "" if in_venv else "run this with .\\.venv\\Scripts\\python.exe")
    if not in_venv:
        say("   Continuing anyway, but packages will go into the system Python.")
    if importlib.util.find_spec("PyQt6") is None:
        record("setup.py done", False, "run .\\.venv\\Scripts\\python.exe setup.py first")
        sys.exit(1)
    record("setup.py done", True)


# ── 1. packages ──────────────────────────────────────────────────────────────

def install_packages() -> None:
    step("1. Packages for offline voice and the wake word")
    missing = [pkg for mod, pkg in EXTRA_PACKAGES.items() if importlib.util.find_spec(mod) is None]
    if missing:
        say(f"   Installing {', '.join(missing)} …")
        pip("install", *missing)
    for mod, pkg in EXTRA_PACKAGES.items():
        record(pkg, importlib.util.find_spec(mod) is not None)

    # mediapipe needs opencv-contrib-python; opencv-python next to it breaks cv2.
    r = subprocess.run([sys.executable, "-m", "pip", "list", "--format=json"],
                       capture_output=True, text=True)
    try:
        names = {p["name"].lower() for p in json.loads(r.stdout)}
    except Exception:
        names = set()
    if "opencv-python" in names and "opencv-contrib-python" in names:
        say("   Two OpenCV packages found — keeping opencv-contrib-python only …")
        pip("uninstall", "-y", "opencv-python")
        pip("install", "--force-reinstall", "--no-deps", "opencv-contrib-python")
    check = subprocess.run([sys.executable, "-c", "import cv2, mediapipe"], capture_output=True)
    record("OpenCV + MediaPipe", check.returncode == 0)


# ── 2. Ollama ────────────────────────────────────────────────────────────────

def find_ollama() -> str:
    found = shutil.which("ollama")
    if found:
        return found
    for p in (Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
              Path(os.environ.get("ProgramFiles", "")) / "Ollama" / "ollama.exe"):
        if p.is_file():
            return str(p)
    return ""


def setup_ollama(model: str, assume_yes: bool) -> None:
    step("2. Ollama (offline AI)")
    exe = find_ollama()
    if not exe and sys.platform == "win32" and shutil.which("winget"):
        if ask("Ollama is not installed. Install it now with winget?", assume_yes):
            say("   Installing Ollama (a few minutes) …")
            subprocess.run(["winget", "install", "--id", "Ollama.Ollama", "-e",
                            "--accept-package-agreements", "--accept-source-agreements",
                            "--silent"])
            exe = find_ollama()
    if not exe:
        record("Ollama installed", False, "install it from https://ollama.com and run this again")
        return
    record("Ollama installed", True, exe)

    if not http_ok(f"{OLLAMA_URL}/api/version"):
        say("   Starting the Ollama server …")
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=flags)
        for _ in range(30):
            if http_ok(f"{OLLAMA_URL}/api/version"):
                break
            time.sleep(1)
    running = http_ok(f"{OLLAMA_URL}/api/version")
    record("Ollama server", running, OLLAMA_URL)
    if not running:
        return

    def have_model() -> bool:
        try:
            with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as r:
                tags = json.loads(r.read())
            return any(m.get("name") == model or m.get("model") == model
                       for m in tags.get("models", []))
        except Exception:
            return False

    if not have_model():
        say(f"   Downloading {model} (about 2 GB; progress is shown below) …")
        subprocess.run([exe, "pull", model])
    record(f"Model {model}", have_model())


# ── 3. models ────────────────────────────────────────────────────────────────

def download_models() -> None:
    step("3. Voices and models")

    # Piper voices
    try:
        from providers import tts_piper
        for v in VOICES:
            if v in tts_piper.installed():
                record(f"Voice {v}", True, "already here")
                continue

            def get(v=v):
                try:
                    tts_piper.download(v)
                    return ""
                except Exception as e:
                    return str(e)[:120]
            err = retry(get)
            record(f"Voice {v}", not err, err)
    except Exception as e:
        record("Piper voices", False, str(e)[:120])

    # Whisper "small" (downloads into the Hugging Face cache on first load)
    try:
        from faster_whisper import WhisperModel

        def load():
            try:
                WhisperModel(WHISPER_SIZE, device="cpu", compute_type="int8", cpu_threads=4)
                return ""
            except Exception as e:
                return str(e)[:120]
        say(f"   Preparing Whisper '{WHISPER_SIZE}' (~480 MB the first time) …")
        err = retry(load)
        record(f"Whisper {WHISPER_SIZE}", not err, err)
    except Exception as e:
        record(f"Whisper {WHISPER_SIZE}", False, str(e)[:120])

    # "Hey Sam"
    try:
        from core import wake_sam
        ok, msg = (True, "already here") if wake_sam.is_ready() else wake_sam.install_and_download(
            logger=lambda m: None)
        record('Wake word "Hey Sam"', ok, msg)
    except Exception as e:
        record('Wake word "Hey Sam"', False, str(e)[:120])

    # Hand gestures — verify the zip: a cut download is otherwise found only
    # when the gesture switch is pressed ("Unable to open zip archive").
    try:
        import zipfile
        from core import gestures

        def fetch():
            if gestures.MODEL_PATH.exists():
                try:
                    zipfile.ZipFile(str(gestures.MODEL_PATH)).namelist()
                    return ""
                except Exception:
                    gestures.MODEL_PATH.unlink()
            err = gestures.download_model()
            if err:
                return err
            try:
                zipfile.ZipFile(str(gestures.MODEL_PATH)).namelist()
                return ""
            except Exception:
                gestures.MODEL_PATH.unlink(missing_ok=True)
                return "download was incomplete"
        err = retry(fetch)
        record("Gesture model", not err, err)
    except Exception as e:
        record("Gesture model", False, str(e)[:120])


# ── 4. settings ──────────────────────────────────────────────────────────────

def write_settings(model: str) -> None:
    step("4. Offline + auto settings")
    from memory import config_manager as cm
    from providers import registry

    LLM, STT, TTS = "openai_compat@ollama", "whisper@local", "piper@piper"
    cm.save_providers(
        mode="auto",
        pipeline={"stt": STT, "llm": LLM, "tts": TTS},
        creds={
            # tool_format "prompt": tools live in the cached system prompt. With
            # native tools llama3.2's template re-sends them every turn, which on
            # a laptop CPU cost ~100 s per reply.
            LLM: {"catalog": "ollama", "base_url": f"{OLLAMA_URL}/v1", "model": model,
                  "api_key": "", "max_tools": "12", "max_tool_chars": "4000",
                  "timeout": "120", "tool_format": "prompt"},
            STT: {"catalog": "local", "backend": "local", "model": WHISPER_SIZE,
                  "device": "cpu", "language": ""},
            TTS: {"catalog": "piper", "voice": VOICES[0], "follow_language": "1",
                  "speed": 1.0},
        },
        sidecar=LLM, sidecar_first=False)
    record("Engine mode", cm.get_provider_mode() == "auto", cm.get_provider_mode())
    for pid in (LLM, STT, TTS):
        missing = registry.missing_fields(pid, cm.get_provider_config(pid))
        record(f"Settings {pid}", not missing, ", ".join(missing))
    key_set = bool(str(cm.load_api_keys().get("gemini_api_key") or "").strip())
    record("Gemini API key", key_set,
           "already saved" if key_set else "SAM will ask for it on first launch")


# ── 5. report ────────────────────────────────────────────────────────────────

def report() -> int:
    step("Summary")
    bad = [r for r in RESULTS if not r[1] and r[0] != "Gemini API key"]
    for name, ok, note in RESULTS:
        say(f"   {'✅' if ok else '❌'} {name}" + (f" — {note}" if note and not ok else ""))
    say("")
    if bad:
        say("Some steps did not finish. Fix the ❌ lines above (most often: no internet,")
        say("or Ollama not installed) and run this script again — finished steps are skipped.")
    else:
        say("All set. Start SAM with:   .\\.venv\\Scripts\\python.exe main.py")
        say("Online it uses Gemini; when the internet drops it switches to the local AI")
        say("(about a minute to warm up, then 5–20 s per reply on a laptop CPU).")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="One-time SAM setup after setup.py")
    ap.add_argument("--yes", action="store_true", help="answer yes to every question")
    ap.add_argument("--skip-ollama", action="store_true")
    ap.add_argument("--skip-models", action="store_true")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args()

    say("SAM setup — offline AI, voices, wake word, gestures and settings")
    check_environment()
    install_packages()
    if not args.skip_ollama:
        setup_ollama(args.model, args.yes)
    if not args.skip_models:
        download_models()
    write_settings(args.model)
    return report()


if __name__ == "__main__":
    sys.exit(main())
