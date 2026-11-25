"""
memory/history.py — every conversation, kept locally and searchable.

SAM remembered facts (long_term.json) and one or two sentences per
session, which the next briefing consumed and deleted. "What did we talk about
on Monday?" or "what was that command you gave me yesterday?" had no answer.

SAM keeps the turns themselves:

    memory/history/2026-11-24.jsonl     one line per turn
        {"t": "20:15:03", "role": "user" | "assistant", "text": "..."}

* Local only, plain text, one file per day — delete a day to forget it.
* Old days are pruned after KEEP_DAYS.
* search() is a keyword ranking (no embeddings, no model, no extra RAM),
  which is what an 8 GB laptop can afford while everything else runs.
"""
from __future__ import annotations

import json
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

HISTORY_DIR = Path(__file__).resolve().parent / "history"
KEEP_DAYS = 90
MAX_TEXT = 2000

_lock = threading.Lock()
_pruned_on: date | None = None


def _file_for(day: date) -> Path:
    return HISTORY_DIR / f"{day.isoformat()}.jsonl"


def append(role: str, text: str, when: datetime | None = None) -> None:
    """Record one turn. Never raises — history must not break a conversation."""
    text = " ".join(str(text or "").split())
    if not text:
        return
    when = when or datetime.now()
    line = json.dumps({"t": when.strftime("%H:%M:%S"),
                       "role": "user" if role == "user" else "assistant",
                       "text": text[:MAX_TEXT]}, ensure_ascii=False)
    try:
        with _lock:
            HISTORY_DIR.mkdir(parents=True, exist_ok=True)
            with open(_file_for(when.date()), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        _prune_once(when.date())
    except Exception as e:
        print(f"[History] could not save a turn: {e}")


def _prune_once(today: date) -> None:
    global _pruned_on
    if _pruned_on == today:
        return
    _pruned_on = today
    cutoff = today - timedelta(days=KEEP_DAYS)
    for p in HISTORY_DIR.glob("*.jsonl"):
        try:
            if date.fromisoformat(p.stem) < cutoff:
                p.unlink()
        except Exception:
            continue


def _read_day(day: date) -> list[dict]:
    p = _file_for(day)
    if not p.exists():
        return []
    out = []
    with _lock:
        lines = p.read_text(encoding="utf-8").splitlines()
    for ln in lines:
        try:
            row = json.loads(ln)
            row["date"] = day.isoformat()
            out.append(row)
        except Exception:
            continue
    return out


def days_available() -> list[str]:
    try:
        return sorted((p.stem for p in HISTORY_DIR.glob("*.jsonl")), reverse=True)
    except Exception:
        return []


def recent(days: int = 1, limit: int = 30) -> list[dict]:
    """The last `limit` turns from the last `days` days, oldest first."""
    rows: list[dict] = []
    today = date.today()
    for i in range(max(1, days) - 1, -1, -1):
        rows.extend(_read_day(today - timedelta(days=i)))
    return rows[-limit:]


def on_day(day: str, limit: int = 60) -> list[dict]:
    try:
        return _read_day(date.fromisoformat(day))[:limit]
    except ValueError:
        return []


_WORD = re.compile(r"\w+", re.UNICODE)


def search(query: str, days: int = 30, limit: int = 8) -> list[dict]:
    """Turns that best match `query` from the last `days` days, best first.

    Score = how many query words appear (whole words count double), with a
    small bonus for recency. Each hit carries the turn before and after it so
    the answer has context."""
    words = [w.lower() for w in _WORD.findall(query or "") if len(w) > 1]
    if not words:
        return []
    today = date.today()
    scored = []
    for i in range(max(1, days)):
        day = today - timedelta(days=i)
        rows = _read_day(day)
        for j, row in enumerate(rows):
            low = row.get("text", "").lower()
            toks = set(_WORD.findall(low))
            score = sum(2 if w in toks else 1 for w in words if w in low)
            if score:
                ctx = [r["text"] for r in rows[max(0, j - 1):j + 2]]
                scored.append((score - i * 0.01, {**row, "context": ctx}))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [r for _, r in scored[:limit]]


def format_rows(rows: list[dict]) -> str:
    """Rows as compact lines for a tool result."""
    return "\n".join(f"[{r.get('date', '')} {r.get('t', '')}] {r.get('role', '')}: "
                     f"{r.get('text', '')[:300]}" for r in rows)
