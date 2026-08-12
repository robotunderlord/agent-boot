"""The three enforcement layers - the mechanism that makes doctrine actually fire.

THE FINDING THIS ENCODES
------------------------
Doctrine is not the scarce thing. Enforcement is.

Surveying a working agent instance produced the result that motivated this module: its doctrine
was already complete. Asked what its stopping rule should be it answered *"stop when the artifact
is in hand, not when the story is coherent"* - an accurate, independently-derived statement of the
exact discipline it kept violating. It could recite the rule and could not follow it, because
nothing fired.

    Boot is a hormone. Orientation has a HALF-LIFE and must be RE-RELEASED, not run once at wake.

So enforcement is three layers, not one:

    SessionStart      -> the tattoo      orientation INJECTED, not "read this first"
    UserPromptSubmit  -> the per-turn    the boot has decayed by turn 40
    PreToolUse        -> the per-action  fires in the half-second BEFORE a mutation

The third layer is the one that earns its keep and the one everybody skips. A "boot gate with
teeth" - the fix reached for first - fires once at turn 0 and cannot reach a turn-40 failure.

TWO RULES THIS MODULE OBEYS
---------------------------
**Merge, never replace.** A settings file usually already has hooks that work. Dropping a
stranger's configuration to install your own is the same defect as a REST write that clobbers the
fields it was not given.

**Configured is not working.** Verification EXECUTES each hook command and greps its output for a
marker, so an unwired hook can never be reported as a live one.
"""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from .status import Status
from .steps import CommandStep, Result


@dataclass(frozen=True)
class Layer:
    """One enforcement layer: a hook event, its payload file, and the marker that proves it fired."""

    event: str
    payload: str
    marker: str
    status_message: str
    matcher: str = ""
    preserve_local: bool = False


LAYERS: tuple[Layer, ...] = (
    Layer("SessionStart", "tattoo.md", "THE LAW OF THE WAKE",
          "Orienting (tattoo)...", preserve_local=True),
    Layer("UserPromptSubmit", "nag.md", "ARTIFACT BEFORE ASSERTION",
          "Re-releasing orientation...", preserve_local=True),
    Layer("PreToolUse", "nag-terse.md", ">>> BEFORE THIS ACTION <<<",
          "Before this action...", matcher="Bash|Edit|Write", preserve_local=True),
)


class EnforcementInstaller:
    """Install, verify and remove the three-layer hook wiring for an agent.

    Every layer whose payload is marked `preserve_local` is treated as the operator's own file:
    written once, then never overwritten. Local rules therefore survive upgrades and never travel
    back upstream.
    """

    def __init__(self, claude_dir: Path, payload_dir: Path, payload_src: Path) -> None:
        """Store the settings directory, the payload destination, and where templates come from."""
        self.claude_dir = Path(claude_dir)
        self.payload_dir = Path(payload_dir)
        self.payload_src = Path(payload_src)
        self.settings = self.claude_dir / "settings.json"
        self.results: list[Result] = []

    # ── payloads ────────────────────────────────────────────────────────────────────────────
    def install_payloads(self) -> None:
        """Copy each template into place, leaving any operator-edited file untouched."""
        self.payload_dir.mkdir(parents=True, exist_ok=True)
        for layer in LAYERS:
            src, dst = self.payload_src / layer.payload, self.payload_dir / layer.payload
            if not src.exists():
                self._record(layer.payload, Status.FAIL, f"template missing: {src}")
                continue
            if dst.exists() and layer.preserve_local:
                self._record(layer.payload, Status.OK, "already present - left alone (holds local edits)")
                continue
            shutil.copyfile(src, dst)
            self._record(layer.payload, Status.OK, f"{dst} ({dst.stat().st_size} b)")

    # ── settings.json ───────────────────────────────────────────────────────────────────────
    def _read_settings(self) -> dict:
        """Return the parsed settings file, or an empty dict when there is none."""
        if not self.settings.exists():
            return {}
        try:
            return json.loads(self.settings.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"[ !! ] {self.settings} is unparseable; refusing to touch it: {exc}") from exc

    def _write_settings(self, data: dict) -> None:
        """Back up and then atomically write the settings file."""
        if self.settings.exists():
            backup = self.settings.with_suffix(f".json.bak-{int(time.time())}")
            shutil.copyfile(self.settings, backup)
            self._record("backup", Status.OK, backup.name)
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.settings.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.settings)

    def command_for(self, layer: Layer) -> str:
        """Return the hook command for a layer - a plain cat of an absolute path."""
        return f"cat {self.payload_dir / layer.payload}"

    def _is_ours(self, entry: dict, layer: Layer) -> bool:
        """Return True when a settings hook entry is one this installer wrote."""
        return any(layer.payload in hook.get("command", "") for hook in entry.get("hooks", []))

    def wire(self) -> None:
        """Merge the three layers into the existing settings, preserving every foreign hook."""
        data = self._read_settings()
        hooks = data.setdefault("hooks", {})
        for layer in LAYERS:
            arr = hooks.setdefault(layer.event, [])
            arr[:] = [e for e in arr if not self._is_ours(e, layer)]
            foreign = len(arr)
            entry: dict = {"matcher": layer.matcher} if layer.matcher else {}
            entry["hooks"] = [{
                "type": "command",
                "command": self.command_for(layer),
                "timeout": 5,
                "statusMessage": layer.status_message,
            }]
            arr.append(entry)
            detail = f"wired -> {layer.payload}" + (f" (kept {foreign} existing)" if foreign else "")
            self._record(layer.event, Status.OK, detail)
        self._write_settings(data)

    # ── verification ────────────────────────────────────────────────────────────────────────
    def steps(self) -> list[CommandStep]:
        """Return a `CommandStep` per layer, so verification runs through the same evidence rule."""
        return [CommandStep(layer.event, self.command_for(layer), marker=layer.marker, critical=True)
                for layer in LAYERS]

    def verify(self) -> bool:
        """Execute every hook command and confirm its marker appears. Returns True when all green."""
        data = self._read_settings()
        hooks = data.get("hooks", {})
        green = True
        for layer, step in zip(LAYERS, self.steps(), strict=True):
            if not any(self._is_ours(e, layer) for e in hooks.get(layer.event, [])):
                self._record(layer.event, Status.FAIL, "NOT wired in settings.json")
                green = False
                continue
            result = step.run()
            self.results.append(result)
            print(result.line().render())
            green &= not result.status.is_red
        return green

    def prove(self) -> bool:
        """Confirm each verification can actually fail. Returns True when every check is real."""
        green = True
        for step in self.steps():
            result = step.prove()
            print(result.line().render())
            green &= not result.status.is_red
        return green

    def uninstall(self) -> None:
        """Remove only the hook entries this installer wrote, leaving payloads and foreign hooks."""
        data = self._read_settings()
        hooks = data.get("hooks", {})
        for layer in LAYERS:
            arr = hooks.get(layer.event, [])
            before = len(arr)
            arr[:] = [e for e in arr if not self._is_ours(e, layer)]
            if not arr:
                hooks.pop(layer.event, None)
            self._record(layer.event, Status.OK, f"removed {before - len(arr)} entry(ies)")
        self._write_settings(data)

    # ── reporting ───────────────────────────────────────────────────────────────────────────
    def _record(self, label: str, status: Status, detail: str) -> None:
        """Record and immediately print one installer line."""
        result = Result(label, status, detail)
        self.results.append(result)
        print(result.line(18).render())

    @property
    def clean(self) -> bool:
        """Return True when no recorded step came back red."""
        return not any(r.status.is_red for r in self.results)
