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


_MODES = {
    "auto": "auto", "automatic": "auto",
    "online": "gemini", "gemini": "gemini", "cloud": "gemini",
    "offline": "pipeline", "local": "pipeline", "ollama": "pipeline", "pipeline": "pipeline",
}


def _settings_summary() -> str:
    from memory.config_manager import get_preferred_language, get_provider_mode
    return f"language={get_preferred_language()}, engine_mode={get_provider_mode()}"


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

        if action == "set_mode":
            raw = str(parameters.get("value") or "").strip().lower()
            mode = _MODES.get(raw)
            if mode is None:
                return outcome.ask("sam_settings",
                                   "which mode: auto, online (Gemini) or offline (local AI)")
            from memory.config_manager import (get_pipeline, get_provider_mode,
                                               save_providers)
            if mode in ("pipeline", "auto") and not get_pipeline().get("llm"):
                return outcome.failed(
                    "sam_settings", "no local AI is set up yet — open ENGINE & "
                    "PROVIDERS and fill in MY OWN SETUP first")
            if get_provider_mode() == mode:
                return outcome.done("sam_settings", mode=mode, changed=False)
            save_providers(mode=mode)
            reconnect = getattr(player, "request_reconnect", None) if player else None
            if callable(reconnect):
                reconnect(reason="new engine mode", fresh=True)
            return outcome.done("sam_settings", mode=mode,
                                note="saved; the conversation restarts in a moment")

        if action == "set_lite":
            raw = str(parameters.get("value") or "").strip().lower()
            if raw not in ("on", "off", "true", "false", "1", "0"):
                return outcome.ask("sam_settings", "lite mode on or off")
            from memory.config_manager import save_ui_lite
            on = raw in ("on", "true", "1")
            save_ui_lite(on)
            return outcome.done("sam_settings", lite_mode="on" if on else "off",
                                note="applies the next time SAM starts")

        return outcome.failed("sam_settings", f"unknown action '{action}'")
    except Exception as e:
        return outcome.failed("sam_settings", f"could not change the setting: {e}")


TOOL = {
    "name": "sam_settings",
    "description": (
        "SAM's own preferences. action='set_language' with value auto | hindi | "
        "english | hinglish when the user asks you to always speak a language, or to "
        "go back to matching theirs ('ab se Hindi mein baat karo', 'talk in Hinglish'). "
        "action='set_mode' with value auto | online | offline when the user asks to use "
        "the local/offline AI, Gemini/online only, or to switch automatically "
        "('offline mode on karo', 'auto mode'). "
        "action='set_lite' with value on | off for the lighter, lower-CPU display. "
        "action='get' to report the current settings. Before set_language or set_mode, "
        "say one short sentence that you are switching, because the conversation "
        "restarts right after."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "set_language | set_mode | set_lite | get"},
            "value": {"type": "STRING",
                      "description": "set_language: auto | hindi | english | hinglish. "
                                     "set_mode: auto | online | offline"},
        },
        "required": ["action"],
    },
    "handler": sam_settings,
    "tier": "core",
}
