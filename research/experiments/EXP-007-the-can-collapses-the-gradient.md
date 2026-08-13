# EXP-007 — living in the can collapses the recall gradient

**Status:** WRITTEN. Measured 2026-08-13, five-probe bench, N=3, against a running container stack.

## The question

EXP-003 measured the recall gradient on a distributed setup: resident 0.1 ms, keyed ~90 ms,
semantic ~1.9 s, multi-hop ~4.4 s. Those numbers assumed the memory tiers were *reachable over a
network* — a database on another host, a vector store on another VLAN.

If the same tiers live inside the agent's own stack, how much of that gradient is real, and how much
of it was just the network?

## Method

Five probes, N=3, median reported. Same question set, same corpus, same tier boundaries. The only
variable is where the tiers live: same-stack instead of across the estate.

- **resident** — a payload file loaded at every turn
- **keyed** — expand a crumb by key
- **semantic** — a meaning question against the indexed corpus
- **ledger** — fire a lesson from a described situation
- **negative** — a key that must NOT resolve

## Result

| tier | EXP-003, distributed | EXP-007, in the can | change |
|---|---|---|---|
| resident | 0.1 ms | **0.0 ms** | — |
| keyed | ~90 ms | **0.6 ms** | **~150x faster** |
| semantic | ~1.9 s | **266 ms** | **~7x faster** |
| ledger | not measured | **0.3 ms** | — |
| negative | not measured | **0.4 ms** | — |

`5 probes: 4 fast, 1 warm, 0 slow, 0 FADING | median 0.4 ms`

## What it means

**Most of the old gradient was network, not memory.** A keyed lookup is not inherently a 90 ms
operation — it is a sub-millisecond operation with 89 ms of network in front of it. Moving the tier
into the stack did not optimise the database; it deleted the distance.

This is the measured case for the in-can architecture, and it is stronger than the argument that
motivated it. The original claim was "local beats network-connected." The number is ~150x on the tier
an agent touches most often.

Two consequences worth acting on:

1. **The keyed tier is now cheap enough to use by default.** At 90 ms there was a real temptation to
   keep things in context rather than look them up. At 0.6 ms there is none — a lookup is cheaper
   than the reasoning required to decide whether to look it up.
2. **The semantic tier is now the only expensive one**, and it is the tier where an expensive answer
   is at least *appropriate*. The pathological case EXP-003 warned about — answering a lookup by
   semantic search — costs ~440x here rather than ~20x. The penalty for classifying badly went **up**,
   not down.

## The defect this run found in the instrument

The negative probe — a key that must not resolve, behaving perfectly — was scored **FADING**. The
bench had no way to express "this should not match," so correct behaviour was reported as decay.

That is worse than a cosmetic bug. FADING is the bench's only actionable verdict; an instrument that
raises it for healthy behaviour teaches its operator to ignore it, and then the one real rot goes
unnoticed among the false ones.

Fixed with a `negate` flag on `Probe`. Found by pointing the bench at its own author's stack, which
is the only reason it was found at all — reading the code did not reveal it.

## Limits

One host, one stack, one day. Absolute numbers are hardware-specific; **the ratios are the finding**.
Note also that EXP-003's numbers came from a different physical topology, not merely a different
configuration — this is a comparison of architectures, not a controlled A/B of one variable.
