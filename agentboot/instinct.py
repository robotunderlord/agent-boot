"""Instincts: reflexes whose response is EXECUTABLE, not advisory.

THE DIFFERENCE FROM A LESSON, AND WHY IT IS THE WHOLE POINT
-------------------------------------------------------------
A lesson that fires emits a sentence: "check what is in the volume before removing it." That sentence
depends entirely on the reader complying with it. A model in a hurry, mid-plan, with a satisfying
next step already formed, reads it and proceeds - and the sentence was true, timely, correctly
matched, and completely ineffective.

An instinct does not ask. It RUNS:

    lesson    "check what is in that volume first"        -> the reader may comply
    instinct  inspects the volume, reports 4GB of pgdata  -> the check HAPPENED

Telling a model to verify is not verification. The only reflex that reliably survives a confident
plan is one that has already done the work by the time the plan is read, which is why the response
here is a Python callable rather than a string.

THREE REACTIONS, AND ONLY ONE OF THEM STOPS ANYTHING
------------------------------------------------------
    OBSERVE   gather real state and attach it. Changes nothing, blocks nothing.
    ADVISE    OBSERVE plus a warning that names the consequence.
    DENY      refuse the action outright.

DENY is rare on purpose. A reflex layer that blocks often gets disabled, and a disabled reflex layer
protects nothing - so the bar for DENY is an action that is IRREVERSIBLE and MISTAKEN, not merely
risky. Everything else observes, because an observation that arrives with evidence attached changes
behaviour without ever needing the authority to stop it.

FAIL CLOSED WHEN REFUSING, FAIL OPEN WHEN ADVISING
----------------------------------------------------
An instinct can throw - it shells out, it reads state, it touches things that are not there.

An ADVISE or OBSERVE instinct that throws is swallowed. Its failure must not take the turn with it,
because the cost of that bug is one missing warning while the cost of the alternative is an agent
that cannot act at all.

A DENY instinct that throws **denies**. This is the asymmetry that matters: a safety check which
errored did not pass, it failed to complete, and treating those two as the same thing is how a
guard silently stops guarding while every indicator stays green. That is the same rule as everywhere
else in this package - success is not evidence - applied at the point where it is most tempting to
be lenient.

WHAT AN INSTINCT MUST NEVER DO
-------------------------------
Never echo the matched situation. A `PreToolUse` payload holds the literal command about to run,
which routinely contains tokens and connection strings. Instincts read it to decide; they return
their own words and their own gathered evidence, never the text they matched on. A safety mechanism
that leaks is a net loss.
"""
from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum

from .lessons import SIGNAL_TERMS, _tokens


class Reaction(IntEnum):
    """How strongly an instinct responds. Ordered so the strongest reaction wins a fan-out."""

    OBSERVE = 0
    ADVISE = 1
    DENY = 2


@dataclass
class Response:
    """What an instinct did and what it found."""

    reaction: Reaction
    message: str
    evidence: str = ""
    instinct: str = ""

    def __bool__(self) -> bool:
        """Return False when this response refuses the action."""
        return self.reaction is not Reaction.DENY

    def render(self) -> str:
        """Return the response as the agent should read it."""
        head = {Reaction.OBSERVE: "[observed]", Reaction.ADVISE: ">>> INSTINCT",
                Reaction.DENY: ">>> REFUSED"}[self.reaction]
        tag = f" {self.instinct}" if self.instinct else ""
        body = f"{head}{tag}  {self.message}"
        return f"{body}\n           evidence: {self.evidence}" if self.evidence else body


@dataclass
class Instinct:
    """A tell, and the Python that runs when the situation matches it.

    `handler` receives the situation string and the raw hook event, and returns a Response. It is
    ordinary Python and may do real work - shell out, read a file, query a store - because an
    instinct that only formats a string is a lesson wearing a costume.
    """

    name: str
    tell: str
    handler: Callable[[str, dict], Response]
    reaction: Reaction = Reaction.ADVISE
    threshold: float = 0.5

    def __post_init__(self) -> None:
        """Refuse an instinct that cannot fire or cannot act."""
        if not self.tell.strip():
            raise ValueError(f"instinct {self.name!r} has no tell - it would never fire")
        if not callable(self.handler):
            raise ValueError(f"instinct {self.name!r} has no handler - it would only be a lesson")

    def matches(self, situation: str) -> float:
        """Return how strongly this instinct's tell matches the situation, 0..1."""
        keys, query = _tokens(self.tell), _tokens(situation)
        if not keys or not query:
            return 0.0
        return len(keys & query) / min(len(keys), len(query), SIGNAL_TERMS)

    def fire(self, situation: str, event: dict | None = None) -> Response:
        """Run the handler, applying the fail-closed/fail-open asymmetry.

        A DENY instinct that raises returns a DENY. It did not pass; it failed to complete, and those
        are different facts that must not be collapsed into a green light.
        """
        try:
            return self.handler(situation, event or {})
        except Exception as exc:  # noqa: BLE001 - the reaction decides what a failure means
            if self.reaction is Reaction.DENY:
                return Response(Reaction.DENY, f"{self.name} could not complete its check "
                                f"({type(exc).__name__}) - refusing rather than assuming it passed",
                                instinct=self.name)
            return Response(Reaction.OBSERVE, "", instinct=self.name)


@dataclass
class Arc:
    """The set of instincts a seat carries, and the path that fires them.

    Named for the reflex ARC rather than for a rule engine on purpose: the defining property is that
    the response happens before deliberation, not that the rules are configurable.

    Distinct from `reflexes.Reflexes`, and the pair is the point. That one generates a TABLE - the
    situation, the tool to reach for, and the tempting wrong move - which makes a capability visible
    at the moment it is needed. This one REACHES. A table still requires the agent to act on what it
    read; the arc has already acted by the time the agent reads anything.
    """

    instincts: list[Instinct] = field(default_factory=list)

    def add(self, *instincts: Instinct) -> Arc:
        """Register instincts and return self so a seat can be wired fluently."""
        self.instincts.extend(instincts)
        return self

    def fire(self, situation: str, event: dict | None = None) -> list[Response]:
        """Run every instinct whose tell matches, strongest reaction first.

        A DENY does NOT short-circuit the others. When an action is refused, the observations that
        explain why are the most valuable thing the layer can produce - stopping early would refuse
        the action and then withhold the reason.
        """
        if not situation.strip():
            return []
        fired = [i.fire(situation, event) for i in self.instincts
                 if i.matches(situation) >= i.threshold]
        real = [r for r in fired if r.message or r.evidence]
        return sorted(real, key=lambda r: -int(r.reaction))

    def verdict(self, situation: str, event: dict | None = None) -> tuple[bool, str]:
        """Return whether the action may proceed, and the block to show the agent.

        The boolean is the decision and the string is the reasoning; a caller that ignores the
        string still gets a correct decision, which is the property a hook needs.
        """
        responses = self.fire(situation, event)
        allowed = all(responses) if responses else True
        return allowed, "\n".join(r.render() for r in responses)


# ---------------------------------------------------------------------------------------------
# Instincts worth having out of the box. Each one exists because the advisory version of it was
# already written down somewhere and was already ignored at least once.
# ---------------------------------------------------------------------------------------------

def _run(command: str, timeout: int = 10) -> str:
    """Run a read-only probe and return its output, or a legible failure. Never raises."""
    try:
        done = subprocess.run(shlex.split(command), capture_output=True, text=True,  # noqa: S603
                              timeout=timeout, check=False)
        return (done.stdout or done.stderr).strip()[:400]
    except Exception as exc:  # noqa: BLE001 - a probe that fails is evidence, not a crash
        return f"probe failed: {type(exc).__name__}: {exc}"


def volume_contents(_situation: str, event: dict) -> Response:
    """Look INSIDE a volume before it is removed, instead of advising someone to.

    The advisory form of this was written down, matched correctly, and ignored - because at the
    moment of deletion the volume is believed to be empty, and a sentence does not disturb a belief.
    Four gigabytes of pgdata in the output does.
    """
    payload = event.get("tool_input") or {}
    command = payload.get("command", "") if isinstance(payload, dict) else ""
    name = ""
    parts = command.split()
    if "volume" in parts and "rm" in parts:
        name = parts[-1]
    if not name:
        return Response(Reaction.OBSERVE, "", instinct="volume-contents")
    found = _run(f"docker volume inspect {name} --format {{{{.Mountpoint}}}}")
    return Response(Reaction.ADVISE,
                    f"about to remove volume {name} - state in a volume does not come back",
                    evidence=found, instinct="volume-contents")


def default_route(_situation: str, _event: dict) -> Response:
    """Prove isolation by the ROUTE TABLE, because 'not exposed' is not 'isolated'.

    A container with no published ports still reaches the whole internet if it has a default route.
    Nothing about the compose file says so, and every check that looks at ports says it is fine.
    """
    routes = _run("ip route show default")
    if not routes or routes.startswith("probe failed"):
        return Response(Reaction.OBSERVE, "no default route - this network cannot leave the host",
                        evidence=routes or "(none)", instinct="default-route")
    return Response(Reaction.ADVISE,
                    "this network HAS a default route - not exposed is not the same as isolated",
                    evidence=routes, instinct="default-route")


def shared_checkout(_situation: str, event: dict) -> Response:
    """Refuse a write to the shared checkout from a seat that should be in its own tree.

    One of the few genuine DENYs: the damage is other people's uncommitted work, it is not
    recoverable from anything the agent controls, and the correct action is one call away.
    """
    payload = event.get("tool_input") or {}
    path = payload.get("file_path", "") if isinstance(payload, dict) else ""
    if not path or "/.claude/worktrees/" in path:
        return Response(Reaction.OBSERVE, "", instinct="shared-checkout")
    return Response(Reaction.DENY,
                    "writing outside an isolated tree - isolate first, then write",
                    evidence=f"target is not under a worktree: {path.rsplit('/', 1)[0]}/",
                    instinct="shared-checkout")


def default_reflexes() -> Arc:
    """Return the instincts every seat carries unless it deliberately drops one."""
    return Arc().add(
        Instinct("volume-contents", "removing a docker volume with state in it",
                 volume_contents, Reaction.ADVISE),
        Instinct("default-route", "checking whether a container network is isolated",
                 default_route, Reaction.ADVISE),
        Instinct("shared-checkout", "editing or writing a file in the shared checkout",
                 shared_checkout, Reaction.DENY),
    )
