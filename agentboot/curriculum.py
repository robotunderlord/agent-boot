"""The curriculum: an education ladder that teaches CAPABILITY, never the teacher's answers.

WHY A CURRICULUM AND NOT A KNOWLEDGE BASE
------------------------------------------
The ledger (`lessons.py`) fires a scar at the moment its situation recurs. That is reactive, and it
is the right shape for a working agent. It is the wrong shape for a NEW one, because a scar handed
to someone who never earned it becomes a rule with its reason amputated - obeyed where it does not
apply, abandoned where it does.

The scars still matter, but they belong to the TEACHER. Their job is to steer the education: they
decide what is worth teaching and in what order, and then they are filed as EVIDENCE in the research
record. The student gets the capability the scar argues for, plus a pointer to the evidence if it
ever wants to check the reasoning. It does not get the injury.

    Scars steer the curriculum. They are not the curriculum.

THE LADDER
----------
Grades are not a decoration - they are a dependency order, and the exam is what enforces it:

    1-12   SCHOOL       literacy of the trade: read before you speak, check before you claim,
                        write it down, say what you do not know
    13-16  UNDERGRAD    the disciplines: verification, recall, scope, boundaries, documentation
    17+    DOCTORATE    original work: form a hypothesis, design the experiment that could REFUTE
                        it, record it, publish it, survive review

A module without an `exam` is refused. An education you cannot be tested on is a reading list, and
the entire point of this package is that reading is not the same as being able to.

WHAT A MODULE MAY NOT CONTAIN
-----------------------------
`teaches` must name a capability - something the student will be able to DO. It may not smuggle in a
specific answer, because a specific answer is inert and rots, while a capability transfers to a
situation nobody has seen yet. Give a man a fish, and so on.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

SCHOOL, UNDERGRAD, DOCTORATE = range(3)
BANDS = {SCHOOL: "school", UNDERGRAD: "undergraduate", DOCTORATE: "doctorate"}


def band_of(grade: int) -> int:
    """Return which band a grade number belongs to."""
    if grade <= 12:
        return SCHOOL
    if grade <= 16:
        return UNDERGRAD
    return DOCTORATE


@dataclass(frozen=True)
class Module:
    """One unit of instruction: a capability, how to practise it, and how it is examined."""

    id: str
    grade: int
    title: str
    teaches: str
    method: str
    exam: str
    evidence: str = ""
    prereq: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Refuse a module that cannot be examined or does not name a capability."""
        if not self.id.strip():
            raise ValueError("a module needs an id")
        if not self.teaches.strip():
            raise ValueError(f"module {self.id!r} must name what the student will be ABLE TO DO")
        if not self.exam.strip():
            raise ValueError(
                f"module {self.id!r} has no exam - an education you cannot be tested on is a "
                "reading list, and reading is not the same as being able to")
        if self.grade < 1:
            raise ValueError(f"module {self.id!r} needs a grade of 1 or higher")

    @property
    def band(self) -> str:
        """Return the human name of this module's band."""
        return BANDS[band_of(self.grade)]

    def render(self) -> str:
        """Return the module as a study card."""
        out = [f"[{self.id}] grade {self.grade} ({self.band}) - {self.title}",
               f"  ABLE TO: {self.teaches}",
               f"  PRACTISE: {self.method}",
               f"  EXAMINED BY: {self.exam}"]
        if self.prereq:
            out.append(f"  AFTER: {', '.join(self.prereq)}")
        if self.evidence:
            out.append(f"  EVIDENCE: {self.evidence}  (the teacher's scar - read it only if you "
                       "want to check the reasoning)")
        return "\n".join(out)

    @classmethod
    def from_dict(cls, data: dict) -> Module:
        """Build a module from a syllabus entry, ignoring unknown keys."""
        known = {f for f in cls.__dataclass_fields__}
        payload = {k: v for k, v in data.items() if k in known}
        if "prereq" in payload:
            payload["prereq"] = tuple(payload["prereq"])
        return cls(**payload)


@dataclass
class Curriculum:
    """The ladder: ordered modules, prerequisite checking, and an honest transcript."""

    modules: list[Module] = field(default_factory=list)

    def add(self, *modules: Module) -> Curriculum:
        """Add modules and return self so a syllabus can be built fluently."""
        self.modules.extend(modules)
        return self

    def load(self, path: Path | str | None = None) -> list[Module]:
        """Load every `*.json` syllabus in a directory, skipping anything malformed.

        A broken syllabus must never stop the boot - the boot is what you need to fix it.
        """
        directory = Path(path) if path else Path.home() / ".agentboot" / "curriculum"
        if not directory.is_dir():
            return []
        loaded: list[Module] = []
        for file in sorted(directory.glob("*.json")):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                print(f"[WARN] syllabus unreadable, skipped: {file} ({exc})")
                continue
            entries = data.get("modules", data) if isinstance(data, dict) else data
            if not isinstance(entries, list):
                print(f"[WARN] syllabus is not a list of modules, skipped: {file}")
                continue
            for entry in entries:
                try:
                    loaded.append(Module.from_dict(entry))
                except (TypeError, ValueError) as exc:
                    print(f"[WARN] bad module in {file}, skipped: {exc}")
        self.modules.extend(loaded)
        return loaded

    # ── ordering ────────────────────────────────────────────────────────────────────────────
    def path(self) -> list[Module]:
        """Return modules in a teachable order: by grade, and never before their prerequisites."""
        remaining = sorted(self.modules, key=lambda m: (m.grade, m.id))
        done: set[str] = set()
        ordered: list[Module] = []
        while remaining:
            ready = [m for m in remaining if set(m.prereq) <= done]
            if not ready:                       # a cycle or a dangling prereq - report, do not hang
                for module in remaining:
                    missing = set(module.prereq) - done
                    print(f"[WARN] {module.id} is unreachable, missing prereq: {sorted(missing)}")
                ordered.extend(remaining)
                break
            for module in ready:
                ordered.append(module)
                done.add(module.id)
                remaining.remove(module)
        return ordered

    def band(self, which: int) -> list[Module]:
        """Return every module in one band, in teachable order."""
        return [m for m in self.path() if band_of(m.grade) == which]

    def missing_prereqs(self) -> list[tuple[str, str]]:
        """Return (module, prereq) pairs naming prerequisites that do not exist."""
        ids = {m.id for m in self.modules}
        return [(m.id, p) for m in self.modules for p in m.prereq if p not in ids]

    # ── output ──────────────────────────────────────────────────────────────────────────────
    def syllabus(self) -> str:
        """Return the whole ladder as study cards, in teachable order."""
        if not self.modules:
            return "(no curriculum loaded - nothing to teach)"
        out, current = [], None
        for module in self.path():
            if module.band != current:
                current = module.band
                out.append(f"\n{'=' * 70}\n{current.upper()}\n{'=' * 70}")
            out.append(module.render())
        return "\n\n".join(out).strip()

    def transcript(self, passed: set[str] | None = None) -> str:
        """Return what has been examined, and what is unlocked next.

        Progress is measured in exams passed, never in modules read. Nothing else would be
        consistent with the rest of this package.
        """
        passed = passed or set()
        ordered = self.path()
        nxt = [m for m in ordered if m.id not in passed and set(m.prereq) <= passed]
        lines = [f"passed {len(passed)}/{len(ordered)} exams"]
        if nxt:
            lines.append("open now:")
            lines += [f"  [{m.id}] grade {m.grade} - {m.title}" for m in nxt[:5]]
        elif len(passed) >= len(ordered) and ordered:
            lines.append("every exam passed - the ladder is finished, the ledger is not")
        return "\n".join(lines)

    def summary(self) -> str:
        """Return a one-line count per band, flagging any dangling prerequisite."""
        counts = {name: len(self.band(b)) for b, name in BANDS.items()}
        dangling = self.missing_prereqs()
        note = f", {len(dangling)} DANGLING PREREQ" if dangling else ""
        return (f"{len(self.modules)} modules "
                f"({counts['school']} school, {counts['undergraduate']} undergrad, "
                f"{counts['doctorate']} doctorate){note}")
