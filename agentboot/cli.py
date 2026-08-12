"""Command line entry points: install the enforcement layers, and run a demo boot.

python3 -m agentboot install          -- wire the three layers, then verify by executing them
python3 -m agentboot install --prove  -- also confirm each check is capable of failing
python3 -m agentboot verify           -- check only, change nothing
python3 -m agentboot uninstall        -- remove only what this installed
python3 -m agentboot demo             -- run a boot against the installed payloads
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .boot import Boot, Tier
from .enforcement import LAYERS, EnforcementInstaller
from .steps import FileStep, LazyStep

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAYLOADS = REPO_ROOT / "payloads"


def _dirs(args: argparse.Namespace) -> tuple[Path, Path]:
    """Resolve the settings and payload directories from flags, env, then defaults."""
    claude = Path(args.claude_dir or os.environ.get("CLAUDE_DIR") or Path.home() / ".claude")
    payloads = Path(args.payload_dir or os.environ.get("AGENTBOOT_DIR") or Path.home() / ".agentboot")
    return claude, payloads


def _installer(args: argparse.Namespace) -> EnforcementInstaller:
    """Build an installer for the resolved directories."""
    claude, payloads = _dirs(args)
    print(f"settings dir : {claude}")
    print(f"payload dir  : {payloads}\n")
    return EnforcementInstaller(claude, payloads, Path(args.payloads or DEFAULT_PAYLOADS))


def _finish(green: bool, payload_dir: Path) -> int:
    """Print the closing verdict and return the process exit code."""
    print()
    if not green:
        print("[ !! ] NOT clean - fix the lines above before trusting any of it.")
        return 1
    print("[ OK ] all three layers wired AND proven to emit.")
    print()
    print("  Now watch one FAIL, or you have proved nothing:")
    print(f"    mv {payload_dir / 'nag-terse.md'} /tmp/ && python3 -m agentboot verify")
    print("  That must go red. Move it back and it must go green again.")
    print("  A check you have never watched fail is indistinguishable from one wired to nothing.")
    return 0


def _demo_boot(payload_dir: Path) -> Boot:
    """Build a small demonstration boot over the installed payload files."""
    enablers = Tier(1, "enablers").add(
        *[FileStep(layer.event, payload_dir / layer.payload, marker=layer.marker, critical=True)
          for layer in LAYERS]
    )
    personality = Tier(2, "personality").add(
        FileStep("Tattoo", payload_dir / "tattoo.md", marker="[STATE]", critical=False),
    )
    resources = Tier(3, "resources").add(
        LazyStep("Reference", "declared, not loaded - wire your own steps here"),
    )
    memories = Tier(4, "memories", gated=True).add(
        LazyStep("Continuity", "loads only behind a green gate"),
    )
    return Boot([enablers, personality, resources, memories])


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the requested command."""
    ap = argparse.ArgumentParser(prog="agentboot", description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=["install", "verify", "uninstall", "demo"])
    ap.add_argument("--claude-dir", help="override ~/.claude")
    ap.add_argument("--payload-dir", help="override ~/.agentboot")
    ap.add_argument("--payloads", help="override the template source directory")
    ap.add_argument("--prove", action="store_true", help="also confirm every check can fail")
    args = ap.parse_args(argv)

    if args.command == "demo":
        _, payloads = _dirs(args)
        return _demo_boot(payloads).run()

    inst = _installer(args)
    if args.command == "uninstall":
        inst.uninstall()
        return 0 if inst.clean else 1

    if args.command == "install":
        inst.install_payloads()
        inst.wire()

    print("\n--- verify: running each hook command for real ---")
    green = inst.verify()
    if args.prove:
        print("\n--- prove: each check must be able to fail ---")
        green &= inst.prove()
    return _finish(green and inst.clean, inst.payload_dir)


if __name__ == "__main__":
    sys.exit(main())
