"""
core/policy.py — which actions need the owner's on-screen confirmation.

SAM's confirmation gate (core/confirm.py) is a button only a person can
press; the model cannot forge it. It guarded three things: shutdown, restart and
Wi-Fi. SAM extends it to everything that destroys, overwrites or leaves the
machine, and makes the list a setting.

DEFAULTS (True = ask first)
    delete_files      deleting a file or folder (even to the Recycle Bin)
    overwrite_files   writing over an existing file, or moving / copying onto one
    move_files        moving files or folders somewhere else
    organize_files    tidying the Desktop (moves many files at once)
    send_message      sending a message to another person
    install_packages  the coding agent installing Python packages
    close_app         closing an application (unsaved work could be lost)
    power             shutdown / restart / Wi-Fi (always asked; cannot be turned off)

Override any of them in config/api_keys.json:
    "confirm_actions": {"move_files": false, "close_app": true}

USAGE IN AN ACTION
    from core import policy
    return policy.gate("delete_files", "Delete report.pdf",
                       "Moves it to the Recycle Bin.", lambda: delete_file(...))

    If the category needs confirmation, the banner goes up and the model is told
    to ask; the callable runs only after CONFIRM. Otherwise it runs at once and
    its result is returned unchanged.
"""
from __future__ import annotations

from typing import Callable

DEFAULTS: dict[str, bool] = {
    "delete_files": True,
    "overwrite_files": True,
    "move_files": True,
    "organize_files": True,
    "send_message": True,
    "install_packages": True,
    "close_app": False,
    "power": True,
}

# Categories the owner may not switch off: the machine itself going away.
ALWAYS = {"power"}


def needs_confirm(category: str) -> bool:
    if category in ALWAYS:
        return True
    try:
        from memory.config_manager import load_api_keys
        overrides = load_api_keys().get("confirm_actions")
    except Exception:
        overrides = None
    if isinstance(overrides, dict) and category in overrides:
        return bool(overrides[category])
    return DEFAULTS.get(category, True)


def approve_and_wait(category: str, title: str, detail: str) -> bool:
    """For work already running on a background thread (the coding agent):
    show the banner and BLOCK until the owner answers. True = go ahead.

    Times out (as "no") with the banner itself, so a job can never hang."""
    if not needs_confirm(category):
        return True
    import threading
    from core import confirm
    if confirm.pending_title():
        return False
    decided = threading.Event()
    answer = {"ok": False}

    def yes():
        answer["ok"] = True
        decided.set()
        return "approved"

    msg = confirm.request(category, title, detail, yes, on_cancel=decided.set)
    if "[CONFIRMATION_PENDING]" not in msg:
        return False                       # no interface: refuse
    decided.wait(confirm.TIMEOUT_SECONDS + 5)
    return answer["ok"]


def gate(category: str, title: str, detail: str, run: Callable[[], str],
         key: str = "") -> str:
    """Run `run` now, or park it behind the confirmation banner."""
    if not needs_confirm(category):
        return run()
    from core import confirm
    if confirm.pending_title():
        return ("Another confirmation is already waiting on screen. Ask the user to "
                "answer that one first; nothing new was done.")
    return confirm.request(key or category, title, detail, run)
