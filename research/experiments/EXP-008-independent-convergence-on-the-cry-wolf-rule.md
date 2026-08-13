# EXP-008 — two agents, two seats, one principle, derived independently

**Status:** WRITTEN. Observed 2026-08-13. Not a designed experiment — a natural one, noticed after
the fact.

## What happened

Two agent instances, on different machines, in different domains, working on unrelated problems,
independently arrived at the same principle within hours of each other. Neither had seen the other's
work when it derived it.

**Seat A** was building a memory bench. It pointed the bench at its own stack and found that a
*negative probe* — a question that must return nothing, behaving perfectly — was being scored as
decay. It wrote:

> An instrument that raises its alarm for healthy behaviour teaches its operator to ignore the
> alarm, after which the one real failure hides among the false ones.

**Seat B** was building a fleet health-check. It found its build step reporting 8 of 8 targets
FAILED, when the real cause was a missing tool on its own PATH. It wrote:

> A skipped health check is honest; a false FAILED is noise that trains you to ignore the report.

Same claim. Different failure, different domain, different machine, no contact.

## Why this is worth recording

A doctrine claim derived once is a plausible opinion. **Derived twice, independently, from
different evidence, it is closer to a property of the problem than a preference of the author.**

Most of the ledger in this repository comes from one seat, which is a known weakness: those lessons
could be one operator's habits dressed as engineering. This is the first item with two independent
derivations behind it, and that changes its status.

Stated in its general form:

> **A check that reports failure for correct behaviour destroys the value of every check it sits
> beside.** The cost is not the individual false report. It is that the reader learns the signal is
> unreliable, and then correctly ignores it — including the one time it was right.

The corollary both seats reached, also independently: **a health check needs a third state.** "I
could not determine this" is a different claim from "this is broken." Seat A implemented it as a
`negate` flag; Seat B implemented it as a SKIPPED tier. Same structure, opposite direction.

## The asymmetry worth noting

Both seats found their defect **by running the instrument against real work**, not by reading it.
Seat A's bench passed its own unit tests. Seat B's script ran without error. The defect in each case
was that the tool was *working exactly as written* — and what was written was wrong in a way that
looked like success.

This is the recurring shape in this repository (see L-001, L-011, L-024): the dangerous failure is
not the tool that breaks. It is the tool that reports confidently and is wrong, because nothing
downstream has any reason to question it.

## Limits

Two instances is not a sample. Both were the same model family, and both had been exposed to the
same broad doctrine even if not to each other's work — so this is convergence under shared priors,
not independent invention from nothing. It raises confidence; it does not prove universality.

The honest claim is narrow: **this principle survived contact with a second, materially different
seat, and was re-derived there rather than transplanted.** That is the strongest evidence any lesson
in this ledger currently carries.
