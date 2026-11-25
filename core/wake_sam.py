"""
core/wake_sam.py — offline "Hey Sam" wake word, built on Vosk.

WHY VOSK AND NOT openWakeWord
    openWakeWord only ships a pretrained "Hey Sam". A new phrase means
    training a model — hours of synthetic data generation and training, more
    than a 4-core laptop should be asked to do. Vosk is a small offline speech
    recogniser that can be restricted to a GRAMMAR: it may only hear "hey sam",
    "hi sam", "okay sam" or "[unk]" (anything else). That turns it into a keyword
    spotter for any phrase, with no training.

    Model: vosk-model-small-en-in-0.4 (Indian English, 36 MB), so Indian
    pronunciation of "Sam" is what it was trained on.

HOW A DETECTION IS DECIDED
    The recogniser returns words with confidences. A wake is the wake word
    ("hey" / "hi" / "okay") immediately followed by "sam", both at or above the
    threshold (default 0.85, "wake_threshold" in config). A lone "sam", or
    "hey" + something else, never wakes it.

    Measured on synthetic speech (Piper voices): "Hey Sam", "Hi Sam, ...",
    and Hindi "हे सैम" woke it; "Hey man", "Say something", "Samsung phone",
    an English sentence and a Hindi sentence did not (8/8). A real microphone
    in a real room is noisier: raise the threshold if it wakes by itself,
    lower it if it misses you.

INTERFACE
    Same as core/wake_word.WakeWordDetector: start(), stop(), ready, reset(),
    feed(frame) from the mic callback (cheap, non-blocking), on_detect() from
    this module's own thread.
"""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import zipfile
from pathlib import Path
from typing import Callable

PHRASE = "Hey Sam"
MODEL_NAME = "vosk-model-small-en-in-0.4"
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
MODEL_DIR = MODELS_DIR / MODEL_NAME
SAMPLE_RATE = 16000
DEFAULT_THRESHOLD = 0.85
WAKE_WORDS = ("hey", "hi", "okay")
GRAMMAR = json.dumps([f"{w} sam" for w in WAKE_WORDS] + ["[unk]"])


def is_installed() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("vosk") is not None
    except Exception:
        return False


def is_ready() -> bool:
    """vosk importable and the model folder present (cheap, no model load)."""
    return is_installed() and (MODEL_DIR / "am").is_dir() and (MODEL_DIR / "conf").is_dir()


def install_and_download(logger: Callable[[str], None] = print,
                         notify: Callable[[str], None] | None = None) -> tuple[bool, str]:
    """pip-install vosk if missing and download the 36 MB model. Never raises."""
    tell = notify or (lambda _m: None)
    try:
        if not is_installed():
            logger("Wake word: installing vosk (one-time)…")
            tell("Wake word: installing vosk (one-time)…")
            r = subprocess.run([sys.executable, "-m", "pip", "install", "vosk"],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace")
            if r.returncode != 0:
                tail = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or [""]
                return False, f"pip install vosk failed: {tail[0][:160]}"
        if not is_ready():
            logger("Wake word: downloading the Hey Sam model (36 MB)…")
            tell("Wake word: downloading the Hey Sam model (36 MB)…")
            import urllib.request
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            tmp = MODELS_DIR / f"{MODEL_NAME}.zip.part"
            urllib.request.urlretrieve(MODEL_URL, tmp)
            with zipfile.ZipFile(tmp) as z:
                z.extractall(MODELS_DIR)
            tmp.unlink(missing_ok=True)
        if not is_ready():
            return False, "downloaded, but the model folder is incomplete."
        logger("Wake word: Hey Sam ready.")
        return True, "Wake word installed and ready."
    except Exception as e:
        return False, f"setup error: {e}"


def wake_in(result: dict, threshold: float) -> bool:
    """True if a Vosk result holds '<wake word> sam' with both words confident."""
    words = result.get("result") or []
    for a, b in zip(words, words[1:]):
        if (a.get("word") in WAKE_WORDS and b.get("word") == "sam"
                and min(float(a.get("conf", 0)), float(b.get("conf", 0))) >= threshold):
            return True
    return False


class SamWakeDetector:
    def __init__(self, on_detect: Callable[[], None],
                 threshold: float = DEFAULT_THRESHOLD,
                 logger: Callable[[str], None] = print,
                 notify: Callable[[str], None] | None = None):
        self._on_detect = on_detect
        self._threshold = threshold
        self._logger = logger
        self._notify = notify or (lambda _m: None)
        self._queue: queue.Queue = queue.Queue(maxsize=100)
        self._thread: threading.Thread | None = None
        self._running = False
        self._model = None
        self._rec = None
        self._ready = False
        self._reset_pending = False

    def start(self) -> bool:
        if self._running:
            return True
        try:
            import vosk
            vosk.SetLogLevel(-1)
            self._model = vosk.Model(str(MODEL_DIR))
            self._rec = self._new_recognizer()
        except Exception as e:
            self._logger(f"Wake word: could not load the Hey Sam model — {e}")
            self._notify("Wake word unavailable — use the WAKE NOW button.")
            self._model = self._rec = None
            return False
        self._running = True
        self._ready = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="SamWakeThread")
        self._thread.start()
        self._logger(f"Wake word: listening for '{PHRASE}'.")
        return True

    def _new_recognizer(self):
        import vosk
        rec = vosk.KaldiRecognizer(self._model, SAMPLE_RATE, GRAMMAR)
        rec.SetWords(True)
        return rec

    def stop(self) -> None:
        self._running = False
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass
        self._rec = self._model = None
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    def reset(self) -> None:
        self._reset_pending = True

    def feed(self, frame_int16) -> None:
        """Called from the mic callback: copy and queue, never block."""
        if not self._running:
            return
        try:
            data = (frame_int16[:, 0] if getattr(frame_int16, "ndim", 1) > 1
                    else frame_int16).tobytes()
            self._queue.put_nowait(data)
        except Exception:
            pass

    def _loop(self) -> None:
        while self._running:
            try:
                chunk = self._queue.get()
                if chunk is None or not self._running:
                    break
                if self._reset_pending:
                    self._reset_pending = False
                    self._rec = self._new_recognizer()
                if self._rec.AcceptWaveform(chunk):
                    hit = wake_in(json.loads(self._rec.Result()), self._threshold)
                else:
                    hit = False
                if hit:
                    self._drain()
                    self._rec = self._new_recognizer()   # one utterance = one wake
                    try:
                        self._on_detect()
                    except Exception as e:
                        self._logger(f"Wake word: on_detect error — {e}")
            except Exception as e:
                self._logger(f"Wake word: recognition error — {e}")

    def _drain(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except Exception:
            pass
