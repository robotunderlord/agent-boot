"""The main loop as a DISPATCHER: answer cheaply, escalate deliberately, spend nothing by default.

THE ANATOMY
-----------
    memory core     keyed + semantic recall        what he knows
    main loop       this module - plain, instant   the NERVOUS SYSTEM, autonomic
    the regions     haiku / opus / local / gemini  the PREFRONTAL CORTEX - the thoughts

The agent is the persistent thing. A model is a REGION it recruits, not the thing it is - which is
why the roster is plural, why regions are named for what they are FOR, and why losing one degrades
a capability rather than ending a life.

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
    tier 2  CORTEX    a recruited region, over the spine            deliberate, reasoned, logged

The spine (LiteLLM) is the PATHWAY, not the thinking. Calling tier 2 "the spine" was a naming
error worth correcting: nerves carry signals, they do not have thoughts.

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

    RECALL = 0      # no model touched - reflex
    LOCAL = 1       # small resident model, no account - autonomic
    CORTEX = 2      # a recruited prefrontal region, reached over the spine - a thought


@dataclass(frozen=True)
class Region:
    """One recruitable prefrontal region: a model, and what kind of thinking it is FOR.

    The prefrontal is PLURAL. It is not "the big model you fall back to" - it is a set of regions
    recruited for different work, at different costs, potentially several at once. A cheap fast one
    for triage, a deep one for design, local silicon for bulk, a different vendor for a second
    opinion. Naming them by what they are FOR rather than by vendor is what makes that choosable:
    "this needs careful reasoning" survives a model being renamed or replaced; "use opus" does not.
    """

    name: str
    model: str
    for_work: str
    endpoint: str = ""      # empty = reached over the default spine
    cost: int = 1           # relative, not currency - only the ordering is meaningful

    def __post_init__(self) -> None:
        """Refuse a region that cannot say what it is for."""
        if not self.for_work.strip():
            raise ValueError(
                f"region {self.name!r} must say what kind of work it is FOR. A roster of models with "
                "no stated purpose is not a choice, it is a list - and a list gets used top-down, "
                "which means the most expensive entry answers everything.")


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
    region: str = ""        # WHICH prefrontal region, when one was recruited

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
    regions: tuple[Region, ...] = ()
    log: list[dict] = field(default_factory=list)

    def recruit(self, for_work: str) -> Region | None:
        """Return the region that best fits the work, cheapest among equal fits, or None.

        Cheapest-that-FITS, never cheapest-available and never best-available. Both failure modes
        are real: consult a roster top-down and the most expensive region answers everything;
        consult it cost-first with a sloppy match and design work goes to a triage model.

        LANDMINE, PAID FOR: matching by substring sends everything to the cheapest region. The word
        "a" from "design A migration plan" is a substring of "tri-A-ge", so every region matched
        every turn and cost alone decided. Whole-token overlap only, and short words are dropped -
        they carry no signal and match everything.
        """
        if not self.regions:
            return None
        words = {w for w in re.findall(r"[a-z]+", for_work.lower()) if len(w) > 3}
        scored = [(len(words & {t for t in re.findall(r"[a-z]+", r.for_work.lower()) if len(t) > 3}), r)
                  for r in self.regions]
        best = max(score for score, _ in scored)
        if best == 0:
            # Nothing matched. Take the cheapest rather than guessing at a specialist.
            return min(self.regions, key=lambda r: r.cost)
        # Strongest fit wins; cost only breaks ties between regions that fit equally well.
        return min((r for score, r in scored if score == best), key=lambda r: r.cost)

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
                    return Route(Tier.LOCAL, "wants a recruited region, but no spine is configured - "
                                             "answering locally and saying so")
                region = self.recruit(text)
                return Route(Tier.CORTEX,
                             f"work the resident brain does badly; recruited "
                             f"{region.name if region else self.spine_model}",
                             region.model if region else self.spine_model,
                             region.name if region else "")

        if len(text) > self.long_turn_chars and self.spine_url:
            region = self.recruit(text)
            return Route(Tier.CORTEX,
                         f"long turn ({len(text)} chars) - context this size is where a small model "
                         f"degrades; recruited {region.name if region else self.spine_model}",
                         region.model if region else self.spine_model,
                         region.name if region else "")

        if self.local_url:
            return Route(Tier.LOCAL, "conversational turn - the resident model is free and instant",
                         self.local_model)
        return Route(Tier.RECALL, "no local brain configured - recall only, and that is honest")

    # ── accounting ──────────────────────────────────────────────────────────────────────────
    def record(self, turn: str, route: Route) -> Route:
        """Log the decision so the routing can be audited rather than assumed."""
        self.log.append({"ts": time.time(), "tier": int(route.tier), "why": route.why,
                         "region": route.region, "chars": len(turn)})
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
                f"{profile['CORTEX']} cortex ({free * 100 // total}% free)")

    # ── backends ────────────────────────────────────────────────────────────────────────────
    def endpoint(self, tier: Tier) -> str:
        """Return the base URL serving a tier, or an empty string when it is not configured."""
        return {Tier.RECALL: "", Tier.LOCAL: self.local_url, Tier.CORTEX: self.spine_url}[tier]

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
            live.append("spine" + ("" if self.dispatcher.reachable(Tier.CORTEX) else " (UNREACHABLE)"))
        return Evidence(f"routing; tiers: {', '.join(live)}", "classify()")

    def failing_variant(self) -> DispatcherStep:
        """Return a dispatcher whose classifier cannot satisfy the assertion."""
        broken = Dispatcher()
        broken.classify = lambda *a, **k: Route(Tier.SPINE, "deliberately wrong for the prove pass")
        return DispatcherStep(broken, critical=self.critical)
