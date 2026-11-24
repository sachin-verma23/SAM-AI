"""
SAM self-test — checks the features added on top of MARK LVII.

    .venv\\Scripts\\python.exe -m tests.sam_tests

No network, no API key, no microphone or camera needed. Every check works on
temporary copies, never on your real memory or settings.
"""
from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_passed = 0
_failed = 0


def check(cond, label: str) -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS  {label}")
    else:
        _failed += 1
        print(f"  FAIL  {label}")


def section(title: str) -> None:
    print(f"\n[{title}]")


# ── Phase 0 ──────────────────────────────────────────────────────────────────

def test_memory_is_safe() -> None:
    section("Memory writes are atomic and never wipe a broken file")
    from memory import memory_manager as mm
    real = mm.MEMORY_PATH
    with tempfile.TemporaryDirectory() as td:
        mm.MEMORY_PATH = Path(td) / "long_term.json"
        try:
            mm.update_memory({"identity": {"name": {"value": "Sachin"}}})
            mm.update_memory({"preferences": {"food": {"value": "paneer"}}})
            data = json.loads(mm.MEMORY_PATH.read_text(encoding="utf-8"))
            check(data["identity"]["name"]["value"] == "Sachin", "a fact is saved")
            check(data["preferences"]["food"]["value"] == "paneer", "a second fact keeps the first")
            check(not (Path(td) / "long_term.json.tmp").exists(), "no temp file is left behind")

            # Simulate a crash mid-write: a half-written file.
            mm.MEMORY_PATH.write_text('{"identity": {"name": {"value": "Sachin", "upd',
                                      encoding="utf-8")
            mm.update_memory({"notes": {"x": {"value": "y"}}})
            broken = list(Path(td).glob("long_term.json.broken-*"))
            check(len(broken) == 1, "an unreadable file is set aside, not overwritten")
            check("Sachin" in broken[0].read_text(encoding="utf-8") if broken else False,
                  "the set-aside file still holds the old content")

            mm.save_session_summary("Talked about SAM.", "Hindi")
            last = mm.pop_last_session()
            check(bool(last) and last["summary"] == "Talked about SAM.", "session summary round-trips")
        finally:
            mm.MEMORY_PATH = real


def test_routine_defaults_are_quiet() -> None:
    section("Unprompted routines are quiet by default")
    from core.routines import desktop as d
    check(d.QUIET_CHECKIN_IDLE >= 30, "check-in waits at least 30 idle minutes")
    check(d.QUIET_NEWS_EVERY >= 120, "news watch runs at most every 2 hours")
    check(d.DEFAULT_QUIET_HOURS == "23:00-07:00", "quiet hours default to 23:00-07:00")


def test_dashboard_off_by_default() -> None:
    section("Phone dashboard is off unless asked for")
    from memory import config_manager as cm
    real = cm.CONFIG_FILE
    with tempfile.TemporaryDirectory() as td:
        cm.CONFIG_FILE = Path(td) / "api_keys.json"
        try:
            check(cm.get_dashboard_enabled() is False, "no setting means the dashboard does not start")
            cm.save_dashboard_enabled(True)
            check(cm.get_dashboard_enabled() is True, "the setting can turn it on")
        finally:
            cm.CONFIG_FILE = real


def test_error_classification() -> None:
    section("Connection errors are classified correctly")
    import main
    from core import gemini
    check(not gemini.is_key_error("received 1007 (invalid frame payload data)"),
          "a 1007 close code is not treated as a bad API key")
    check(gemini.is_key_error("API key not valid. Please pass a valid API key."),
          "a real bad-key message is recognised")
    check(main._is_network_error(TimeoutError()), "a bare TimeoutError counts as a network error")
    check(main._is_network_error(BaseExceptionGroup("g", [ConnectionResetError()])),
          "a network error inside a TaskGroup group is found")
    check(not main._is_network_error(ValueError("x")), "an ordinary bug is not a network error")


TESTS = [
    test_memory_is_safe,
    test_routine_defaults_are_quiet,
    test_dashboard_off_by_default,
    test_error_classification,
]


def main() -> int:
    for t in TESTS:
        try:
            t()
        except Exception:
            global _failed
            _failed += 1
            print(f"  FAIL  {t.__name__} raised:")
            traceback.print_exc()
    print("\n" + "=" * 56)
    print(f"{_passed} passed, {_failed} failed")
    print("=" * 56)
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
