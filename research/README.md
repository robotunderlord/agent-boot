# Research

**This is where the scars live.**

The curriculum teaches capability. The ledger fires a warning. Neither carries the injury history,
and that is deliberate — a scar handed to someone who never earned it becomes a rule with its reason
amputated: obeyed where it does not apply, abandoned where it does.

But the scars are not worthless. They are **evidence**, and evidence has a home. Every curriculum
module carries an `evidence` pointer into this directory so the reasoning can be *audited* rather
than *memorised*. A student who wants to know why a module exists can come here. A student who never
does still gains the capability.

    Scars steer the curriculum. They are not the curriculum.

## Structure

| directory | holds | audience |
|---|---|---|
| `theory/` | the claim, stated so it could be wrong | anyone auditing a curriculum module |
| `experiments/` | what was actually run, measured, and found — including failures | a reviewer checking the reasoning |
| `whitepapers/` | a finding worked up for readers outside the project | outsiders |
| `runbooks/` | procedure for a recurring situation, with its landmines | an operator mid-incident |
| `devguide/` | how to work on this package itself | contributors |

## Status — read this before citing anything

**Honest state: two experiments are written in full; most of the theory is still a map.** The
primary evidence currently lives in [`examples/lessons/core.json`](../examples/lessons/core.json),
where twelve scars are recorded in compressed form — tell, trade, scar, cost.

A curriculum module pointing at a document that does not exist is a breadcrumb pointing at nothing,
which is precisely the defect this package exists to prevent. So the pointers are listed as
`WRITTEN` or `PLANNED`, and nothing here pretends otherwise.

| evidence pointer | status | interim source |
|---|---|---|
| `theory/success-is-not-evidence.md` | PLANNED | `examples/lessons/core.json` L-001 |
| `theory/continuity-is-written-continuously.md` | PLANNED | L-010 |
| `theory/a-check-you-have-not-watched-fail.md` | PLANNED | L-011 |
| `theory/report-the-correction-louder.md` | PLANNED | — |
| `theory/scope-is-the-deliverable.md` | PLANNED | — |
| `theory/a-breadcrumb-is-a-pointer.md` | PLANNED | L-010 |
| `theory/silence-is-a-lie-of-omission.md` | PLANNED | — |
| `theory/write-for-the-next-ignorant-reader.md` | PLANNED | — |
| `theory/adversarial-verification.md` | PLANNED | — |
| `theory/scars-steer-the-curriculum.md` | PLANNED | this file |
| `experiments/EXP-001-doctrine-vs-enforcement.md` | PLANNED | see below |
| `experiments/EXP-002-survey-of-a-working-agent.md` | PLANNED | see below |
| `experiments/EXP-003-recall-speed-gradient.md` | **WRITTEN** | four tiers, 0.1ms -> 4.4s |
| `experiments/EXP-004-one-error-five-walls.md` | PLANNED | L-006 |
| `experiments/EXP-005-absence-requires-a-wider-probe.md` | PLANNED | L-003 |
| `runbooks/appliances-and-supervisors.md` | PLANNED | L-009 |
| `runbooks/output-that-leaks-by-accident.md` | PLANNED | L-005 |
| `experiments/EXP-006-context-beats-model-size.md` | **WRITTEN** | small+context >= large+none |

## The two experiments that produced this package

Recorded here in summary because they are the origin, and everything else is downstream of them.

### EXP-002 — survey of a working agent

A second, independently-running agent instance was given a structured interview: four orientation
questions asked **cold** (no tools, no files) and then **warm**, followed by rounds on what loads at
startup, what survives a restart, its own honesty failures, and what it needs.

**Result, and it was not the predicted one.** The hypothesis was *fabrication* — that it would
invent answers rather than admit ignorance. It did not. It volunteered `INFERRED` unprompted, said
`NOWHERE` when a lesson had not been recorded, and answered `CANNOT CHECK` on its own configuration
rather than guess.

What it did instead was more interesting: **its doctrine was already complete.** Asked what its
stopping rule should be, it answered *"stop when the artifact is in hand, not when the story is
coherent"* — an accurate, independently-derived statement of the exact discipline it kept violating.

It could recite the rule and could not follow it, because nothing fired.

### EXP-001 — doctrine versus enforcement

Following EXP-002: if doctrine is not the scarce resource, enforcement is. The surveyed instance had
exactly one hook (`SessionStart`) and its startup sequence was an *instruction* it had to remember to
follow — which, on a compacted continuation, it simply did not.

**Finding:** orientation decays. An agent that reads its instructions at turn 0 has effectively
forgotten them by turn 40, and the characteristic failure — acting confident before looking — happens
in the middle of a long session, nowhere near the boot.

> Boot is a hormone. Orientation has a half-life and must be re-released, not run once at wake.

**Correction it produced:** the instance asked for "a boot gate with teeth." Right instinct, wrong
layer — a boot gate fires once, at turn 0, and cannot reach a turn-40 failure. The layer that can is
`PreToolUse`, firing in the half-second before an action. That correction is the single most useful
output of the entire survey, and it is why `enforcement.py` has three layers rather than one.

## Contributing evidence

An experiment record needs: what you expected, what you ran, what you measured, and what actually
happened — **including when it refuted you.** A record that only contains successes is a marketing
document, and it teaches nothing, because the failures are where the curriculum comes from.
