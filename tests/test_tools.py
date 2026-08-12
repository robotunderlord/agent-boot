"""Tests for the tool registry - specifically, that it refuses to publish a capability it cannot prove."""
import json
import tempfile
import unittest
from pathlib import Path

from agentboot import Tool, ToolRegistry


class AToolMustSayWhenToUseIt(unittest.TestCase):
    """A registry keyed by name answers the wrong question; `when` is what makes it reachable."""

    def test_missing_when_is_rejected(self):
        """A tool with no trigger is never reached for, so it is refused at construction."""
        with self.assertRaises(ValueError):
            Tool(name="thing", when="", reach="thing")

    def test_missing_name_is_rejected(self):
        """A tool needs a name."""
        with self.assertRaises(ValueError):
            Tool(name="  ", when="sometimes", reach="thing")


class DiscoveryIsNonFatal(unittest.TestCase):
    """A malformed manifest must never take the boot down - the boot is how you diagnose it."""

    def test_unreadable_manifest_is_skipped(self):
        """A missing manifest path is warned about, not raised."""
        registry = ToolRegistry()
        found = registry.discover(env={"AGENTBOOT_TOOLS": "/nonexistent/nope.json"},
                                  tools_dir="/nonexistent")
        self.assertEqual(found, [])

    def test_malformed_json_is_skipped(self):
        """Broken JSON is warned about, not raised."""
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("{not json at all", encoding="utf-8")
            found = ToolRegistry().discover(env={"AGENTBOOT_TOOLS": str(bad)}, tools_dir="/nonexistent")
            self.assertEqual(found, [])

    def test_bad_entry_is_skipped_but_good_ones_load(self):
        """One invalid entry must not discard its valid neighbours."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mixed.json"
            path.write_text(json.dumps({"tools": [
                {"name": "no-when", "reach": "x"},
                {"name": "good", "when": "a situation", "reach": "echo good"},
            ]}), encoding="utf-8")
            found = ToolRegistry().discover(env={"AGENTBOOT_TOOLS": str(path)}, tools_dir="/nonexistent")
            self.assertEqual([t.name for t in found], ["good"])


class DiscoveryReadsBothSources(unittest.TestCase):
    """Manifests arrive by env var and by dropped-in directory."""

    def test_tools_dir_manifests_are_loaded(self):
        """A container declares what it mounted by dropping JSON into tools.d."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "a.json").write_text(json.dumps(
                [{"name": "alpha", "when": "situation a", "reach": "echo alpha"}]), encoding="utf-8")
            found = ToolRegistry().discover(env={}, tools_dir=d)
            self.assertEqual([t.name for t in found], ["alpha"])

    def test_discovered_tools_are_marked_learned(self):
        """Origin distinguishes what the image carried from what the environment added."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "a.json").write_text(json.dumps(
                [{"name": "alpha", "when": "situation a", "reach": "echo alpha"}]), encoding="utf-8")
            found = ToolRegistry().discover(env={}, tools_dir=d)
            self.assertEqual(found[0].origin, "learned")


class UnprovenToolsDoNotReachTheReflexTable(unittest.TestCase):
    """The whole point: an agent must never be pointed at a capability that is not there."""

    def _registry(self):
        """Return a registry with one working tool and one that cannot possibly probe green."""
        return ToolRegistry().register(
            Tool(name="real", when="a real situation", reach="echo real",
                 probe="echo PRESENT", marker="PRESENT"),
            Tool(name="ghost", when="a situation that will never be served", reach="ghost-binary",
                 probe="echo nothing-here", marker="ABSOLUTELY-NOT-PRESENT"),
        )

    def test_verify_drops_the_unreachable_tool(self):
        """A tool whose probe fails is not counted as verified."""
        registry = self._registry()
        verified = registry.verify()
        self.assertEqual([t.name for t in verified], ["real"])

    def test_reflex_table_omits_the_unreachable_tool(self):
        """The generated table cannot rot, because it is built from what actually answered."""
        registry = self._registry()
        registry.verify()
        table = registry.reflex_table()
        self.assertIn("a real situation", table)
        self.assertNotIn("a situation that will never be served", table)

    def test_reflex_table_is_honest_when_nothing_verified(self):
        """An empty table says so rather than rendering an inviting blank."""
        self.assertIn("nothing to reach for", ToolRegistry().reflex_table())

    def test_as_tier_probes_every_registered_tool(self):
        """Every claimed tool becomes a boot step, so nothing is taken on faith."""
        registry = self._registry()
        tier = registry.as_tier()
        self.assertEqual(len(tier.steps), 2)
        statuses = [s.run().status.is_red for s in tier.steps]
        self.assertEqual(statuses, [False, True])


if __name__ == "__main__":
    unittest.main()
