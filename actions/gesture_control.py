"""
gesture_control — switch webcam hand-gesture control on or off by voice.

    "gesture control on karo"   -> action=on
    "turn off gestures"         -> action=off
    "kaun se gestures hain?"    -> action=status

The work is done by core/gestures.py; main.py exposes the switch to tools as
player.on_gesture_toggle, the same callable the CONTROLS drawer button uses.
"""
from __future__ import annotations

from core import outcome

_HELP = ("open palm = play/pause, fist = mute, thumbs up/down = volume, victory = "
         "next track, pointing up = previous track, rock sign = wake SAM, "
         "swipe left/right = back/forward")


def gesture_control(parameters: dict, player=None) -> str:
    action = str(parameters.get("action") or "status").strip().lower()
    try:
        from core import gestures
        ctl = gestures.controller()
        if action == "status":
            return outcome.done("gesture_control", state=ctl.status,
                                running=ctl.running(), gestures=_HELP)
        if action not in ("on", "off"):
            return outcome.failed("gesture_control", f"unknown action '{action}'")
        toggle = getattr(player, "on_gesture_toggle", None) if player else None
        if not callable(toggle):
            return outcome.failed("gesture_control", "the assistant is not running")
        result = toggle(action == "on")
        if action == "off":
            return outcome.done("gesture_control", state="off")
        if result != "on":
            return outcome.failed("gesture_control", str(result))
        # The camera opens on the gesture thread; "started" is the honest word.
        return outcome.started("gesture_control", state="starting", gestures=_HELP)
    except Exception as e:
        return outcome.failed("gesture_control", f"could not change gesture control: {e}")


TOOL = {
    "name": "gesture_control",
    "description": (
        "Webcam hand-gesture control of the PC. action='on' or 'off' when the user asks "
        "to enable or disable gestures; action='status' to say whether it is on and which "
        "gestures exist (open palm play/pause, fist mute, thumbs up/down volume, victory "
        "next, pointing up previous, rock sign wake, swipe back/forward)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {"action": {"type": "STRING", "description": "on | off | status"}},
        "required": ["action"],
    },
    "handler": gesture_control,
    "tier": "core",
}
