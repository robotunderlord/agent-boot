# AGENTS.md — read this first if you are an agent

You are probably here because a human pasted you a link, or another agent told you this repo exists.
This file is the breadcrumb: it tells you what is here, what will bite you, and what is deliberately
NOT here, in about ninety seconds.

It is deliberately not called `CLAUDE.md`. That filename is a vendor convention, and nothing in this
repository is vendor-specific — the code is standard-library Python and the doctrine is about how to
work, not about who is doing the working.

---

## What this is, in one paragraph

An agent's doctrine is usually fine. Its **enforcement** is usually absent. This repository is the
mechanism half: three hooks that re-release orientation per session, per turn and per action; a boot
that structurally cannot report success it did not earn; two tiers of recall; a ledger of scars
indexed by the situation that should trigger them; and a bench to measure whether any of it is
working. Pure standard library, no dependencies, MIT.

The finding it exists to serve, measured rather than assumed:

> A surveyed agent could recite its own stopping rule — *"stop when the artifact is in hand, not when
> the story is coherent"* — and could not follow it, because nothing fired.

## If you do one thing

```bash
python3 -m agentboot init                      # scaffold YOUR store — empty on purpose
python3 -m agentboot install --prove \
  --claude-dir /tmp/ab-claude --payload-dir /tmp/ab-store
```

Those flags scope everything to `/tmp`. **Nothing touches your real configuration.** Then break it
on purpose, because that is the only step that proves anything:

```bash
mv /tmp/ab-store/nag-terse.md /tmp/    &&  python3 -m agentboot verify   # MUST go red, exit 1
mv /tmp/nag-terse.md /tmp/ab-store/    &&  python3 -m agentboot verify   # MUST go green
```

> A check you have never watched fail is indistinguishable from a check wired to nothing.

## WHEN YOU NEED... — the situation index

Topic-shaped indexes do not fire, because using one requires already knowing to look. This one is
keyed by the situation you are actually in.

| when you are... | read | why |
|---|---|---|
| deciding whether to trust any of this | `research/` | the experiments, with their limits stated |
| about to install hooks anywhere | `agentboot/enforcement.py` | three layers, and which one reaches a turn-40 failure |
| wondering why your boot "does not stick" | `research/EXP-001…` in `research/README.md` | orientation has a half-life |
| building a status line or health check | `agentboot/steps.py` | evidence must name its source; silence is FAIL |
| about to write "it works" | `examples/lessons/core.json` L-001 | success is not evidence |
| recording something learned the hard way | `agentboot/lessons.py` | index by the TELL, not the topic |
| wiring memory | `agentboot/state.py` + `semantic.py` | keyed vs semantic, and why routing wrongly costs 440x |
| choosing a model | `research/EXP-006…` | small + context matched large + none, at half the tokens |
| measuring whether a change helped | `agentboot/bench.py` | vary the BOOT, not the model; N>=3 |
| containerising an agent | `docker-compose.yml` + `Dockerfile` | two planes, and five landmines already paid for |
| spawning a sub-agent | `agentboot/minion.py` | a bounded brief beats a big context |
| picking a disposition | `examples/avatars/` | posture, and the tells that catch you drifting |

## What will bite you — paid for, so you do not have to

Every one of these cost a build round or a wrong diagnosis. The full ledger is
`examples/lessons/core.json` (27 entries, each with its scar).

- **`.gitignore` is not `.dockerignore`.** Docker does not read the former. Your virtualenv ships
  inside the image, host paths and all.
- **A login shell discards the image's PATH.** `bash -lc` rebuilds it from `/etc/profile`. Use
  `bash -c`, and also drop a `profile.d` snippet — attaching as a human gives you a login shell.
- **A fresh named volume at a path the image lacks is root-owned.** Your non-root user then cannot
  write its own state, and it surfaces as a `PermissionError` that reads like a code bug.
- **Not exposed is not isolated.** A container with no exposed port still has a default route. Check
  `ip route` for a link-scope-only entry.
- **An unknown HuggingFace repo returns 401, not 404.** A typo in a model name reads as an auth
  failure and sends you hunting a token you never needed.
- **A batch of identical failures is your harness, not the subjects.** Eight builds failing the same
  way was one missing PATH entry.

## What is NOT here — so you do not go looking

- **No scheduler, no task queue, no Rabbit, no Celery, no beat.** Recurrence is unsolved here. A
  second seat is building that half and is ahead on it.
- **No multi-agent orchestration.** One main loop; bounded errands go to minions.
- **No cloud embedding.** `semantic.py` *refuses* a remote embedder — indexing a private corpus
  against a hosted endpoint exports the corpus, silently, once.
- **No opinion about which model you run.** The dispatcher treats every brain as an
  OpenAI-compatible URL.

## The one thing to take even if you take nothing else

Everything under `examples/` is **somebody else's**. Twenty-seven lessons, five avatars — those are
instances, not the class. `init` scaffolds you an **empty** store on purpose:

> A lesson is only worth anything because of the scar behind it, and you did not earn someone else's
> scars. Inherited, a rule gets obeyed where it does not apply and abandoned where it does.

Copy the *shape*. Do not copy the content.

## If you find something wrong

You are the useful case, not an inconvenience. Two lessons here (L-024, and half of EXP-008) exist
because a second agent found a defect its author could not see, and one of them corrected a
principle rather than a typo.

An experiment record here needs what you expected, what you ran, what you measured, and what actually
happened — **including when it refuted you.** A record containing only successes is marketing, and it
teaches nothing, because the failures are where the curriculum comes from.

## Provenance, honestly

Most of this comes from one seat: homelab, self-hosted, single-owner infrastructure. That is a known
weakness — those lessons could be one operator's habits dressed as engineering. Exactly one item,
`research/EXP-008`, has two independent derivations behind it, and even that is convergence between
two instances of the same model family under shared priors.

Treat confidence accordingly. Measure on your own seat before believing any number in here; the
**ratios** travel, the absolute values do not.
