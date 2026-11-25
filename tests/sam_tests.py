"""
SAM self-test — checks SAM's features.

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
    check((ROOT / "LICENSE").exists() and (ROOT / "NOTICE").exists(),
          "LICENSE and NOTICE are present (the licence requires them)")
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
            and re.search(r"SAM", (ROOT / f).read_text(encoding="utf-8"))]
    check(not left, f"no 'SAM' left in code or pages ({', '.join(left) or 'none'})")
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
            j = main.SamLive.__new__(main.SamLive)
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


# ── Phase 5 ──────────────────────────────────────────────────────────────────

def test_confirmation_policy() -> None:
    section("Sensitive actions wait for the on-screen confirmation")
    import threading, time as _t
    from core import confirm, policy
    from actions.file_controller import file_controller
    shown, said = [], []
    confirm.bind(show=lambda t, d: shown.append(t), hide=lambda: None,
                 log=lambda m: None, say=said.append)
    try:
        with _TempConfig():
            check(policy.needs_confirm("delete_files"), "deleting asks by default")
            check(not policy.needs_confirm("close_app"), "closing an app does not ask by default")
        home_tmp = Path.home() / ".sam_test_tmp"
        home_tmp.mkdir(exist_ok=True)
        try:
            f = home_tmp / "victim.txt"
            f.write_text("keep me", encoding="utf-8")
            out = file_controller({"action": "delete", "path": str(home_tmp), "name": "victim.txt"})
            check("[CONFIRMATION_PENDING]" in out and f.exists(), "delete is parked, the file is untouched")
            check(bool(shown) and "victim.txt" in shown[-1], "the banner names the file")
            confirm.resolve(False)
            check(f.exists(), "CANCEL keeps the file")
            check(any("CANCELLED" in x for x in said), "SAM is told it was cancelled")

            out = file_controller({"action": "write", "path": str(home_tmp), "name": "victim.txt",
                                   "content": "new"})
            check("[CONFIRMATION_PENDING]" in out, "overwriting an existing file asks first")
            confirm.resolve(True)
            for _ in range(50):
                if f.read_text(encoding="utf-8") == "new":
                    break
                _t.sleep(0.05)
            check(f.read_text(encoding="utf-8") == "new", "CONFIRM performs the write")
            check(any("CONFIRMED ACTION RESULT" in x for x in said), "SAM is told the result")

            out = file_controller({"action": "write", "path": str(home_tmp), "name": "fresh.txt",
                                   "content": "x"})
            check("[CONFIRMATION_PENDING]" not in out and (home_tmp / "fresh.txt").exists(),
                  "creating a new file does not ask")
        finally:
            for p in home_tmp.glob("*"):
                p.unlink()
            home_tmp.rmdir()

        result = {}
        th = threading.Thread(target=lambda: result.setdefault(
            "ok", policy.approve_and_wait("install_packages", "Install x", "x")))
        th.start(); _t.sleep(0.3); confirm.resolve(False); th.join(5)
        check(result.get("ok") is False and not th.is_alive(), "a background job hears CANCEL at once")
        th = threading.Thread(target=lambda: result.__setitem__(
            "ok2", policy.approve_and_wait("install_packages", "Install y", "y")))
        th.start(); _t.sleep(0.3); confirm.resolve(True); th.join(5)
        check(result.get("ok2") is True, "a background job hears CONFIRM")
        check(policy.needs_confirm("power"), "power actions always ask")
    finally:
        confirm.bind(None, None, None, None)


# ── Phase 3 ──────────────────────────────────────────────────────────────────

def test_offline_engine_is_light() -> None:
    section("Offline engine: short prompt, short tool list")
    import main
    from core import offline_tools
    from providers import schema
    local = main._load_local_prompt()
    check(local and len(local) < 2000, f"local prompt is short ({len(local)} chars)")
    check("#" not in local.splitlines()[0], "comment lines are removed")
    full = main._load_system_prompt()
    check(len(full) > 3 * len(local), "it is much shorter than the online prompt")
    decls = main.TOOL_DECLARATIONS + [{"name": "computer_settings"}, {"name": "open_app"},
                                      {"name": "web_search"}]
    slim = offline_tools.slim_declarations(decls)
    names = [d["name"] for d in slim]
    check("web_search" not in names, "online-only tools are not in the offline list")
    check(names[:2] == ["computer_settings", "open_app"], "PC control comes first")
    check("shutdown_sam" in names and "save_memory" in names, "memory and shutdown are kept")
    check(schema.payload_size(offline_tools.SLIM) < 4500,
          f"the whole offline tool list is small ({schema.payload_size(offline_tools.SLIM)} chars)")
    from providers.llm_openai import OpenAICompatLLM
    llm = OpenAICompatLLM({"base_url": "http://127.0.0.1:11434/v1", "model": "m",
                           "tool_format": "prompt"})
    check(llm.caps["tool_format"] == "prompt", "tool_format=prompt is honoured")
    check(main._ONLINE_ONLY_TOOLS >= {"web_search", "browser_control"},
          "web tools are withheld while offline")


# ── Phase 6 ──────────────────────────────────────────────────────────────────

def test_memory_edit_and_history() -> None:
    section("Memory can be edited; conversations are kept and searchable")
    from memory import memory_manager as mm, history
    real_mem, real_hist = mm.MEMORY_PATH, history.HISTORY_DIR
    with tempfile.TemporaryDirectory() as td:
        mm.MEMORY_PATH = Path(td) / "long_term.json"
        history.HISTORY_DIR = Path(td) / "history"
        try:
            mm.update_memory({"preferences": {"food": {"value": "paneer"}}})
            mm.edit_entry("preferences", "food", "dal makhani")
            check(mm.load_memory()["preferences"]["food"]["value"] == "dal makhani",
                  "a value can be edited")
            mm.edit_entry("preferences", "food", "dal makhani", new_category="notes",
                          new_key="Favourite Dish")
            m = mm.load_memory()
            check("food" not in m["preferences"] and m["notes"]["favourite_dish"]["value"] == "dal makhani",
                  "a fact can be renamed / moved, the old one is removed")
            check(mm.edit_entry("notes", "x", "  ").startswith("Nothing"), "an empty value is refused")

            history.append("user", "Desktop par ek naya folder Projects2026 bana do")
            history.append("assistant", "Folder Projects2026 bana diya.")
            history.append("user", "Volume 30 percent kar do")
            hits = history.search("Projects2026 folder")
            check(hits and "Projects2026" in hits[0]["text"], "search finds an earlier turn")
            check(len(history.recent(days=1)) == 3, "recent() returns today's turns")
            from actions.conversation_history import conversation_history
            out = conversation_history({"action": "search", "query": "volume"})
            check("status=done" in out and "Volume 30" in out, "the tool returns the match")
            check("UNTRUSTED" in out, "history reaches the model marked as data")
        finally:
            mm.MEMORY_PATH, history.HISTORY_DIR = real_mem, real_hist


# ── Phase 7 ──────────────────────────────────────────────────────────────────

def test_wake_word_hey_sam() -> None:
    section("Wake word 'Hey Sam'")
    from core import wake_word, wake_sam
    with _TempConfig() as cm:
        check(wake_word.wake_phrase() == "Hey Sam", "hints say 'Hey Sam'")
        cm.update_config(wake_threshold=0.9)
        check(abs(wake_word._threshold() - 0.9) < 1e-9, "the threshold is configurable")

    def res(*pairs):
        return {"result": [{"word": w, "conf": c} for w, c in pairs]}
    T = wake_sam.DEFAULT_THRESHOLD
    check(wake_sam.wake_in(res(("hey", 1.0), ("sam", 0.95)), T), "'hey sam' wakes it")
    check(wake_sam.wake_in(res(("hi", 0.9), ("sam", 0.9), ("[unk]", 1)), T), "'hi sam ...' wakes it")
    check(not wake_sam.wake_in(res(("sam", 1.0)), T), "a lone 'sam' does not")
    check(not wake_sam.wake_in(res(("hey", 1.0), ("[unk]", 1.0)), T), "'hey' + something else does not")
    check(not wake_sam.wake_in(res(("hey", 0.5), ("sam", 0.6)), T), "a low-confidence match does not")
    check(not wake_sam.wake_in(res(("sam", 1.0), ("hey", 1.0)), T), "the words must be in order")

    if wake_sam.is_ready():
        hits = []
        det = wake_sam.SamWakeDetector(lambda: hits.append(1), logger=lambda m: None)
        check(det.start() and det.ready, "the Vosk model loads")
        det.stop()
    else:
        print("  SKIP  Vosk model not downloaded")


# ── Phase 8 ──────────────────────────────────────────────────────────────────

def test_gestures() -> None:
    section("Hand gestures")
    from core import gestures as g
    L = g.GestureLogic()
    fired = []
    t = 0.0
    def run(gesture, seconds, score=0.9, wrist=None):
        nonlocal t
        end = t + seconds
        while t < end:
            f = L.feed(t, gesture, score, wrist)
            if f:
                fired.append(f)
            t += 0.125                         # 8 frames per second
    run("Open_Palm", 0.3)
    check(fired == [], "a pose seen briefly does nothing")
    run("Open_Palm", 1.5)
    check(fired == ["Open_Palm"], "a steady open palm fires once, not repeatedly")
    run(None, 0.5); fired.clear()
    run("Thumb_Up", 3.0)
    check(2 <= fired.count("Thumb_Up") <= 4, f"thumbs up repeats while held ({len(fired)})")
    run(None, 0.5); fired.clear()
    run("Victory", 2.0, score=0.4)
    check(fired == [], "a low-confidence pose is ignored")
    run(None, 2.0); fired.clear()
    for i in range(5):
        f = L.feed(t, None, 0.0, 0.2 + i * 0.12); t += 0.1
        if f: fired.append(f)
    check(fired == ["swipe_right"], "a fast hand movement to the right is a swipe")
    L2 = g.GestureLogic({"Open_Palm": ""})
    out = [L2.feed(i * 0.125, "Open_Palm", 0.9, None) for i in range(20)]
    check(not any(out), "a gesture mapped to '' is disabled")
    check(set(g.DEFAULT_ACTIONS.values()) & {"shutdown_computer", "delete"} == set(),
          "no destructive action is mapped")
    with _TempConfig() as cm:
        check(cm.get_gestures_enabled() is False, "gesture control is off by default")
    from actions.gesture_control import gesture_control
    out = gesture_control({"action": "status"})
    check("status=done" in out and "palm" in out, "the voice tool reports status and the gestures")
    print("  INFO  ", g.missing() or "mediapipe, OpenCV and the model are all present")


# ── setup_sam.py ─────────────────────────────────────────────────────────────

def test_setup_script_on_a_fresh_install() -> None:
    section("setup_sam.py on a laptop with no settings yet")
    import importlib
    setup_sam = importlib.import_module("setup_sam")
    with _TempConfig() as cm:
        setup_sam.RESULTS.clear()
        setup_sam.write_settings("llama3.2:3b")
        check(cm.get_provider_mode() == "auto", "engine mode becomes auto")
        llm = cm.get_provider_config("openai_compat@ollama")
        check(llm.get("tool_format") == "prompt" and llm.get("model") == "llama3.2:3b",
              "the Ollama settings match the tuned laptop")
        check(cm.get_pipeline() == {"stt": "whisper@local", "llm": "openai_compat@ollama",
                                    "tts": "piper@piper"}, "the offline pipeline is complete")
        data = json.loads(cm.CONFIG_FILE.read_text(encoding="utf-8"))
        check("gemini_api_key" not in data and "os_system" not in data,
              "no key is invented, so first launch still asks for it")
        from gui import window
        real = window._read_full_config
        window._read_full_config = lambda: data
        try:
            check(window.MainWindow._check_config(None) is False, "the setup screen will still appear")
        finally:
            window._read_full_config = real


# ── self-update ──────────────────────────────────────────────────────────────

def test_self_update() -> None:
    section("SAM changes its own code only through branch + tests + CONFIRM")
    import subprocess
    from core import self_update as su
    real_root = su.ROOT
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)

        def g(*a):
            return subprocess.run(["git", *a], cwd=repo, capture_output=True,
                                  text=True).stdout.strip()

        def write(name, text):
            (repo / name).write_text(text, encoding="utf-8")

        def read(name):
            return (repo / name).read_text(encoding="utf-8")

        g("init", "-q", "-b", "main")
        g("config", "user.email", "t@example.invalid")
        g("config", "user.name", "test")
        (repo / "tests").mkdir()
        write("tests/__init__.py", "")
        write("tests/sam_tests.py",
              "import sys, pathlib\nsys.exit(1 if pathlib.Path('BREAK').exists() else 0)\n")
        write("app.py", "print('v1')\n")
        g("add", "-A")
        g("commit", "-q", "-m", "base")
        su.ROOT = repo
        quiet = lambda m: None
        try:
            said, restarts = [], []

            def agent_ok(folder, text, player):
                (folder / "app.py").write_text("print('v2')\n", encoding="utf-8")
                (folder / "new_setting.py").write_text("ENABLED = True\n", encoding="utf-8")
                return "added new_setting.py"

            su.run_change("add a new setting", say=said.append, log=quiet,
                          ask_apply=lambda t, d, run: run(),
                          restart=lambda: restarts.append(1), improve=agent_ok)
            check(read("app.py") == "print('v2')\n" and (repo / "new_setting.py").exists(),
                  "a tested change is applied after CONFIRM")
            check(restarts == [1], "SAM restarts to load it")
            check(g("rev-parse", "--abbrev-ref", "HEAD") == "main"
                  and not g("branch", "--list", "sam-self/*"),
                  "back on main, the work branch is gone")
            check(g("log", "-1", "--format=%s").startswith(su.COMMIT_PREFIX),
                  "the change is one labelled commit")

            def agent_breaks(folder, text, player):
                (folder / "BREAK").write_text("x", encoding="utf-8")
                (folder / "app.py").write_text("print('v3')\n", encoding="utf-8")
                return "broke it"

            said.clear()
            su.run_change("break the tests", say=said.append, log=quiet,
                          ask_apply=lambda t, d, run: run(), restart=lambda: None,
                          improve=agent_breaks)
            check(read("app.py") == "print('v2')\n" and not (repo / "BREAK").exists(),
                  "a change that fails the tests is thrown away completely")
            check(any("NOT applied" in m for m in said), "SAM says it was not applied")

            def agent_syntax(folder, text, player):
                (folder / "app.py").write_text("def broken(:\n", encoding="utf-8")
                return "oops"

            su.run_change("bad syntax", say=quiet, log=quiet,
                          ask_apply=lambda t, d, run: run(), restart=lambda: None,
                          improve=agent_syntax)
            check(read("app.py") == "print('v2')\n", "code that does not compile is thrown away")

            def agent_later(folder, text, player):
                (folder / "later.py").write_text("X = 1\n", encoding="utf-8")
                return "later"

            su.run_change("wait for me", say=quiet, log=quiet,
                          ask_apply=lambda t, d, run: "pending", restart=lambda: None,
                          improve=agent_later)
            check(not (repo / "later.py").exists() and su.status()["pending"],
                  "without CONFIRM nothing is applied; the change waits on its branch")
            su.discard_pending()
            check(not su.status()["pending"], "a waiting change can be discarded")

            write("dirty.txt", "x")
            check("uncommitted" in su.available(), "it refuses to start on a dirty working tree")
            (repo / "dirty.txt").unlink()

            su.rollback(restart=lambda: restarts.append(2), log=quiet)
            check(read("app.py") == "print('v1')\n" and not (repo / "new_setting.py").exists(),
                  "rollback undoes the last applied change")
        finally:
            su.ROOT = real_root
    from core import policy
    check(policy.needs_confirm("self_update"), "self-update always needs CONFIRM")
    from actions.self_update import self_update
    check("status=ask" in self_update({"action": "change", "instruction": "x"}),
          "a vague request is asked about, not guessed")


# ── restart, voice confirmation, new skills ─────────────────────────────────

def test_restart_and_voice_confirm() -> None:
    section("restart SAM; confirming by voice needs the user's own 'yes'")
    import time as _t
    from core import confirm
    from actions.restart_sam import restart_sam
    from actions.confirm_action import confirm_action
    confirm.bind(show=lambda a, b: None, hide=lambda: None, log=lambda m: None, say=lambda m: None)
    try:
        class P:
            restarts = 0
            words = (0.0, "")
            def request_restart(self):
                P.restarts += 1
            def last_user_words(self):
                return P.words
        p = P()
        out = restart_sam({}, player=p)
        check("[CONFIRMATION_PENDING]" in out and P.restarts == 0, "restart waits for CONFIRM")
        check("not answered" in confirm_action({"action": "confirm"}, player=p),
              "the model cannot confirm when the user has said nothing")
        P.words = (_t.monotonic(), "nahi, ruko")
        check("not a clear yes" in confirm_action({"action": "confirm"}, player=p),
              "'nahi' is not taken as yes")
        P.words = (_t.monotonic(), "haan restart kar do")
        out = confirm_action({"action": "confirm"}, player=p)
        for _ in range(40):
            if P.restarts:
                break
            _t.sleep(0.05)
        check("status=done" in out and P.restarts == 1, "the user's spoken 'haan' confirms and SAM restarts")

        restart_sam({}, player=p)
        P.words = (_t.monotonic() - 999, "haan")
        check("not answered" in confirm_action({"action": "confirm"}, player=p),
              "a 'yes' said before the banner does not count")
        check("status=done" in confirm_action({"action": "cancel"}, player=p), "cancel works by voice")

        confirm.request("self_update", "Let SAM change its own code", "x", lambda: "ran")
        P.words = (_t.monotonic() + 1, "confirm")
        check("button on screen" in confirm_action({"action": "confirm"}, player=p),
              "code changes can only be confirmed with the screen button")
        confirm.resolve(False)
    finally:
        confirm.bind(None, None, None, None)


def test_create_skill() -> None:
    section("SAM writes a new skill for itself (tested, then CONFIRM)")
    import subprocess
    from core import self_update as su, gemini
    from actions import create_skill as cs
    real_root, real_text = su.ROOT, gemini.text
    good = (
        "```python\n"
        "import random\n"
        "PLUGIN = {\"name\": \"dice_roll\", \"description\": \"Roll a dice.\",\n"
        "          \"parameters\": {\"type\": \"OBJECT\", \"properties\": {}}}\n"
        "def run(parameters, player=None, session_memory=None):\n"
        "    return f\"You rolled {random.randint(1, 6)}.\"\n"
        "```"
    )
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        def g(*a):
            return subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True).stdout.strip()
        g("init", "-q", "-b", "main"); g("config", "user.email", "t@example.invalid"); g("config", "user.name", "t")
        for d in ("tests", "plugins", "actions"):
            (repo / d).mkdir()
        (repo / "tests" / "__init__.py").write_text("", encoding="utf-8")
        (repo / "tests" / "sam_tests.py").write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
        (repo / "plugins" / "_template.py").write_text("# template\n", encoding="utf-8")
        (repo / "actions" / "__init__.py").write_text("", encoding="utf-8")
        (repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
        g("add", "-A"); g("commit", "-q", "-m", "base")
        su.ROOT = repo
        try:
            gemini.text = lambda *a, **k: good
            restarts = []
            su.run_change("New skill: roll a dice", say=lambda m: None, log=lambda m: None,
                          ask_apply=lambda t, d, run: run(), restart=lambda: restarts.append(1),
                          improve=cs.write_skill)
            f = repo / "plugins" / "dice_roll.py"
            check(f.exists() and restarts == [1], "a working skill is added and SAM restarts")
            from core.plugin_loader import discover_plugins
            reg = discover_plugins(plugins_dir=repo / "plugins", core_tool_names=set(),
                                   logger=lambda m: None)
            out = reg.run("dice_roll", {}, player=None, session_memory=None)
            check(reg.has("dice_roll") and "You rolled" in out, "the new skill loads and answers")

            gemini.text = lambda *a, **k: "```python\nPLUGIN = {\"name\": \"broken_one\"}\n```"
            said = []
            su.run_change("New skill: broken", say=said.append, log=lambda m: None,
                          ask_apply=lambda t, d, run: run(), restart=lambda: None,
                          improve=cs.write_skill)
            check(not (repo / "plugins" / "broken_one.py").exists() and any("NOT applied" in m for m in said),
                  "a skill the loader rejects is thrown away")

            gemini.text = lambda *a, **k: ("```python\nfrom PyQt6.QtWidgets import QWidget\n"
                                           "PLUGIN = {\"name\": \"ui_thing\", \"description\": \"x\", "
                                           "\"parameters\": {\"type\": \"OBJECT\", \"properties\": {}}}\n"
                                           "def run(p, player=None, session_memory=None):\n    return 'x'\n```")
            su.run_change("New skill: ui", say=lambda m: None, log=lambda m: None,
                          ask_apply=lambda t, d, run: run(), restart=lambda: None,
                          improve=cs.write_skill)
            check(not (repo / "plugins" / "ui_thing.py").exists(), "a skill that touches Qt is refused")

            gemini.text = lambda *a, **k: None
            su.run_change("New skill: offline", say=lambda m: None, log=lambda m: None,
                          ask_apply=lambda t, d, run: run(), restart=lambda: None,
                          improve=cs.write_skill)
            check(g("status", "--porcelain") == "" and g("rev-parse", "--abbrev-ref", "HEAD") == "main",
                  "no model answer leaves the repo clean on main")
        finally:
            su.ROOT, gemini.text = real_root, real_text
    from actions.create_skill import create_skill
    check("status=ask" in create_skill({"description": "x"}), "a vague skill request is asked about")


TESTS = [
    test_memory_is_safe,
    test_routine_defaults_are_quiet,
    test_dashboard_off_by_default,
    test_error_classification,
    test_rebrand,
    test_language_preference,
    test_auto_switching,
    test_confirmation_policy,
    test_offline_engine_is_light,
    test_memory_edit_and_history,
    test_wake_word_hey_sam,
    test_gestures,
    test_setup_script_on_a_fresh_install,
    test_self_update,
    test_restart_and_voice_confirm,
    test_create_skill,
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
