# Reguard Core v0.1 — Packaging Audit

**Date:** 2026-08-30
**Release candidate:** `Reguard 0.1.0rc1`

---

## 1. Public install path

`Reguard` (the Python distribution name) → CLI entrypoint `reguard`.

Preferred end-state after PyPI publication:

```bash
pipx install reguard
# or
uvx reguard --version
```

Until publication, the wheel at
`dist/reguard-0.1.0rc1-py3-none-any.whl` is the canonical install
target:

```bash
pip install reguard-0.1.0rc1-py3-none-any.whl
```

## 2. Distribution identity

| Field | Value |
|---|---|
| distribution_name | `Reguard` |
| python_package_name | `compliance` (the package) |
| CLI entrypoint | `reguard` |
| version | `0.1.0rc1` |
| Python | `>=3.12` |
| License | `AGPL-3.0-only` |

PyPI normalizes the distribution name to lowercase (`reguard`)
when published; the source-of-truth name in `pyproject.toml` is
`Reguard`.

## 3. Build artefacts

```text
dist/reguard-0.1.0rc1-py3-none-any.whl      205,487 bytes
dist/reguard-0.1.0rc1.tar.gz                170,819 bytes
```

SHA-256 hashes:

```text
7b3e132ff9f6d779a9262307d5a5b54ba71e1a261a69fe60741799ac949a21ea  reguard-0.1.0rc1-py3-none-any.whl
fbd967cca3f58a8b240d6633a19fa0193e92f03ec3f61528770d3935bb360145  reguard-0.1.0rc1.tar.gz
```

Build command:

```bash
python -m build --sdist --wheel
```

## 4. Package contents

The wheel contains 78 entries. Top-level structure:

```text
compliance/                                  # runtime package
  cli/                                       # top-level CLI
  integrations/                              # three-abstraction model
    families/langgraph_state/                # Family A pilot
    integrations_builtin.py                  # built-in manifests
  adapters/                                  # frozen-five legacy
  pipeline/                                  # evidence + result types
  requirements/ai_act/article_12_1.py        # frozen requirement v1.4.0
  corpus_runner/                             # corpus orchestration (out of v0.1 scope)
reguard-0.1.0rc1.dist-info/                  # PEP 427 metadata
  METADATA
  WHEEL
  entry_points.txt
  RECORD
```

No `.env`, no `compliance.db`, no `.git`, no source cache, no
workspace, no audit folder, no credentials, no Obsidian vault.

## 5. Runtime dependencies

| Package | Required version | License |
|---|---|---|
| `sqlalchemy` | `>=2.0` | MIT |
| `httpx` | `>=0.27` | BSD-3-Clause |
| `pydantic` | `>=2.0` | MIT |
| `PyYAML` | `>=6.0` | MIT |

All transitive dependencies pulled by `pip install` (in clean venv):

- `sqlalchemy 2.0.52`
- `httpx 0.28.1`
- `pydantic 2.13.5`
- `PyYAML 6.0.3`
- `typing-extensions` (pydantic dep)
- `annotated-types` (pydantic dep)
- `anyio` (httpx dep)
- `certifi` (httpx dep)
- `h11` (httpx dep)
- `httpcore` (httpx dep)
- `idna` (httpx dep)
- `sniffio` (httpx dep)

All dependencies are MIT or BSD-3-Clause; no copyleft
transitive deps.

## 6. Build / source-tree inclusion

The wheel does NOT include:

- `tests/` (correct — tests are not runtime)
- `audit/` (correct — internal-only)
- `data/` (correct — corpus-only)
- `docs/` (correct — informational only)
- `examples/` (correct — informational only)
- `migrations/` (correct — operational only)
- `notes/` (correct — internal-only)
- `out/` (correct — runtime output)
- `runtime/` (correct — internal sandbox scripts)
- `scripts/` (correct — internal maintenance)
- `.github/` (correct — workflow only)

The sdist DOES include `tests/` and `examples/` (and the
`audit/` directory at the repository root) because they are
part of the source tree. The wheel correctly excludes them.

## 7. Source-cache and workspace

The `corpus_runner/cache/` and `corpus_runner/workspace/`
modules in the wheel contain only Python source code; they
do not bundle any user-specific data or paths. Runtime
caches live under `~/.reguard/` and are NOT shipped.

## 8. License files in wheel

The wheel includes `LICENSE` via `setuptools.package-data`
because `[project] license = { text = "AGPL-3.0-only" }` is
declared in `pyproject.toml` and the LICENSE file lives at
the repository root.

## 9. Conclusion

**READY.** The wheel is self-contained; installing the wheel
in a fresh virtualenv gives a fully functional `reguard` CLI
with no source checkout required.

— end of packaging audit —
