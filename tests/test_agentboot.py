"""Tests for the invariants that make this framework worth anything.

Every test here asserts that something REFUSES to lie. A framework whose selling point is "a status
line cannot fake a pass" has to demonstrate the refusal, not describe it.
"""
import json
import tempfile
import unittest
from pathlib import Path

from agentboot import Boot, CommandStep, EnforcementInstaller, Evidence, FileStep, Status, Step, Tier
from agentboot.status import StatusLine


class EvidenceRules(unittest.TestCase):
    """Evidence must name its source, or it is an assertion in a lab coat."""

    def test_rejects_missing_source(self):
        """Evidence without a source is refused at construction."""
        with self.assertRaises(ValueError):
            Evidence("something happened", "")

    def test_rejects_missing_detail(self):
        """Evidence without a detail is refused at construction."""
        with self.assertRaises(ValueError):
            Evidence("   ", "/some/path")

    def test_status_line_rejects_empty_detail(self):
        """An empty detail would render as a bare green line, so it is refused."""
        with self.assertRaises(ValueError):
            StatusLine(Status.OK, "Thing", "")


class SilenceIsNotSuccess(unittest.TestCase):
    """A step that returns nothing must be recorded FAIL, never OK."""

    def test_step_returning_none_is_failure(self):
        """The signature of a check wired to nothing is silence; silence must go red."""

        class SilentStep(Step):
            """A step that runs happily and verifies nothing at all."""

            def check(self):
                """Return nothing, as a broken check does."""
                return None

            def failing_variant(self):
                """Return self; this step is already incapable of passing honestly."""
                return self

        self.assertEqual(SilentStep("Silent").run().status, Status.FAIL)


class CommandStepBelievesTheMarker(unittest.TestCase):
    """Exit 0 is not evidence. Only the marker in the output is."""

    def test_exit_zero_without_marker_fails(self):
        """A command that succeeds but emits the wrong thing is a failure."""
        step = CommandStep("Probe", "echo wrong-output", marker="EXPECTED")
        self.assertEqual(step.run().status, Status.FAIL)

    def test_marker_present_passes(self):
        """A command whose output carries the marker passes."""
        step = CommandStep("Probe", "echo EXPECTED-here", marker="EXPECTED")
        self.assertEqual(step.run().status, Status.OK)

    def test_nonzero_exit_with_marker_still_passes(self):
        """The artifact is the output, not the return code."""
        step = CommandStep("Probe", "echo EXPECTED; exit 3", marker="EXPECTED")
        self.assertEqual(step.run().status, Status.OK)


class EveryCheckMustBeAbleToFail(unittest.TestCase):
    """prove() is the only thing separating a passing check from an unwired one."""

    def test_file_step_failing_variant_fails(self):
        """A FileStep's failing variant points at a path that cannot exist."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "real.md"
            path.write_text("MARKER here", encoding="utf-8")
            step = FileStep("Doc", path, marker="MARKER")
            self.assertEqual(step.run().status, Status.OK)
            self.assertEqual(step.failing_variant().run().status, Status.FAIL)
            self.assertEqual(step.prove().status, Status.OK)

    def test_prove_reports_a_check_that_cannot_fail(self):
        """A step whose failing variant still passes is reported broken, not healthy."""

        class AlwaysPasses(Step):
            """A step rigged so that even its failing variant succeeds."""

            def check(self):
                """Always return evidence, regardless of reality."""
                return Evidence("fine", "nowhere")

            def failing_variant(self):
                """Return self - which is exactly the bug this catches."""
                return self

        self.assertEqual(AlwaysPasses("Bogus").prove().status, Status.FAIL)


class TheGateIsAHardStop(unittest.TestCase):
    """A gated tier must not run when a critical step is red."""

    def _boot(self, marker):
        """Build a two-tier boot whose first tier is critical and second is gated."""
        enablers = Tier(1, "enablers").add(
            CommandStep("Probe", "echo REAL", marker=marker, critical=True)
        )
        memory_step = CommandStep("Memory", "echo LOADED", marker="LOADED")
        return Boot([enablers, Tier(2, "memories", gated=True).add(memory_step)]), memory_step

    def test_gate_green_runs_the_memory_tier(self):
        """With the critical step green, the gated tier runs."""
        boot, _ = self._boot("REAL")
        self.assertEqual(boot.run(), 0)
        self.assertIn("Memory", [r.step for r in boot.results])

    def test_gate_held_skips_the_memory_tier(self):
        """With the critical step red, the gated tier does not run at all."""
        boot, _ = self._boot("NEVER-APPEARS")
        self.assertEqual(boot.run(), 1)
        self.assertNotIn("Memory", [r.step for r in boot.results])


class InstallerMergesRatherThanClobbers(unittest.TestCase):
    """Dropping a stranger's config to install your own is the description-wipe bug."""

    def test_foreign_hooks_and_keys_survive(self):
        """Existing hooks and unrelated settings keys are preserved across install."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            claude, payloads = root / "claude", root / "payloads"
            claude.mkdir()
            settings = claude / "settings.json"
            settings.write_text(json.dumps({
                "model": "some-model",
                "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo FOREIGN"}]}]},
            }), encoding="utf-8")

            src = Path(__file__).resolve().parents[1] / "agentboot" / "templates"
            EnforcementInstaller(claude, payloads, src).install_payloads()
            EnforcementInstaller(claude, payloads, src).wire()

            data = json.loads(settings.read_text(encoding="utf-8"))
            self.assertEqual(data["model"], "some-model")
            commands = [h["command"] for e in data["hooks"]["SessionStart"] for h in e["hooks"]]
            self.assertIn("echo FOREIGN", commands)
            self.assertEqual(len(commands), 2)

    def test_reinstall_does_not_duplicate(self):
        """Re-running the installer is idempotent."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            claude, payloads = root / "claude", root / "payloads"
            claude.mkdir()
            src = Path(__file__).resolve().parents[1] / "agentboot" / "templates"
            for _ in range(3):
                inst = EnforcementInstaller(claude, payloads, src)
                inst.install_payloads()
                inst.wire()
            data = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(len(data["hooks"]["PreToolUse"]), 1)


class LocalEditsSurviveUpgrades(unittest.TestCase):
    """A payload the operator has edited must never be overwritten."""

    def test_existing_payload_is_left_alone(self):
        """An edited nag file keeps its local rules across a reinstall."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            claude, payloads = root / "claude", root / "payloads"
            claude.mkdir()
            payloads.mkdir()
            mine = payloads / "nag.md"
            mine.write_text("MY LOCAL RULES", encoding="utf-8")
            src = Path(__file__).resolve().parents[1] / "agentboot" / "templates"
            EnforcementInstaller(claude, payloads, src).install_payloads()
            self.assertEqual(mine.read_text(encoding="utf-8"), "MY LOCAL RULES")


if __name__ == "__main__":
    unittest.main()
