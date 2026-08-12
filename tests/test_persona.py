"""Tests for personality-as-mechanism.

The claim under test is narrow and checkable: a persona must change what is RESIDENT, not merely
exist as a file. A biography that loads is still decoration.
"""
import tempfile
import unittest
from pathlib import Path

from agentboot.persona import Persona, PersonaStep, Wardrobe

AVATARS = Path(__file__).resolve().parents[1] / "avatars"

GOOD = """# Ada Example - the Tester

## Who
Somebody long dead.

## Posture

- Check the thing before you say the thing.
- Prefer the measurement to the memory.

## Tells

You have left it when you are narrating rather than reading.
"""

NO_POSTURE = """# Empty Person - the Ornament

## Who
A biography with no disposition attached.
"""


class ABiographyIsNotADisposition(unittest.TestCase):
    """A persona with no posture changes no behaviour and is refused."""

    def test_persona_without_posture_is_rejected(self):
        """Constructing a postureless persona raises."""
        with self.assertRaises(ValueError):
            Persona(name="Nobody", posture=())

    def test_markdown_without_posture_is_rejected(self):
        """An avatar file with no Posture bullets is not loadable."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ornament.md"
            path.write_text(NO_POSTURE, encoding="utf-8")
            with self.assertRaises(ValueError):
                Persona.from_markdown(path)

    def test_wardrobe_skips_unloadable_avatars_without_dying(self):
        """One bad avatar must not stop the others loading."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ornament.md").write_text(NO_POSTURE, encoding="utf-8")
            (Path(tmp) / "good.md").write_text(GOOD, encoding="utf-8")
            loaded = Wardrobe().load(tmp)
            self.assertEqual([p.name for p in loaded], ["Ada Example"])


class ParsingSplitsNameFromRole(unittest.TestCase):
    """Titles are written by humans, so the separator may not be an ASCII hyphen."""

    def test_ascii_hyphen_title(self):
        """A plain hyphen separates name from role."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.md"
            path.write_text(GOOD, encoding="utf-8")
            persona = Persona.from_markdown(path)
            self.assertEqual(persona.name, "Ada Example")
            self.assertEqual(persona.role, "the Tester")

    def test_em_dash_title_still_yields_a_role(self):
        """An em-dash must not silently drop the role - that is a parser lying quietly."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.md"
            path.write_text(GOOD.replace("Ada Example - the Tester", "Ada Example — the Tester"),
                            encoding="utf-8")
            self.assertEqual(Persona.from_markdown(path).role, "the Tester")


class TheTellsAreWhatGoResident(unittest.TestCase):
    """A posture is aspirational; a tell can fire mid-action, which is where it does any good."""

    def _persona(self):
        """Return a persona parsed from the good fixture."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.md"
            path.write_text(GOOD, encoding="utf-8")
            return Persona.from_markdown(path)

    def test_nag_block_carries_posture_and_self_check(self):
        """Both halves reach the resident text."""
        block = self._persona().nag_block()
        self.assertIn("Check the thing before you say the thing.", block)
        self.assertIn("SELF-CHECK", block)
        self.assertIn("narrating rather than reading", block)

    def test_step_flags_a_persona_that_cannot_self_detect(self):
        """A persona with no tells is loaded but reported as unable to notice its own drift."""
        persona = Persona(name="Terse", posture=("do the thing",), tells="")
        self.assertIn("NO TELLS", PersonaStep(persona).run().detail)

    def test_persona_step_can_fail(self):
        """The personality tier must be provable like every other tier."""
        self.assertTrue(PersonaStep(self._persona()).failing_variant().run().status.is_red)


class TheShippedAvatarsAllLoad(unittest.TestCase):
    """Every avatar in this repo must be a working mechanism, not a nice piece of writing."""

    def test_all_avatars_load_with_posture_and_tells(self):
        """Each shipped avatar parses, carries a role, postures, and self-check tells."""
        wardrobe = Wardrobe()
        loaded = wardrobe.load(AVATARS)
        self.assertGreaterEqual(len(loaded), 5)
        for persona in loaded:
            self.assertTrue(persona.role, f"{persona.name} has no role")
            self.assertTrue(persona.posture, f"{persona.name} has no posture")
            self.assertTrue(persona.tells, f"{persona.name} cannot self-detect drift")

    def test_lookup_by_role_works(self):
        """You ask for the discipline you need, not the historical figure's surname."""
        wardrobe = Wardrobe()
        wardrobe.load(AVATARS)
        self.assertIsNotNone(wardrobe.get("skeptic"))
        self.assertIsNotNone(wardrobe.get("adversary"))
        self.assertIsNone(wardrobe.get("nobody-by-that-name"))

    def test_personality_tier_loads_before_resources(self):
        """Disposition is tier 2; capability without disposition is the failure mode."""
        wardrobe = Wardrobe()
        wardrobe.load(AVATARS)
        self.assertEqual(wardrobe.as_tier().number, 2)


if __name__ == "__main__":
    unittest.main()
