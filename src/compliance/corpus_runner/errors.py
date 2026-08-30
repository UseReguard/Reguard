"""Machine-readable infrastructure error classification.

A corpus-runner attempt records one of these `error_class` tokens.
The compliance verdict remains the five-state RunStatus; this layer
adds orchestration-only diagnostics so the 20-repo gate can report
e.g. `CONTAINER_START_ERROR=2, INSTALL_ERROR=5, PROBE_ERROR=1`.

The classifier is also responsible for the retry policy. Only
transient infrastructure failures (class names ending with
`_TRANSIENT` or flagged RETRYABLE below) are candidates for
automatic retry; everything else is terminal.

The classifier does NOT change v1.4.0 contract semantics. It is
purely additive orchestration metadata.
"""
from __future__ import annotations


class TerminalizationConflict(Exception):
    """Raised by `persistence.terminalize_job` when an attempt is
    made to terminalise an evaluation_job with a *different*
    compliance_status than the one already persisted.

    No silent overwrite: a successful retry with the same payload is
    a no-op; a retry with a different payload raises this so the
    caller can surface a deterministic INTERNAL_SCHEDULER_ERROR
    attempt error rather than letting PASS ↔ PASS↔FAIL corruption
    land silently in the DB.
    """

# Canonical error classes. New codes are added here when a new
# failure mode is observed in the corpus gates.
SHA_RESOLUTION_ERROR = "SHA_RESOLUTION_ERROR"
CLONE_ERROR = "CLONE_ERROR"
CHECKOUT_ERROR = "CHECKOUT_ERROR"
CONTAINER_START_ERROR = "CONTAINER_START_ERROR"
INSTALL_ERROR = "INSTALL_ERROR"
PROBE_ERROR = "PROBE_ERROR"
ADAPTER_ERROR = "ADAPTER_ERROR"
EVIDENCE_SCHEMA_ERROR = "EVIDENCE_SCHEMA_ERROR"
TIMEOUT = "TIMEOUT"
INTERNAL_SCHEDULER_ERROR = "INTERNAL_SCHEDULER_ERROR"
SKIPPED_UNSUPPORTED_SCENARIO = "SKIPPED_UNSUPPORTED_SCENARIO"

# Retry policy: only infrastructure failures in this set are
# retried automatically. Compliance statuses
# (PASS / FAIL / UNKNOWN / UNSUPPORTED) are NEVER retried.
RETRYABLE_ERROR_CLASSES: frozenset[str] = frozenset({
    CONTAINER_START_ERROR,   # transient: OCI runtime hiccup
    TIMEOUT,                 # transient: host pressure
})


def is_retryable(error_class: str | None) -> bool:
    """Return True if a given error class may be retried.

    Compliance verdicts (PASS / FAIL / UNKNOWN / UNSUPPORTED)
    have no error_class and therefore never retry."""
    if not error_class:
        return False
    return error_class in RETRYABLE_ERROR_CLASSES


def classify_probe_status(probe_status: str | None) -> str:
    """Map orchestrator probe_status values to a runner-level
    error class. probe_status == 'ok' yields an empty string
    (no error class)."""
    if probe_status is None or probe_status == "ok":
        return ""
    mapping = {
        "probe_failed": PROBE_ERROR,
        "no_trajectory": PROBE_ERROR,
        "adapter_raised": ADAPTER_ERROR,
    }
    return mapping.get(probe_status, PROBE_ERROR)


def classify_compliance_error(compliance_status: str | None) -> str:
    """Compatibility bridge: an ERROR compliance_status maps to
    PROBE_ERROR for diagnostics."""
    if compliance_status == "ERROR":
        return PROBE_ERROR
    return ""
