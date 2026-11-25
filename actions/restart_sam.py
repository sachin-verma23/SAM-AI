"""
restart_sam — "restart SAM" / "SAM restart karo": end the whole SAM process and
start it again.

Order: CONFIRM (core/policy.py category "restart_sam", voice "haan" works through
confirm_action) → the conversation summary is saved and engines stopped
(SamLive.finish) → a fresh SAM process starts → this one exits.

Not to be confused with restarting the COMPUTER (computer_settings
restart_computer).
"""
from __future__ import annotations

from core import outcome


def restart_sam(parameters: dict, player=None) -> str:
    restart = getattr(player, "request_restart", None) if player else None
    if not callable(restart):
        return outcome.failed("restart_sam", "SAM is not running with its interface")
    from core import policy

    def go() -> str:
        restart()
        return "SAM is restarting"

    return policy.gate("restart_sam", "Restart SAM",
                       "Saves this conversation, closes SAM and opens it again", go)


TOOL = {
    "name": "restart_sam",
    "description": (
        "Restart SAM itself — the whole assistant app closes and opens again (the "
        "conversation summary is saved first). Use when the user says 'restart SAM', "
        "'SAM restart karo', 'reload yourself'. NOT for restarting the computer — that is "
        "computer_settings with action restart_computer."
    ),
    "parameters": {"type": "OBJECT", "properties": {}},
    "handler": restart_sam,
    "tier": "core",
}
