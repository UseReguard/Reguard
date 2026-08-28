# Article 12(1) Gate 1 — container re-run of the three pinned repos

Date: 2026-08-28 (UTC)
Executor: `--executor container` (frozen repo-runtime image, OCI-runtime-agnostic
via podman on this host)
Image: `python-agent-runtime:dev` (build at 2026-08-28, sha a60f0ccc1876)
Runtime version: `1.0.0`
Requirement: `AI_ACT_12_1_AUTOMATIC_EVENT_LOGGING` v1.3.0
Scenario: `compliance.synthetic.hello`

## Comparison with the v1.3 host-subprocess audit

| Repo                       | Pinned SHA                                     | v1.3 host | Container | Match |
|----------------------------|------------------------------------------------|-----------|-----------|-------|
| SWE-agent/mini-swe-agent   | 25941c89cfbc91eb40b3f8756348c91d9977d57e       | PASS (A)  | PASS (A)  | ✓     |
| he-yufeng/CoreCoder        | a03ef36412e432fc49d972d4007b36ce44ec5d9a       | FAIL (D)  | FAIL (D)  | ✓     |
| HKUDS/nanobot              | 4d204ba077a86dc42225c16f8f90032013ea1969       | FAIL (C)  | FAIL (C)  | ✓     |

Containers used the same adapter, requirement, scenario, and pinned SHAs as
the v1.3 audit. Only the probe execution backend changed: from a per-run
host virtualenv (`--executor subprocess`) to the frozen runtime container
invoked through `reguard.pipeline.container_runner.run_in_container`
(`--executor container`).

## Per-run evidence

`audit/container_gate1/<repo>.json` contains the full structured record
(status, checks, evidence_origins, runtime_version, etc.). The only
field-level differences vs the v1.3 host audit are:

- `framework_artifact_paths` — host tempdir prefix differs
  (`/tmp/cp_work_s9xxlr8v/...` vs the host's old tmpdir)
- `completed_at` / `started_at` / `duration_seconds`

Verdict, recording category, evidence origins, event count, checks, and
PASS/FAIL logic are identical.

## What this confirms (P1 acceptance)

- Real repo execution happens inside the frozen container, not on the host
  during the probe phase.
- The adapter / RequirementTest v1.3.0 / A-E classification / PASS-FAIL
  logic lives entirely outside the container and is reused unchanged.
- Driver invocation: `scripts/compliance-check.py --executor container
  --repo-path <pinned checkout>`.
- Container-backed run_probe path is wired through the orchestrator
  (`run_probe(..., executor="container")` → `_run_probe_container` →
  `container_runner.run_in_container` → runtime `exec` subcommand).
- The runtime is a generic exec primitive; it does not know about
  Article 12(1).
- OCI-runtime discovery is automatic (`podman` first, then `docker`);
  this Gate 1 used podman.
- No LLM credentials were required (deterministic model + stub LLM +
  bus subscribe).
- No Docker socket bind into the container (`/var/run/docker.sock` is
  never mounted).
- Container runs as UID 10001 (non-root).
- Container security flags applied: `--cap-drop ALL`,
  `--security-opt no-new-privileges`, `--pids-limit 256`, `--memory 4g`,
  `--cpus 2`, `--tmpfs /tmp:rw,nosuid,size=2g`.
- `/input` is mounted read-only; `/artifacts` is a writable bind mount.

## Known follow-ups (out of scope for Gate 1)

- Strict two-phase network policy (install=enabled, probe=disabled)
  requires a multi-stage container invocation and is documented as a
  TODO inside `container_runner.py`.
- Container-vs-subprocess artefact equivalence is enforced at the
  verdict level here; a property-style test that checks
  evidence_origins equality across the two backends is a potential
  follow-up.

Per current objective: P2–P6 are NOT executed in this iteration.
