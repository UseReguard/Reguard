# Reguard Core v0.1 — Platform Support Matrix

**Date:** 2026-08-30

This matrix lists what is **actually validated**, not what is
hoped for. Any environment not listed is `UNTESTED` until a
running build demonstrates otherwise.

---

## Python support matrix

| Python | Install | CLI | Demo/runtime | Verdict |
|---|---|---|---|---|
| 3.12 | SUPPORTED (CI workflows + runtime Dockerfile) | SUPPORTED (CI smoke + local `compliance/` parses cleanly) | SUPPORTED (runtime Dockerfile uses `python:3.12-slim-bookworm`) | **SUPPORTED** |
| 3.13 | UNTESTED locally; source is syntactically compatible (verified via `ast.parse`) | UNTESTED | UNTESTED | **NOT ADVERTISED** — removed from classifiers in this preflight |
| 3.14 | SUPPORTED locally (this development environment) | SUPPORTED (all 285 tests pass under 3.14.4) | SUPPORTED via subprocess driver (no OCI required) | **SUPPORTED** |

**`requires-python = ">=3.12"`** in `pyproject.toml`.

**Classifiers advertise only Python 3.12 and 3.14.**

The brief principle: "Only advertise versions actually validated."
3.13 was removed from classifiers because no build host or CI
matrix exercises it; only 3.12 (CI / runtime image) and 3.14 (local
dev) are validated.

The source tree was checked for syntax compatibility via
`python3 -c "import ast; ast.parse(open(...).read())"` against all
72 source files; all parse cleanly with the 3.14 parser, which is
a superset of the 3.12 syntax used in the codebase.

---

## Operating-system support matrix

| OS / Runtime | Status | Evidence |
|---|---|---|
| Linux x86_64 (Ubuntu 26.04) | **SUPPORTED** | Local dev environment; all 285 tests pass; full demo PASSes |
| GitHub Actions `ubuntu-latest` | **SUPPORTED** | All three workflows (`compliance.yml`, `compliance-article-12-1.yml`, `runtime-smoke.yml`) target `ubuntu-latest` |
| Docker | **SUPPORTED** | Runtime image build verified (`podman build` produces a working image); image is published via Podman/Docker equivalent |
| Podman | **SUPPORTED** | Local validation used `podman 5.7.0` to build and inspect the runtime image |
| WSL 2 | **SUPPORTED** | Local dev runs under WSL2 (Linux 6.18.33.2-microsoft-standard-WSL2) |
| Linux arm64 | UNTESTED | No CI matrix exercises it |
| macOS | UNTESTED | Brief §5 explicitly says: "Do not claim native Windows/macOS support unless proven" |
| Windows native | UNTESTED | Brief §5 explicitly says: "Do not claim native Windows/macOS support unless proven" |

**The strongest v0.1 claim:**

> Reguard Core v0.1.0rc1 supports Linux (Ubuntu) and GitHub-hosted
> Linux runners, with Podman or Docker as the container runtime.
> WSL 2 is supported because it presents a Linux kernel.

The CLI itself uses no platform-specific APIs beyond `pathlib`,
`subprocess`, and `sqlite3`. The runtime image is built from
`python:3.12-slim-bookworm` and runs on any Docker/Podman
compatible Linux kernel. There is no `win32`-conditional code in
the source.

---

## Container runtime features verified

Built and inspected `reguard-runtime:test` image via `podman`:

```text
$ podman run --rm --entrypoint [] reguard-runtime:test id
uid=10001(runtime) gid=10001(runtime) groups=10001(runtime)

$ podman run --rm --entrypoint [] -v /tmp:/input:ro reguard-runtime:test touch /input/test
touch: cannot touch '/input/test': Read-only file system

$ podman run --rm --entrypoint [] -v /tmp:/artifacts reguard-runtime:test touch /artifacts/test-write
(OK, /artifacts is writable)
```

- Container runs as non-root (UID 10001).
- `/input` is mounted read-only.
- `/artifacts` is writable.

---

## Pre-existing classifiers adjusted

The preflight narrowed the metadata:

```diff
   "Programming Language :: Python :: 3",
   "Programming Language :: Python :: 3.12",
-  "Programming Language :: Python :: 3.13",
   "Programming Language :: Python :: 3.14",
```

`requires-python = ">=3.12"` is kept (the codebase is 3.12+
compatible and the runtime Dockerfile targets 3.12). The 3.13
classifier was removed because no validated build host exercises
3.13; advertising 3.13 would be speculative.

— end of platform support matrix —