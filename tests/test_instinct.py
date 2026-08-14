"""Tests for instincts.

The property under test is that the response is EXECUTED rather than suggested, and that a check
which errored is never mistaken for a check that passed.
"""
import unittest

from agentboot.instinct import (
    Instinct,
    Reaction,
    Arc,
    Response,
    default_reflexes,
    shared_checkout,
    volume_contents,
)


def observer(message="looked", evidence="found something"):
    """Return a handler that reports what it 'found'."""
    return lambda _s, _e: Response(Reaction.OBSERVE, message, evidence)


def thrower(_situation, _event):
    """Return a handler that fails the way a real probe fails."""
    raise RuntimeError("the probe blew up")


class AnInstinctRunsRatherThanAdvises(unittest.TestCase):
    """A sentence depends on compliance; a handler has already done the work."""

    def test_the_handler_is_actually_called(self):
        """This is the entire difference from a lesson."""
        calls = []
        i = Instinct("x", "removing a docker volume", lambda s, e: calls.append(s) or
                     Response(Reaction.OBSERVE, "ran"))
        i.fire("removing a docker volume with state in it")
        self.assertEqual(len(calls), 1)

    def test_an_instinct_without_a_handler_is_refused(self):
        """A handler-less instinct is a lesson wearing a costume."""
        with self.assertRaises(ValueError):
            Instinct("x", "some tell", None)

    def test_an_instinct_without_a_tell_is_refused(self):
        """It would never fire, and would look installed."""
        with self.assertRaises(ValueError):
            Instinct("x", "   ", observer())


class FailClosedWhenRefusingFailOpenWhenAdvising(unittest.TestCase):
    """A check that errored did not pass. Those are different facts."""

    def test_a_deny_instinct_that_throws_denies(self):
        """A guard that silently stops guarding while indicators stay green is the worst case."""
        i = Instinct("guard", "writing to the shared checkout", thrower, Reaction.DENY)
        response = i.fire("writing to the shared checkout")
        self.assertIs(response.reaction, Reaction.DENY)
        self.assertFalse(response)
        self.assertIn("could not complete", response.message)

    def test_an_advisory_instinct_that_throws_is_swallowed(self):
        """One missing warning beats an agent that cannot act at all."""
        i = Instinct("adv", "removing a docker volume", thrower, Reaction.ADVISE)
        self.assertTrue(i.fire("removing a docker volume"))

    def test_a_swallowed_failure_produces_no_noise(self):
        """A broken instinct must not fill the turn with empty responses."""
        r = Arc().add(Instinct("adv", "removing a docker volume", thrower, Reaction.ADVISE))
        self.assertEqual(r.fire("removing a docker volume"), [])


class TheArcDecidesAndExplains(unittest.TestCase):
    """A refusal that withholds its reasoning is the least useful possible refusal."""

    def _arc(self):
        """Return an arc holding one observer and one refuser on the same tell."""
        return Arc().add(
            Instinct("watcher", "writing a file to the shared checkout", observer("saw it")),
            Instinct("guard", "writing a file to the shared checkout",
                     lambda _s, _e: Response(Reaction.DENY, "not here", instinct="guard"),
                     Reaction.DENY))

    def test_a_deny_blocks_the_action(self):
        """The boolean must be correct even for a caller that ignores the text."""
        allowed, _ = self._arc().verdict("writing a file to the shared checkout")
        self.assertFalse(allowed)

    def test_a_deny_does_not_suppress_the_observations(self):
        """When an action is refused the observations ARE the explanation."""
        _, text = self._arc().verdict("writing a file to the shared checkout")
        self.assertIn("saw it", text)
        self.assertIn("REFUSED", text)

    def test_the_strongest_reaction_is_reported_first(self):
        """The refusal must not be buried under the observations that support it."""
        _, text = self._arc().verdict("writing a file to the shared checkout")
        self.assertLess(text.index("REFUSED"), text.index("saw it"))

    def test_an_unrelated_situation_fires_nothing(self):
        """Silence is the normal case for a reflex layer."""
        allowed, text = self._arc().verdict("rename a css variable")
        self.assertTrue(allowed)
        self.assertEqual(text, "")

    def test_an_empty_situation_fires_nothing(self):
        """An absent payload must not be matched against."""
        self.assertEqual(self._arc().fire("   "), [])


class ItNeverEchoesWhatItMatchedOn(unittest.TestCase):
    """A PreToolUse payload holds the literal command, and commands hold credentials."""

    def test_the_command_text_is_not_returned(self):
        """A safety mechanism that leaks is a net loss."""
        event = {"tool_input": {"command": "docker volume rm secret-token-AKIA123 --force"}}
        response = volume_contents("removing a docker volume", event)
        self.assertNotIn("AKIA123", response.render())


class TheShippedInstincts(unittest.TestCase):
    """Each ships because its advisory form was already written down and already ignored."""

    def test_writing_outside_a_worktree_is_denied(self):
        """The damage is other people's uncommitted work and the fix is one call away."""
        event = {"tool_input": {"file_path": "/home/x/projects/live/app.py"}}
        self.assertFalse(shared_checkout("writing a file", event))

    def test_writing_inside_a_worktree_is_allowed(self):
        """A guard that fires on the correct action gets switched off."""
        event = {"tool_input": {"file_path": "/home/x/.claude/worktrees/w1/app.py"}}
        self.assertTrue(shared_checkout("writing a file", event))

    def test_a_volume_removal_attaches_real_evidence(self):
        """'It is empty' is a belief; the mountpoint listing is not."""
        event = {"tool_input": {"command": "docker volume rm pgdata"}}
        response = volume_contents("removing a docker volume with state in it", event)
        self.assertIs(response.reaction, Reaction.ADVISE)
        self.assertIn("pgdata", response.message)

    def test_a_command_that_is_not_a_volume_removal_stays_quiet(self):
        """Matching the tell is not the same as the action actually being that action."""
        event = {"tool_input": {"command": "docker volume ls"}}
        self.assertEqual(volume_contents("docker volume", event).message, "")

    def test_the_default_set_carries_exactly_one_refuser(self):
        """A reflex layer that blocks often gets disabled, and then protects nothing."""
        deny = [i for i in default_reflexes().instincts if i.reaction is Reaction.DENY]
        self.assertEqual([i.name for i in deny], ["shared-checkout"])


if __name__ == "__main__":
    unittest.main()
