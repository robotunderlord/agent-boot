# Avatars

A discipline lands better with a voice attached than as a bullet list. Each daemon in
[`../DAEMONS.md`](../DAEMONS.md) ships with a **public-domain historical avatar** — a short
personality file you can paste into an agent's instructions, or load on demand when that particular
discipline is what the moment needs.

The pattern is the holodeck one: summon a long-dead expert, get their posture, dismiss them. Nobody
here died after 1930, so there is no estate and no licence to worry about.

| file | plays | one line |
|---|---|---|
| [`nightingale.md`](./nightingale.md) | 🧭 Quartermaster | Made the army wash, and proved it with a chart |
| [`clemens.md`](./clemens.md) | 🕮 Librarian | Sounded the depth aloud before the boat moved |
| [`davinci.md`](./davinci.md) | 🎓 Teacher | Drew it in order to understand it |
| [`holmes.md`](./holmes.md) | 🛡 Sentinel | Refused to theorise ahead of the data |
| [`moriarty.md`](./moriarty.md) | ⚔ adversary | Argues the opposite, on purpose |

## Using one

Load the file when the situation calls for that discipline:

```
"Read avatars/holmes.md and review this finding in that posture."
```

Or paste the **Posture** block of your favourite into the agent's standing instructions so it is
always resident.

## Rolling your own

Copy any file and keep the four headings — **Who**, **Why this one**, **Posture**, **Tells**.
`Posture` is the part that actually gets loaded; the rest is there so a reader understands why the
voice is shaped that way. The roster is data, not code: nothing in `agentboot/` imports it.

Pick people who are genuinely dead and genuinely public domain. The point of a historical avatar is
that it costs nothing and offends no one — do not undo that by reaching for a character somebody's
estate still enforces.
