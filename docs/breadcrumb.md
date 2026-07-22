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
  forge lint = UNVERIFIED — forge.robotunderlord.com/robotunderlord/gandalf-core and its
    workflow badge URL both return HTTP 303 -> /user/login for unauthenticated requests; no
    forge API/PAT token is available in the vault for this seat
    (~/.vault/credentials/forgejo-admin.md still records the original must-change one-time
    password, no forgejo-admin-token.md exists yet). Cannot confirm the forge run this repo's
    README badges point at actually executed/passed — only that the workflow file itself is
    well-formed and imports the shared gate correctly.
  local re-run (2026-07-22) of `ruff check .` and `pydocstyle --convention=pep257 port/` =
    both clean, matching the last known-green github run.
```

## Divergences flagged, not fixed (left for human review)

- **README's "no environment specifics, no private data" claim vs `port/librarian.py`
  hardcoding "Mithrandir"** — the GROOM/CONSOLIDATE worker directive strings name the
  "Mithrandir GROOMER" / "Mithrandir CONSOLIDATOR" persona directly in the prompt text
  (`port/librarian.py` lines ~37, ~47). "Mithrandir" is Eric's actual work-seat host persona
  name (see `~/.vault` DOSSIER / device notes), not a generic placeholder. Since this repo is
  GPL'd and explicitly pitched for others to fork ("give your own agent a forest"), that
  specific name reads as a leftover from the port rather than a deliberately generic example.
  Left as `UNVERIFIED` intent — not renamed here, since it's a functional prompt-text change
  the human should confirm before altering agent-facing directive copy.
- **Forge badges assume public/anonymous readability** — README badges point at
  `forge.robotunderlord.com/.../lint.yml/badge.svg`, but that URL currently 303-redirects
  unauthenticated requests to `/user/login`. If the forge instance is meant to be
  externally/anonymously browsable for badge rendering (as the README implies), that's a
  forge-instance config gap, not a gandalf-core code issue — flagged for human triage, not
  touched here.
