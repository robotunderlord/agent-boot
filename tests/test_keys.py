"""Tests for the carried keyring - above all, that an unfingerprintable key is refused, not installed."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agentboot.keys import KeyFault, Keyring, KeyStep

HAVE_SSH_KEYGEN = subprocess.run(["which", "ssh-keygen"], capture_output=True).returncode == 0


class FakeKeyring(Keyring):
    """A keyring whose decrypt step is supplied directly, so tests need no ansible-vault."""

    def __init__(self, plaintext: bytes, **kw):
        """Store the plaintext this keyring will pretend to decrypt."""
        super().__init__(**kw)
        self.plaintext = plaintext

    def _decrypt(self, key):
        """Return the canned plaintext instead of shelling out to ansible-vault."""
        return self.plaintext


class TheStoreIsDiscovered(unittest.TestCase):
    """Keys are found by extension, so adding one is a file drop rather than a code change."""

    def test_missing_store_is_not_an_error(self):
        """An agent with no carried keys boots; it just cannot authenticate."""
        self.assertEqual(Keyring("/nonexistent/store").keys(), [])

    def test_vault_files_become_keys(self):
        """Every *.vault in the store maps to an install path."""
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store"
            store.mkdir()
            (store / "id_agent.vault").write_text("ciphertext", encoding="utf-8")
            (store / "notes.txt").write_text("not a key", encoding="utf-8")
            keys = Keyring(store, install_dir=Path(tmp) / "ssh").keys()
            self.assertEqual([k.name for k in keys], ["id_agent"])


class ThePasswordIsNeverCarried(unittest.TestCase):
    """The one bootstrap secret is mounted at runtime; a copy of the being alone opens nothing."""

    def test_missing_password_file_is_an_honest_failure(self):
        """The error names the design, so the next reader does not go looking for a bug.

        `shutil.which` is patched so this test exercises the PASSWORD branch regardless of whether
        ansible-vault happens to be installed. Without the patch this passed on a developer host and
        failed inside the container, which is a test that measures the machine rather than the code.
        """
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store"
            store.mkdir()
            (store / "id_agent.vault").write_text("ciphertext", encoding="utf-8")
            ring = Keyring(store, install_dir=Path(tmp) / "ssh",
                           password_file=Path(tmp) / "absent-pass")
            key = ring.keys()[0]
            with mock.patch("agentboot.keys.shutil.which", return_value="/usr/bin/ansible-vault"):
                with self.assertRaises(KeyFault) as ctx:
                    ring._decrypt(key)
            self.assertIn("mounted at runtime", str(ctx.exception))

    def test_missing_vault_binary_is_named_plainly(self):
        """The other branch: with no ansible-vault, the store simply cannot be opened."""
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store"
            store.mkdir()
            (store / "id_agent.vault").write_text("ciphertext", encoding="utf-8")
            ring = Keyring(store, install_dir=Path(tmp) / "ssh")
            with mock.patch("agentboot.keys.shutil.which", return_value=None):
                with self.assertRaises(KeyFault) as ctx:
                    ring._decrypt(ring.keys()[0])
            self.assertIn("not installed", str(ctx.exception))


@unittest.skipUnless(HAVE_SSH_KEYGEN, "ssh-keygen required to exercise the fingerprint gate")
class AKeyWithoutAFingerprintIsRefused(unittest.TestCase):
    """The scar: a key that decrypts cleanly, has no fingerprint, and fails silently much later."""

    def _store(self, tmp):
        """Return a store containing one ciphertext placeholder."""
        store = Path(tmp) / "store"
        store.mkdir()
        (store / "id_agent.vault").write_text("ciphertext", encoding="utf-8")
        return store

    def test_garbage_is_refused_and_removed(self):
        """Decrypting to plausible-looking garbage must not leave a key on disk."""
        with tempfile.TemporaryDirectory() as tmp:
            ring = FakeKeyring(b"-----BEGIN OPENSSH PRIVATE KEY-----\nnot actually a key\n",
                               store=self._store(tmp), install_dir=Path(tmp) / "ssh")
            key = ring.keys()[0]
            with self.assertRaises(KeyFault) as ctx:
                ring.install(key)
            self.assertIn("NO FINGERPRINT", str(ctx.exception))
            self.assertFalse(key.install_to.exists(), "a refused key must not be left on disk")

    def test_empty_decrypt_is_refused(self):
        """A key that decrypts to nothing is caught before it is written."""
        with tempfile.TemporaryDirectory() as tmp:
            ring = FakeKeyring(b"   \n", store=self._store(tmp), install_dir=Path(tmp) / "ssh")
            with self.assertRaises(KeyFault):
                ring.install(ring.keys()[0])

    def test_a_real_key_installs_at_0600_and_reports_its_fingerprint(self):
        """The happy path: a genuine key lands with restrictive permissions and proves itself."""
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "genuine"
            subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-q", "-f", str(real)],
                           check=True, capture_output=True)
            ring = FakeKeyring(real.read_bytes(), store=self._store(tmp),
                               install_dir=Path(tmp) / "ssh")
            key = ring.keys()[0]
            fingerprint = ring.install(key)
            self.assertIn("SHA256:", fingerprint)
            self.assertEqual(key.install_to.stat().st_mode & 0o777, 0o600)

    def test_key_material_never_appears_in_the_evidence(self):
        """A boot line may carry a fingerprint. It may never carry the key."""
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "genuine"
            subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-q", "-f", str(real)],
                           check=True, capture_output=True)
            secret = real.read_bytes()
            ring = FakeKeyring(secret, store=self._store(tmp), install_dir=Path(tmp) / "ssh")
            detail = KeyStep(ring, ring.keys()[0]).run().detail
            body = secret.decode().splitlines()[1]
            self.assertNotIn(body, detail)
            self.assertIn("SHA256:", detail)

    def test_failing_variant_actually_fails(self):
        """The key step must be able to go red, or it proves nothing."""
        with tempfile.TemporaryDirectory() as tmp:
            ring = FakeKeyring(b"x", store=self._store(tmp), install_dir=Path(tmp) / "ssh")
            step = KeyStep(ring, ring.keys()[0])
            self.assertTrue(step.failing_variant().run().status.is_red)


if __name__ == "__main__":
    unittest.main()
