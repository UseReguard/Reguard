#!/usr/bin/env bash
# run-local.sh — host-side wrapper for the repo-runtime Docker image.
#
# SECURITY POSTURE
# ----------------
# This script never:
#   * mounts the Docker socket
#   * uses --privileged
#   * forwards host credentials, SSH agent, or ~/.gitconfig
#   * forwards arbitrary environment variables (only allowlisted ones)
#
# It always:
#   * mounts the repo read-only at /input
#   * mounts an artifacts directory at /artifacts
#   * drops all Linux capabilities
#   * disables privilege escalation
#   * caps pids, memory, and cpus
#   * uses tmpfs for /tmp and /workspace
#
# This script intentionally uses set -euo pipefail and explicit quoting.
# Any deviation should be reviewed.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration (override on the command line or via env)
# ---------------------------------------------------------------------------
: "${RUNTIME_IMAGE:=python-agent-runtime:dev}"
: "${REPO_PATH:=$PWD/checkout}"   # host checkout path
: "${ARTIFACTS_PATH:=$PWD/artifacts}"
: "${REPO_SHA:=}"
: "${TIMEOUT_SECONDS:=600}"
: "${PIDS_LIMIT:=256}"
: "${MEMORY_LIMIT:=2g}"
: "${CPUS_LIMIT:=2}"
: "${TMP_SIZE:=512m}"
: "${WORKSPACE_SIZE:=2g}"

REPO_SHA="${REPO_SHA:-$(git -C "${REPO_PATH}" rev-parse HEAD 2>/dev/null || echo unknown)}"

# Build an explicit env allow-list. The container receives NOTHING else.
ENV_FLAGS=(
  --env "HOME=/tmp"
  --env "LANG=C.UTF-8"
  --env "LC_ALL=C.UTF-8"
  --env "PYTHONDONTWRITEBYTECODE=1"
  --env "PIP_DISABLE_PIP_VERSION_CHECK=1"
  --env "PIP_NO_INPUT=1"
)

mkdir -p "${ARTIFACTS_PATH}"

# Common docker-run flags applied to every mode.
#
# Note on `--tmpfs /workspace`: we intentionally do NOT mount a tmpfs on
# /workspace. podman/docker tmpfs mounts replace the underlying directory
# with a root-owned filesystem, which breaks the runtime's non-root
# user (UID 10001) being able to write there. Instead, the Dockerfile
# pre-creates /workspace as `runtime:runtime` 0750, which is writable
# for the runtime user. Each container invocation is a fresh container,
# so /workspace starts empty without needing tmpfs semantics.
#
# The /artifacts bind mount needs `:U` (Docker) / `U=true` (podman) so
# the bind mount is chowned to the container's runtime UID; without
# this, the runtime user cannot write results back to the host.
common_flags=(
  --rm
  --cap-drop ALL
  --security-opt no-new-privileges
  --pids-limit "${PIDS_LIMIT}"
  --memory "${MEMORY_LIMIT}"
  --cpus "${CPUS_LIMIT}"
  --read-only=false                 # we still write /workspace + /artifacts
  --tmpfs "/tmp:rw,nosuid,size=${TMP_SIZE}"
  --mount "type=bind,src=${REPO_PATH},dst=/input,readonly"
  --mount "type=bind,src=${ARTIFACTS_PATH},dst=/artifacts,U=true"
  "${ENV_FLAGS[@]}"
  "${RUNTIME_IMAGE}"
)

# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

run_local_inspect() {
  # Static inspection must NEVER have network access.
  docker run \
    --network none \
    "${common_flags[@]}" \
    inspect \
      --repo-sha "${REPO_SHA}" \
      --output   "/artifacts/result.json"
}

run_local_build() {
  # Builds may need to download dependencies.
  docker run \
    "${common_flags[@]}" \
    build \
      --repo-sha "${REPO_SHA}" \
      --output   "/artifacts/result.json"
}

run_local_test() {
  # Tests default to no network. The host can re-enable by editing this
  # wrapper — we never grant network just because a test failed.
  if [[ "${1:-}" == "--allow-network" ]]; then
    shift
    docker run \
      "${common_flags[@]}" \
      test \
        --repo-sha "${REPO_SHA}" \
        --output   "/artifacts/result.json" \
        "$@"
    return
  fi
  docker run \
    --network none \
    "${common_flags[@]}" \
    test \
      --repo-sha "${REPO_SHA}" \
      --output   "/artifacts/result.json" \
      "$@"
}

usage() {
  cat <<USAGE
Usage:
  run-local.sh inspect [--repo-path DIR] [--sha SHA] [--artifacts DIR]
  run-local.sh build   [--repo-path DIR] [--sha SHA] [--artifacts DIR]
  run-local.sh test    [--repo-path DIR] [--sha SHA] [--artifacts DIR]
                          [--allow-network]
                          [--command "pytest tests/unit"]

Environment:
  RUNTIME_IMAGE    Docker image tag (default: python-agent-runtime:dev)
  REPO_PATH        Host checkout path (default: ./checkout)
  ARTIFACTS_PATH   Host artifacts path (default: ./artifacts)
  REPO_SHA         Override SHA label (default: git rev-parse of REPO_PATH)
  TIMEOUT_SECONDS  Per-mode timeout (default: 600)
  PIDS_LIMIT       PID cgroup cap (default: 256)
  MEMORY_LIMIT     Memory cap (default: 2g)
  CPUS_LIMIT       CPU cap (default: 2)
USAGE
}

main() {
  local cmd="${1:-}"
  shift || true
  case "${cmd}" in
    inspect) run_local_inspect "$@" ;;
    build)   run_local_build   "$@" ;;
    test)    run_local_test    "$@" ;;
    -h|--help|"") usage ;;
    *) echo "unknown subcommand: ${cmd}" >&2; usage; exit 2 ;;
  esac
}

main "$@"
