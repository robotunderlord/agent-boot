# EXP-006 — context beats model size

**Status:** WRITTEN. Run 2026-07-29. A/B of one grooming errand across models and framings.

## The question

For well-scoped work, does a bigger model beat a smaller one — or does the right *context* beat
both?

This is not idle. It decides whether an always-on agent needs a frontier model resident, or whether
a small one with good recall is genuinely sufficient. The whole cost profile of a persistent agent
turns on the answer.

## Method

The same errand, run three ways:

| run | model | primed with an operating brief? |
|---|---|---|
| 1 | large | **no** |
| 2 | large | yes |
| 3 | small | yes |

Same task, same tools, same success criteria.

## Result

**Run 1 — the large, unprimed model cowboyed the errand and had to be stopped.** It did not read
before acting; it started changing things. Raw capability did not produce care.

**Runs 2 and 3 were both competent and read-first.** And the important one:

> The small primed model **matched or beat** the large unprimed one, at **under half the tokens**.

## What it means

**For well-scoped work, a cheap model with the right boot context outperforms a bigger model
without it.** Capability is not the binding constraint; orientation is.

This is the empirical justification for a three-tier dispatcher (`agentboot/dispatch.py`):

- if the answer is in recall, no model is needed at all
- if the turn is conversational, a small resident model with memory behind it is *not a compromise* —
  it is the measured-correct choice
- escalation is for work where the small brain genuinely underperforms, which is a narrower set than
  intuition suggests

An architecture that routes every turn to the largest available model is not buying quality. It is
paying for capability that the *context*, not the parameters, was already supplying.

## The caution attached to it

The same night produced a second finding worth keeping beside this one: automated QC agents
generated roughly **80% false positives**. Real findings existed among them, but severity triage was
not automatic.

**Consequence: never let an automated finding drive an automatic fix.** A verification gate is
mandatory. A cheap model with good context is competent at *scoped* work — that is what was
measured — and this experiment says nothing about letting it act unsupervised on unscoped work.

## Limits

One errand, one night, one operator's task shape. "Well-scoped" is doing real load-bearing work in
the claim and is not defined rigorously here. Treat as a strong directional finding, not a
benchmark.
