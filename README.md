# 🧙 Gandalf Core

<!-- Service/lib-repo badge row. github-hosted → action badges point at github. lint = the
     central validate gate (imported via .forgejo/workflows/lint.yml, python: true → ruff +
     pydocstyle); the github lint.yml mirrors it for immediate push status. No docsite, no
     build artifact, no Argo CD — so no docs/build/argocd badge. Host-only badges
     (harden/join/netbox/vault/librenms/graylog) do NOT apply — this is a framework/lib repo. -->
[![lint](https://github.com/robotunderlord/gandalf-core/actions/workflows/lint.yml/badge.svg)](https://github.com/robotunderlord/gandalf-core/actions/workflows/lint.yml)
![ruff](https://github.com/robotunderlord/gandalf-core/actions/workflows/lint.yml/badge.svg)
![pydocstyle](https://github.com/robotunderlord/gandalf-core/actions/workflows/lint.yml/badge.svg)
![version](https://img.shields.io/badge/version-0.1.0-blue)

A portable operating framework for long-running AI agent instances (Claude Code and
kin) — a small **forest of always-on background daemons** plus the engineering
disciplines that keep an agent fast, honest, and continuous across sessions.

It is not a tool or a library. It is a **posture**: a drop-in instruction set (a
`CLAUDE.md` section, a system prompt, or a boot directive) that wakes four standing
daemons and a handful of operating rules at the start of every session.

## The forest — four daemons

| Daemon | Job |
|---|---|
| 🧭 **Quartermaster** | Boot self-optimization — tunes startup speed × recall accuracy; loads the index + breadcrumbs, not the bulk. |
| 🕮 **Librarian** | Context logrotation, indexing & paging — keeps the working context lean and everything else recallable; trims cold detail out, backfills breadcrumbs, and hands off *before* a hard context wall. |
| 🎓 **Teacher** | Turns work into durable skill — name the lesson, give the *why*. |
| 🛡 **Sentinel** | Adversarial verification — distrust confident-but-wrong; root-cause, never paper over. |

The full specification, including the **brick-wall protocol** and the **Resume
Brief** hand-off artifact, is in **[`DAEMONS.md`](./DAEMONS.md)**.

## Why

Long-running agents fail in predictable ways: they lose the thread across sessions,
they trust their own confident-but-wrong output, they crash into a context wall and
get force-compacted into a lossy summary with no way back, and they re-learn the
same lessons forever. The forest is four disciplines that each close one of those
holes — and, crucially, gives the two load-bearing ones (Librarian, Quartermaster)
a **real mechanism** instead of leaving them as good intentions.

## Use it

1. Drop [`DAEMONS.md`](./DAEMONS.md) into your agent's always-on instructions.
2. Tune the brick-wall threshold to your model's **real** context ceiling.
3. Give the substrate daemons teeth: trigger the Librarian's hand-off on the *actual*
   context meter (not a felt sense), and back the Quartermaster with a real benchmark.

## The one non-negotiable

A model cannot reliably sense its own context depth from the inside. On a hard
context ceiling, a hand-off that fires on a *feeling* fires late — and late is a lost
session. **Trigger on the number.**

## Versioning

Semver, fleet standard: **`0.x.y` = pre-production**, bumped to **`1.0.0` when it goes to
production**. The current version is the canonical `[project].version` in
[`pyproject.toml`](./pyproject.toml) — today **`0.1.0`**.

## Lint / CI

Linting is the shared **`validate`** reusable gate (yamllint + ruff + pydocstyle + gitleaks),
imported — never re-implemented — by [`.forgejo/workflows/lint.yml`](./.forgejo/workflows/lint.yml)
with `python: true`. A github-hosted mirror ([`.github/workflows/lint.yml`](./.github/workflows/lint.yml))
runs the same ruff + pydocstyle steps so the badges stay green on the github home. Run it locally:

```sh
python3 -m venv .venv && .venv/bin/pip install ruff pydocstyle
.venv/bin/ruff check .
.venv/bin/pydocstyle --convention=pep257 port/
```

## License

Released under the GNU General Public License — see [`LICENSE`](./LICENSE).

## Origin

Distilled from running a persistent agent across long, multi-session engineering
work. The framework is deliberately **generic** — it carries no environment
specifics, no private data. Fork it, tune it, give your own agent a forest.
