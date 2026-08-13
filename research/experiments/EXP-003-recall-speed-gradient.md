# EXP-003 — the recall-speed gradient

**Status:** WRITTEN. Measured 2026-07-29 with a fixed question tree across every memory tier.

## The question

Recall is not one thing. How much slower is each tier than the one above it — and does the
difference matter enough to change how an agent answers?

## Result — four orders of magnitude

| tier | what it is | measured |
|---|---|---|
| **resident** | already in context — a loaded doctrine file | **0.1 ms** |
| **keyed** | a find-by-key lookup | **~90 ms** |
| **semantic** | vector search over the corpus | **~1.9 s** |
| **multi-hop** | connecting crumbs across sources, cold | **~4.4 s** |

**Resident to multi-hop is a factor of ~44,000.**

## What it means

This gradient is the reason an agent's memory has to be *tiered* rather than uniform, and it is the
measured shape behind `agentboot/dispatch.py` and the split between `state.py` (keyed) and
`semantic.py`:

- **Answering a lookup with semantic search costs ~20x more than a keyed hit** and can return a
  plausible neighbour rather than the fact. Classification is not an optimisation here; it changes
  the *correctness* of the answer, not only its latency.
- **The 4.4 s multi-hop tier is worth engineering away.** Pre-connecting relationships at write time
  — a crumb that already points at what it relates to — moves that work off the critical path
  entirely. This is why a crumb is required to carry a `ref`.
- **Resident beats everything by four orders of magnitude.** Which is the argument for keeping
  doctrine and posture *loaded* rather than retrievable: anything consulted on nearly every turn
  should not be a lookup at all.

## The autonomic reading

The gradient maps onto how a nervous system is organised, and the analogy earns its place:

```
resident   0.1 ms    reflex      no deliberation, no lookup - it is simply already there
keyed      90 ms     autonomic   a fast involuntary retrieval
semantic   1.9 s     recall      deliberate remembering
multi-hop  4.4 s     reasoning   connecting things that were never connected before
```

An agent that routes every question through the slowest tier is not being thorough. It is doing
long-division to answer "what is your name" — and the cost is not only time, it is that the slow
path introduces uncertainty the fast path did not have.

## Limits

One host, one corpus, one night. The absolute numbers are specific to that hardware; the **ratios**
are the finding. Re-measure on your own before quoting any of it as a target.
