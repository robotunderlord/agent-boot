"""Intake: the questionnaire a BLANK container runs to build its own store.

TWO WAYS TO SHIP AN AGENT
-------------------------
**Cooked** - the curriculum and a starter store are baked in. It boots educated and can work
immediately. Right when the seat is known in advance and you want every instance identical.

**Blank + questionnaire** - it boots with the ability to learn and nothing learned, then INTERVIEWS
its environment and writes its own store from the answers. Right when the seat is not known, which
is most of the time, and the only honest option when the environment has rules the image cannot
guess.

The second is the default, and the reason is the same one that separates the class from the objects:
a container that arrives already knowing your rules has been handed somebody else's answers. One
that asks gets yours.

WHAT THE ANSWERS BECOME
-----------------------
Nothing here is a preference survey. Every question exists because its answer WRITES something:

    identity, irreversibility, secrets  ->  the LOCAL RULES block in the nags
    what is frozen, how work is validated ->  the per-action nag
    what it can reach                    ->  tools.d manifest, then PROBED before it is believed
    where the work stands                ->  the tattoo's running-thread block
    which discipline it most lacks       ->  the resident posture

A question whose answer changes no file does not belong here. It is a survey, and surveys are how
you end up with a container full of opinions and no configuration.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Question:
    """One intake question, the file its answer writes, and who is competent to answer it.

    `answered_by` is the load-bearing field, and it has three values because there are three
    genuinely different kinds of knowledge here:

        agent    DISCOVERABLE. Run the probe. Whose account this is, what is on PATH.
        context  the installing session, which usually already knows this user, likely HAS this.
                 It must PROPOSE and get confirmation - never write it silently. Drafting from
                 real knowledge is good; laundering a draft into a fact is not.
        human    POLICY. It leaves no trace in the environment and cannot be inferred from it.
                 Ask. A guessed rule is worse than an absent one, because it will be obeyed.

    Capability is discoverable. Habit is often already known. Policy is neither.
    """

    key: str
    prompt: str
    why: str
    writes: str
    answered_by: str = "human"      # "agent" = discoverable by probe, "human" = policy, must be told
    probe: str = ""                 # a command the installing agent can run to draft the answer

    def __post_init__(self) -> None:
        """Refuse a question whose answer writes nothing - that is a survey, not an intake."""
        if not self.writes.strip():
            raise ValueError(f"question {self.key!r} writes nothing; intake is not a survey")
        if self.answered_by not in ("agent", "context", "human"):
            raise ValueError(
                f"question {self.key!r}: answered_by must be 'agent', 'context' or 'human'")
        if self.answered_by == "agent" and not self.probe.strip():
            raise ValueError(
                f"question {self.key!r} claims an agent can answer it but offers no probe - "
                "that is an invitation to guess")


QUESTIONS: tuple[Question, ...] = (
    Question("identity",
             "Whose authority do you act under here, and what are you forbidden to touch?",
             "An agent that does not know whose account it is using cannot judge a boundary.",
             "nag LOCAL RULES", "agent", "id -un; id -u; git config --get user.email"),
    Question("irreversible",
             "What actions here cannot be undone? Name them concretely.",
             "Irreversibility is the only thing that turns a mistake into an incident.",
             "nag-terse LOCAL RULES", "human"),
    Question("secrets",
             "What must never leave this machine, and which ordinary commands would emit it?",
             "Credentials leak most often from commands nobody thinks of as touching secrets.",
             "nag LOCAL RULES", "human"),
    Question("frozen",
             "What is shared or standard here, and therefore must not be bent to suit one caller?",
             "Bending a shared component for one caller is how a bandaid gets built beside the "
             "correct mechanism.",
             "nag-terse LOCAL RULES", "human"),
    Question("validation",
             "How is work actually validated here - what is the real test, and what must you NOT "
             "do by hand?",
             "Hand-triggering a pipeline is the classic way to spend an hour diagnosing your own "
             "trigger.",
             "nag-terse LOCAL RULES", "human"),
    Question("reach",
             "What can you reach from here? For each: when you would use it, the command, and the "
             "tempting wrong move it replaces.",
             "A capability nothing connects to a situation is a capability you do not have.",
             "tools.d/environment.json", "agent",
             "for t in git jq rg curl docker kubectl python3; do command -v $t; done"),
    Question("standing",
             "Where does the work stand right now - working on, last verified fact, next single "
             "action, open unknowns?",
             "The running thread is the only thing that does not survive a kill unless written.",
             "tattoo [STATE]", "context"),
    Question("weakness",
             "What do you get told twice? Which discipline do you most need standing over your "
             "shoulder?",
             "The resident posture should target the actual failure, not a flattering one.",
             "posture.md", "context"),
)


class Intake:
    """Render the intake sheet, and turn returned answers into a configured store."""

    def __init__(self, payload_dir: Path | str) -> None:
        """Store where the answers will be written."""
        self.payload_dir = Path(payload_dir)

    def sheet(self) -> str:
        """Return the intake brief, addressed to the AI that is installing this.

        Grouped by who can competently answer, because the failure this prevents is an installer
        guessing a policy it could have asked about in one line.
        """
        out = [
            "AGENT INTAKE - you are installing this container. Answering these configures it.",
            "",
            "You are almost certainly an AI session doing this install, and you probably already",
            "know this user. Good - use that. But keep the three kinds of knowledge separate:",
            "",
            "  [agent]   DISCOVER it. Run the probe, read the output, answer from the artifact.",
            "  [context] You likely KNOW this already. Draft it, show your draft, and get it",
            "            CONFIRMED before writing. Proposing from memory is fine; writing it",
            "            silently is how a wrong assumption becomes a standing rule.",
            "  [human]   POLICY. It leaves no trace you can probe and you must not infer it. ASK.",
            "",
            "'I do not know' is a real answer and beats a guess: an absent rule is honest, a",
            "guessed one gets obeyed.",
            "",
        ]
        for band, label in (("agent", "DISCOVER THESE YOURSELF"),
                            ("context", "DRAFT THESE, THEN CONFIRM"),
                            ("human", "ASK - DO NOT INFER")):
            group = [q for q in QUESTIONS if q.answered_by == band]
            if not group:
                continue
            out += [f"{'=' * 70}", f"{label}", f"{'=' * 70}", ""]
            for q in group:
                out += [f"[{q.key}] {q.prompt}",
                        f"     why: {q.why}",
                        f"     writes: {q.writes}"]
                if q.probe:
                    out.append(f"     probe: {q.probe}")
                out.append("")
        out += [
            "Return as JSON: {\"identity\": \"...\", \"irreversible\": \"...\", ...}",
            "Then: python3 -m agentboot intake --answers answers.json",
        ]
        return "\n".join(out)

    # ── applying answers ────────────────────────────────────────────────────────────────────
    def _append_local(self, filename: str, keys: tuple[str, ...], answers: dict) -> str | None:
        """Append the answered rules to a payload's LOCAL RULES area."""
        target = self.payload_dir / filename
        if not target.exists():
            return None
        lines = [f"  - [{k}] {answers[k].strip()}" for k in keys if answers.get(k, "").strip()]
        if not lines:
            return None
        block = "\n".join(["", "--- LOCAL RULES (from intake) ---", *lines, ""])
        target.write_text(target.read_text(encoding="utf-8") + block, encoding="utf-8")
        return str(target)

    def apply(self, answers: dict) -> list[str]:
        """Write every answered question into the store, returning the files changed.

        Unanswered questions write nothing. A blank answer must not produce a confident-looking
        empty rule - an absent rule is honest, an empty one is a lie with a heading.
        """
        written: list[str] = []
        self.payload_dir.mkdir(parents=True, exist_ok=True)

        for filename, keys in (("nag.md", ("identity", "secrets")),
                               ("nag-terse.md", ("irreversible", "frozen", "validation"))):
            if path := self._append_local(filename, keys, answers):
                written.append(path)

        if (reach := answers.get("reach", "").strip()):
            tools = self.payload_dir / "tools.d"
            tools.mkdir(parents=True, exist_ok=True)
            target = tools / "intake.json"
            target.write_text(json.dumps({
                "//": ["Declared at intake. Every entry is PROBED before it is believed; anything "
                       "that fails its probe is dropped rather than left as a lure.",
                       "Raw intake answer preserved below so the next reader can see what was "
                       "claimed versus what verified."],
                "raw_answer": reach,
                "tools": [],
            }, indent=2) + "\n", encoding="utf-8")
            written.append(str(target))

        if (standing := answers.get("standing", "").strip()):
            tattoo = self.payload_dir / "tattoo.md"
            if tattoo.exists():
                tattoo.write_text(
                    tattoo.read_text(encoding="utf-8")
                    + f"\n## [STATE] from intake\n\n{standing}\n", encoding="utf-8")
                written.append(str(tattoo))

        return written


def load_answers(path: Path | str) -> dict:
    """Read an answers file, returning only string values keyed by known questions."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    known = {q.key for q in QUESTIONS}
    unknown = set(data) - known - {"//"}
    if unknown:
        print(f"[WARN] ignoring unknown intake keys: {sorted(unknown)}")
    return {k: v for k, v in data.items() if k in known and isinstance(v, str)}
