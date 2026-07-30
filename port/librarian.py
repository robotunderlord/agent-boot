#!/usr/bin/env python3
"""
librarian.py — THE LIBRARIAN, ported for the work seat.

Each worker is a plain headless `claude -p` (cheap model) handed ONE directive. The
batch claude does the thinking itself — reads the transcript, routes the aging tail,
shelves keepers to your vault (breadcrumbs left behind), and at consolidate time
archives the FULL session to Open WebUI. Boots fresh, does the job, exits. Zero
context accumulation in the main session — the daemon just fires the worker.

Config via ENV (set to YOUR paths — nothing hardcoded):
  VAULT             your Obsidian vault root (breadcrumbs -> $VAULT/.ai/)
  CLAUDE_PROJECTS   dir holding Claude Code .jsonl transcripts (to auto-find newest)
  LIBRARIAN_MODEL   cheap model for the workers (default: a haiku-class alias)
  LIBRARIAN_PERSONA name the worker directives address the agent by (default: LIBRARIAN)
  OWUI_URL/OWUI_KEY/OWUI_MODEL   for the Open WebUI archive (see owui_sync.py)

Usage:
  librarian.py groom       --jsonl <t.jsonl>
  librarian.py consolidate --jsonl <t.jsonl>          # ~65% / session-end sweep (brick wall)
  librarian.py groom       --loop --interval 300      # run as a daemon
"""
import os
import sys
import glob
import time
import argparse
import subprocess

HERE   = os.path.dirname(os.path.abspath(__file__))
PY     = sys.executable
OWUI   = f'"{PY}" "{os.path.join(HERE, "owui_sync.py")}"'
VAULT  = os.environ.get("VAULT", os.path.expanduser("~/vault"))
AI     = os.path.join(VAULT, ".ai")
DEFAULT_MODEL = os.environ.get("LIBRARIAN_MODEL", "claude-haiku-4-5-20251001")
PERSONA = os.environ.get("LIBRARIAN_PERSONA", "LIBRARIAN")

WORKERS = {
"groom": lambda sid, jsonl: f"""You are the {PERSONA} GROOMER (lite context router). Keep the working \
context lean by shelving aging detail to the vault, leaving breadcrumbs.
1. Read the AGING tail of the transcript {jsonl} (older exchanges, NOT the most recent ~10 — those stay \
active). Skip tool-result noise.
2. Route each substantive, aging, not-yet-shelved segment: GROOM valuable-but-aging / KEEP still-active / DROP noise.
3. For each GROOM: append a one-line breadcrumb to "{AI}/groom-log.md" ("<=12-word gist -> shelved: <note>"), \
and write the detail (key facts, NO secrets) to "{AI}/shelved/{sid}-<n>.md".
4. NEVER shelve credentials/keys/tokens — those stay only in your secrets store.
Be terse and cheap. Print one line per segment "<gist> -> ROUTE". Then exit.""",

"consolidate": lambda sid, jsonl: f"""You are the {PERSONA} CONSOLIDATOR (session-end / ~65% brick-wall sweep).
1. ARCHIVE the full session to Open WebUI: run `{OWUI} sync --jsonl "{jsonl}"`.
2. Read the transcript {jsonl}; audit for open threads, decisions, unsaved work, leaked creds.
3. Write the RESUME BRIEF to "{AI}/resume-brief.md" — fields Task / State / Next / Threads / Watch / Refs, \
POINTERS not payload (so a cold session resumes with zero prior context).
4. Groom remaining major threads to "{AI}/shelved/". Then exit.
After this runs, it is SAFE to `/clear` and paste the resume brief — everything is archived + shelved.""",
}


def fire(worker, sid, jsonl, model, timeout):
    """Spawn a headless `claude -p` worker for the given directive; return its exit code."""
    os.makedirs(os.path.join(AI, "shelved"), exist_ok=True)
    directive = WORKERS[worker](sid, jsonl)
    print(f"[librarian] batch claude: worker={worker} session={sid[:8]} model={model}")
    r = subprocess.run(["claude", "-p", directive, "--model", model],
                       capture_output=True, text=True, timeout=timeout)
    print(r.stdout.strip()[:3000])
    if r.returncode != 0:
        print(f"[librarian] rc={r.returncode}: {r.stderr[:400]}")
    return r.returncode


def newest_jsonl():
    """Return the most recently modified transcript under $CLAUDE_PROJECTS, or ""."""
    d = os.environ.get("CLAUDE_PROJECTS", "")
    if not d: return ""
    files = sorted(glob.glob(os.path.join(d, "**", "*.jsonl"), recursive=True),
                   key=os.path.getmtime, reverse=True)
    return files[0] if files else ""


def main():
    """Parse CLI arguments and run the chosen worker once, or as a loop daemon."""
    ap = argparse.ArgumentParser(prog="librarian.py")
    ap.add_argument("worker", choices=list(WORKERS))
    ap.add_argument("--session", default="")
    ap.add_argument("--jsonl", default="")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=int, default=300)
    a = ap.parse_args()

    def resolve():
        j = a.jsonl or newest_jsonl()
        sid = a.session or (os.path.basename(j)[:-6] if j.endswith(".jsonl") else "session")
        return sid, j

    if a.loop:
        print(f"[librarian] daemon: {a.worker} every {a.interval}s  (vault={VAULT})")
        while True:
            try:
                sid, j = resolve()
                if j: fire(a.worker, sid, j, a.model, a.timeout)
                else: print("[librarian] no transcript found (set CLAUDE_PROJECTS or pass --jsonl)")
            except Exception as e:
                print(f"[librarian] {e}")
            time.sleep(a.interval)
    else:
        sid, j = resolve()
        if not j: sys.exit("no transcript — pass --jsonl or set CLAUDE_PROJECTS")
        sys.exit(fire(a.worker, sid, j, a.model, a.timeout))


if __name__ == "__main__":
    main()
