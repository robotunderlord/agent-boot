# agent-boot

**Doctrine is not the scarce thing. Enforcement is.**

Three hooks and a gated boot that make an AI coding agent obey the rules it already knows.

Pure standard library — no dependencies, no build step, no wheels. Clone it and run it, on amd64 or
arm64, Linux or macOS. The agent can install it for itself.

```bash
git clone https://github.com/robotunderlord/agent-boot
cd agent-boot
python3 -m agentboot init            # scaffold YOUR store - empty on purpose
python3 -m agentboot install --prove # wire the hooks, then prove they fire
```

---

## This is a class, not an inheritance

Everything under `examples/` is somebody else's. Twelve lessons, five avatars, a set of nag
templates — those are *instances*. The package is the **class**: the ability to hold lessons,
personas and tools, and the discipline for writing good ones.

`init` deliberately scaffolds you an **empty** ledger and wardrobe with the shape documented and no
content. That is not laziness, it is the point:

> **A lesson is only worth anything because of the scar behind it, and you did not earn someone
> else's scars.** Inherited, a rule gets obeyed where it does not apply and abandoned where it does —
> because the reason was never yours.

Copy the shape from `examples/`. Do not copy the content. `Ledger.load()` and `Wardrobe.load()`
default to *your* `~/.agentboot/`, never to this repository's.

Same rule stated in one line: **teach the resource, not the object.** What transfers to a situation
you have never seen is knowing how to find out. A specific answer is inert and rots.

---

## The problem

Agents get their rules in a `CLAUDE.md` and break them anyway. The usual response is to write the
rules down again, harder. That does not work, and here is why:

> **Boot is a hormone. Orientation has a HALF-LIFE, and must be RE-RELEASED — not run once at wake.**

An agent that reads its instructions at turn 0 has effectively forgotten them by turn 40. The
characteristic failure — *acting confident before having looked* — happens in the middle of a long
session, nowhere near the boot.

This was measured, not assumed. A working agent instance was surveyed with a structured interview,
and the result was not what anyone expected: **its doctrine was already complete.** Asked what its
stopping rule should be, it answered

> *"stop when the artifact is in hand, not when the story is coherent"*

— an accurate, independently-derived statement of the exact discipline it kept violating. It could
recite the rule and could not follow it, because **nothing fired.**

## The three layers

An instruction is not a mechanism. These are mechanisms.

| layer | hook | fires | catches |
|---|---|---|---|
| **orientation** | `SessionStart` | every session, **including resume and compact** | starting blank; not reading your own notes |
| **re-release** | `UserPromptSubmit` | **every message** | drift over a long session |
| **point-of-action** | `PreToolUse` (`Bash\|Edit\|Write`) | **before every mutation** | acting before looking |

The third is the one that earns its keep, and the one everybody skips. The fix people reach for
first is "a boot gate with teeth" — but a boot gate fires once, at turn 0, and cannot reach a
turn-40 failure. `PreToolUse` fires in the half-second *before* the agent acts.

`SessionEnd` is a backstop only: **it does not fire on SIGKILL, and a reboot always SIGKILLs.**
Anything deferred to "end of session" is lost exactly when it matters most. Write continuously.

## Then make it fail

The installer verifies by **executing** each hook command and grepping its output for a marker, so
"configured" is never reported as "working". Finish the job yourself:

```bash
mv ~/.agentboot/nag-terse.md /tmp/
python3 -m agentboot verify      # MUST print [ !! ] and exit 1
mv /tmp/nag-terse.md ~/.agentboot/
python3 -m agentboot verify      # MUST go green again
```

> **A check you have never watched fail is indistinguishable from a check wired to nothing.**

`install --prove` goes further: every check ships a `failing_variant()`, and `--prove` runs it to
confirm the check is *capable* of failing. A check whose failing variant passes is reported as
broken, not healthy.

## A boot that cannot lie

The framework is small and its one real idea is structural: **a step reports success by returning
evidence that names its source — never by asserting it.**

```python
from agentboot import Boot, Tier, FileStep, CommandStep

Boot([
    Tier(1, "enablers").add(
        FileStep("Credentials", "~/.config/creds", critical=True),
        CommandStep("Registry", "curl -sf https://registry/health", marker='"ok"', critical=True),
    ),
    Tier(2, "memories", gated=True).add(...),   # will NOT run if a critical step is red
]).run()
```

- `Evidence` refuses to exist without a `source`. Unsourced evidence is an assertion in a lab coat.
- A step that returns nothing is recorded **FAIL**, not pass — silence is the signature of a check
  wired to nothing.
- `CommandStep` believes the **marker in the output**, never the exit code. Exit 0 is not evidence; a
  fallback can answer in place of the thing you meant to probe.
- A **gated** tier does not run when any critical step is red. The gate is a hard stop, not a warning.

That last one is the point. The failure it prevents is *reasoning confidently from a memory of a
fact instead of the fact* — which is what a long agent session reliably produces.

## The forest — four daemons, and who plays them

The disciplines are in **[`DAEMONS.md`](./DAEMONS.md)**. Each is a role, and each ships with a
public-domain **avatar** in [`examples/avatars/`](./examples/avatars) — a personality file you can load so the
discipline arrives with a voice attached instead of as a bullet list.

| Daemon | Job | Avatar |
|---|---|---|
| 🧭 **Quartermaster** | Boot self-optimization; loads the index, not the bulk | **Florence Nightingale** — rounds, checklists, and the statistics that proved filth outkilled bullets |
| 🕮 **Librarian** | Context logrotation, indexing, hand-off before the wall | **Samuel Clemens** — riverboat pilot and compulsive notebook-keeper |
| 🎓 **Teacher** | Turns work into durable skill; name the lesson, give the why | **Leonardo da Vinci** — the notebooks, the maker's habit of drawing it to understand it |
| 🛡 **Skeptic** | Adversarial verification; distrust confident-but-wrong | **Sherlock Holmes** — *"a capital mistake to theorize before one has data"* |
| ⚔ *(optional)* | Red-team a finding you want to believe | **Professor Moriarty** — argues the opposite on purpose |

All five are public domain - and all five are EXAMPLES. Pick your own; the roster is data,
not code, and it lives in your store, not in this repo.

> The name **Mark Twain** was a leadsman's call — *two fathoms, safe water* — sounded aloud before the
> boat was allowed to move. A measurement taken before it is safe to proceed. That is this whole
> repository in three words.

## Make your memory index SITUATION-shaped

The most common cause of an agent re-deriving the same fact is not a missing note. It is a note that
never **fires**. An index keyed by topic does not trigger when a situation arises:

```
BAD    project_naming_conventions - naming conventions for the build

GOOD   about to change a name/tag in a shared pipeline -> read the OLD WORKING BUILD first
       -> the shared pipeline is frozen; the fix belongs in the caller [project_naming_conventions]
```

Same file, same content, different shape. One is documentation. The other is a reflex.

## What gets installed

| file | role |
|---|---|
| `~/.agentboot/nag.md` | per-turn doctrine — **edit it**, it is a template |
| `~/.agentboot/nag-terse.md` | per-action doctrine — **edit it**, it is a template |
| `~/.agentboot/tattoo.md` | wake signal + running-thread `[STATE]` block |

All three are **yours**. They ship with universal rules plus a marked `LOCAL RULES` block for what
is specific to your shop. The installer never overwrites them once they exist, so your edits survive
upgrades and your local rules never travel back upstream.

The installer **merges** into an existing `settings.json` — foreign hooks and settings keys are
preserved, and the file is backed up before every write.

## Principles, condensed

- **Artifact before assertion.** You do not know it until you have read it *this session*.
  "Plausible" is not "checked".
- **Success is not evidence.** A green light wired to nothing looks exactly like a green light.
- **An instruction is not a mechanism.** When a rule keeps getting broken, do not rewrite the rule —
  ask which *layer* would have caught it, and wire that layer.
- **If you re-derived it, you failed to record it.** Write the lesson when it lands, not at the end.
- **Injection beats instruction.** A file already in context cannot be skipped.
- **A hesitant wrong answer costs a minute. A confident one costs the evening.**

## Commands

```
python3 -m agentboot init                # scaffold YOUR empty ledger + wardrobe
python3 -m agentboot install [--prove]   # wire the layers, verify by executing them
python3 -m agentboot verify              # check only, change nothing
python3 -m agentboot demo                # run a boot over the installed payloads
python3 -m agentboot uninstall           # remove only what this installed
```

`--claude-dir` / `--payload-dir`, or `CLAUDE_DIR` / `AGENTBOOT_DIR`, override the defaults.

## Also here

[`port/`](./port) holds two standalone daemon tools ported from a live agent seat — `librarian.py`
(context grooming and hand-off) and `owui_sync.py` (Open WebUI archive). Every environment-specific
value is an environment variable; see each module's docstring.

## License

MIT — see [`LICENSE`](./LICENSE).

## Origin

Built by **[RobotUnderlord](https://github.com/robotunderlord)** while running a persistent agent
across long, multi-session infrastructure work — and then rebuilt properly after surveying a second
agent instance and discovering the problem was never the doctrine.

Deliberately generic: no environment specifics, no private data. Fork it, tune it, give your own
agent a forest.
