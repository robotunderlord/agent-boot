# EXP-009 — a Python boot is not a little faster than a markdown boot, it is a different shape

**Status:** WRITTEN. Measured 2026-08-13 on minas-morgul, median of 20 (shell) / 200 (in-process) runs.

## The question

The boot pattern has always been markdown read by a hook: a set of doctrine files, `cat`'d into
context at session start and on every turn. The instruction was to move the pattern to Python
"because it's faster."

Faster is a claim. How much, and — more usefully — does the advantage hold as the doctrine grows?

## Method

Two implementations of the same eight-step boot, same doctrine content (~40 lines per step):

- **shell-out** — eight `subprocess.run(["cat", file])` calls, one per doctrine file. This is the
  existing pattern.
- **in-process** — `CommonTongue.brief()` plus a full reflex-arc fire over the situation. Pure
  Python objects, no subprocess, no file read per turn.

Warmed three rounds first. Median reported, because the mean on subprocess work is dragged by
scheduler noise and the median is what a turn actually experiences.

## Result

| boot | median | per step |
|---|---|---|
| shell-out, 8 × `cat` | **5.902 ms** | 0.738 ms |
| in-process Python | **0.027 ms** | ~0.003 ms |

**217x faster in-process.**

## What it means

The ratio is not the finding. **The shape is.**

The 0.738 ms per step is *process spawn*, and it is fixed — it does not depend on how much doctrine
the file holds, and it does not get cheaper with practice. So the markdown boot costs
`0.74 ms × (number of doctrine files)`, forever, on every single turn that fires it.

That is a structural penalty on writing more doctrine. Every lesson learned, every trade recorded,
every instinct added makes the boot measurably slower — so the pattern quietly charges you for
getting better, and the cheapest boot is the one that knows nothing. A design whose incentives point
away from learning is the wrong design regardless of how fast it is today.

In-process, the same growth is free at this resolution. Eight steps cost 0.027 ms; the cost is
matching, not spawning, and matching over a few hundred lessons stays under a millisecond.

## The second finding, which was not the question

Moving to Python changed what a boot step *can be*, and that turned out to matter more than the
timing. A `cat` can only emit text. A Python step can **run**:

- it can probe live state and attach the evidence, instead of advising someone to go and look
- it can refuse, and refuse *closed* when its own check fails to complete
- it can be tested, and prove it is able to fail (`failing_variant()`)

The 217x is a nice number. The reason the pattern actually had to move is that an advisory boot
depends on the reader complying with it, and a executable one does not.

## Limits

- One host, one filesystem, warm page cache. A cold cache widens the gap; it does not narrow it.
- `cat` is close to the cheapest possible subprocess. A boot that shells out to `python3`, `jq` or
  `curl` per step pays considerably more than 0.74 ms, so this is the *favourable* case for the old
  pattern.
- The in-process figure excludes the one-time import of `agentboot` (~15 ms), which is paid once per
  process rather than once per turn. For a resident agent that is the correct accounting; for a
  one-shot CLI invocation it is not, and the two patterns are much closer there.
