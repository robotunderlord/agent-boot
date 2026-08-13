"""The main loop as a DISPATCHER: answer cheaply, escalate deliberately, spend nothing by default.

THIS IS A NERVOUS SYSTEM, NOT A MIND
------------------------------------
The main loop should be plain to the point of being boring, and fast the way a reflex is fast -
because a reflex does not deliberate, it responds. What makes it look intelligent is not the model
in it; it is everything behind it. The measured recall gradient (research/EXP-003) reads exactly
like one:

    resident   0.1 ms    reflex      already there; nothing is retrieved
    keyed      90 ms     autonomic   fast, involuntary retrieval
    semantic   1.9 s     recall      deliberate remembering
    multi-hop  4.4 s     reasoning   connecting what was never connected

Four orders of magnitude between the ends. An agent that routes every question through the slowest
tier is doing long division to answer "what is your name".

AND THE SMALL BRAIN IS NOT A COMPROMISE
---------------------------------------
Measured, not assumed (research/EXP-006): a SMALL model with the right context matched or beat a
LARGE model without it, at under half the tokens - while the large unprimed one cowboyed the errand
and had to be stopped. Capability was never the binding constraint. Orientation was.

So a tiny local model backed by good recall is the CORRECT choice here, not the cheap one.

THE SHAPE
---------
The main loop is not a big model. It is a router with a small one attached, and its job is to be
conversationally instant while deciding what actually deserves a real brain:

    tier 0  RECALL    keyed lookup or semantic hit answers it       no model at all
    tier 1  LOCAL     a small CPU model, resident, free             no account
    tier 2  SPINE     LiteLLM -> the heavy brains                   deliberate, reasoned, logged

Most turns are tier 0 or 1. "What did I do last session", "expand that crumb", "what is X", an
acknowledgement, a status question - none of those need a frontier model, and routing them to one
is how an always-on agent becomes an expensive one.

THE RULE THAT MAKES IT WORK
---------------------------
**The routing decision itself must be free.** Calling a paid model to decide whether to call a paid
model has already lost - you pay on every turn including the ones you were trying to avoid paying
for. So classification here is rules plus recall: string shape, question shape, and whether the
answer is already in memory. Crude on purpose, and cheap enough to run on every single turn.

ESCALATION IS A DECISION, AND IT IS RECORDED
--------------------------------------------
`Route` carries a `why`. An escalation without a stated reason is indistinguishable from a default,
and a default to the expensive path is how the bill arrives. If nothing can say why the small brain
was insufficient, the small brain was sufficient.

WORKS WITH NO MODEL AT ALL
--------------------------
If no local brain is configured, the dispatcher degrades to tier 0 and says so. An agent that can
still expand a crumb and answer from memory with zero models attached is far more useful than one
that refuses to start - and it is the honest baseline this thing should always retain.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from enum import IntEnum

from .steps import Evidence, Step, StepFailed


class Tier(IntEnum):
    """How expensive an answer was allowed to be. Lower is cheaper; cheapest sufficient wins."""

    RECALL = 0      # no model touched
    LOCAL = 1       # small resident model, no account
    SPINE = 2       # the heavy brains, via LiteLLM


# Shapes that recall answers better than any model - they want a FACT, not prose.
RECALL_SHAPES = (
    re.compile(r"^\s*(expand|what is|who is|where is|when did|what did .* (do|say))\b", re.I),
    re.compile(r"\[\[.+?\]\]"),                       # an explicit crumb reference
    re.compile(r"^\s*(status|state|where were we|what.s open)\b", re.I),
)

# Shapes that genuinely want a big brain. Deliberately short: the default is NOT to escalate.
ESCALATE_SHAPES = (
    re.compile(r"\b(design|architect|refactor|implement|debug|why does|explain why|plan)\b", re.I),
    re.compile(r"\b(write|draft|compose)\b.{0,40}\b(doc|spec|essay|report|module|test)s?\b", re.I),
)


@dataclass(frozen=True)
class Route:
    """A routing decision: which tier, and WHY - because an unreasoned escalation is a default."""

    tier: Tier
    why: str
    model: str = ""

    def __post_init__(self) -> None:
        """Refuse a route that cannot justify itself."""
        if not self.why.strip():
            raise ValueError(
                "a route needs a `why`. An escalation with no stated reason is indistinguishable "
                "from a default, and defaulting to the expensive tier is how the bill arrives.")


@dataclass
class Dispatcher:
    """Classify each turn and answer at the cheapest sufficient tier.

    Backend-agnostic by construction: the local brain and the spine are both just OpenAI-compatible
    endpoints. Whether the small one is llama.cpp, vLLM on CPU, or ollama is a deployment choice,
    and this class deliberately does not care.
    """

    local_url: str = field(default_factory=lambda: os.environ.get("AGENT_LOCAL_LLM", ""))
    local_model: str = field(default_factory=lambda: os.environ.get("AGENT_LOCAL_MODEL", "local"))
    spine_url: str = field(default_factory=lambda: os.environ.get("AGENT_SPINE_URL", ""))
    spine_model: str = field(default_factory=lambda: os.environ.get("AGENT_SPINE_MODEL", "spine"))
    long_turn_chars: int = 400
    log: list[dict] = field(default_factory=list)

    # ── the free classifier ─────────────────────────────────────────────────────────────────
    def classify(self, turn: str, *, recall_hit: bool = False) -> Route:
        """Choose a tier for this turn, using no model and no network.

        Runs on every turn, so it must stay free. Rules and a recall flag only.
        """
        text = turn.strip()
        if not text:
            return Route(Tier.RECALL, "empty turn - nothing to answer")

        if recall_hit and not any(p.search(text) for p in ESCALATE_SHAPES):
            return Route(Tier.RECALL, "recall already holds the answer; no model needed")

        for pattern in RECALL_SHAPES:
            if pattern.search(text):
                return Route(Tier.RECALL, "a lookup question - memory answers it exactly, a model guesses")

        for pattern in ESCALATE_SHAPES:
            if pattern.search(text):
                if not self.spine_url:
                    return Route(Tier.LOCAL, "wants a big brain, but no spine is configured - "
                                             "answering locally and saying so")
                return Route(Tier.SPINE, f"work of a kind the small brain does badly: {pattern.pattern[:40]}",
                             self.spine_model)

        if len(text) > self.long_turn_chars and self.spine_url:
            return Route(Tier.SPINE, f"long turn ({len(text)} chars) - context this size is where a "
                                     "small model degrades", self.spine_model)

        if self.local_url:
            return Route(Tier.LOCAL, "conversational turn - the resident model is free and instant",
                         self.local_model)
        return Route(Tier.RECALL, "no local brain configured - recall only, and that is honest")

    # ── accounting ──────────────────────────────────────────────────────────────────────────
    def record(self, turn: str, route: Route) -> Route:
        """Log the decision so the routing can be audited rather than assumed."""
        self.log.append({"ts": time.time(), "tier": int(route.tier), "why": route.why,
                         "chars": len(turn)})
        return route

    def dispatch(self, turn: str, *, recall_hit: bool = False) -> Route:
        """Classify and record in one call - the normal entry point for the main loop."""
        return self.record(turn, self.classify(turn, recall_hit=recall_hit))

    @property
    def spend_profile(self) -> dict[str, int]:
        """Return how many turns went to each tier. The shape of the bill, before it arrives."""
        out = {t.name: 0 for t in Tier}
        for entry in self.log:
            out[Tier(entry["tier"]).name] += 1
        return out

    def summary(self) -> str:
        """Return a one-line description of where the turns actually went."""
        profile = self.spend_profile
        total = sum(profile.values()) or 1
        free = profile["RECALL"] + profile["LOCAL"]
        return (f"{total} turns: {profile['RECALL']} recall, {profile['LOCAL']} local, "
                f"{profile['SPINE']} spine ({free * 100 // total}% free)")

    # ── backends ────────────────────────────────────────────────────────────────────────────
    def endpoint(self, tier: Tier) -> str:
        """Return the base URL serving a tier, or an empty string when it is not configured."""
        return {Tier.RECALL: "", Tier.LOCAL: self.local_url, Tier.SPINE: self.spine_url}[tier]

    def reachable(self, tier: Tier, timeout: float = 3.0) -> bool:
        """Return True when the tier's endpoint answers its model list."""
        import urllib.error
        import urllib.request
        url = self.endpoint(tier)
        if not url:
            return False
        try:
            with urllib.request.urlopen(f"{url.rstrip('/')}/models", timeout=timeout) as resp:
                return resp.status < 500
        except urllib.error.HTTPError as exc:
            return exc.code in (401, 403)      # a door is proof something is serving
        except Exception:  # noqa: BLE001 - unreachable is unreachable
            return False

    def step(self, critical: bool = False) -> DispatcherStep:
        """Return the boot step that proves the main loop can answer at all."""
        return DispatcherStep(self, critical=critical)


class DispatcherStep(Step):
    """Boot step proving the dispatcher routes, and reporting which tiers are actually live."""

    def __init__(self, dispatcher: Dispatcher, critical: bool = False) -> None:
        """Store the dispatcher this step verifies."""
        super().__init__("dispatch", critical=critical)
        self.dispatcher = dispatcher

    def check(self) -> Evidence:
        """Confirm classification works and report the live tiers.

        RECALL is always available - it needs no model - so the main loop can always answer
        something. That is the property worth asserting: this must never be a hard failure just
        because no brain is attached.
        """
        probe = self.dispatcher.classify("what is the recall gate?")
        if probe.tier is not Tier.RECALL:
            raise StepFailed(f"a lookup question routed to {probe.tier.name}, not RECALL")
        live = ["recall"]
        if self.dispatcher.local_url:
            live.append("local" + ("" if self.dispatcher.reachable(Tier.LOCAL) else " (UNREACHABLE)"))
        if self.dispatcher.spine_url:
            live.append("spine" + ("" if self.dispatcher.reachable(Tier.SPINE) else " (UNREACHABLE)"))
        return Evidence(f"routing; tiers: {', '.join(live)}", "classify()")

    def failing_variant(self) -> DispatcherStep:
        """Return a dispatcher whose classifier cannot satisfy the assertion."""
        broken = Dispatcher()
        broken.classify = lambda *a, **k: Route(Tier.SPINE, "deliberately wrong for the prove pass")
        return DispatcherStep(broken, critical=self.critical)
