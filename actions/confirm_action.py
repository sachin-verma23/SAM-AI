from __future__ import annotations

from core import confirm, outcome


def confirm_action(parameters: dict, player=None) -> str:
    """Allow SAM to resolve pending confirmation requests by voice."""
    action = str(parameters.get("action") or "").strip().lower()
    title = confirm.pending_title()

    if not title:
        return outcome.failed("confirm_action", "no pending confirmation request was found on screen")

    if action == "confirm":
        confirm.resolve(True)
        return outcome.done("confirm_action", choice="confirm")

    if action == "cancel":
        confirm.resolve(False)
        return outcome.done("confirm_action", choice="cancel")

    return outcome.failed("confirm_action", f"unknown action '{action}'")


TOOL = {
    "name": "confirm_action",
    "description": (
        "Resolves a pending on-screen confirmation request by voice. Use this tool "
        "when the user responds to a [CONFIRMATION_PENDING] banner. "
        "action='confirm' if they say yes/confirm; action='cancel' if they say no/cancel."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["confirm", "cancel"]},
        },
        "required": ["action"],
    },
    "handler": confirm_action,
    "tier": "core",
}
