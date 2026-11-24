"""
core/connectivity.py — is the internet (and Gemini) reachable right now?

SAM's "auto" engine mode uses Gemini Live while online and the local stack
(Whisper + Ollama + Piper) while offline. Everything that has to make that
choice asks here, so there is one answer and one cache.

HOW IT CHECKS
    A TCP connection to Gemini's own API host on 443, with a short timeout. If
    DNS fails or nothing answers, it tries a public DNS server on 53 to tell
    "Google is unreachable" apart from "no network at all" — both count as
    offline for SAM, because without Gemini there is nothing online to use.

    No HTTP request, no API key, no quota: a connect and a close. Results are
    cached for a few seconds so a burst of callers costs one probe.

    Deliberately conservative about going ONLINE: a single good probe after an
    outage is not trusted until `stable_online()` sees two in a row, so a
    flickering Wi-Fi does not bounce the conversation between engines.
"""
from __future__ import annotations

import socket
import threading
import time

GEMINI_HOST = ("generativelanguage.googleapis.com", 443)
FALLBACK_HOST = ("8.8.8.8", 53)
PROBE_TIMEOUT = 2.0
CACHE_SECONDS = 8.0

_lock = threading.Lock()
_last_check = 0.0
_last_result = True
_good_streak = 0
_forced: bool | None = None     # tests (and a future "pretend offline" switch)


def _probe(host: tuple[str, int], timeout: float) -> bool:
    try:
        with socket.create_connection(host, timeout=timeout):
            return True
    except OSError:
        return False


def check_now(timeout: float = PROBE_TIMEOUT) -> bool:
    """Probe immediately (ignores the cache) and record the result."""
    global _last_check, _last_result, _good_streak
    if _forced is not None:
        return _forced
    ok = _probe(GEMINI_HOST, timeout)
    with _lock:
        _last_check = time.monotonic()
        _last_result = ok
        _good_streak = _good_streak + 1 if ok else 0
    return ok


def is_online(max_age: float = CACHE_SECONDS) -> bool:
    """True when Gemini's API host is reachable. Cached for `max_age` seconds."""
    if _forced is not None:
        return _forced
    with _lock:
        fresh = (time.monotonic() - _last_check) < max_age
        result = _last_result
    return result if fresh else check_now()


def stable_online() -> bool:
    """Online, and confirmed by at least two probes in a row."""
    if _forced is not None:
        return _forced
    if not check_now():
        return False
    with _lock:
        return _good_streak >= 2


def network_present(timeout: float = PROBE_TIMEOUT) -> bool:
    """Any network at all (used only to word messages: 'no internet' vs 'Google unreachable')."""
    return _probe(FALLBACK_HOST, timeout) or _probe(GEMINI_HOST, timeout)


def force(state: bool | None) -> None:
    """Pin the answer (True/False) or return to real probing (None)."""
    global _forced
    _forced = state
