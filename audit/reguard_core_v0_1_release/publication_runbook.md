# Reguard Core v0.1.0rc1 — Owner Publication Runbook

**Date:** 2026-08-30
**Audience:** Repository owner / release engineer
**Status:** This runbook is for **after** the v0.1.0rc1 hygiene + artifact
freeze phase. Steps are deliberately ordered so each step's output is the
next step's input. Do not skip steps.

---

## 0. Preconditions

- Working tree at the release-source commit (the commit that bundles
  the staged hygiene fixes and the v0.1 productization content).
- Working tree is clean: `git status --short` returns no `M`, `D`, or
  `??` entries that aren't in the intended release set.
- Python ≥ 3.12 available; build tooling installed (`pip install
  build twine`).
- PyPI and GHCR credentials available via trusted publishing (or the
  alternative manual token workflow documented in §5 and §6).
- No Git tag has been pushed yet for `v0.1.0-rc.1`.

---

## 1. Review final diff

```bash
git fetch --all --prune
git checkout main
git pull --ff-only
git log --oneline -5
git status --short
git diff --stat HEAD~1
```

Confirm:
- Working tree clean (`git status --short` empty or only expected).
- Last commit is the release-source commit (intended SHA recorded
  here: `__TO_BE_FILLED_IN__`).
- No untracked high-risk content (`notes/`, `data/*.db`,
  `data/raw/ISO*`, `data/raw/SOC*`, etc.).
- No developer-path leaks:
  ```bash
  git ls-files | xargs -I{} grep -l "/home/<owner>\|/mnt/c/Users/<owner>\|C:\\Users\\<owner>" "{}" 2>/dev/null
  ```
  must return no matches.

---

## 2. Create final release commit (if not already done)

The hygiene pass stages 40 deletions, 26 modifications, and ~56 new
files for v0.1 productization. These need to land as a single
intentional commit so the artifact SHA is reproducible.

```bash
git add -A
git commit -m "release(v0.1.0rc1): hygiene + productization freeze

- Remove notes/, data/eu_ai_compliance.db, third-party standards
  (ISO/SOC2/PCI-DSS/NEN7510/NIST-CSF/HIPAA/CCPA/ISO9001) from tracking
  (redistribution / privacy)
- Replace developer-path hardcodes with env-var defaults
- Add .gitignore for .reguard/, *.egg-info under src/, third-party
  standards, notes/
- Add v0.1 productization: src/compliance/{cli,corpus_runner,integrations}/
- Add examples/, action.yml, integrations/ manifests
- Add tests/{cache,cli,corpus,evidence,integrations,security}/
- Add audit/{reguard_core_v0_1,reguard_core_v0_1_release,integration_discovery,gate2_p3,corpus_pipeline_architecture_diagnosis}
- Add migrations/006-011 (corpus runner schema)
- License: AGPL-3.0-only (PEP 639)
"
```

Record the resulting SHA:

```bash
git rev-parse HEAD
```

Update `release_artifact_manifest.json` `source_git_sha` with the
exact SHA. The wheel/sdist hashes in the manifest MUST have been
built from a working tree at this exact SHA.

---

## 3. Record Git SHA

```bash
RELEASE_SHA=$(git rev-parse HEAD)
echo "Release SHA: $RELEASE_SHA"
```

Write this into `audit/reguard_core_v0_1_release/release_artifact_manifest.json`
under `source_git_sha`. Re-commit the manifest update with the same
release commit (it should already be in it).

---

## 4. Rebuild artifacts from clean commit

```bash
rm -rf build/ dist/ src/*.egg-info/ src/compliance.egg-info/
python -m build --sdist --wheel
python -m twine check dist/*
sha256sum dist/*
```

The expected hashes (verified 2026-08-30 from this exact working
tree before the hygiene commit landed):

```text
dist/reguard-0.1.0rc1-py3-none-any.whl
  sha256 : 0a724d59d1b57cea15121472d07520612cd6fbc662e2719e6fae67bb38579487
  size   : 205,601 bytes

dist/reguard-0.1.0rc1.tar.gz
  sha256 : 9767a9ed44a210b6bee2e55b42195972d9b1352c4cd0c3650fcd0c22026bfbc3
  size   : 170,996 bytes
```

**Wheel is byte-reproducible.** Two consecutive `python -m build`
invocations from the same working tree produce the same SHA-256.
**Sdist content is byte-reproducible but archive metadata varies**
(mtime/ordering); the SHA of the gzipped tar is non-deterministic
across rebuilds. Re-record the actual hashes from this step into
the manifest.

---

## 5. Publish OCI RC image (does NOT happen in this phase)

Target concept:

```text
ghcr.io/usereguard/reguard-runtime:0.1.0rc1
```

If the runtime image is built from the runtime/ subtree:

```bash
cd runtime/
docker build -t ghcr.io/usereguard/reguard-runtime:0.1.0rc1 .
docker push ghcr.io/usereguard/reguard-runtime:0.1.0rc1
```

Record the immutable digest:

```bash
docker inspect --format='{{index .RepoDigests 0}}' \
  ghcr.io/usereguard/reguard-runtime:0.1.0rc1
```

Persist the tag and digest in the run provenance for any
`reguard check` invocation that uses a non-default runtime
(`--runtime-image <tag>` and the digest the harness resolved).

If the OCI runtime is not yet public, this remains:
**`OCI_PUBLICATION = PENDING_EXTERNAL_ACTION`**.

---

## 6. Publish PyPI 0.1.0rc1

The wheel's distribution name normalizes to `reguard` (PEP 503) from
the project name `Reguard`.

```bash
python -m twine upload dist/reguard-0.1.0rc1-py3-none-any.whl \
                    dist/reguard-0.1.0rc1.tar.gz
```

**Preferred:** Trusted publishing. Configure on PyPI once for the
repository `UseReguard/Reguard` with environment `pypi` and
workflow file `.github/workflows/release.yml` (or whichever workflow
runs `twine upload`). No PyPI token in GitHub Secrets required.

**Manual fallback:** create a PyPI API token at
<https://pypi.org/manage/account/token/>, scope it to the `reguard`
project only, and pass it via `TWINE_USERNAME=__token__` +
`TWINE_PASSWORD=<the token>` env vars.

Verify after upload:

```bash
pip install --index-url https://pypi.org/simple/ reguard==0.1.0rc1
reguard --version
reguard doctor
```

---

## 7. Create/push v0.1.0-rc.1 tag

```bash
git tag -a v0.1.0-rc.1 -m "Reguard Core 0.1.0rc1 release candidate

wheel sha256:    0a724d59d1b57cea15121472d07520612cd6fbc662e2719e6fae67bb38579487
sdist sha256:    9767a9ed44a210b6bee2e55b42195972d9b1352c4cd0c3650fcd0c22026bfbc3
license:         AGPL-3.0-only
contract:        AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING 1.4.0

Source SHA: $(git rev-parse HEAD)
" $RELEASE_SHA

git push origin v0.1.0-rc.1
```

Do **not** push a non-annotated tag; PyPI/GHCR consumers should be
able to retrieve the commit metadata.

---

## 8. Run remote GitHub Action consumer test

This requires a fresh consumer repository (NOT the Reguard
repository) that uses the published tag:

```yaml
# <consumer-repo>/.github/workflows/reguard.yml
name: reguard
on: [push, pull_request]
jobs:
  reguard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: UseReguard/Reguard@v0.1.0-rc.1
        with:
          reguard-version: 0.1.0rc1    # pinned for the RC
          fail-on: FAIL,ERROR,UNKNOWN,UNSUPPORTED
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: reguard
          path: .reguard/results/
```

This is the only test that proves the published wheel, the
published action, and the published OCI runtime (if any) all
function end-to-end against a real GitHub Actions runner.

---

## 9. Inspect failures/user experience

If the remote smoke fails:

1. Read the action's step summary (`.reguard/results/<run-id>/summary.md`).
2. Read the JSON result (`.reguard/results/<run-id>/result.json`).
3. Read the evidence (`.reguard/results/<run-id>/evidence.json`).
4. If the failure is an environment-specific issue
   (e.g. PyPI unreachable, OCI registry authentication), fix the
   release infrastructure. Do not weaken the engine semantics.
5. If the failure is a contract bug, fix in source, rebuild, restart
   from §4.

---

## 10. Promote to v0.1.0 (only if RC passes)

After at least one consumer-repo RC run PASSes:

```bash
# Bump version in pyproject.toml (remove rc1)
# Update reguard_version references
# Rebuild
# Re-run tests
# Tag v0.1.0
git tag -a v0.1.0 -m "Reguard Core 0.1.0 stable" $RELEASE_SHA
git push origin v0.1.0
```

Do **not** publish a v0.1.0 wheel until the v0.1.0-rc.1 wheel has
been used successfully by at least one external consumer.

---

## 11. Roll-back plan (if a publication issue surfaces)

PyPI does not allow re-uploading the same `filename`. The recovery
policy is documented in §11a below. GHCR allows tag deletion; use
carefully.

---

## 11a. Failure recovery matrix

Once a tag has been pushed publicly, it is **immutable**. Do not
move, force-push, delete, or re-create `v0.1.0-rc.1`. The tag
identifies exactly one source commit forever.

| Failure point                       | PyPI published? | Source change required? | Recovery                                                                            |
|-------------------------------------|---------------:|-----------------------:|-------------------------------------------------------------------------------------|
| `validate`                          |             no |                  maybe | Fix before tag is created, OR cut `v0.1.0-rc.2` if the tag was already public       |
| `build`                             |             no |                  maybe | Re-run if transient; cut `v0.1.0-rc.2` if a source/workflow fix is required         |
| `publish-pypi`                      |             no |                  maybe | Re-run if configuration/transient and same immutable source                          |
| `publish-runtime` after PyPI success |            yes |                    no | Re-run only `publish-runtime` against the same tag                                  |
| `publish-runtime` after PyPI success |            yes |                   yes | Publish `0.1.0rc2`; do NOT replace RC1                                              |
| `release` after PyPI/GHCR success   |            yes |                    no | Re-run only `release` against the same tag                                          |
| Remote consumer smoke               |            yes |                  maybe | Document the defect; cut `v0.1.0rc2` for fixes                                      |

**Key invariant:** Once PyPI has accepted `0.1.0rc1`, any
code/workflow change that affects released behaviour requires
`0.1.0rc2`.

---

## 11b. Operator release sequence

The canonical release flow uses the corrected workflow at
`.github/workflows/release.yml`:

1. Configure the PyPI Trusted Publisher (values in
   `trusted_publishing_setup.md`).
2. Create the GitHub `pypi` environment with optional required
   reviewer.
3. Verify Actions has `Read and write permissions` (or
   `Read repository contents and packages permissions`).
4. Confirm `UseReguard` allows package publication (org-level).
5. Verify the release workflow at the exact `main` SHA targeted
   for tagging.
6. Create the immutable tag:

   ```bash
   git tag -a v0.1.0-rc.1 <FINAL_RC1_TAG_TARGET_SHA> \
     -m "Reguard Core 0.1.0rc1 release candidate"
   ```

7. Push the tag **once**:

   ```bash
   git push origin v0.1.0-rc.1
   ```

   Do not re-push, force-push, move, delete, or replace the tag.

8. Monitor the workflow run; failures should be classified against
   the recovery matrix above.
9. Re-run only the failed jobs when the failure is transient or
   configuration-only. If a code/workflow change is required, cut
   RC2 (do NOT modify RC1).
10. After the workflow succeeds, run the clean remote consumer
    smoke from `remote_consumer_smoke_plan.md`.

**RC1 is immutable.** Any move, force-push, deletion, or replacement
of `v0.1.0-rc.1` is prohibited.

---

## 12. Verification after publication

Once the wheel is on PyPI:

```bash
pip install --upgrade --index-url https://pypi.org/simple/ reguard==0.1.0rc1
reguard --version                  # expect: reguard 0.1.0rc1
reguard doctor                     # expect: doctor: OK
reguard list                       # expect: langgraph-state family listed
```

In a separate, fresh consumer directory (NOT the Reguard repo):

```bash
git clone https://github.com/UseReguard/Reguard /tmp/reguard-v0_1_consumer_demo
cd /tmp/reguard-v0_1_consumer_demo/examples/minimal-agent
reguard doctor --repo-path .
reguard check  --repo-path .
# expect: PASS for AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING contract 1.4.0
```

`compliance.__file__` must resolve from
`site-packages`, never from the source tree:

```bash
python3 -c "import compliance; print(compliance.__file__)"
# expect: <prefix>/lib/python3.X/site-packages/compliance/__init__.py
# must NOT contain: /tmp/reguard-v0_1_consumer_demo/src/
```

---

## End of runbook

This runbook is intentionally prescriptive. Each step's output is
the next step's input. Do not improvise.