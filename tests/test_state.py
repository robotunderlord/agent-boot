"""Tests for the keyed tier.

The rules worth enforcing here are not about MongoDB. They are about what a crumb IS, and about a
health probe that proves the thing it claims. Both are testable without a database.
"""
import unittest

from agentboot.state import Crumb, KeyedState, KeyedStateStep, StateUnavailable


class ACrumbIsAPointerNotACopy(unittest.TestCase):
    """The whole value of a crumb is that it is small and points elsewhere."""

    def test_ref_is_required(self):
        """Without a ref, the crumb IS the detail - a second source of truth that will drift."""
        with self.assertRaises(ValueError) as ctx:
            Crumb(key="k", summary="something happened", ref="")
        self.assertIn("POINTER", str(ctx.exception))

    def test_key_is_required(self):
        """It is looked up by key or not at all."""
        with self.assertRaises(ValueError):
            Crumb(key="  ", summary="s", ref="r")

    def test_summary_is_required(self):
        """An empty marker points nowhere useful."""
        with self.assertRaises(ValueError):
            Crumb(key="k", summary="", ref="r")

    def test_render_shows_the_pointer(self):
        """A recalled crumb must show where the detail actually lives."""
        rendered = Crumb(key="db:s#1", summary="why it failed", ref="research/EXP.md").render()
        self.assertIn("db:s#1", rendered)
        self.assertIn("research/EXP.md", rendered)


class TheFacultyFailsHonestly(unittest.TestCase):
    """An unreachable backend is a named failure, never a silent degradation."""

    def test_unreachable_backend_raises_named_error(self):
        """A bad address fails as StateUnavailable, with the address in the message."""
        state = KeyedState(url="mongodb://127.0.0.1:1/", timeout_ms=200)
        with self.assertRaises(StateUnavailable):
            state.open()

    def test_step_goes_red_rather_than_raising(self):
        """A faculty must not take the boot down; it reports FAIL and the boot continues."""
        state = KeyedState(url="mongodb://127.0.0.1:1/", timeout_ms=200)
        result = KeyedStateStep(state).run()
        self.assertTrue(result.status.is_red)

    def test_failing_variant_actually_fails(self):
        """The keyed check must be provable like every other check."""
        state = KeyedState(url="mongodb://127.0.0.1:1/", timeout_ms=200)
        self.assertTrue(KeyedStateStep(state).failing_variant().run().status.is_red)

    def test_not_critical_by_default(self):
        """Losing recall should not hold the gate that stops the agent acting at all."""
        self.assertFalse(KeyedState().step().critical)


if __name__ == "__main__":
    unittest.main()
