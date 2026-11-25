"""
core/wake_word.py — SAM's wake word: "Hey Sam".

The detector itself lives in core/wake_sam.py (offline, Vosk, Indian English
model). This module is the stable entry point main.py and the settings drawer
use, so the engine behind it can change without touching them.

Design goals:
  • ZERO cost when the feature is off — nothing is imported or loaded until
    the user switches the wake word on.
  • ZERO latency on the audio path — the microphone callback only does a cheap,
    non-blocking queue push; recognition runs on the detector's own thread.
  • Fully local and offline — audio fed here never leaves the machine; the only
    network use is the one-time model download the user triggers from the UI.

Settings in config/api_keys.json:
    wake_threshold   word confidence needed (default 0.85); raise it if SAM wakes
                     by itself, lower it if it misses you
"""
from __future__ import annotations

from typing import Callable

SAMPLE_RATE = 16000


def wake_phrase() -> str:
    """What the user says to wake the assistant — for every on-screen hint."""
    return "Hey Sam"


def _threshold() -> float:
    from core import wake_sam
    try:
        from memory.config_manager import load_api_keys
        v = float(load_api_keys().get("wake_threshold", wake_sam.DEFAULT_THRESHOLD))
        return min(0.99, max(0.3, v))
    except Exception:
        return wake_sam.DEFAULT_THRESHOLD


def is_installed() -> bool:
    from core import wake_sam
    return wake_sam.is_installed()


def is_ready() -> bool:
    """Package and model present (cheap file check, no model load)."""
    from core import wake_sam
    return wake_sam.is_ready()


def install_and_download(logger: Callable[[str], None] = print,
                         notify: Callable[[str], None] | None = None) -> tuple[bool, str]:
    """One-click setup for the UI button. Never raises."""
    from core import wake_sam
    return wake_sam.install_and_download(logger=logger, notify=notify)


def WakeWordDetector(on_detect: Callable[[], None], threshold: float | None = None,
                     logger: Callable[[str], None] = print,
                     notify: Callable[[str], None] | None = None):
    """The "Hey Sam" detector: start(), stop(), ready, reset(), feed(frame)."""
    from core import wake_sam
    return wake_sam.SamWakeDetector(on_detect, threshold=threshold or _threshold(),
                                    logger=logger, notify=notify)
