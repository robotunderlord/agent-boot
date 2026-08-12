"""Personality as a mechanism: the thing that shortens the distance between mistake and detection.

WHY THIS IS A MODULE AND NOT A FOLDER OF MARKDOWN
-------------------------------------------------
Two agents can hold identical doctrine and perform completely differently, and the difference is not
knowledge. It is **detection latency**.

    One catches the mistake at step 0, before acting.
    The other is five steps past it before anything registers.

Five steps past is not five times worse - it is qualitatively worse, because by then the honest fix
is to unwind, and unwinding is expensive, so the agent patches forward instead. That is how a bandaid
gets built next to the mechanism that was already correct. The compounding, not the original error,
is what costs the evening.

What closes that distance is disposition: the standing habit of noticing *I am about to assert
something I have not read* before the assertion, rather than after five things have been built on it.
Disposition is not a fact you can look up when needed - by the time you think to look it up, you have
already acted. It has to be **resident**.

Hence the boot order, which is not arbitrary:

    1 ENABLERS -> 2 PERSONALITY -> 3 RESOURCES -> gate -> 4 MEMORIES

Personality loads at tier 2, **before** the agent knows what it can reach. Capability without
disposition is precisely the agent that acts confidently and looks afterwards.

THE TELLS ARE THE ACTUAL MECHANISM
----------------------------------
A posture is aspirational; a **tell** is operational. "You have left this posture when you are
explaining away an inconvenient detail" is a self-check that can fire mid-action, which is the only
place it does any good. So `Persona` carries both, and the tells - not the noble description - are
what gets injected into the per-turn nag.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .boot import Tier
from .steps import Evidence, Step, StepFailed

HEADING = re.compile(r"^##\s+(.+?)\s*$", re.M)
BULLET = re.compile(r"^\s*[-*]\s+(.+?)\s*$", re.M)
TITLE_SPLIT = re.compile(r"\s+[-–—]\s+")


@dataclass
class Persona:
    """A disposition the agent carries: how it behaves, and how it notices it has stopped.

    `posture` is what it does. `tells` are how it catches itself drifting - which is the half that
    actually changes behaviour, because it can fire while an action is in flight.
    """

    name: str
    role: str = ""
    posture: tuple[str, ...] = ()
    tells: str = ""
    source: Path | None = None

    def __post_init__(self) -> None:
        """Reject a persona with no posture - a name and a biography change no behaviour."""
        if not self.name.strip():
            raise ValueError("a persona needs a name")
        if not self.posture:
            raise ValueError(f"persona {self.name!r} has no posture - a biography is not a disposition")

    @classmethod
    def from_markdown(cls, path: Path | str) -> Persona:
        """Parse an avatar file into a loadable persona.

        Expects `## Posture` (a bullet list) and, ideally, `## Tells`. The title line supplies the
        name and role: `# Samuel Clemens - the Librarian`.
        """
        path = Path(path)
        text = path.read_text(encoding="utf-8")

        title = next((ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")), path.stem)
        # Titles are written "Name - Role"; accept an em-dash or en-dash separator too, because
        # prose written by a human will use one and a parser that only knows ASCII silently drops
        # the role rather than failing loudly.
        name, role = TITLE_SPLIT.split(title, maxsplit=1) if TITLE_SPLIT.search(title) else (title, "")
        name, role = name.strip(), role.strip()

        sections: dict[str, str] = {}
        marks = list(HEADING.finditer(text))
        for i, mark in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            sections[mark.group(1).strip().lower()] = text[mark.end():end].strip()

        posture = tuple(BULLET.findall(sections.get("posture", "")))
        if not posture:
            raise ValueError(f"{path} has no '## Posture' bullet list - nothing to load")
        return cls(name=name, role=role, posture=posture,
                   tells=sections.get("tells", ""), source=path)

    def nag_block(self) -> str:
        """Return the resident text: the posture, and the tells that catch drift mid-action."""
        out = [f"--- POSTURE: {self.name}" + (f" ({self.role})" if self.role else "") + " ---"]
        out += [f"  - {line}" for line in self.posture]
        if self.tells:
            indented = self.tells.replace("\n", "\n  ")
            out += ["", "  SELF-CHECK (are you still in it?):", f"  {indented}"]
        return "\n".join(out)

    def step(self) -> PersonaStep:
        """Return the boot step that proves this persona actually loaded."""
        return PersonaStep(self)


class PersonaStep(Step):
    """Boot step proving a persona is resident, not merely present on disk."""

    def __init__(self, persona: Persona) -> None:
        """Store the persona this step verifies."""
        super().__init__(persona.name, critical=True)
        self.persona = persona

    def check(self) -> Evidence:
        """Confirm the persona carries a usable posture."""
        if not self.persona.posture:
            raise StepFailed("loaded but carries no posture - decoration, not disposition")
        detail = f"{len(self.persona.posture)} postures" + (", tells present" if self.persona.tells else
                                                            ", NO TELLS (cannot self-detect drift)")
        return Evidence(detail, str(self.persona.source or self.persona.name))

    def failing_variant(self) -> PersonaStep:
        """Return a persona step with the posture stripped out."""
        hollow = object.__new__(Persona)
        hollow.name, hollow.role, hollow.posture, hollow.tells, hollow.source = (
            self.persona.name, self.persona.role, (), "", self.persona.source)
        return PersonaStep(hollow)


@dataclass
class Wardrobe:
    """The loaded personas, and the tier that proves they are resident."""

    personas: list[Persona] = field(default_factory=list)

    def load(self, directory: Path | str | None = None) -> list[Persona]:
        """Load every avatar markdown file in a directory, skipping any that carry no posture."""
        folder = Path(directory) if directory else Path.home() / ".agentboot" / "avatars"
        if not folder.is_dir():
            return []
        loaded = []
        for path in sorted(folder.glob("*.md")):
            if path.name.lower() == "readme.md":
                continue
            try:
                loaded.append(Persona.from_markdown(path))
            except (OSError, ValueError) as exc:
                print(f"[WARN] avatar not loadable, skipped: {path} ({exc})")
        self.personas.extend(loaded)
        return loaded

    def get(self, name: str) -> Persona | None:
        """Return a persona by case-insensitive name or role match."""
        needle = name.lower()
        for persona in self.personas:
            if needle in persona.name.lower() or needle in persona.role.lower():
                return persona
        return None

    def as_tier(self, number: int = 2, name: str = "personality") -> Tier:
        """Return the tier that loads disposition BEFORE the agent learns what it can reach."""
        return Tier(number, name).add(*[p.step() for p in self.personas])

    def nag_block(self, *names: str) -> str:
        """Return the resident posture text for the named personas, or all of them."""
        chosen = [p for n in names if (p := self.get(n))] if names else self.personas
        return "\n\n".join(persona.nag_block() for persona in chosen)

    def summary(self) -> str:
        """Return a one-line count, flagging any persona that cannot self-detect drift."""
        blind = [p.name for p in self.personas if not p.tells]
        note = f", {len(blind)} with NO tells" if blind else ", all carry tells"
        return f"{len(self.personas)} personas{note}"
