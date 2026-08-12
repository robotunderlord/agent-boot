"""Tests for the holding session - above all, that a DEAD session is never reported as a live one."""
import unittest

from agentboot.session import MAIN, Session, SessionHost, SessionStep

LISTING = (
    "agent-side [Created 1month ago] (EXITED - attach to resurrect)\n"
    "agent-main [Created 14days ago] (current)\n"
)


class FakeHost(SessionHost):
    """A host with a canned listing, so tests do not need a live multiplexer."""

    def __init__(self, session, listing=LISTING, installed=True):
        """Store the canned listing and whether the binary should appear installed."""
        super().__init__(session)
        self.listing = listing
        self.installed = installed

    def available(self):
        """Report whether the multiplexer is installed, per the fixture."""
        return self.installed

    def _list(self):
        """Return the canned listing instead of shelling out."""
        return self.listing


class OneSessionIsTheMainLoop(unittest.TestCase):
    """There is exactly one holding session, and its name says so."""

    def test_default_name_is_main(self):
        """A bare Session is the main loop."""
        self.assertEqual(Session().name, MAIN)

    def test_for_agent_appends_main(self):
        """The canonical name states that this is THE loop, not a peer."""
        self.assertEqual(Session.for_agent("gandalf").name, "gandalf-main")

    def test_empty_name_is_rejected(self):
        """Attach has to be able to ask for something."""
        with self.assertRaises(ValueError):
            Session(name="   ")


class AListedSessionIsNotALiveSession(unittest.TestCase):
    """The landmine: an exited session is printed by name exactly like a running one."""

    def test_exited_session_is_not_alive(self):
        """A session marked EXITED must not read as alive, however it is listed."""
        self.assertFalse(FakeHost(Session(name="agent-side")).alive())

    def test_running_session_is_alive(self):
        """A session with no EXITED marker is alive."""
        self.assertTrue(FakeHost(Session(name="agent-main")).alive())

    def test_sessions_maps_every_name_to_liveness(self):
        """Both are listed; only one is alive - which is why this returns a dict."""
        self.assertEqual(FakeHost(Session()).sessions(),
                         {"agent-side": False, "agent-main": True})

    def test_step_reports_exited_as_a_failure(self):
        """The boot must go red on a dead agent whose name is still in the listing."""
        result = SessionStep(FakeHost(Session(name="agent-side"))).run()
        self.assertTrue(result.status.is_red)
        self.assertIn("EXITED", result.detail)

    def test_step_reports_missing_session_as_a_failure(self):
        """A name that was never there is a different failure, and says so."""
        result = SessionStep(FakeHost(Session(name="never-existed"))).run()
        self.assertTrue(result.status.is_red)
        self.assertIn("no session named", result.detail)

    def test_missing_multiplexer_is_a_failure(self):
        """If nothing is holding the agent, that is the finding."""
        result = SessionStep(FakeHost(Session(name="agent-main"), installed=False)).run()
        self.assertTrue(result.status.is_red)
        self.assertIn("not installed", result.detail)

    def test_failing_variant_actually_fails(self):
        """The session check must be provable like every other check."""
        step = SessionStep(FakeHost(Session(name="agent-main")))
        self.assertEqual(step.run().status.is_red, False)
        self.assertTrue(step.failing_variant().run().status.is_red)


class TheAddressIsRendered(unittest.TestCase):
    """One session, four addresses - and a TTY forced on every remote form."""

    def setUp(self):
        """Build a host for the canonical session."""
        self.host = SessionHost(Session.for_agent("gandalf"))

    def test_local(self):
        """Locally, attach by name."""
        self.assertEqual(self.host.attach_command(), "zellij attach gandalf-main")

    def test_container_forces_a_tty(self):
        """docker exec without -it produces an unusable attach."""
        self.assertEqual(self.host.attach_command(container="gandalf"),
                         "docker exec -it gandalf zellij attach gandalf-main")

    def test_remote_forces_a_tty(self):
        """ssh without -t runs non-interactively and the attach renders garbage."""
        self.assertEqual(self.host.attach_command(host="legolas"),
                         "ssh -t legolas zellij attach gandalf-main")

    def test_remote_through_a_container(self):
        """Both wrappers compose, outermost last."""
        self.assertEqual(self.host.attach_command(container="gandalf", host="legolas"),
                         "ssh -t legolas docker exec -it gandalf zellij attach gandalf-main")

    def test_start_command_includes_the_layout(self):
        """The layout is what decides the main loop, so it belongs in the start command."""
        host = SessionHost(Session.for_agent("gandalf", layout="/opt/main.kdl"))
        self.assertEqual(host.start_command(),
                         "zellij --layout /opt/main.kdl --session gandalf-main")


if __name__ == "__main__":
    unittest.main()
