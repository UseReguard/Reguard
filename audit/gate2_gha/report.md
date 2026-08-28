# Article 12(1) Gate 2 — GitHub Actions container reproducibility

Date: 2026-08-28 (UTC)
Executor: `--executor container`, GHA `ubuntu-latest` with the runtime
container image built in-job from `runtime/Dockerfile`.
OCI runtime: docker (the GHA runner default).
Image: `python-agent-runtime:dev` (the build hash is regenerated each
job, the Dockerfile is the source of truth).

## Comparison: GHA container vs local container vs v1.3 host subprocess

| Repo                       | Pinned SHA                                     | v1.3 host | local container | GHA container | Match |
|----------------------------|------------------------------------------------|-----------|-----------------|---------------|-------|
| SWE-agent/mini-swe-agent   | 25941c89cfbc91eb40b3f8756348c91d9977d57e       | PASS (A)  | PASS (A)        | **PASS (A)**  | ✓     |
| he-yufeng/CoreCoder        | a03ef36412e432fc49d972d4007b36ce44ec5d9a       | FAIL (D)  | FAIL (D)        | **FAIL (D)**  | ✓     |
| HKUDS/nanobot              | 4d204ba077a86dc42225c16f8f90032013ea1969       | FAIL (C)  | FAIL (C)        | **FAIL (C)**  | ✓     |

For every repo:

- requirement_version: `1.3.0` (unchanged across all three backends)
- runtime_version: `1.0.0` (unchanged)
- adapter_version: `1.1.0` (unchanged)
- repository SHA: matches pinned value
- recording category: identical to v1.3 host audit (A / C / D)
- verdict: identical
- event count: identical (3 / 3 / 2)
- evidence origins: identical sets
- checks passed: identical
- checks failed: identical

The only differences across backends are timestamps, durations, and
host-tempdir prefixes inside the framework_artifact_paths field
(same as Gate 1 — the `audit/container_gate1/<repo>.json` files are
already in the repo).

`audit/gate2_gha/<repo>.json` contains the exact compliance-result.json
as uploaded by the GHA workflow.

## CI-specific deltas

The first few attempts produced `ERROR` rather than `PASS/FAIL`.
Three problems were diagnosed and fixed in P2:

1. **`failed to map segment from shared object`** when Python tried
   to `dlopen` `_pydantic_core.so`. The runtime container runs as
   UID 10001; if pip cannot write to
   `/usr/local/lib/python3.12/site-packages` it falls back to
   `/tmp/.local/lib/...`. On the GitHub Actions runner the default
   tmpfs that the OCI runtime builds on top of `/tmp` refuses mmap
   of shared objects written there, killing the import.
   Fix: chown `/usr/local` to the runtime user inside
   `runtime/Dockerfile`, so pip installs land on the container's
   writable overlay (where mmap behaves normally).
2. **`unknown key 'U=true'` mount option** when the container was
   run via docker (the GHA runner default). The `:U=true` suffix
   is podman-specific; docker rejects it as malformed.
   Fix: gate the suffix on `runtime == "podman"`; docker sees a
   plain bind mount and uses its default mount semantics, which
   already satisfy --user-based chown semantics.
3. **`Runtime selects 'image not found'` because podman was first on
   PATH**. Rootless podman on the GHA runner has a separate image
   store and falls back to registry pulls when the docker-built
   image is not in its store.
   Fix: container_runner now prefers `docker`, with
   `REGUARD_RUNTIME_BINARY` env override. The GHA workflow sets
   `REGUARD_RUNTIME_BINARY=docker` explicitly so the image built in
   the earlier step is the one the runner later launches.

Also: container_runner now passes a sum of `install_timeout_seconds`
+ `run_timeout_seconds` as the runtime's `--timeout-seconds` (was
`run_timeout_seconds` only). The runtime treats that flag as a total
budget for the whole exec mode (setup + install + exec). The host
subprocess path uses both budgets separately and the previous 120s
budget was tight on cold GHA runners for the larger transitive
dep trees (mini-swe-agent pulls litellm / datasets / huggingface).

Container_runner additionally stitches the *tail* of each per-step
log (00_setup / 01_install / 02_exec) into the surfaced stderr so a
failing inner step no longer looks like a generic `exit 1`.

## What this confirms (P2 acceptance)

- The container-backed Article 12(1) pipeline reproduces in GHA.
- The same engine, same RequirementTest (v1.3.0), same adapter
  versions, same pinned SHAs produce the same verdicts.
- No CI-specific compliance logic was added — the same
  `compliance-check.py` runs in both environments.
- The runtime is built from `runtime/Dockerfile` in-job; no
  external image registry dependency.
- The same compliance-result.json schema is produced in both
  environments.

No semantic divergence between GHA container and local container
or v1.3 host. P2 acceptance criteria met.
