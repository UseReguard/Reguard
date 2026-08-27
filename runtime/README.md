# repo-runtime

A small, generic Docker runtime for inspecting / building / testing
Python repositories that the rest of our compliance pipeline receives
as plain file trees.

It is intentionally ignorant of:

* GitHub URLs or the GitHub API
* the corpus SQLite database (`agent_repositories`, `agent_repository_audits`)
* legal articles, compliance status, audit verdicts
* Redis, Celery, Kubernetes, vector databases
* LLM calls, model-based classification

The contract is: **the host checks out an exact repository SHA, the
runtime inspects / builds / tests it, and writes a structured JSON
result plus per-command logs. The host then destroys the container.**

The runtime does not know about compliance, and the compliance engine
will not know about Docker. Three layers stay separate:

```
CORPUS / ORCHESTRATION     REPOSITORY RUNTIME     COMPLIANCE ENGINE
─────────────────────      ──────────────────     ─────────────────
GitHub URL                 filesystem input       deterministic evidence
repo DB                    build metadata         legal rules
exact SHA                  Python environment     PASS / FAIL / UNKNOWN
queue                      build/test exec        / NOT_APPLICABLE
temp checkout              resource/time policy
Docker invocation
```

---

## Modes

| mode     | purpose                                       | executes repo code? |
|----------|-----------------------------------------------|---------------------|
| `inspect`| static inventory of the checkout              | **no**              |
| `build`  | install dependencies, prepare environment     | yes                 |
| `test`   | run the test suite                            | yes                 |

`inspect` never imports repository modules, never runs `setup.py`,
never installs dependencies. It uses AST parsing for `.py` files and
stdlib parsers for TOML/JSON/YAML/INI.

`build` and `test` first copy the read-only `/input` into a writable
`/workspace/repo`, then run the detected command from there. The host
checkout at `/input` is never modified.

---

## CLI

```
repo-runtime inspect --repo-sha <sha> --output /artifacts/result.json
repo-runtime build   --repo-sha <sha> --output /artifacts/result.json
repo-runtime test    --repo-sha <sha> --output /artifacts/result.json \
                     [--command "pytest tests/unit"]
```

All modes accept:

```
--repo-path        (default /input)
--artifacts-dir    (default /artifacts)
--repo-sha         (recorded in the result)
--timeout-seconds  (default 600)
--network          none|enabled  (build defaults to enabled; inspect/test to none)
```

---

## Result contract

Every mode writes `/artifacts/result.json` matching this schema:

```json
{
  "schema_version": "1",
  "runtime_version": "0.1.0",
  "mode": "inspect",
  "status": "success",
  "repo":   { "sha": "...", "path": "/input" },
  "environment": { "python_version": "3.12.x", "network_policy": "none" },
  "detection": {
    "package_manager": "uv",
    "build_system":    "hatchling",
    "test_framework":  "pytest",
    "layout":          "src",
    "has_pyproject":   true,
    "has_setup_py":    false,
    "has_setup_cfg":   false,
    "has_requirements":false,
    "has_uv_lock":     true,
    "has_poetry_lock": false,
    "has_pipfile":     false,
    "python_version_constraint": ">=3.10",
    "files_inspected": 42,
    "python_files":    17
  },
  "commands":  [],
  "artifacts": [],
  "duration_ms": 1234,
  "exit_code":    0,
  "error":      null
}
```

`status` ∈ `success | failed | unsupported | timeout | error`. Do not
interpret these as compliance verdicts — `PASS` / `FAIL` belong to
the compliance engine.

`commands[]` records each subprocess invocation (inspect leaves it
empty). Each entry has `argv`, `cwd`, `exit_code`, `duration_ms`,
`timed_out`, `stdout_artifact`, `stderr_artifact`.

---

## Supported project layouts

Detection precedence (see `runtime/detect.py`):

1. `uv.lock`            → `uv` (uses `uv sync --frozen` then `uv pip install -e .`)
2. `poetry.lock`        → `poetry install --no-interaction`
3. `pyproject.toml`     → `pip install -e .` (or `poetry install` if `[tool.poetry]` is present)
4. `requirements*.txt`  → `pip install -r <first deterministic file>`
5. `setup.py` / `setup.cfg` → `pip install -e .` (legacy setuptools)
6. `Pipfile`            → **unsupported** by the MVP (pipenv not implemented)
7. none                 → **unsupported**

For test mode, pytest is detected from:

* `[tool.pytest.ini_options]` in `pyproject.toml`
* `[tool:pytest]` in `setup.cfg`
* `pytest.ini` / `conftest.py` at the repo root
* any file matching `test_*.py` / `*_test.py`

If detection fails, the result is `unsupported`. We do **not** parse
README text to derive a test command — that is host policy.

---

## Security model

### A. Static inspection

`inspect` must not execute repository code. The host should run it with:

```
--network none
--read-only
--cap-drop ALL
--security-opt no-new-privileges
```

The repo is mounted read-only at `/input`. The runtime reads paths
under `/input` only via `os.walk`, `open(..., 'rb')`, `ast.parse`,
and stdlib TOML/JSON parsers. It never:

* imports a module from the repo
* runs `setup.py`
* runs `pip install` against repo deps
* shells out to a repo-supplied command
* dereferences symlinks into the host filesystem

### B. Build / test execution

`build` and `test` are treated as **hostile execution**. The runtime:

* copies `/input` (read-only) into `/workspace/repo` (writable tmpfs),
  then operates only on the copy
* uses `subprocess.Popen` with `shell=False` and `argv` arrays, never
  shell strings
* kills the entire process group on timeout
* runs as a fixed non-root UID (default 10001)
* receives an allow-listed environment (`HOME`, `LANG`, `LC_ALL`,
  etc.) — never host credentials, SSH agent, or cloud secrets

The host should run with:

```
--cap-drop ALL
--security-opt no-new-privileges
--pids-limit 256
--memory 2g
--cpus 2
--tmpfs /tmp:rw,nosuid,size=512m
--tmpfs /workspace:rw,nosuid,size=2g
--mount type=bind,src=$REPO,dst=/input,readonly
--mount type=bind,src=$ARTIFACTS,dst=/artifacts
```

The host must NOT:

* mount the Docker socket
* use `--privileged`
* forward arbitrary environment variables
* forward host home directory or `.gitconfig`
* forward GitHub tokens or cloud credentials (the runtime doesn't need them)

### Limitations

Docker is the MVP isolation boundary, **not** a claim of perfect
hostile-code containment. Specifically:

* the runtime runs as a non-root user but a determined attacker with
  repo-supplied `setup.py` code can still attempt kernel-exploit
  payloads, container-escape primitives, and resource-exhaustion
  attacks beyond what cgroups enforce
* a malicious `setup.py` invoked via `pip install -e .` runs as the
  runtime UID and can read `/artifacts` (its own output directory)
* a malicious `pytest` plugin loaded via `conftest.py` runs as the
  runtime UID for the duration of the test run

For repos we don't trust at all, the next step is firecracker /
gVisor / a sandboxed microVM. The current runtime is appropriate for
public-open-source repositories whose authors are not adversaries
against our specific audit pipeline.

---

## Network policy

| mode     | default | host may override? |
|----------|---------|--------------------|
| inspect  | `none`  | yes (but: don't)   |
| build    | `enabled` (deps download) | yes |
| test     | `none`  | yes (explicit)     |

The runtime itself never silently enables networking. The host is the
only place that can grant network access.

---

## Artifacts

`/artifacts` always contains:

* `result.json` — the structured Result (always written, even on error)
* per-command `<label>.stdout.log` and `<label>.stderr.log`

For inspect only:

* `python_files.json` — AST-parsed inventory of every `.py` file plus
  its top-level definitions and imports

Filenames are stable. The directory is otherwise empty unless a
specific command produced output.

---

## Repository layout

```
runtime/
  Dockerfile              — pinned python:3.12-slim-bookworm + uv + non-root user
  entrypoint.py           — CLI dispatcher (argparse)
  models.py               — Result schema (stable JSON contract)
  detect.py               — static detection of build / test strategy
  commands/
    _common.py            — subprocess timeout, atomic write, copy helpers
    inspect.py            — static inventory
    build.py              — installable environment
    test.py               — test suite execution
  scripts/
    run-local.sh          — host-side Docker wrapper
  README.md               — this file

tests/runtime/
  fixtures/               — 10 synthetic repositories
  test_detect.py          — detection precedence + ordering
  test_inspect.py         — inspect-mode security + invariants
  test_result_schema.py   — JSON shape stability
  test_timeout.py         — subprocess timeout behaviour

.github/workflows/
  runtime-smoke.yml       — CI: build image + run inspect on a fixture
```

---

## Local quickstart (with Docker)

```bash
# 1. Build the image
docker build -t python-agent-runtime:dev -f runtime/Dockerfile .

# 2. Run inspect against any local repo path
REPO_PATH=/path/to/some/repo
ARTIFACTS_PATH=/tmp/agent-runtime-out
runtime/scripts/run-local.sh inspect

# 3. Inspect the result
cat "${ARTIFACTS_PATH}/result.json" | python3 -m json.tool
```

## Local quickstart (without Docker — inspect only)

Inspect mode is pure-stdlib and runs the same on the host as inside
the container, which makes it convenient for development:

```bash
PYTHONPATH=. python3 runtime/entrypoint.py inspect \
  --repo-path tests/runtime/fixtures/01-pyproject-simple \
  --artifacts-dir /tmp/inspect-out \
  --repo-sha deadbeef
cat /tmp/inspect-out/result.json | python3 -m json.tool
```

Build and test still require the Docker image because they invoke
`pip` / `uv` / `pytest` against the repo, which is exactly what
inspect must not do.

---

## GitHub Actions

`.github/workflows/runtime-smoke.yml` builds the image and runs
inspect against an in-repo fixture, then uploads `result.json` as an
artifact. The same image is reusable for the compliance pipeline.

---

## Non-goals

* Article 12 logic, legal rules, or any compliance check
* AST compliance detectors
* corpus database integration or repository discovery
* GitHub API searching
* Redis / Celery / Kubernetes / vector databases
* LLM calls or model-based classification
* dynamic malware analysis
* browser automation

The compliance engine will consume `result.json` and the artifacts
directory. It will not import this package.
