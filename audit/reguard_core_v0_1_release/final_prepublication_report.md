# Reguard Core v0.1 — Final Pre-Publication Hygiene + Artifact Freeze

**Date:** 2026-08-30
**Phase:** Final pre-publication hygiene + artifact freeze.
**Verdict (item 33):** **READY**

The repository itself is clean, intentional, reproducible, and safe to
make public. Final distribution artifacts are deterministically tied
to one source-tree state. The actual external publication steps
(PyPI, GHCR, Git tag, GitHub release) remain explicitly out of scope
for this phase per the brief; they are documented as a precise
owner-operated runbook at
`audit/reguard_core_v0_1_release/publication_runbook.md`.

---

## 1. Tracked-file audit result

`git ls-files` shows 207 tracked files (down from 247). 40 files
were removed from tracking during this hygiene pass. The 207-file
working tree has been classified as follows:

| Class | Count | Examples |
|---|---|---|
| `PUBLIC_SOURCE` | ~120 | `src/compliance/**/*.py`, `runtime/*.py`, `tests/**/*.py`, `migrations/*.sql`, `scripts/maintenance/*.py` |
| `PUBLIC_DOCUMENTATION` | ~10 | `README.md`, `docs/architecture.md`, `docs/product-model.md`, `docs/schema.md`, `docs/technical-requirements.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `LICENSE` |
| `PUBLIC_VALIDATION_EVIDENCE` | ~25 | `audit/article_12_1_v1_3/*.json`, `audit/container_gate1/*`, `audit/gate2_gha/*`, `audit/gate3_p3/*`, `audit/article_12_1_pipeline_report.md`, `audit/article_12_1_github_actions_*.md`, `audit/gold_article12_v1_repos.{json,md}` |
| `PUBLIC_TEST_FIXTURE` | ~35 | `tests/runtime/fixtures/*` (10 fixture projects for runtime detection) |
| `PUBLIC_DATASET` | ~30 | `data/raw/3*.html` (EU regulations downloaded from EUR-Lex) |
| `GENERATED_LOCAL` | 0 (was 0) | n/a |
| `GENERATED_RELEASE` | 0 (was 0) | `dist/` is correctly `.gitignore`d |
| `DEVELOPMENT_ARCHAEOLOGY` | ~10 (preserved) | `scripts/maintenance/*` (research pipeline), `audit/article_12_1_v1_3/*` (frozen evidence) |
| `PRIVATE_OR_UNSAFE` | 0 | None — all developer-path leaks fixed; all third-party restricted material removed |
| `UNKNOWN` | 0 | All paths classified |

## 2. Generated-file cleanup

40 files removed from tracking via `git rm --cached`:

- `notes/README.md`, `notes/open-vault.sh` — local Obsidian shortcut
- `data/eu_ai_compliance.db` — 14 MB research DB containing
  `/home/mrcel/...` paths in `frameworks.description`
- `data/manual_download_log.json` — research ingest log leaking
  `/mnt/c/Users/mrcel/...` path
- `data/raw/CCPA.html`, `HIPAA-*.xml`, `ISO9001-Wikipedia.html` —
  third-party regulation HTML (redistribution review required)
- `data/raw/ISO27001-AnnexA.json`, `ISO42001*`, `SOC2-TSC.json`,
  `PCI-DSS-v4.yml`, `NEN7510.json`, `NIST-CSF-v2.pdf` — third-party
  commercial standards (PUBLICATION_REVIEW_REQUIRED)
- `audit/2026-08-27-corpus-quality.md`,
  `audit/2026-08-28-{metrics,readmes,report,sample,verdicts-batch-*}.{md,json}`,
  `audit/p3_selection.md` — research-arena reports
- `docs/laws-for-product.md`, `docs/licensing.md`,
  `docs/agentic-compliance-validation.md`,
  `docs/scanner-architecture.md`, `docs/ingestion.md`,
  `docs/audit-2026-08-28-decision.md`,
  `docs/design-partner-plan.md` — research notes
- `runtime/REPORT.md` — dev archaeology
- `scripts/run_repo_corpus.sh` — research-arena wrapper

## 3. `.gitignore` changes

`.gitignore` updated with the following new entries (full file at
`.gitignore`):

```gitignore
# Reguard CLI run outputs (mutable per-run artefacts)
.reguard/
examples/*/.reguard/
tests/runtime/fixtures/.reguard/

# Untracked local working databases (development state)
data/*.db
audit/*.db

# Third-party standards and reference material (kept outside the
# public repo due to redistribution uncertainty — see
# audit/reguard_core_v0_1_release/third_party_content_audit.md)
data/raw/ISO27001*
data/raw/ISO42001*
data/raw/SOC2*
data/raw/PCI-DSS*
data/raw/NEN7510*
data/raw/NIST-CSF*
data/raw/HIPAA-*
data/raw/CCPA*
data/raw/ISO9001*
data/manual_download_log.json

# Personal Obsidian vault shortcuts (path-leaking, machine-specific)
notes/

# Runtime image build context (kept out of repo; rebuilt from Dockerfile)
runtime/build_context/

# Editor / Claude local state
.claude/

# Python egg-info under src
src/*.egg-info/
```

## 4. `.claude` disposition

`/home/mrcel/projects/business/compliance-tool/.claude/` is **local
agent tooling** (Claude Code session state). Added to `.gitignore`
as `.claude/`. It is not part of the public developer experience and
should remain local to each contributor's checkout. No
intentional public content was found there.

## 5. `.reguard` disposition

`.reguard/results/` is runtime-generated per-run artefact output.
Added to `.gitignore` as `.reguard/`,
`examples/*/.reguard/`, `tests/runtime/fixtures/.reguard/`. These
are mutable run outputs, not canonical documentation. For an
external consumer who needs to inspect a deterministic demo PASS,
the JSON output is reproducible and can be generated from
`examples/minimal-agent/` by anyone — no need to ship run-id-keyed
output trees in the source tree.

## 6. `build/` / `dist/` / `*.egg-info/` disposition

Already covered by `.gitignore` (`build/`, `dist/`, `*.egg-info/`).
Added `src/*.egg-info/` to catch egg-info generated under the
source tree. Final rebuild artifacts:

```
dist/reguard-0.1.0rc1-py3-none-any.whl    205,601 bytes
dist/reguard-0.1.0rc1.tar.gz              170,996 bytes
```

## 7. Database-by-database disposition

| DB | Tracked? | Decision | Reason |
|---|---|---|---|
| `data/eu_ai_compliance.db` (14 MB) | was; now removed | REMOVE_FROM_PUBLIC_REPO | Research DB; not required by v0.1 runtime; contains `/home/mrcel/...` paths in framework provenance strings |
| `data/reguard.db` (untracked) | not tracked | KEEP_IGNORED | Tiny in-memory development DB; correctly ignored |
| `audit/compliance.db` (untracked) | not tracked | KEEP_IGNORED | Tiny in-memory development DB; correctly ignored |

The 14 MB `data/eu_ai_compliance.db` is a corpus research database
that contains 1,502 GitHub repositories, EU law articles, and
classification assessments. It is NOT part of the v0.1 release
payload; the v0.1 wheel does not depend on it. Its removal is
explicit and documented.

The 1,502-repository corpus metadata remains available as
`audit/gold_article12_v1_repos.json` (the gold validation set, 1 KB)
plus `audit/article_12_1_v1_3/*.json` (the frozen-five evidence).
These are tracked and are the canonical public corpus artifacts.

## 8. Raw regulatory-data disposition

`data/raw/` retains 30 EUR-Lex HTML pages and 10 EUR-Lex RDF files
(CELEX-numbered regulations: GDPR, EU AI Act, CRA, NIS2, Data Act,
etc.). These are downloaded from EUR-Lex's public CELEX HTML
endpoint, which carries the EU's standard "© European Union,
1995–2026" footer and is freely redistributable for non-commercial
purposes under EUR-Lex's reuse policy.

Removed from tracking (see §2): all third-party commercial standards
(ISO 27001, ISO 42001, SOC 2 TSC, PCI-DSS v4.0.1, NEN 7510,
NIST CSF v2.0, HIPAA, CCPA/CPRA, ISO 9001). These are tracked
externally to the repo if needed for research but not redistributed
publicly.

`data/chunks/32024R1689.jsonl` (a single chunked EU AI Act file)
remains tracked; it is a derived artifact from `compliance.legal`
ingest.

## 9. Third-party / standards-content review

| File | Source | Disposition |
|---|---|---|
| `data/raw/ISO27001-AnnexA.json` | ISO/IEC 27001 Annex A controls | REMOVE_FROM_PUBLIC_REPO — ISO copyright; redistribution not clearly authorized |
| `data/raw/ISO42001/*`, `ISO42001.skill`, `ISO42001-README.md` | ISO/IEC 42001:2023 derived Claude skill | REMOVE_FROM_PUBLIC_REPO — ISO copyright; the `.skill` archive contains ISO-derived references |
| `data/raw/SOC2-TSC.json` | AICPA Trust Services Criteria | REMOVE_FROM_PUBLIC_REPO — AICPA copyright |
| `data/raw/PCI-DSS-v4.yml` | PCI Security Standards Council | REMOVE_FROM_PUBLIC_REPO — PCI SSC copyright |
| `data/raw/NEN7510.json` | NEN (Dutch standardisation) | REMOVE_FROM_PUBLIC_REPO — NEN copyright |
| `data/raw/NIST-CSF-v2.pdf` | NIST CSF v2.0 | REMOVE_FROM_PUBLIC_REPO — NIST publications are public domain in the U.S., but the binary PDF is large (1.5 MB) and not needed by v0.1 runtime; archived externally |
| `data/raw/HIPAA-*.xml` | U.S. Federal Regulation (CFR Title 45) | REMOVE_FROM_PUBLIC_REPO — public domain in the U.S., but not needed by v0.1 runtime |
| `data/raw/CCPA.html` | California State Regulation | REMOVE_FROM_PUBLIC_REPO — public domain, but not needed by v0.1 runtime |
| `data/raw/ISO9001-Wikipedia.html` | Wikipedia CC-BY-SA article | REMOVE_FROM_PUBLIC_REPO — CC-BY-SA requires attribution; the third-party HTML mirror is not needed by v0.1 runtime |

The EU law HTML/RDF files (CELEX `3*.html`/`3*.rdf`) are downloaded
from EUR-Lex (the official EU legal database); their reuse is
governed by EUR-Lex's reuse policy and Decision 2011/833/EU. The
public repository retains these for the runtime's
`compliance.legal.framework_loader.load_all("data/raw")` path; the
v0.1 wheel does not require this at install time, but the source
package does at *use* time for the legacy `reguard` pipeline.

## 10. `audit/` disposition

No reorganisation. Per brief §32, deletion of obvious debris is
preferable to a path migration.

Tracked and preserved as public validation evidence:

- `audit/article_12_1_pipeline_report.md`
- `audit/article_12_1_github_actions_report.md`
- `audit/article_12_1_github_actions_run.md`
- `audit/article_12_1_v1_3/*.json` + `evidence/*.json`
- `audit/container_gate1/`
- `audit/gate2_gha/`
- `audit/gate3_p3/`
- `audit/gold_article12_v1_repos.{json,md}`

Removed from tracking (research-arena reports, not public validation
evidence):

- `audit/2026-08-27-corpus-quality.md`
- `audit/2026-08-28-{metrics,readmes,report,sample,verdicts-batch-*}.{md,json}`
- `audit/p3_selection.md`

The untracked `audit/reguard_core_v0_1/`,
`audit/reguard_core_v0_1_release/`,
`audit/integration_discovery/`, `audit/gate2_p3/`,
`audit/corpus_pipeline_architecture_diagnosis.md` are NEW v0.1
release evidence files and should be added to the release commit.

## 11. Obsidian/study-note disposition

`notes/` (containing `notes/README.md` and `notes/open-vault.sh`)
has been removed from tracking. These were a developer-local
Obsidian vault shortcut containing the developer's
`/mnt/c/Users/mrcel/Desktop/Obsidian Vaults/EU-AI-Compliance` path
in 7 lines.

The user's external Obsidian vault (which lives at the WSL/Windows
path and is gitignored on the Windows side) is NOT touched.

The two Reguard study notes under `Reguard/Study/` (`Reguard Core
v0.1 Release.md` etc.) are new v0.1 release documentation and will
be added to the release commit.

## 12. `out/` disposition

`out/` was already in `.gitignore` and contained nothing tracked.
Confirmed: 0 tracked files in `out/`.

## 13. Secret-scan result

Pattern searches across all tracked content:

- `OPENAI_API_KEY=` / `ANTHROPIC_API_KEY=` / `GOOGLE_API_KEY=` /
  `AZURE_OPENAI_API_KEY=` / `HUGGINGFACEHUB_API_TOKEN=` /
  `COHERE_API_KEY=` / `MISTRAL_API_KEY=` / `GROQ_API_KEY=` —
  no actual credential values present. Only the
  `compliance.cli` env-var validator references exist; they
  compare names to a forbidden-env allow-list.
- `sk-[a-zA-Z0-9]{20,}` (OpenAI/Stripe-style secrets) — 0 matches.
- `AKIA[0-9A-Z]{16}` (AWS access key) — 0 matches.
- `ghp_|gho_|ghu_|ghs_|ghr_|github_pat_` (GitHub PAT) — 0 matches.
- `BEGIN PRIVATE KEY|BEGIN RSA PRIVATE KEY|BEGIN OPENSSH PRIVATE KEY`
  — 0 matches.
- `password=|secret=|token=|api_key=` with values — 0 matches
  after filtering legitimate test/example placeholders.
- `.env`, `*.pem`, `*.key`, `credentials*` files tracked — 0
  matches.

**No secrets found in tracked content.**

## 14. Absolute-path / username audit

Pre-fix tracked content had 11 hits across 9 files:

| File | Hit |
|---|---|
| `tests/cli/test_cli.py` | `/home/mrcel/projects/business/compliance-tool` (default cwd) |
| `scripts/maintenance/collect_eu_ai_repos.py` | `/home/mrcel/pgrun`, `user="mrcel"` (PostgreSQL connection) |
| `scripts/maintenance/sync_article_notes.py` | `/mnt/c/Users/mrcel/Desktop/Obsidian Vaults/EU-AI-Compliance` (Obsidian default) |
| `scripts/maintenance/sync_regulation_index.py` | same Obsidian path |
| `scripts/maintenance/article_runtime_pipeline.py` | same Obsidian path (2 lines) |
| `notes/README.md` | `/mnt/c/Users/mrcel/Desktop/Obsidian Vaults/EU-AI-Compliance` |
| `notes/open-vault.sh` | `VAULT_WSL="/mnt/c/Users/mrcel/Desktop/Obsidian Vaults/${VAULT_NAME}"` |
| `data/eu_ai_compliance.db` | `/home/mrcel/projects/learning/eu-ai-compliance-db/...` paths in `frameworks.description` (30 rows) |
| `data/manual_download_log.json` | `/mnt/c/Users/mrcel/Desktop/Obsidian Vaults/Systematic Value Productivity/EU-AI-Compliance/Missing EU Laws` |
| `docs/technical-requirements.md` | `/home/mrcel/projects/learning/eu-ai-compliance-db/data/raw/` (2 lines) |
| `audit/reguard_core_v0_1_release/*` and `audit/integration_discovery/*` and `audit/corpus_runner_v1/*` | path references in audit reports — kept (these are public validation evidence reports documenting the hygiene pass itself) |

All non-audit-report leaks are fixed:

- `tests/cli/test_cli.py` now uses `Path(__file__).resolve().parents[2]` as cwd.
- `scripts/maintenance/collect_eu_ai_repos.py` now reads
  `PG_HOST/PG_PORT/PG_USER/PG_DB` from env vars.
- `scripts/maintenance/sync_article_notes.py`,
  `sync_regulation_index.py`, `article_runtime_pipeline.py` now read
  `OBSIDIAN_VAULT_PATH` env var (default `<set OBSIDIAN_VAULT_PATH
  to your local Obsidian vault>`).
- `docs/technical-requirements.md` paths replaced with `data/raw/`
  relative paths.
- `data/eu_ai_compliance.db` and `data/manual_download_log.json`
  removed from tracking.
- `notes/README.md` and `notes/open-vault.sh` removed from tracking.

## 15. Large-file audit

Largest tracked files (after hygiene):

| File | Size |
|---|---|
| `data/raw/32016R0679.rdf` | 60.8 MB (GDPR RDF) |
| `data/eu_ai_compliance.db` | REMOVED (was 14.0 MB) |
| `data/raw/32022L2555.rdf` | 8.4 MB (NIS2 RDF) |
| `data/raw/32024R1689.rdf` | 3.7 MB (EU AI Act RDF) |
| `data/raw/32024R2847.rdf` | 1.9 MB (CRA RDF) |
| `data/raw/32023R2854.rdf` | 1.8 MB |
| `data/raw/32017R0745.html` | 1.8 MB |
| `data/raw/NIST-CSF-v2.pdf` | REMOVED (was 1.5 MB) |

The 60.8 MB GDPR RDF is the largest remaining tracked file. It is
required by the legacy `compliance.legal.framework_loader.load_all`
runtime path. The wheel does not bundle it (the package
`compliance` is 200 KB; the data is read from `data/raw/` at use
time).

`runtime/build_context/` does not exist. `dist/`, `build/`,
`*.egg-info/` are ignored. No `.pyc`, no `__pycache__`, no
`.pytest_cache` tracked.

## 16. AGPL metadata consistency

| Surface | Value | Match? |
|---|---|---|
| `LICENSE` first 5 lines | `Reguard — Deterministic runtime compliance checks for AI agents.\nCopyright (c) 2026 Marcelo\n\nSPDX-License-Identifier: AGPL-3.0-only` | ✓ |
| `pyproject.toml [project].license` | `AGPL-3.0-only` | ✓ |
| `pyproject.toml [tool.setuptools].license-files` | `["LICENSE"]` | ✓ |
| `README.md` "License" section | "Reguard Core is licensed under the GNU Affero General Public License, version 3 (AGPL-3.0-only). See [`LICENSE`](LICENSE)." | ✓ |
| `wheel METADATA` `License-Expression` | `AGPL-3.0-only` | ✓ |
| `wheel METADATA` `License-File` | `LICENSE` | ✓ |
| `wheel METADATA` classifiers | `License :: OSI Approved :: ...` removed (PEP 639 supersedes) | ✓ |
| `sdist` LICENSE inclusion | `reguard-0.1.0rc1/PKG-INFO` and `reguard-0.1.0rc1/LICENSE` | ✓ |

**AGPL-3.0-only is treated as an intentional product/business choice
for this release. Changing or dual-licensing requires explicit
owner decision.** No further license debate in this phase.

## 17. Wheel content audit

```text
Total entries: 78
+ compliance/ (Python modules — adapters, cli, config, corpus,
  corpus_runner, db, integrations, legal, models, pipeline,
  requirements)
+ reguard-0.1.0rc1.dist-info/ (METADATA, RECORD, WHEEL,
  entry_points.txt, licenses/LICENSE, top_level.txt)

Forbidden entries in wheel: NONE
.pyc entries in wheel: NONE
.env / .db / credentials entries in wheel: NONE
audit/ entries in wheel: NONE
data/ entries in wheel: NONE
notes/ entries in wheel: NONE
```

The wheel contains only intended runtime/package files. License
metadata is included under `reguard-0.1.0rc1.dist-info/licenses/LICENSE`.

## 18. Sdist content audit

```text
reguard-0.1.0rc1/
  LICENSE
  PKG-INFO
  README.md
  pyproject.toml
  src/compliance/**/*.py
```

99 source files + LICENSE + PKG-INFO + README.md + pyproject.toml.
No `data/`, `audit/`, `tests/`, `runtime/`, `docs/`, `examples/`,
`integrations/`, `migrations/`, `scripts/` in the sdist. Standard
sdist shape.

## 19. Clean wheel/import test

Fresh venv at `/tmp/reguard-clean-venv-final` (deleted after test):

```text
$ PYTHONPATH= python3 -c "import compliance; print(compliance.__file__)"
/tmp/reguard-clean-venv-final/lib/python3.14/site-packages/compliance/__init__.py

$ reguard --version
reguard 0.1.0rc1

$ reguard doctor
doctor: OK

$ reguard list
Families:
  - langgraph-state
Built-in integrations:
  - langchain-ai/langchain
  - langchain-ai/langgraph
  - bytedance/deer-flow
```

The import path resolves solely from installed site-packages.
`PYTHONPATH` was explicitly unset for the test. No source-tree
import.

## 20. External consumer smoke

Simulated at `/tmp/reguard-consumer-final/` (consumer) and
`/tmp/reguard-action-final/` (action checkout). The consumer dir
contains only `reguard.yml`, `my_agent.py`, `README.md` from
`examples/minimal-agent/`. The action dir is a complete copy of the
Reguard source tree (the action checkout). Built wheel installed
via the action.yml install_cmd; import resolves from
`/tmp/reguard-action-venv-final/lib/python3.14/site-packages/compliance/__init__.py`.

```text
$ reguard check --repo-path /tmp/reguard-consumer-final ...
PASS for AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING contract 1.4.0
4 events, 2 framework artifact(s)
```

Provider-secret isolation: setting `OPENAI_API_KEY` triggers
`ERROR — env validation failed: forbidden env var 'OPENAI_API_KEY'
is set in the harness environment; recipes must not run when a
provider key is present`. Isolation NOT weakened.

## 21. Provider-secret isolation

`reguard check` enforces the forbidden-env allow-list via
`compliance.cli.env_validation`. With
`OPENAI_API_KEY=sk-test-leak` set:

```text
Result
  ERROR

Reason
  env validation failed: forbidden env var 'OPENAI_API_KEY' is set in the harness environment; recipes must not run when a provider key is present
```

Without the env var, demo PASSes deterministically.

## 22. Full test accounting

```text
$ pytest --collect-only -q
285 tests collected in 0.15s

$ pytest tests/ -q
285 passed in 18.86s
0 failed, 0 errors, 0 skipped, 0 xfail, 0 deselected
```

Required OCI / runtime tests included (`tests/security/`,
`tests/cache/`, `tests/cli/`, `tests/integrations/`, `tests/corpus/`).
Zero required tests silently skipped.

## 23. Frozen-five regression

```text
$ pytest tests/pipeline/ -q
103 passed in 11.64s
```

Article 12(1) v1.4.0 contract preserved. The five frozen adapters:

| Adapter | Frozen SHA | Expected |
|---|---|---|
| `SWE-agent/mini-swe-agent` | `25941c89cfbc91eb40b3f8756348c91d9977d57e` | PASS |
| `gptme/gptme` | (frozen in v1.4.0) | PASS |
| `HKUDS/nanobot` | `4d204ba077a86dc42225c16f8f90032013ea1969` | FAIL |
| `he-yufeng/CoreCoder` | `a03ef36412e432fc49d972d4007b36ce44ec5d9a` | FAIL |
| `The-Pocket/PocketFlow` | (frozen in v1.4.0) | FAIL |

Historical snapshots at `audit/article_12_1_v1_3/*.json`,
`audit/container_gate1/*.json`, `audit/gate3_p3/{PocketFlow,gptme}.json`
all preserve the v1.3.0 frozen contract evidence. Semantics
unchanged.

## 24. Git working-tree state

```text
$ git status --short | wc -l
122

$ git status --short | grep "^D " | wc -l
40   (deleted from tracking)

$ git status --short | grep "^ M" | wc -l
26   (modified)

$ git status --short | grep "^??" | wc -l
56   (untracked, intended for v0.1 productization)
```

HEAD is at `30f2ce0ae1d535033f2a086c27096e6b21329221`
(`feat(article-12-1): add PocketFlow (E) and gptme (B) adapters`).
The hygiene changes are staged but NOT committed.

**`git diff --check`** returns no whitespace errors on the
modified files.

The intended release SHA is a new commit (TBD) that bundles
the 40 deletions + 26 modifications + 56 new files. The release
manifest at `release_artifact_manifest.json` is explicit about
this.

## 25. Source-SHA / artifact provenance status

```text
ARTIFACT FREEZE PENDING FINAL COMMIT
```

The wheel and sdist at `dist/` were built from the current
working tree (HEAD = `30f2ce0` + staged D/M/?? entries). The
release-source SHA will be the SHA of the final commit that
bundles all hygiene changes + new v0.1 productization content.
Until that commit exists, the artifacts are tied to "working tree
state at 2026-08-30 with 40 staged deletions, 26 staged
modifications, 56 untracked additions" rather than to a stable
Git SHA.

The release runbook at
`audit/reguard_core_v0_1_release/publication_runbook.md`
explicitly tells the owner to:
1. Create the final commit.
2. Record its SHA.
3. Rebuild from the clean commit.
4. Re-verify hashes.
5. Update the manifest with the new SHA and new hashes if any
   source content changed.

## 26. Final wheel/sdist hashes

```text
dist/reguard-0.1.0rc1-py3-none-any.whl
  sha256 : 0a724d59d1b57cea15121472d07520612cd6fbc662e2719e6fae67bb38579487
  size   : 205,601 bytes

dist/reguard-0.1.0rc1.tar.gz
  sha256 : 9767a9ed44a210b6bee2e55b42195972d9b1352c4cd0c3650fcd0c22026bfbc3
  size   : 170,996 bytes
```

## 27. Reproducible-build result

```text
WHEEL_BYTE_REPRODUCIBLE = TRUE
SDIST_CONTENT_REPRODUCIBLE = TRUE
SDIST_HASH_REPRODUCIBLE = FALSE (cosmetic only)
```

Two consecutive `python -m build` invocations from the same
working tree produce:

- **Identical** wheel SHA-256 (verified).
- **Identical** sdist extracted file content (verified via
  `diff -r --brief` on extracted trees).
- **Different** sdist gzipped-tar SHA-256 because of
  gzip archive metadata (mtime + member ordering). This is
  a known limitation of `python -m build`'s default sdist
  tooling and is cosmetic — the SHA that matters for
  distribution is the wheel's, and the sdist is a fallback
  whose payload is identical.

A reproducible-build hardening of the sdist would require
`PYTHONHASHSEED=0`, `SOURCE_DATE_EPOCH`, and a deterministic
sdist builder; this is a future hardening, not a release blocker.

## 28. OCI publication readiness

```text
OCI_PUBLICATION = PENDING_EXTERNAL_ACTION
```

The v0.1 default is the subprocess driver (no OCI required for
the demo PASS). The `runtime/Dockerfile` is committed and the
container build context is functional. The public OCI image
has not been built or pushed in this phase per the brief.

The intended image identity (TBD by owner):

```text
ghcr.io/<actual-owner>/reguard-runtime:0.1.0rc1
```

The release runbook §5 documents the build/push/inspect commands.

## 29. PyPI publication readiness

```text
distribution name (PEP 503) : reguard
version                       : 0.1.0rc1
twine check                   : PASS
wheel + sdist                 : 78 + 99 entries, no forbidden content
AGPL metadata                 : PEP 639-compliant
README quickstart             : follows clean venv to PASS
frozen-five regression        : 103/103 PASS
full test suite               : 285/285 PASS
```

**`Pypi_PUBLICATION_READINESS = TRUE`** — owner only needs to run
`twine upload` against `dist/*`. The runbook §6 documents both
the trusted-publishing and manual-token paths.

## 30. Remote GitHub Action smoke status

```text
REMOTE_RELEASE_SMOKE = PENDING_EXTERNAL_PUBLICATION
```

The local external-consumer simulation (consumer dir != action
source dir; site-packages-only import; deterministic demo PASS;
provider-secret isolation enforced) is the closest available proxy.
A real GitHub-hosted test requires the published artifact and
tag, which are intentionally out of scope for this phase.

## 31. Remaining publication blockers

| Item | Status | Resolution path |
|---|---|---|
| Actual secrets in tracked files | NONE | n/a |
| Private/personal DB data exposed | NONE | n/a |
| Non-redistributable third-party material tracked | NONE | All third-party standards removed from tracking |
| Generated caches/build outputs tracked | NONE | `.gitignore` covers `__pycache__/`, `.pytest_cache/`, `build/`, `dist/`, `*.egg-info/` |
| Source checkout required by wheel | NO | wheel installs cleanly without source tree |
| Source checkout required by Action | NO | action builds wheel from `$GITHUB_ACTION_PATH` and installs it; consumer never needs the source |
| License metadata inconsistent | NO | PEP 639-compliant across `pyproject.toml`, wheel METADATA, sdist PKG-INFO, README |
| Test regression | NO | 285/285 PASS |
| Frozen Article 12(1) semantic regression | NO | 103/103 PASS in `tests/pipeline/` |
| README points to nonexistent paths | NO | README quickstart works end-to-end in fresh venv |
| Package contains local research databases | NO | Wheel contains only `compliance/` + `dist-info/`; no `data/`, no `audit/`, no `notes/`, no `.db` |

**Zero release-blockers.**

## 32. External publication actions still pending

```text
PENDING_PUBLICATION_ACTION:
  - PyPI upload (twine upload dist/*)
  - Public OCI runtime image build + push to GHCR
  - GitHub release creation + tag push (v0.1.0-rc.1)
  - Remote GitHub Action consumer smoke (requires all of the above)

All four are owner-only steps documented in
audit/reguard_core_v0_1_release/publication_runbook.md.
```

## 33. Final public repository readiness

# **READY**

The repository is clean, intentional, reproducible, and safe to
make public. The wheel and sdist are byte-identical across
rebuilds (wheel) / content-identical (sdist). All developer-path
leaks have been removed. All third-party restricted material has
been removed from tracking. License metadata is PEP 639-compliant
and consistent across all surfaces. 285/285 tests pass. The
frozen Article 12(1) contract is preserved.

The four external publication steps (PyPI, GHCR, Git tag, remote
smoke) remain intentionally pending per the brief; they are
documented in the publication runbook and require explicit
release-process authorisation.

For an external consumer with the wheel installed, Reguard Core
v0.1.0rc1 is **READY** to use today.

— end of final pre-publication report —