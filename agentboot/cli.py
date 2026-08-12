"""Command line entry points: install the enforcement layers, hold a posture, and run a demo boot.

python3 -m agentboot install          -- wire the three layers, then verify by executing them
python3 -m agentboot install --prove  -- also confirm each check is capable of failing
python3 -m agentboot verify           -- check only, change nothing
python3 -m agentboot uninstall        -- remove only what this installed
python3 -m agentboot demo             -- run a boot against the installed payloads
python3 -m agentboot posture --persona skeptic  -- print a posture block
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from .boot import Boot, Tier
from .curriculum import Curriculum
from .enforcement import LAYERS, POSTURE_LAYER, EnforcementInstaller
from .intake import Intake, load_answers
from .persona import Wardrobe
from .steps import FileStep, LazyStep

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "examples"
DEFAULT_PAYLOADS = EXAMPLES / "payloads"
DEFAULT_AVATARS = EXAMPLES / "avatars"
CURRICULUM = REPO_ROOT / "curriculum"


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
    layers = LAYERS + (POSTURE_LAYER,) if getattr(args, "persona", None) else LAYERS
    return EnforcementInstaller(claude, payloads, Path(args.payloads or DEFAULT_PAYLOADS), layers)


def _finish(green: bool, payload_dir: Path, count: int) -> int:
    """Print the closing verdict and return the process exit code."""
    print()
    if not green:
        print("[ !! ] NOT clean - fix the lines above before trusting any of it.")
        return 1
    print(f"[ OK ] all {count} layers wired AND proven to emit.")
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


LESSON_HOWTO = """# Your ledger

These lessons are YOURS. Nothing ships here with the package, and nothing you write here travels
back upstream.

That separation is the point. A lesson is only worth anything because of the scar behind it, and you
did not earn someone else's scars - inheriting them gives you a rule you will obey where it does not
apply and abandon where it does. `examples/lessons/` in the repo shows the SHAPE. Do not copy the
content.

## The shape

    id     a stable handle, e.g. L-001
    tell   HOW YOU RECOGNISE THE SITUATION     <- the index key; get this wrong and nothing fires
    trade  what to do instead
    scar   the incident that taught it
    cost   what it actually cost, in units that motivate
    tags   extra words to match on

## The one rule that matters

Write the `tell` as the situation you will be IN, not the topic it concerns.

    BAD    "API pagination"
    GOOD   "about to report a total from a list endpoint without checking for a next page"

A ledger keyed by topic requires you to already know to look it up. Keyed by the tell, it fires on
its own. That difference is the whole value.

## Writing one

Add any `*.json` file in this directory:

    {"lessons": [
      {"id": "L-001",
       "tell":  "about to ...",
       "trade": "instead, ...",
       "scar":  "the time that ...",
       "cost":  "an evening",
       "tags":  ["..."]}
    ]}

Write it the moment it lands. Deferring to end of session loses it, because a kill does not fire
your cleanup - and that is exactly when it matters most.
"""

AVATAR_HOWTO = """# Your avatars

An avatar is a DISPOSITION you can load, not a biography. Keep four headings:

    # Name - the Role

    ## Who            one paragraph, so a reader knows why this voice
    ## Why this one   what makes them fit THIS discipline
    ## Posture        a bullet list        <- this is what actually loads
    ## Tells          how you notice you have DRIFTED OUT of it

`Posture` is required; a file without it is refused as decoration. `Tells` is the half that does the
real work, because it can fire while an action is still in flight - the only place a self-check
helps.

Pick people who are genuinely dead and genuinely public domain, and pick your OWN. The examples in
the repo are somebody else's choices; they will not mean to you what they meant to whoever chose
them.
"""


def _init(payload_dir: Path, cooked: bool = False) -> int:
    """Scaffold the operator's own ledger and wardrobe - the shape, never the content.

    This exists because the package is a CLASS, not an inheritance. Shipping a populated ledger
    hands a new agent somebody else's history, which is knowledge; what actually transfers is the
    ability to keep your own, which is education.
    """
    for sub, howto in (("lessons", LESSON_HOWTO), ("avatars", AVATAR_HOWTO)):
        folder = payload_dir / sub
        folder.mkdir(parents=True, exist_ok=True)
        readme = folder / "README.md"
        if readme.exists():
            print(f"[ OK ] {sub:<10} already yours, left alone ({folder})")
            continue
        readme.write_text(howto, encoding="utf-8")
        print(f"[ OK ] {sub:<10} scaffolded EMPTY at {folder}")

    tools = payload_dir / "tools.d"
    tools.mkdir(parents=True, exist_ok=True)
    print(f"[ OK ] {'tools.d':<10} {tools}")

    if cooked:
        target = payload_dir / "curriculum"
        target.mkdir(parents=True, exist_ok=True)
        copied = 0
        for src in sorted(CURRICULUM.glob("*.json")):
            dst = target / src.name
            if not dst.exists():
                shutil.copyfile(src, dst)
                copied += 1
        loaded = Curriculum()
        loaded.load(target)
        print(f"[ OK ] {'curriculum':<10} {copied} syllabus file(s) -> {loaded.summary()}")
        print()
        print("COOKED: it boots with the ladder loaded. Grades are a dependency order and the exam")
        print("enforces it - progress is measured in exams passed, never in modules read.")
        return 0

    print()
    print("BLANK on purpose. It has the ability to hold lessons, personas and tools; what goes in")
    print("them is yours. Copy the SHAPE from examples/, never the content.")
    print()
    print("Now run the intake - it configures this container from what you can discover, what you")
    print("already know about the user, and what only they can tell you:")
    print("    python3 -m agentboot intake")
    return 0


def _write_posture(payload_dir: Path, wanted: str, avatars: Path) -> None:
    """Render the chosen avatar's posture into the payload the fourth hook layer reads."""
    wardrobe = Wardrobe()
    wardrobe.load(avatars)
    persona = wardrobe.get(wanted)
    if persona is None:
        names = ", ".join(f"{p.name} ({p.role})" for p in wardrobe.personas) or "none found"
        raise SystemExit(f"[ !! ] no avatar matching {wanted!r}. Available: {names}")
    payload_dir.mkdir(parents=True, exist_ok=True)
    target = payload_dir / "posture.md"
    if target.exists():
        print("[ OK ] posture.md....... already present - left alone (yours to edit)")
        return
    target.write_text(persona.nag_block() + "\n", encoding="utf-8")
    print(f"[ OK ] posture.md....... {persona.name} ({persona.role}), {len(persona.posture)} postures")


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the requested command."""
    ap = argparse.ArgumentParser(prog="agentboot", description=__doc__.split("\n")[0])
    ap.add_argument("command",
                    choices=["init", "intake", "syllabus", "install", "verify",
                             "uninstall", "demo", "posture"])
    ap.add_argument("--claude-dir", help="override ~/.claude")
    ap.add_argument("--payload-dir", help="override ~/.agentboot")
    ap.add_argument("--payloads", help="override the template source directory")
    ap.add_argument("--prove", action="store_true", help="also confirm every check can fail")
    ap.add_argument("--persona", help="keep an avatar's posture resident every turn (e.g. skeptic)")
    ap.add_argument("--avatars", help="override the avatar source directory")
    ap.add_argument("--cooked", action="store_true",
                    help="init preloaded with the curriculum instead of blank")
    ap.add_argument("--answers", help="intake: a JSON file of answers to apply")
    args = ap.parse_args(argv)

    if args.command == "init":
        _, payloads = _dirs(args)
        return _init(payloads, cooked=args.cooked)

    if args.command == "intake":
        _, payloads = _dirs(args)
        intake = Intake(payloads)
        if not args.answers:
            print(intake.sheet())
            return 0
        written = intake.apply(load_answers(args.answers))
        for path in written:
            print(f"[ OK ] wrote {path}")
        if not written:
            print("[WARN] no answers applied - every field was blank, so nothing was written.")
        return 0

    if args.command == "syllabus":
        _, payloads = _dirs(args)
        cur = Curriculum()
        cur.load(payloads / "curriculum") or cur.load(CURRICULUM)
        print(cur.summary())
        print()
        print(cur.syllabus())
        return 0

    if args.command == "posture":
        wardrobe = Wardrobe()
        wardrobe.load(Path(args.avatars or DEFAULT_AVATARS))
        print(wardrobe.nag_block(*([args.persona] if args.persona else [])))
        return 0

    if args.command == "demo":
        _, payloads = _dirs(args)
        return _demo_boot(payloads).run()

    inst = _installer(args)
    if args.command == "uninstall":
        inst.uninstall()
        return 0 if inst.clean else 1

    if args.command == "install":
        if args.persona:
            _write_posture(inst.payload_dir, args.persona, Path(args.avatars or DEFAULT_AVATARS))
        inst.install_payloads()
        inst.wire()

    print("\n--- verify: running each hook command for real ---")
    green = inst.verify()
    if args.prove:
        print("\n--- prove: each check must be able to fail ---")
        green &= inst.prove()
    return _finish(green and inst.clean, inst.payload_dir, len(inst.layers))


if __name__ == "__main__":
    sys.exit(main())
