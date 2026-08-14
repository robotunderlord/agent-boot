"""The reflexive hook: emit the rules that fire for THIS turn, and nothing else.

WHY THIS REPLACES `cat nag.md`
------------------------------
A static payload is the same forty lines every turn, whatever you are doing. The model re-reads a
rule about CI concurrency while renaming a variable, and the one line that mattered is buried among
thirty-nine that did not. That is a poster on a wall. It costs tokens on every turn and its
signal-to-noise gets worse with every rule you add - so the file punishes you for writing more
doctrine, which is exactly backwards.

A REFLEX reads the situation and emits only what applies:

    static    40 lines, every turn, regardless           a poster
    reflexive 0-3 lines, only when they fire             a reflex

The consequence worth naming: **silence is the normal case.** A turn that trips nothing should
produce nothing. If this thing speaks on every turn it has degenerated back into a poster, and the
matcher needs tightening rather than the output trimming.

THE CONTRACT, MEASURED FROM WORKING HOOKS ON A REAL SEAT
---------------------------------------------------------
The harness pipes JSON on stdin::

    {session_id, transcript_path, cwd, hook_event_name, ...}
    UserPromptSubmit adds the user's text; PreToolUse adds the tool name and its input.

And the rule that outranks everything else here:

    READ STDIN, DO THE WORK, **ALWAYS EXIT 0**.

A hook that errors must never break the session. This module therefore catches everything, tolerates
an empty or garbled pipe, and prefers emitting nothing to raising. A reflex that can crash the agent
is a worse problem than the one it was written to prevent.

WHAT IT MUST NEVER DO
---------------------
**Never echo the tool input back.** A `PreToolUse` payload contains the actual command about to run,
which routinely holds tokens, passwords and connection strings. This module reads that input to
MATCH against, and emits only its own rules - never the text it matched on. Echoing the situation
would turn the safety mechanism into the leak.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .lessons import Ledger

MAX_SITUATION_CHARS = 4000       # enough to match on; bounded so a huge paste cannot stall the turn


def read_event(stream=None) -> dict:
    """Return the hook payload, or an empty dict for an absent or garbled pipe.

    Never raises. A hook that dies on malformed input takes the turn with it.
    """
    try:
        raw = (stream or sys.stdin).read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001 - any parse failure is simply "no event"
        return {}


def situation_of(event: dict) -> str:
    """Extract the text to match against, from whichever event shape arrived.

    Deliberately tolerant about key names: the payload schema is the harness's to change, and a
    reflex system that breaks on a renamed field is a reflex system that silently stops firing.
    """
    parts: list[str] = []
    for key in ("prompt", "user_prompt", "message", "reason"):
        value = event.get(key)
        if isinstance(value, str):
            parts.append(value)

    tool = event.get("tool_name") or event.get("toolName")
    if isinstance(tool, str):
        parts.append(tool)

    payload = event.get("tool_input") or event.get("toolInput")
    if isinstance(payload, dict):
        # Only the fields that describe INTENT. Never sweep the whole object: it carries argument
        # values, and those are where credentials live.
        for key in ("command", "description", "file_path", "path", "pattern", "prompt", "url"):
            value = payload.get(key)
            if isinstance(value, str):
                parts.append(value)
    elif isinstance(payload, str):
        parts.append(payload)

    return " ".join(parts)[:MAX_SITUATION_CHARS]


@dataclass
class ReflexHook:
    """Match the current turn against the ledger and emit only what fires."""

    ledger: Ledger | None = None
    store: Path = field(default_factory=lambda: Path.home() / ".agentboot")
    limit: int = 3
    # Tuned by measurement, not taste: 0.5 gave 6/6 on a fixed case set (three true positives fire,
    # three plausible-but-wrong situations stay silent). Higher starts dropping real hits; lower
    # starts firing on any turn that merely MENTIONS docker.
    #
    # When in doubt, bias toward SILENCE. A false fire at the moment of action is worse than a miss:
    # it teaches the reader that this channel is noise, and then the one that mattered is ignored
    # too. That is EXP-008, applied to the mechanism that enforces EXP-008.
    threshold: float = 0.5

    def load(self) -> ReflexHook:
        """Load the operator's ledger. Silent on failure - an empty ledger simply fires nothing."""
        if self.ledger is None:
            self.ledger = Ledger()
            try:
                self.ledger.load(self.store / "lessons")
            except Exception:  # noqa: BLE001 - a broken ledger must not break the turn
                pass
        return self

    def render(self, situation: str) -> str:
        """Return the block to inject, or an empty string when nothing applies.

        Empty is the expected result. Most turns should trip nothing.
        """
        if not situation.strip():
            return ""
        self.load()
        hits = self.ledger.match(situation, threshold=self.threshold, limit=self.limit)
        if not hits:
            return ""
        lines = [">>> THIS SITUATION HAS BITTEN BEFORE <<<", ""]
        for lesson in hits:
            lines.append(f"  [{lesson.id}] {lesson.trade}")
            if lesson.cost:
                lines.append(f"           last time: {lesson.cost}")
        return "\n".join(lines)

    def run(self, stream=None) -> int:
        """Entry point: read the event, emit any reflexes, and ALWAYS return 0."""
        try:
            block = self.render(situation_of(read_event(stream)))
            if block:
                print(block)
        except Exception:  # noqa: BLE001 - the contract outranks the feature
            pass
        return 0


def main(argv: list[str] | None = None) -> int:
    """Console entry point for use as a hook command."""
    _ = argv
    return ReflexHook().run()


if __name__ == "__main__":
    sys.exit(main())
