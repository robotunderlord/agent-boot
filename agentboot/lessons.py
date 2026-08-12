"""The ledger: things learned the hard way, recorded so they fire BEFORE the mistake repeats.

WHY THIS IS THE POINT OF THE WHOLE FRAMEWORK
--------------------------------------------
Orientation, enforcement and the tool registry are all present-tense - they help an agent act well
right now. None of them stop it making the same mistake for the fifth time. Repetition is the
actual cost centre: not the hour lost to a hard problem, but the same hour lost again in a month
because what was learned lived only in a finished session.

A lesson is therefore stored the way a REFLEX is stored, not the way documentation is stored:

    tell   - how you RECOGNISE you are in this situation      <- the index key
    trade  - what to do instead
    scar   - the incident that taught it, and what it cost
    cost   - what it actually cost, in the units that motivate

**The `tell` is the index, and that is the whole design.** A ledger keyed by topic answers "what do
we know about X", which requires already knowing to ask about X. A ledger keyed by the TELL answers
"what does this situation resemble", which is the only thing an agent actually has in the moment.
An index that must be consulted deliberately is documentation; an index that fires on the situation
is a habit.

**The `scar` is not decoration.** A rule with its reason amputated does not survive contact with a
new situation - the agent obeys it where it does not apply and abandons it where it does. History
is what makes a rule portable, which is why "understanding history" and "stop repeating" are the
same requirement.

HONEST ABOUT THE MATCHING
-------------------------
Matching is deliberately crude: normalised token overlap across `tell` and `tags`. There is no
model here and there should not be - a dependency-free ledger that surfaces four plausible lessons
is worth more than a clever one that cannot run in the container. Treat a match as "you may be
here before", never as a verdict.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

STOPWORDS = frozenset("""
a an the and or but if then than that this these those is are was were be been being am
to of in on at by for with from as it its into over under about not no do does did done
i you we they he she them us our your their my me have has had will would can could should
""".split())

WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    """Return the meaningful lowercase tokens of a string."""
    return {w for w in WORD.findall(text.lower()) if w not in STOPWORDS and len(w) > 2}


@dataclass(frozen=True)
class Lesson:
    """One thing learned the hard way, indexed by how you recognise the situation."""

    id: str
    tell: str
    trade: str
    scar: str = ""
    cost: str = ""
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject a lesson that cannot be recognised or cannot be acted on."""
        if not self.id.strip():
            raise ValueError("a lesson needs an id")
        if not self.tell.strip():
            raise ValueError(f"lesson {self.id!r} needs a `tell` - a lesson with no trigger never fires")
        if not self.trade.strip():
            raise ValueError(f"lesson {self.id!r} needs a `trade` - a tell with no action is just a worry")

    @property
    def keywords(self) -> set[str]:
        """Return the tokens this lesson is matched on."""
        return _tokens(self.tell) | {t.lower() for t in self.tags}

    def score(self, situation: str) -> float:
        """Return how strongly this lesson matches a described situation, from 0.0 to 1.0."""
        keys = self.keywords
        if not keys:
            return 0.0
        return len(keys & _tokens(situation)) / len(keys)

    def render(self) -> str:
        """Return the lesson as it should appear when it fires."""
        out = [f"[{self.id}] WHEN: {self.tell}", f"          DO: {self.trade}"]
        if self.scar:
            out.append(f"         WHY: {self.scar}")
        if self.cost:
            out.append(f"        COST: {self.cost}")
        return "\n".join(out)

    @classmethod
    def from_dict(cls, data: dict) -> Lesson:
        """Build a lesson from a manifest entry, ignoring unknown keys."""
        known = {f for f in cls.__dataclass_fields__}
        payload = {k: v for k, v in data.items() if k in known}
        if "tags" in payload:
            payload["tags"] = tuple(payload["tags"])
        return cls(**payload)


@dataclass
class Ledger:
    """The bag of tricks - loaded at boot, matched against the situation at hand."""

    lessons: list[Lesson] = field(default_factory=list)

    def add(self, *lessons: Lesson) -> Ledger:
        """Add lessons and return self so registration can chain."""
        self.lessons.extend(lessons)
        return self

    def load(self, path: Path | str | None = None) -> list[Lesson]:
        """Load lessons from a directory of JSON files, skipping anything malformed.

        A broken ledger file must never stop the boot - the boot is what you need in order to fix it.
        """
        directory = Path(path) if path else Path.home() / ".agentboot" / "lessons"
        if not directory.is_dir():
            return []
        loaded: list[Lesson] = []
        for file in sorted(directory.glob("*.json")):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                print(f"[WARN] ledger file unreadable, skipped: {file} ({exc})")
                continue
            entries = data.get("lessons", data) if isinstance(data, dict) else data
            if not isinstance(entries, list):
                print(f"[WARN] ledger file is not a list of lessons, skipped: {file}")
                continue
            for entry in entries:
                try:
                    loaded.append(Lesson.from_dict(entry))
                except (TypeError, ValueError) as exc:
                    print(f"[WARN] bad lesson in {file}, skipped: {exc}")
        self.lessons.extend(loaded)
        return loaded

    def match(self, situation: str, *, threshold: float = 0.2, limit: int = 3) -> list[Lesson]:
        """Return the lessons whose tell most resembles the situation, strongest first.

        Crude by design. A hit means "you may have been here before" - go look. It is not a verdict,
        and it must never be reported as one.
        """
        scored = [(lesson.score(situation), lesson) for lesson in self.lessons]
        hits = sorted(((s, ln) for s, ln in scored if s >= threshold), key=lambda p: -p[0])
        return [lesson for _, lesson in hits[:limit]]

    def brief(self, situation: str, **kw) -> str:
        """Return a printable block of the lessons that fire for a situation."""
        hits = self.match(situation, **kw)
        if not hits:
            return ""
        head = ">>> YOU MAY HAVE BEEN HERE BEFORE - check before you re-derive <<<"
        return "\n\n".join([head] + [lesson.render() for lesson in hits])

    def duplicate_tells(self) -> list[tuple[str, str]]:
        """Return id pairs whose tells overlap heavily - a sign the ledger is repeating itself.

        The ledger has the same failure mode as the agent: writing the same lesson twice under two
        names, which is re-derivation wearing a filing system.
        """
        dupes = []
        for i, first in enumerate(self.lessons):
            for second in self.lessons[i + 1:]:
                keys = first.keywords | second.keywords
                if keys and len(first.keywords & second.keywords) / len(keys) >= 0.6:
                    dupes.append((first.id, second.id))
        return dupes

    def summary(self) -> str:
        """Return a one-line count of the ledger's contents."""
        scarred = sum(1 for lesson in self.lessons if lesson.scar)
        return f"{len(self.lessons)} lessons ({scarred} carry the scar that explains them)"
