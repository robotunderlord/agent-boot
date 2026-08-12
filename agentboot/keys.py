"""The agent carries its own keys - as ciphertext, on its person, and never as plaintext in an image.

THE PROBLEM
-----------
An agent that cannot authenticate is an agent that cannot work, and the usual answers are all bad:

* **Bake the key into the image.** Now the image cannot be shared, published or rebuilt in the open,
  and every copy of it is a credential.
* **Fetch it from a secret store at boot.** Now authentication depends on the network, and the agent
  cannot bootstrap the very connection it needs in order to bootstrap.
* **Carry nothing and mount it.** Portable and safe, but the agent is inert anywhere the mount is
  missing - which is every new machine, which is exactly when you need it.

The workable shape is the middle one: **the keys travel with the agent as ansible-vault ciphertext,
and the one password that opens them does not.** The being is portable, a stolen copy is inert, and
the single bootstrap secret is mounted at runtime rather than carried.

THE SCAR THIS MODULE EXISTS FOR
-------------------------------
A stored copy of a private key was subtly mangled. It read back fine. It had the right length, the
right header, no error on decrypt - and **no fingerprint**. Every SSH attempt using it failed
silently, in a way that looked like a server-side permission problem, hours away from the actual
cause.

So `install()` does not trust a successful decrypt. A decrypted key must produce a **fingerprint**
or it is refused and deleted, because a key that cannot be fingerprinted is not a key - it is a
future outage with a plausible alibi. This is the evidence rule from `steps.py` applied to
credentials: the artifact, not the indicator.

Nothing here ever prints key material. Fingerprints only.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .boot import Tier
from .status import Status
from .steps import Evidence, Step, StepFailed


class KeyFault(Exception):
    """Raised when a key cannot be decrypted, installed, or proven real."""


@dataclass(frozen=True)
class Key:
    """One credential that travels with the agent as ciphertext."""

    name: str
    cipher: Path
    install_to: Path
    mode: int = 0o600

    @property
    def public(self) -> Path:
        """Return the path the public half would occupy."""
        return self.install_to.with_suffix(self.install_to.suffix + ".pub")


class Keyring:
    """Decrypt the agent's own keys into place, and refuse anything that cannot be proven real.

    `password_file` is the single bootstrap secret. It is deliberately NOT part of the store: it is
    mounted or injected at runtime, so a copy of the being on its own opens nothing.
    """

    def __init__(self, store: Path | str, install_dir: Path | str | None = None,
                 password_file: Path | str | None = None) -> None:
        """Store where the ciphertext lives, where keys are installed, and where the password is."""
        self.store = Path(store)
        self.install_dir = Path(install_dir or Path.home() / ".ssh")
        self.password_file = Path(
            password_file or os.environ.get("AGENTBOOT_VAULT_PASS")
            or Path.home() / ".agentboot-vault-pass"
        )

    # ── discovery ───────────────────────────────────────────────────────────────────────────
    def keys(self) -> list[Key]:
        """Return every `*.vault` in the store, mapped to its installed location."""
        if not self.store.is_dir():
            return []
        return [
            Key(name=path.stem, cipher=path, install_to=self.install_dir / path.stem)
            for path in sorted(self.store.glob("*.vault"))
        ]

    # ── the artifact check ──────────────────────────────────────────────────────────────────
    @staticmethod
    def fingerprint(path: Path) -> str:
        """Return a key's fingerprint, or an empty string if it does not have one.

        This is the whole point of the module. A decrypt that 'worked' proves nothing; a key that
        cannot be fingerprinted will fail at authentication time, far from here, looking like
        somebody else's problem.
        """
        if not shutil.which("ssh-keygen"):
            return ""
        try:
            proc = subprocess.run(["ssh-keygen", "-lf", str(path)],
                                  capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return ""
        return proc.stdout.strip() if proc.returncode == 0 else ""

    # ── installation ────────────────────────────────────────────────────────────────────────
    def _decrypt(self, key: Key) -> bytes:
        """Return the plaintext of one key, without ever letting it reach stdout."""
        if not shutil.which("ansible-vault"):
            raise KeyFault("ansible-vault is not installed - cannot open the store")
        if not self.password_file.exists():
            raise KeyFault(f"vault password not present at {self.password_file} "
                            "(it is mounted at runtime by design, never carried)")
        try:
            proc = subprocess.run(
                ["ansible-vault", "view", "--vault-password-file", str(self.password_file),
                 str(key.cipher)],
                capture_output=True, timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise KeyFault(f"decrypt failed to run: {exc}") from exc
        if proc.returncode != 0:
            # stderr may echo the path but never the content; the plaintext is on stdout only.
            raise KeyFault(f"decrypt failed for {key.name} (rc={proc.returncode})")
        return proc.stdout

    def install(self, key: Key) -> str:
        """Decrypt one key into place at 0600 and return its fingerprint.

        Refuses - and removes - any key that decrypts without producing a fingerprint.
        """
        plaintext = self._decrypt(key)
        if not plaintext.strip():
            raise KeyFault(f"{key.name} decrypted to nothing")

        key.install_to.parent.mkdir(parents=True, exist_ok=True)
        # Create with restrictive permissions from the outset rather than chmod-ing afterwards:
        # between write and chmod, a world-readable private key exists on disk.
        fd = os.open(key.install_to, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, key.mode)
        try:
            os.write(fd, plaintext)
        finally:
            os.close(fd)

        fingerprint = self.fingerprint(key.install_to)
        if not fingerprint:
            key.install_to.unlink(missing_ok=True)
            raise KeyFault(
                f"{key.name} decrypted but has NO FINGERPRINT - refusing to install a key that "
                "would fail silently at authentication time. Removed."
            )
        return fingerprint

    def load(self) -> list[tuple[str, Status, str]]:
        """Install every key in the store, returning (name, status, detail) per key.

        Idempotent: an already-installed key with a valid fingerprint is re-verified, not rewritten.
        """
        out = []
        for key in self.keys():
            existing = self.fingerprint(key.install_to) if key.install_to.exists() else ""
            if existing:
                out.append((key.name, Status.OK, f"already present ({existing.split()[1][:18]}...)"))
                continue
            try:
                fingerprint = self.install(key)
            except KeyFault as exc:
                out.append((key.name, Status.FAIL, str(exc)))
                continue
            out.append((key.name, Status.OK, f"installed 0{key.mode:o} ({fingerprint.split()[1][:18]}...)"))
        return out

    # ── boot integration ────────────────────────────────────────────────────────────────────
    def as_tier(self, number: int = 1, name: str = "enablers") -> Tier:
        """Return a boot tier that installs and proves every carried key."""
        return Tier(number, name).add(*[KeyStep(self, key) for key in self.keys()])


class KeyStep(Step):
    """Boot step that installs one carried key and proves it has a fingerprint."""

    def __init__(self, keyring: Keyring, key: Key) -> None:
        """Store the keyring and the key this step is responsible for."""
        super().__init__(key.name, critical=True)
        self.keyring = keyring
        self.key = key

    def check(self) -> Evidence:
        """Install the key if needed and return its fingerprint as evidence."""
        existing = self.keyring.fingerprint(self.key.install_to) if self.key.install_to.exists() else ""
        try:
            fingerprint = existing or self.keyring.install(self.key)
        except KeyFault as exc:
            raise StepFailed(str(exc)) from exc
        # Show the hash only - never the path's contents, never the key.
        short = fingerprint.split()[1][:20] if len(fingerprint.split()) > 1 else fingerprint[:20]
        return Evidence(f"carried, installed 0{self.key.mode:o} ({short}...)", str(self.key.cipher))

    def failing_variant(self) -> KeyStep:
        """Return the same step pointed at ciphertext that cannot exist."""
        ghost = Key(name=self.key.name,
                    cipher=self.key.cipher.with_suffix(".__absent__"),
                    install_to=self.key.install_to.with_suffix(".__absent__"),
                    mode=self.key.mode)
        return KeyStep(self.keyring, ghost)
