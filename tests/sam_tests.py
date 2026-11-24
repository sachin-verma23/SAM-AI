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


# ── Phase 1 ──────────────────────────────────────────────────────────────────

def test_rebrand() -> None:
    section("Everything the user sees is called SAM")
    import re, subprocess
    from gui import theme
    from memory import config_manager as cm
    check(theme.APP_VERSION.startswith("SAM"), "app version is SAM")
    check(theme.APP_OWNER == "Sachin Verma", "owner is Sachin Verma")
    check("FatihMakes" in theme.APP_BASED_ON, "the original author is credited (licence)")
    real = cm.CONFIG_FILE
    with tempfile.TemporaryDirectory() as td:
        cm.CONFIG_FILE = Path(td) / "api_keys.json"
        try:
            check(cm.get_assistant_name() == "SAM", "default assistant name is SAM")
        finally:
            cm.CONFIG_FILE = real
    files = subprocess.run(["git", "ls-files", "*.py", "*.html", "*.txt"], cwd=ROOT,
                           capture_output=True, text=True).stdout.split()
    left = [f for f in files if f != "tests/sam_tests.py"
            and re.search(r"JARVIS", (ROOT / f).read_text(encoding="utf-8"))]
    check(not left, f"no 'JARVIS' left in code or pages ({', '.join(left) or 'none'})")
    from gui.window import MainWindow
    check(MainWindow._subtitle("SAM").endswith("Sachin Verma"), "header subtitle names the owner")


# ── Phase 2 ──────────────────────────────────────────────────────────────────

class _TempConfig:
    """Point config_manager at a throwaway api_keys.json for one test."""

    def __enter__(self):
        from memory import config_manager as cm
        self.cm, self.real = cm, cm.CONFIG_FILE
        self.td = tempfile.TemporaryDirectory()
        cm.CONFIG_FILE = Path(self.td.name) / "api_keys.json"
        return cm

    def __exit__(self, *exc):
        self.cm.CONFIG_FILE = self.real
        self.td.cleanup()


def test_language_preference() -> None:
    section("Hindi / English / Hinglish preference")
    import main
    with _TempConfig() as cm:
        check(cm.get_preferred_language() == "auto", "default is auto (match the user)")
        block = main._language_block()
        check("MOST RECENT" in block and "Hinglish" in block, "auto mode mirrors the user, Hinglish included")
        cm.save_preferred_language("hinglish")
        check("Always reply in natural Hinglish" in main._language_block(), "hinglish mode is enforced")
        cm.save_preferred_language("hindi")
        check("everyday spoken Hindi" in main._language_block(), "hindi mode is enforced")
        try:
            cm.save_preferred_language("french")
            check(False, "an unknown language is refused")
        except ValueError:
            check(True, "an unknown language is refused")

        from actions.sam_settings import sam_settings

        class P:
            calls = []
            def request_reconnect(self, reason="", fresh=False):
                self.calls.append((reason, fresh))
        p = P()
        out = sam_settings({"action": "set_language", "value": "Hinglish"}, player=p)
        check("status=done" in out and cm.get_preferred_language() == "hinglish",
              "the voice tool saves the language")
        check(p.calls == [("new language", True)], "and restarts the session fresh to apply it")
        out = sam_settings({"action": "set_language", "value": "klingon"}, player=p)
        check("status=ask" in out, "an unclear language makes the tool ask, not guess")
    prompt = (ROOT / "core" / "prompt.txt").read_text(encoding="utf-8")
    check("HINGLISH is the exception" in prompt, "the base prompt allows Hinglish")
    check('"aap"' in prompt, "the base prompt uses the respectful 'aap'")


# ── Phase 4 ──────────────────────────────────────────────────────────────────

def test_auto_switching() -> None:
    section("Online/offline automatic switching")
    import time as _t
    from core import connectivity, gemini
    import main
    try:
        connectivity.force(False)
        with _TempConfig() as cm:
            cm.CONFIG_FILE.write_text(json.dumps({"gemini_api_key": "x" * 39}), encoding="utf-8")
            start = _t.monotonic()
            out = gemini.call("hello", tier=gemini.FAST)
            check(out is None and _t.monotonic() - start < 2.0,
                  "offline with no local AI gives up at once instead of timing out on every model")
            cm.save_providers(mode="auto")
            check(cm.get_provider_mode() == "auto", "'auto' is a stored engine mode")

            class _UI:
                def write_log(self, *_): pass
            j = main.JarvisLive.__new__(main.JarvisLive)
            j.ui = _UI()
            want, why = j._auto_wants_local()
            check(want and why == "No internet", "offline: auto mode picks the local AI")
            connectivity.force(True)
            want, why = j._auto_wants_local()
            check(not want, "online with a key: auto mode picks Gemini")
            cm.CONFIG_FILE.write_text(json.dumps({"providers": {"mode": "auto"}}), encoding="utf-8")
            want, why = j._auto_wants_local()
            check(want and why == "No Gemini key", "no Gemini key: auto mode picks the local AI")

            from actions.sam_settings import sam_settings
            out = sam_settings({"action": "set_mode", "value": "offline"})
            check("status=failed" in out, "offline mode is refused until a local AI is set up")
            cm.save_providers(pipeline={"llm": "openai_compat@ollama"})
            out = sam_settings({"action": "set_mode", "value": "online"})
            check("status=done" in out and cm.get_provider_mode() == "gemini", "voice can switch to online")
    finally:
        connectivity.force(None)
    check(isinstance(connectivity.is_online(), bool), "a real connectivity probe answers")


TESTS = [
    test_memory_is_safe,
    test_routine_defaults_are_quiet,
    test_dashboard_off_by_default,
    test_error_classification,
    test_rebrand,
    test_language_preference,
    test_auto_switching,
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
