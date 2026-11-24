"""core/routines/desktop.py — routines as the desktop app runs them.

main.py builds a host from its own session (can the assistant speak, how long
has the user been quiet, how to put words in its mouth) and calls attach().
The first time, the built-in routines are created from what the app did before
Mark LVII, so nobody loses a morning briefing to an upgrade:

    opening      the startup briefing — on if the MORNING BRIEF switch was on
    check-in     the proactive check-in after 30 quiet minutes, at most hourly
    news-watch   the topic watch, every 2 hours between 08:00 and 22:00
    quiet hours  23:00-07:00 (nothing unprompted is said then)

They stay routines from then on: switch them off, move the briefing to 08:30,
change its news topic or the check-in's subjects, by voice or from the panel.
"""
from __future__ import annotations

import threading
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent.parent
_lock = threading.Lock()
_engine = None

# What the check-in may be about, in rotation. Data now rather than code: the
# three focuses the proactive engine always had, and the user can change them.
DEFAULT_FOCUSES = [
    "The user's active projects or goals, if any are stored: ask how something is going, "
    "or offer a relevant tip.",
    "The time of day and the user's wellbeing: a warm check-in, a reminder to take a break, "
    "or something timely.",
    "Something genuinely interesting or useful — a fact, a suggestion, or a question based on "
    "what you know about this person.",
]


# SAM defaults: speak unprompted less often, and never at night. The original
# defaults (check-in after 15 idle minutes, news every 30 minutes, round the
# clock, no quiet hours) were noisy and kept background work running all day.
QUIET_CHECKIN_IDLE = 30        # minutes of silence before a check-in
QUIET_CHECKIN_COOLDOWN = 60    # at most one check-in per hour
QUIET_NEWS_EVERY = 120         # news-topic watch every 2 hours, 08:00-22:00
DEFAULT_QUIET_HOURS = "23:00-07:00"


def routines_path() -> Path:
    return _BASE / "memory" / "routines.json"


def seed_defaults(engine, brief_enabled: bool) -> None:
    """Create the built-in routines once, from the settings the app had."""
    if engine.seeded:
        return
    if engine.find_builtin("briefing") is None:
        engine.add(name="Opening briefing", kind="builtin", builtin="briefing",
                   trigger={"type": "startup"}, system=True, enabled=bool(brief_enabled),
                   options={"news": True, "news_topic": "top world news today", "extra": ""})
    if engine.find_builtin("checkin") is None:
        engine.add(name="Check-in", kind="builtin", builtin="checkin",
                   trigger={"type": "idle", "minutes": QUIET_CHECKIN_IDLE,
                            "cooldown": QUIET_CHECKIN_COOLDOWN}, system=True, quiet=True,
                   options={"focuses": list(DEFAULT_FOCUSES)})
    if engine.find_builtin("news_watch") is None:
        engine.add(name="News watch", kind="builtin", builtin="news_watch",
                   trigger={"type": "time", "rule": {"type": "interval",
                                                     "minutes": QUIET_NEWS_EVERY,
                                                     "start": "08:00", "end": "22:00"}},
                   system=True, quiet=True)
    if not engine.quiet_hours():
        engine.set_quiet_hours(DEFAULT_QUIET_HOURS)
    engine.mark_seeded()


def attach(host, log=print):
    """Start the routine engine for this app. Returns it."""
    global _engine
    with _lock:
        if _engine is None:
            from core.routines.engine import RoutineEngine
            eng = RoutineEngine(routines_path(), host, log=log, autostart=False)
            try:
                from memory.config_manager import get_brief_enabled
                brief = get_brief_enabled()
            except Exception:
                brief = True
            seed_defaults(eng, brief)
            eng.start()
            _engine = eng
        else:
            _engine.host = host
        return _engine


def engine():
    return _engine


def set_builtin_enabled(name: str, enabled: bool) -> None:
    """The HUD's switch for a built-in routine (MORNING BRIEF) turned it on or off."""
    eng = _engine
    found = eng.find_builtin(name) if eng else None
    if found and bool(found["enabled"]) != bool(enabled):
        eng.update(found["id"], enabled=bool(enabled))


def mirror_brief_switch(enabled: bool) -> None:
    """The briefing was switched by voice: keep the HUD's MORNING BRIEF setting
    telling the same story, and the fallback path too if routines ever fail."""
    from memory.config_manager import save_brief_enabled
    save_brief_enabled(bool(enabled))


class CallbackHost:
    """A host made of plain callables — what main.py hands to attach()."""

    def __init__(self, ready, idle_seconds, say, prompt, builtin, log):
        self.ready, self.idle_seconds, self.say = ready, idle_seconds, say
        self.prompt, self.builtin, self.log = prompt, builtin, log

    def start_task(self, text, agent, minutes, deliver):
        from core.tasks import desktop as tasks
        tasks.ensure().start(text, agent=agent, minutes=minutes, deliver=deliver, origin="routine")
