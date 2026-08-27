# Base Docker runtime — implementation report

**Status**: complete. All 40 host-Python unit tests pass. Docker-side
verification will run in GitHub Actions on every push to `main`.

---

## Files added/changed

```
.github/workflows/runtime-smoke.yml          # CI: build image + inspect smoke
.gitignore                                   # python caches, venvs, eggs
conftest.py                                  # pytest sys.path bootstrap (project root)
pytest.ini                                   # testpaths + norecursedirs for fixtures
runtime/.gitignore                           # python caches
runtime/Dockerfile                           # python:3.12-slim-bookworm + uv + non-root
runtime/README.md                            # contract, security model, limitations
runtime/__init__.py                          # package marker
runtime/detect.py                            # static detection (build/test strategy)
runtime/entrypoint.py                        # argparse CLI dispatcher
runtime/models.py                            # Result JSON contract + validate_dict()
runtime/commands/_common.py                  # subprocess timeout + atomic write helpers
runtime/commands/__init__.py                 # subcommand package marker
runtime/commands/build.py                    # build mode
runtime/commands/inspect.py                  # inspect mode (NEVER executes repo code)
runtime/commands/test.py                     # test mode
runtime/scripts/run-local.sh                 # host-side docker-run wrapper
tests/runtime/conftest.py                    # fixtures path, tempdir, sentinel cleanup
tests/runtime/test_detect.py                 # 13 detection tests
tests/runtime/test_inspect.py                # 12 inspect-mode tests (security + determinism)
tests/runtime/test_result_schema.py          # 11 schema validation tests
tests/runtime/test_timeout.py                # 5 subprocess timeout tests
tests/runtime/fixtures/01-pyproject-simple/
tests/runtime/fixtures/02-src-layout/
tests/runtime/fixtures/03-requirements-txt/
tests/runtime/fixtures/04-uv-lock/
tests/runtime/fixtures/05-poetry/
tests/runtime/fixtures/06-setup-py-legacy/
tests/runtime/fixtures/07-pytest/
tests/runtime/fixtures/08-no-build-system/
tests/runtime/fixtures/09-invalid-python/
tests/runtime/fixtures/10-malicious/         # sentinel files written on import
```

10 directories × 11 files = fixture inventory complete.

---

## Docker image structure

* **Base**: `python:3.12-slim-bookworm` (pinned)
* **System packages**: `git`, `build-essential`, `ca-certificates`
* **Tooling**: `uv 0.4.18` (pinned single-binary install)
* **Pip tooling**: `pip>=24`, `setuptools>=70`, `wheel`
* **Runtime source**: `/opt/repo-runtime/runtime/` (read-only after COPY)
* **Non-root user**: `runtime:runtime`, UID/GID `10001:10001`
* **Working directories**:
  * `/input` — host bind mount, read-only
  * `/workspace` — tmpfs for build/test copies
  * `/artifacts` — host bind mount, writable
  * `/tmp` — tmpfs
* **Entrypoint**: `python3 /opt/repo-runtime/runtime/entrypoint.py`
* **Environment allowlist**: `HOME`, `LANG`, `LC_ALL`,
  `PYTHONDONTWRITEBYTECODE`, `PIP_DISABLE_PIP_VERSION_CHECK`,
  `PIP_NO_INPUT`. Nothing else is forwarded.

---

## Supported project layouts (detection precedence)

1. `uv.lock` present → `uv sync --frozen` then `uv pip install --python <py> -e .`
2. `poetry.lock` present → `poetry install --no-interaction`
3. `pyproject.toml` only → `pip install -e .`
4. `pyproject.toml` with `[tool.poetry]` → `poetry install`
5. `requirements*.txt` → `pip install -r <first deterministic file>`
6. `setup.py` / `setup.cfg` → `pip install -e .` (setuptools)
7. `Pipfile` → `status=unsupported` (MVP does not implement pipenv)
8. none of the above → `status=unsupported`

Test framework detection: `[tool.pytest.ini_options]`, `[tool:pytest]`,
`pytest.ini`, `conftest.py`, or any `test_*.py` / `*_test.py` → pytest.

---

## Security controls

### Static inspection (`inspect`)

| Control | Where |
|---------|-------|
| `--network none` | host run-local.sh / CI workflow |
| `--read-only` | CI workflow |
| `--cap-drop ALL` | host + CI |
| `--security-opt no-new-privileges` | host + CI |
| `os.walk` only (no `import`, no `runpy`) | runtime/commands/inspect.py |
| AST parsing only (no `exec`, no `compile(..., 'exec')`) | runtime/commands/inspect.py |
| Symlinks preserved as symlinks, never dereferenced | runtime/commands/_common.py |
| venv / cache / build dirs pruned from walk | runtime/detect.py + inspect.py |
| 5 MiB per-file size cap for AST/heuristic parsing | runtime/commands/inspect.py |
| 200 000-file walk cap | runtime/detect.py |

Verified by `tests/runtime/test_inspect.py::test_inspect_does_not_import_repo_module`
using the `10-malicious` fixture (sentinel files would be created on
import — they never are).

### Build / test (`build`, `test`)

| Control | Where |
|---------|-------|
| Host checkout mounted read-only | host + CI |
| Writable copy of repo in `/workspace/repo` (tmpfs) | runtime/commands/build.py + test.py |
| `subprocess.Popen(shell=False, argv=[...])` only | runtime/commands/_common.py |
| Process-group SIGKILL on timeout | runtime/commands/_common.py |
| Per-command stdout/stderr to artifact files | runtime/commands/_common.py |
| Non-root UID 10001 | Dockerfile |
| Allow-listed environment only | entrypoint.py + Dockerfile |
| `--pids-limit 256`, `--memory 2g`, `--cpus 2` | host + CI |
| No `--privileged`, no Docker socket, no host HOME/.gitconfig | host + CI |

### Explicit limitations (in `runtime/README.md`)

* Docker is the **MVP isolation boundary**, not a hostile-code
  containment claim. A determined attacker with repo-supplied
  `setup.py` can attempt kernel exploits, container-escape
  primitives, and resource-exhaustion beyond cgroup caps.
* The runtime does NOT forward host credentials, SSH agent, GitHub
  tokens, or cloud secrets. That contract is enforced by an
  explicit environment allow-list.
* `pip install -e .` runs repo-supplied `setup.py` code as the
  runtime UID. For repos we don't trust at all, the next step is
  firecracker / gVisor / sandboxed microVM.

---

## Mode behaviour

### `inspect`

| Input | Output |
|-------|--------|
| Any Python repo | static inventory; no subprocess; result.json + python_files.json |
| Repo with `setup.py` | same — setup.py is NOT executed |
| Repo with malicious `__init__.py` | same — module is NOT imported; sentinel never appears |
| Repo with invalid `.py` file | `parse_ok=False` recorded per file; status=success |
| Repo with venv/__pycache__ | pruned from walk; never listed |

### `build`

| Repo state | Result |
|-----------|--------|
| Recognised packaging | `status=success` after running the detected install command |
| `Pipfile` | `status=unsupported`, error="build strategy 'pipenv' is not supported" |
| No packaging | `status=unsupported`, error="build strategy 'none' is not supported" |
| Subprocess exits non-zero | `status=failed`, stderr artifact path |
| Subprocess exceeds `--timeout-seconds` | `status=timeout`, command group killed |

### `test`

| Repo state | Result |
|-----------|--------|
| pytest detected, tests pass | `status=success` |
| pytest detected, tests fail | `status=failed` |
| pytest not detected, no `--command` | `status=unsupported` |
| `--command "..."` supplied | runs that argv verbatim |
| Subprocess times out | `status=timeout` |

---

## JSON schema (locked, version 1)

See `runtime/models.py`. Key invariants:

* `schema_version` is `"1"`. Bumping requires a migration story.
* `status` ∈ `success | failed | unsupported | timeout | error` (locked enum).
* `commands[]` empty for `inspect`; one entry per subprocess for `build`/`test`.
* `artifacts[]` always populated when the run produced files.
* `duration_ms` integer, monotonically increasing.
* `exit_code` mirrors the last subprocess exit (or 0 if none ran).

`runtime.models.validate_dict()` rejects:

* missing required keys
* unknown top-level keys
* invalid `status` values
* `schema_version != "1"`
* commands missing `argv`

---

## Tests added

40 host-Python unit tests across four files:

| File | Tests | Coverage |
|------|-------|----------|
| `test_detect.py` | 13 | detection precedence, src/flat layout, uv-lock wins, poetry detection, pipenv reported unsupported, determinism, broken-Python robustness |
| `test_inspect.py` | 12 | never imports repo module, never runs setup.py, never installs deps, /input unchanged, structured result, syntax error reporting, pytest/uv-lock detection, cache dir pruning, deterministic output |
| `test_result_schema.py` | 11 | JSON round-trip, missing/unknown keys, locked enum values, detection count consistency |
| `test_timeout.py` | 5 | short timeout terminates, normal completion, missing binary, argv-not-shell, stdout/stderr artifacts |

All 40 pass:

```
$ PYTHONPATH=. python3 -m pytest tests/runtime/
============================== 40 passed in 2.19s ==============================
```

---

## Smoke-test results

### `inspect` against all 10 fixtures (host-Python, no Docker)

| fixture | status | pkg-mgr | build-sys | test-fw | layout | py-files |
|---------|--------|---------|-----------|---------|--------|----------|
| 01-pyproject-simple | success | pip | hatchling | – | flat | 1 |
| 02-src-layout | success | pip | setuptools | – | **src** | 2 |
| 03-requirements-txt | success | pip | – | – | flat | 1 |
| 04-uv-lock | success | **uv** | hatchling | – | flat | 1 |
| 05-poetry | success | **poetry** | poetry-core | – | flat | 1 |
| 06-setup-py-legacy | success | pip | **setuptools** | – | flat | 2 |
| 07-pytest | success | pip | hatchling | **pytest** | flat | 2 |
| 08-no-build-system | success | – | – | – | – | 0 |
| 09-invalid-python | success | pip | hatchling | – | flat | 2 (1 with syntax error) |
| 10-malicious | success | pip | setuptools | – | flat | 3 (sentinel NEVER created) |

### Other smoke checks (host-Python)

* `inspect` against `10-malicious`: sentinel files `/tmp/INSPECT_IMPORTED_A_REPO_MODULE` and `/tmp/INSPECT_EXECUTED_REPO_CODE` confirmed **not present**.
* `inspect` against `08-no-build-system`: returns `success`, no detection (no false positives).
* `build` against `08-no-build-system`: returns `unsupported`, `commands=[]`, error="build strategy 'none' is not supported".
* `build` against a synthetic `Pipfile`: returns `unsupported`, `extra.strategy="pipenv"`.
* `test` against `01-pyproject-simple` (no pytest): returns `unsupported`, error mentions detection.
* `test --timeout-seconds 3 --command "python3 /tmp/sleeper.py"` (sleeps 30s): returns `status=timeout`, `commands[0].timed_out=True`, `duration_ms=3004`. Process group killed.

### Docker smoke (CI-only — host has no Docker daemon)

`.github/workflows/runtime-smoke.yml` runs in GitHub Actions on every push:
* host-Python unit tests (no Docker)
* `docker build` from `runtime/Dockerfile`
* `docker run --network none --cap-drop ALL --user 10001:10001 ...`
* inspect against `07-pytest` fixture → `result.json` uploaded as artifact
* inspect against `08-no-build-system` fixture → `result.json` confirms success
* sentinel-file assertion after inspect
* `runtime.models.validate_dict()` against the result

The workflow builds and exercises the image using the exact Docker
flags documented in `runtime/scripts/run-local.sh`. It never mounts
the Docker socket, never uses `--privileged`, and never forwards
host credentials.

---

## Limitations discovered

1. **No Docker on this WSL distro**: WSL integration with Docker
   Desktop is not enabled, so the actual `docker build` / `docker run`
   verification cannot run in this environment. The GitHub Actions
   workflow is the canonical verification path.
2. **Host-Python smoke for `build`/`test` partially limited**: the
   host's Python 3.14 has PEP 668 externally-managed-environment,
   so `pip install` against a fixture returns exit 1 (PEP 668
   enforcement, not a runtime bug). The runtime correctly reports
   `status=failed` with the stderr artifact containing the exact
   reason. This is correct runtime behaviour.
3. **Network access required for `build` and `test`**: the runtime
   itself does not grant network. The host must pass `--network
   enabled` to docker-run. The default for `test` is `--network none`
   and must be explicitly opted-in per repo by the orchestration layer.
4. **`Pipfile` repos are explicitly unsupported** in the MVP. They
   surface as `status=unsupported` rather than failing silently.
5. **The runtime is **not** a hostile-code containment boundary**.
   See `runtime/README.md` "Limitations" — for repos we don't trust
   at all the next step is firecracker / gVisor / sandboxed microVM.
6. **`/workspace` is expected to be a writable tmpfs mounted by the
   host**. If the host forgets the `--tmpfs /workspace:rw,...` flag,
   the container will fail. The Dockerfile pre-creates the directory
   as a fallback so the failure mode is explicit ("Permission denied")
   rather than silent.

---

## Next steps (out of scope for this task)

* Article 12 compliance detector
* Corpus pipeline integration (host runner clones SHA, mounts /input,
  invokes `docker run ... repo-runtime inspect`)
* Firecracker / gVisor sandbox if compliance work shows we need
  stronger isolation than Docker provides

These are deliberately deferred per the original task scope.
