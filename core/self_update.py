"""
core/self_update.py — SAM changes its own code when the owner asks, safely.

    "SAM, ek nayi setting banao jisse briefing band ho jaye"
    "SAM, apne andar ek naya feature jodo: ..."

THE FLOW (every arrow is a gate; nothing reaches `main` without the owner)

    voice request
      → CONFIRM #1 on screen ("Let SAM change its own code: …")
      → a new git branch sam-self/<time>; the working tree must be clean
      → the coding agent (actions/dev_agent._improve_folder) edits SAM's own
        folder, guided by AGENTS.md and the project profile in core/code_checks
      → checks: every changed .py compiles, `python -m tests.sam_tests` passes
          ✗ failed  → every change is thrown away, the branch deleted, and SAM
                      says why
          ✓ passed  → committed on the branch; the working tree goes back to
                      the current version
      → CONFIRM #2 on screen ("Apply … and restart SAM")
          CONFIRM   → fast-forward the original branch, restart SAM
          CANCEL    → nothing applied; the branch stays (say "apply it" later)

    "pichla code change wapas lo" → CONFIRM → `git revert` of the last
    self-update commit, restart.

WHY THESE GATES
    A model that reads web pages and documents could be told by one of them to
    "change your code". The tool is therefore never enough on its own: the
    owner presses CONFIRM twice, and the change is tested before the second.
    core/policy.py marks "self_update" as a category that can never be turned off.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
BRANCH_PREFIX = "sam-self/"
COMMIT_PREFIX = "SAM self-update: "
TEST_TIMEOUT = 600

_lock = threading.Lock()
_state = {"status": "idle", "branch": "", "base": "", "instruction": "", "summary": ""}


# ── git helpers ──────────────────────────────────────────────────────────────

def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout.strip()


def available() -> str:
    """'' when self-update can run here, otherwise why not."""
    try:
        git("rev-parse", "--is-inside-work-tree")
    except Exception:
        return "SAM's folder is not a git repository (git is needed to undo changes)"
    dirty = git("status", "--porcelain")
    if dirty:
        files = ", ".join(line[3:] for line in dirty.splitlines()[:5])
        return (f"there are uncommitted changes in SAM's folder ({files}) — commit or "
                f"discard them first, so a failed attempt cannot mix with them")
    return ""


def status() -> dict:
    with _lock:
        out = dict(_state)
    try:
        out["pending"] = [b.strip(" *") for b in
                          git("branch", "--list", BRANCH_PREFIX + "*").splitlines() if b.strip()]
        out["last_applied"] = git("log", "-1", "--format=%h %s", f"--grep=^{COMMIT_PREFIX}",
                                  check=False)
    except Exception:
        out["pending"], out["last_applied"] = [], ""
    return out


def _set(**kw) -> None:
    with _lock:
        _state.update(kw)


# ── checks ───────────────────────────────────────────────────────────────────

def _changed_files(base: str) -> list[str]:
    names = set(git("diff", "--name-only", base).splitlines())
    names |= set(git("ls-files", "--others", "--exclude-standard").splitlines())
    return sorted(n for n in names if n)


def verify(files: list[str]) -> str:
    """'' when the change compiles and the self-test passes, otherwise the problem."""
    for f in files:
        if f.endswith(".py") and (ROOT / f).exists():
            r = subprocess.run([sys.executable, "-m", "py_compile", f], cwd=ROOT,
                               capture_output=True, text=True)
            if r.returncode != 0:
                return f"{f} does not compile: {(r.stderr or '').strip()[-300:]}"
    try:
        r = subprocess.run([sys.executable, "-m", "tests.sam_tests"], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=TEST_TIMEOUT)
    except subprocess.TimeoutExpired:
        return "the self-test did not finish in time"
    if r.returncode != 0:
        fails = [l.strip() for l in r.stdout.splitlines() if "FAIL" in l][:5]
        return "the self-test failed: " + ("; ".join(fails) or r.stdout.strip()[-300:])
    return ""


# ── the job ──────────────────────────────────────────────────────────────────

def run_change(instruction: str, player=None,
               say: Callable[[str], None] = lambda m: None,
               log: Callable[[str], None] = print,
               ask_apply: Optional[Callable[[str, str, Callable[[], str]], str]] = None,
               restart: Callable[[], None] = lambda: None,
               improve: Optional[Callable[[Path, str, object], str]] = None) -> str:
    """The whole flow after CONFIRM #1. Blocking; call it on a worker thread.
    `improve` is the coding agent (injectable for tests)."""
    problem = available()
    if problem:
        say(f"[SELF_UPDATE] Could not start: {problem}.")
        return problem
    if improve is None:
        from actions import dev_agent

        def improve(folder, text, pl):
            if not dev_agent._job_lock.acquire(blocking=False):
                raise RuntimeError("the coding agent is busy with another job")
            try:
                dev_agent._new_job(folder, "self-update", text, pl, kind="improve")
                return dev_agent._improve_folder(folder, text, pl)
            finally:
                dev_agent._job_lock.release()

    base = git("rev-parse", "--abbrev-ref", "HEAD")
    branch = BRANCH_PREFIX + time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
    _set(status="working", branch=branch, base=base, instruction=instruction, summary="")
    git("checkout", "-q", "-b", branch)
    log(f"SYS: Self-update started on branch {branch}.")

    def discard(reason: str) -> str:
        git("reset", "-q", "--hard", check=False)
        git("clean", "-q", "-fd", check=False)
        git("checkout", "-q", base, check=False)
        git("branch", "-q", "-D", branch, check=False)
        _set(status="idle", branch="")
        log(f"SYS: Self-update discarded — {reason}")
        say(f"[SELF_UPDATE] The code change was NOT applied: {reason}. Everything is "
            f"back as it was. Tell the user briefly, in their language.")
        return reason

    try:
        summary = improve(ROOT, instruction, player) or ""
    except Exception as e:
        return discard(f"the coding agent failed ({type(e).__name__}: {str(e)[:160]})")

    files = _changed_files(base)
    if not files:
        return discard("the coding agent did not change anything")
    _set(status="testing", summary=summary)
    log(f"SYS: Self-update: testing {len(files)} changed file(s)…")
    problem = verify(files)
    if problem:
        return discard(problem)

    git("add", "-A")
    git("commit", "-q", "-m", f"{COMMIT_PREFIX}{instruction[:60]}",
        "-m", f"Instruction: {instruction}\n\n{summary[:1500]}")
    git("checkout", "-q", base)
    _set(status="waiting for confirmation")
    short = ", ".join(files[:6]) + (" …" if len(files) > 6 else "")

    def apply() -> str:
        return apply_branch(branch, restart=restart, log=log)

    if ask_apply is None:
        return f"tested and committed on {branch}; not applied"
    msg = ask_apply(f"Apply SAM code change and restart",
                    f"{instruction[:120]} — {len(files)} file(s): {short}", apply)
    say(f"[SELF_UPDATE] The change is written and passed every test ({len(files)} "
        f"files: {short}). What it did: {summary[:500]} — It is NOT applied yet. "
        f"Ask the user to press CONFIRM on screen to apply it and restart SAM. "
        f"Tell them in their language, briefly, without reading file paths aloud.")
    return msg


def apply_branch(branch: str = "", restart: Callable[[], None] = lambda: None,
                 log: Callable[[str], None] = print) -> str:
    """Fast-forward the current branch to a tested self-update branch, then restart."""
    if not branch:
        pending = status().get("pending") or []
        if not pending:
            return "there is no tested change waiting"
        branch = sorted(pending)[-1]
    problem = available()
    if problem:
        return problem
    git("merge", "-q", "--ff-only", branch)
    git("branch", "-q", "-d", branch, check=False)
    _set(status="idle", branch="")
    log(f"SYS: Self-update applied from {branch}. Restarting SAM…")
    restart()
    return f"applied {branch}; SAM is restarting"


def rollback(restart: Callable[[], None] = lambda: None,
             log: Callable[[str], None] = print) -> str:
    """Revert the most recent applied self-update commit, then restart."""
    problem = available()
    if problem:
        return problem
    sha = git("log", "-1", "--format=%H", f"--grep=^{COMMIT_PREFIX}", check=False)
    if not sha:
        return "SAM has not changed its own code yet, so there is nothing to undo"
    subject = git("log", "-1", "--format=%s", sha)
    git("revert", "--no-edit", sha)
    log(f"SYS: Reverted '{subject}'. Restarting SAM…")
    restart()
    return f"reverted '{subject}'; SAM is restarting"


def discard_pending() -> str:
    pending = status().get("pending") or []
    for b in pending:
        git("branch", "-q", "-D", b, check=False)
    return f"deleted {len(pending)} untested or unapplied change(s)" if pending else "nothing waiting"
