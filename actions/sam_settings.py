"""
sam_settings — SAM's own preferences, changed by voice.

    "ab se Hindi mein baat karo"         -> language = hindi
    "talk to me in Hinglish"             -> language = hinglish
    "reply in whatever language I use"   -> language = auto

A setting that is baked into the session at connect time (the language rule
lives in the system prompt) only takes effect after a rebuild, so the tool
asks for one: the conversation restarts in a second and long-term memory is
untouched.
"""
from __future__ import annotations

from core import outcome

_ALIASES = {
    "auto": "auto", "automatic": "auto", "same": "auto", "mirror": "auto",
    "hindi": "hindi", "हिंदी": "hindi", "हिन्दी": "hindi",
    "english": "english", "angrezi": "english", "अंग्रेज़ी": "english",
    "hinglish": "hinglish", "mix": "hinglish", "mixed": "hinglish",
}


def _settings_summary() -> str:
    from memory.config_manager import get_preferred_language
    return f"language={get_preferred_language()}"


def sam_settings(parameters: dict, player=None) -> str:
    action = str(parameters.get("action") or "get").strip().lower()
    try:
        if action == "get":
            return outcome.done("sam_settings", settings=_settings_summary())

        if action == "set_language":
            raw = str(parameters.get("value") or "").strip().lower()
            mode = _ALIASES.get(raw)
            if mode is None:
                return outcome.ask(
                    "sam_settings",
                    "which language: auto (match the user), hindi, english or hinglish")
            from memory.config_manager import get_preferred_language, save_preferred_language
            if get_preferred_language() == mode:
                return outcome.done("sam_settings", language=mode, changed=False)
            save_preferred_language(mode)
            reconnect = getattr(player, "request_reconnect", None) if player else None
            if callable(reconnect):
                # Fresh session: a resumed one could keep the old instruction.
                reconnect(reason="new language", fresh=True)
                return outcome.done(
                    "sam_settings", language=mode,
                    note="saved; the conversation restarts in a moment to apply it")
            return outcome.done("sam_settings", language=mode,
                                note="saved; applies from the next session")

        return outcome.failed("sam_settings", f"unknown action '{action}'")
    except Exception as e:
        return outcome.failed("sam_settings", f"could not change the setting: {e}")


TOOL = {
    "name": "sam_settings",
    "description": (
        "SAM's own preferences. action='set_language' with value auto | hindi | "
        "english | hinglish when the user asks you to always speak a language, or to "
        "go back to matching theirs ('ab se Hindi mein baat karo', 'talk in Hinglish'). "
        "action='get' to report the current settings. Before set_language, say one "
        "short sentence in the NEW language that you are switching, because the "
        "conversation restarts right after."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "set_language | get"},
            "value": {"type": "STRING",
                      "description": "For set_language: auto | hindi | english | hinglish"},
        },
        "required": ["action"],
    },
    "handler": sam_settings,
    "tier": "core",
}
