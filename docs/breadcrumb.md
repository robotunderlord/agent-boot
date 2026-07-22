# Breadcrumb — gandalf-core

Narvi as-built reconcile pass (Vikunja #1078). Three-way reconcile method: docs (claim) vs
code (intent) vs live state (truth). Every tag below is one of `live` / `intended-not-yet-live`
/ `stale` / `UNVERIFIED` — never asserted from memory.

```yaml
object: gandalf-core — portable operating framework (posture/instruction-set + two ported
  Python CLI tools), GPLv3, framework/library repo — NOT a deployed service or host  [live]
netbox: none — confirmed no inventory entry (NetBox journal-entry search for "gandalf-core"
  returned 0 results, 2026-07-22). Expected: this repo has no VIP/device/host of its own  [live]
librenms: none — not a monitored host or service, nothing to poll  [live]
vault: none — no ~/.vault/credentials/ entry for this repo; no secrets are committed in-repo
  (port/owui_sync.py requires OWUI_KEY via env only, never hardcoded; manual read + local
  ruff/pydocstyle both clean, gitleaks is part of the forge `validate` gate)  [live]
redbook: ~/.vault/11-projects/gandalf-common-fellowship-architecture.md (related "one image,
  three roles" framing — a sibling concept, not this repo); ~/.vault/11-projects/gandalf-os.md
  (productization spec that references a similar daemon posture); repo docs (this file +
  README.md + DAEMONS.md) are meant to be picked up by the next `redbook.py ingest` full
  rebuild so the loop closes both ways — query `redbook.py query "gandalf-core"` after that
  ingest to confirm this file surfaces  [intended-not-yet-live: not yet re-ingested as of
  2026-07-22]
deploys: nowhere. This is a *posture* — a CLAUDE.md section / system-prompt drop-in
  (DAEMONS.md) — not a running process. port/librarian.py and port/owui_sync.py are standalone
  CLI tools an agent seat invokes on demand (`claude -p` workers + Open WebUI archive calls);
  nothing in this repo runs as a standing daemon by itself  [live, per README + code reading]
host_or_node: N/A — no VIP, no k8s workload. Confirmed: `kubectl --kubeconfig
  ~/.kube/theshire.yaml get all -A` has zero resources named gandalf-core (2026-07-22,
  read-only check)  [live]
related_repos: gandalf-common (fellowship "one image, three roles" architecture — a distinct,
  larger framework this repo's posture-only approach does not attempt to replace);
  gandalf-voice-agent (separate two-tier voice daemon, unrelated to this repo's four-daemon
  posture); forge-workflows (supplies the central `validate` reusable this repo's
  `.forgejo/workflows/lint.yml` imports — could not fetch its content for this reconcile,
  robotunderlord/forge-workflows is not mirrored to github, so its contents are UNVERIFIED
  from this seat)
as_built_verified: 2026-07-22
ci_status: |
  github(origin) lint = SUCCESS, verified live via GitHub Actions API
    (run completed 2026-07-18T02:35:29Z, workflow .github/workflows/lint.yml, branch main).
  forge lint = STALE / has never actually run — corrected finding, see divergence #1 below.
    The forge repo is real (found via API search: `gandalf/gandalf-core`, private, owner
    "gandalf"), but its `main` branch is still pinned at the FIRST commit (c226407) — it has
    never received the two follow-up commits that added `.forgejo/workflows/lint.yml`,
    `pyproject.toml`, or the `.github/` mirror. `git ls-tree forge/main` confirms
    `.forgejo/workflows/lint.yml` does not exist on forge at all, so the forge lint gate this
    repo's README badges claim as the canonical CI source has never fired, not even once.
    This branch's push carries the missing commits to forge for the first time (as
    `narvi/asbuilt-2026-07-21`, not merged to forge main).
  local re-run (2026-07-22) of `ruff check .` and `pydocstyle --convention=pep257 port/` =
    both clean, matching the last known-green github run.
```

## Divergences flagged, not fixed (left for human review)

1. **Forge is not actually the CI home for this repo yet — it's 2 commits stale and has
   never run lint.** `git fetch forge && git log forge/main` shows forge's `main` is still at
   the very first commit; `.forgejo/workflows/lint.yml`, `pyproject.toml`, and the ruff/
   pydocstyle setup only ever reached `origin` (github). README's claim "Forge is the CI
   home: that forge run backs the lint/ruff/pydocstyle badges" is therefore **stale** — no
   forge run has ever existed to back them. Separately, the local `.git/config` `forge`
   remote was pointing at `robotunderlord/gandalf-core` (404 on forge, "push to create not
   enabled for organizations"); the repo actually exists at `gandalf/gandalf-core` (private,
   owned by the personal `gandalf` forge account, not the `robotunderlord` org every other
   estate repo uses). Both the local remote URL and the README badge URLs are corrected in
   this PR to point at the real path. Whether gandalf-core should be transferred into the
   `robotunderlord` org (matching estate convention) and whether forge `main` should be
   fast-forwarded to pick up the missing commits are left as **UNVERIFIED / needs_human** —
   not done here (org transfer + a direct push to someone else's `main` are exactly the kind
   of production-risk/destructive calls this pass is told to leave for a human, and this repo
   is private so a fast-forward push has no anonymous-badge urgency behind it).
2. **README's "no environment specifics, no private data" claim vs `port/librarian.py`
   hardcoding "Mithrandir"** — the GROOM/CONSOLIDATE worker directive strings name the
   "Mithrandir GROOMER" / "Mithrandir CONSOLIDATOR" persona directly in the prompt text
   (`port/librarian.py` lines ~37, ~47). "Mithrandir" is Eric's actual work-seat host persona
   name (see `~/.vault` DOSSIER / device notes), not a generic placeholder. Since this repo is
   GPL'd and explicitly pitched for others to fork ("give your own agent a forest"), that
   specific name reads as a leftover from the port rather than a deliberately generic example.
   Left as `UNVERIFIED` intent — not renamed here, since it's a functional prompt-text change
   the human should confirm before altering agent-facing directive copy.
3. **Even with the badge URL fixed, the badges still won't render for outside viewers** —
   the forge repo is `private`, so `.../badge.svg` 303-redirects to `/user/login` regardless
   of namespace. If these badges are meant to be visible on the public github mirror's
   README (the likely intent, since github is described as "where gandalf-core lives
   primarily"), the forge repo would need to be made public, or the badges would need to
   track the github Actions run instead. Left for human decision, not changed here.
