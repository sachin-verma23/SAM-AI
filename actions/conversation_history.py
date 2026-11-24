"""
conversation_history — let SAM look up what was said in earlier conversations.

    "kal humne kis baare mein baat ki thi?"   -> action=recent, days=2
    "what was that folder name I told you?"   -> action=search, query="folder"
    "Monday ko kya baat hui thi?"             -> action=day, date=2026-11-23

Reads memory/history/*.jsonl (memory/history.py). Local only, no model call.
"""
from __future__ import annotations

from core import outcome


def conversation_history(parameters: dict, player=None) -> str:
    from memory import history
    action = str(parameters.get("action") or "search").strip().lower()
    try:
        if action == "search":
            query = str(parameters.get("query") or "").strip()
            if not query:
                return outcome.ask("conversation_history", "what should I look for")
            days = int(parameters.get("days") or 30)
            rows = history.search(query, days=days, limit=8)
            if not rows:
                return outcome.done("conversation_history", found=0,
                                    note=f"nothing matching '{query}' in the last {days} days")
            return outcome.done("conversation_history", found=len(rows)) + "\n" + \
                outcome.untrusted("history", history.format_rows(rows))
        if action == "recent":
            days = int(parameters.get("days") or 1)
            rows = history.recent(days=days, limit=30)
            if not rows:
                return outcome.done("conversation_history", found=0,
                                    note="no saved conversation in that period")
            return outcome.done("conversation_history", found=len(rows)) + "\n" + \
                outcome.untrusted("history", history.format_rows(rows))
        if action == "day":
            day = str(parameters.get("date") or "").strip()
            rows = history.on_day(day)
            if not rows:
                return outcome.done("conversation_history", found=0,
                                    note=f"no conversation saved on {day or 'that day'}",
                                    days_with_history=", ".join(history.days_available()[:10]))
            return outcome.done("conversation_history", found=len(rows)) + "\n" + \
                outcome.untrusted("history", history.format_rows(rows))
        return outcome.failed("conversation_history", f"unknown action '{action}'")
    except Exception as e:
        return outcome.failed("conversation_history", f"could not read the history: {e}")


TOOL = {
    "name": "conversation_history",
    "description": (
        "Look up what the user and you said in EARLIER conversations (saved on this PC). "
        "action='search' with query when they ask about something said before; "
        "action='recent' with days (1 = today) for 'what did we talk about today/yesterday'; "
        "action='day' with date YYYY-MM-DD for a specific day. Summarise what you find in "
        "your own words; never read the log out."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "search | recent | day"},
            "query": {"type": "STRING", "description": "words to look for (search)"},
            "days": {"type": "INTEGER", "description": "how many days back (default 30 for search, 1 for recent)"},
            "date": {"type": "STRING", "description": "YYYY-MM-DD (day)"},
        },
        "required": ["action"],
    },
    "handler": conversation_history,
    "tier": "core",
}
