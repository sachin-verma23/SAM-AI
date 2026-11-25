"""
core/offline_tools.py — the tool list SAM gives a small LOCAL model.

WHY A SEPARATE LIST
    Measured on the target laptop (i5-8250U, llama3.2:3b on Ollama): the CPU
    reads a prompt at ~14 tokens per second. The full tool declarations are
    ~1,500 tokens, and llama3.2's chat template re-inserts native tool
    definitions into EVERY user turn, so each reply waited ~100 s before the
    model even started.

    So offline SAM uses prompt-format tools (one line each, in the system
    prompt, which Ollama caches between turns) and only the tools that matter
    without the internet, with short descriptions that still name the actions.

    The names are the real tool names, so main.py runs them exactly as it runs
    Gemini's calls — nothing new to dispatch, nothing that can drift.
"""
from __future__ import annotations

# Ordered by importance: a tight budget keeps the top of the list.
SLIM: list[dict] = [
    {"name": "confirm_action",
     "description": "Resolves a pending on-screen confirmation request by voice. action: confirm|cancel.",
     "parameters": {"type": "OBJECT", "properties": {
         "action": {"type": "STRING"}},
         "required": ["action"]}},
    {"name": "computer_settings",
     "description": "PC control. action: volume_set|volume_up|volume_down|mute|unmute|"
                    "brightness_set|brightness_up|brightness_down|media_play_pause|media_next|"
                    "media_previous|lock_screen|take_screenshot|dark_mode|minimize_window|"
                    "maximize_window|show_desktop|open_task_manager; value = level or amount",
     "parameters": {"type": "OBJECT", "properties": {
         "action": {"type": "STRING"}, "value": {"type": "STRING"}},
         "required": ["action"]}},
    {"name": "open_app",
     "description": "Open an application by its real name, e.g. 'Google Chrome', 'Notepad'.",
     "parameters": {"type": "OBJECT", "properties": {"app_name": {"type": "STRING"}},
                    "required": ["app_name"]}},
    {"name": "computer_control",
     "description": "action=close_app with app_name to close a program; action=type with text; "
                    "action=hotkey with keys like 'ctrl+c'; action=press with key.",
     "parameters": {"type": "OBJECT", "properties": {
         "action": {"type": "STRING"}, "app_name": {"type": "STRING"},
         "text": {"type": "STRING"}, "keys": {"type": "STRING"}, "key": {"type": "STRING"}},
         "required": ["action"]}},
    {"name": "file_controller",
     "description": "Files. action: list|create_file|create_folder|delete|move|copy|rename|read|"
                    "write|find. path: desktop|downloads|documents|home or a full path.",
     "parameters": {"type": "OBJECT", "properties": {
         "action": {"type": "STRING"}, "path": {"type": "STRING"}, "name": {"type": "STRING"},
         "destination": {"type": "STRING"}, "new_name": {"type": "STRING"},
         "content": {"type": "STRING"}},
         "required": ["action"]}},
    {"name": "save_memory",
     "description": "Silently save a personal fact. category: identity|preferences|projects|"
                    "relationships|wishes|notes. key snake_case, value in English.",
     "parameters": {"type": "OBJECT", "properties": {
         "category": {"type": "STRING"}, "key": {"type": "STRING"}, "value": {"type": "STRING"}},
         "required": ["category", "key", "value"]}},
    {"name": "recall_memory",
     "description": "Look up something stored about the user. query empty = everything.",
     "parameters": {"type": "OBJECT", "properties": {"query": {"type": "STRING"}}}},
    {"name": "conversation_history",
     "description": "What was said in earlier conversations. action=search with query, "
                    "or action=recent with days (1 = today).",
     "parameters": {"type": "OBJECT", "properties": {
         "action": {"type": "STRING"}, "query": {"type": "STRING"}, "days": {"type": "INTEGER"}},
         "required": ["action"]}},
    {"name": "reminder",
     "description": "Set a reminder. date YYYY-MM-DD, time HH:MM (24h), message.",
     "parameters": {"type": "OBJECT", "properties": {
         "date": {"type": "STRING"}, "time": {"type": "STRING"}, "message": {"type": "STRING"}},
         "required": ["date", "time", "message"]}},
    {"name": "undo",
     "description": "Reverse your last change (file or setting). action=list to show history.",
     "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING"}}}},
    {"name": "system_status",
     "description": "CPU, RAM, temperature and battery of this PC.",
     "parameters": {"type": "OBJECT", "properties": {}}},
    {"name": "sam_settings",
     "description": "action=set_language value auto|hindi|english|hinglish; "
                    "action=set_mode value auto|online|offline; action=get.",
     "parameters": {"type": "OBJECT", "properties": {
         "action": {"type": "STRING"}, "value": {"type": "STRING"}},
         "required": ["action"]}},
    {"name": "shutdown_sam",
     "description": "Close SAM itself when the user says goodbye or asks it to stop.",
     "parameters": {"type": "OBJECT", "properties": {}}},
]


def slim_declarations(available) -> list[dict]:
    """The slim versions of whichever tools are actually available, in SLIM order.

    `available` is the full declaration list (dicts or SDK objects); a tool the
    build does not have is not offered, so a slim entry can never point at
    something that does not exist."""
    names = set()
    for d in available or ():
        n = d.get("name") if isinstance(d, dict) else getattr(d, "name", "")
        if n:
            names.add(n)
    return [dict(d) for d in SLIM if d["name"] in names]
