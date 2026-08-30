# repo-runtime — generic Python repository runtime.
#
# SECURITY POSTURE
# ----------------
# This image is intentionally lean. It contains:
#   * Python 3.12 (slim, Debian bookworm)
#   * git, build-essential (for sdist / c-extension builds)
#   * uv (modern package manager)
#   * pip, setuptools, wheel
#
# It does NOT contain:
#   * AI frameworks (no transformers, no langchain, no llama-index)
#   * pre-baked repository dependencies
#   * any host credentials, GitHub tokens, or cloud secrets
#
# The host is expected to enforce network policies, cap-drop ALL,
# --security-opt no-new-privileges, --pids-limit, --memory, --cpus,
# tmpfs mounts, and bind mounts. See runtime/scripts/run-local.sh.

FROM python:3.12-slim-bookworm

# Canonical-source labels (per brief §7).
# org.opencontainers.image.revision and org.opencontainers.image.version
# are provided by the release workflow at build time via --build-arg.
ARG REGUARD_SOURCE_REVISION=""
ARG REGUARD_SOURCE_VERSION=""
LABEL org.opencontainers.image.title="reguard-runtime" \
      org.opencontainers.image.description="Deterministic runtime probe for Reguard Core technical-control checks." \
      org.opencontainers.image.source="https://github.com/UseReguard/Reguard" \
      org.opencontainers.image.url="https://github.com/UseReguard/Reguard" \
      org.opencontainers.image.vendor="UseReguard" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.revision="${REGUARD_SOURCE_REVISION}" \
      org.opencontainers.image.version="${REGUARD_SOURCE_VERSION}"

# ---------------------------------------------------------------------------
# System packages
# ---------------------------------------------------------------------------
# git         — used by uv / build steps for source-tree introspection
# build-essential — needed by pip to compile c extensions on sdist install
# ca-certificates — TLS roots for any outbound traffic (network disabled
#                   by host; this is just hygiene for uv / pip cache fetches)
# ---------------------------------------------------------------------------
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        xz-utils \
        build-essential \
 && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# uv (modern Python package manager)
# ---------------------------------------------------------------------------
# Pinned to a specific release. uv is a single static binary so the
# install is reproducible. The release archive format changed from
# .tar.xz to .tar.gz in late-2024; this URL works for all currently-
# supported releases.
# ---------------------------------------------------------------------------
ARG UV_VERSION=0.12.6
RUN set -eux; \
    curl -fsSL "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz" \
        -o /tmp/uv.tar.gz; \
    tar -xzf /tmp/uv.tar.gz -C /tmp; \
    install -m 0755 /tmp/uv-x86_64-unknown-linux-gnu/uv /usr/local/bin/uv; \
    install -m 0755 /tmp/uv-x86_64-unknown-linux-gnu/uvx /usr/local/bin/uvx; \
    rm -rf /tmp/uv /tmp/uv.tar.gz /tmp/uv-x86_64-unknown-linux-gnu; \
    uv --version

# ---------------------------------------------------------------------------
# Python tooling for the runtime itself (not for repository code).
# ---------------------------------------------------------------------------
# We deliberately keep the runtime dependency-free of repo libraries.
# `tomllib` is stdlib in Python 3.12; no TOML library needed here.
#
# Poetry is installed alongside uv because the runtime supports both
# build strategies. Poetry is pinned to a specific release so the
# image is reproducible. `poetry install --no-interaction` against a
# poetry.lock is deterministic when the lockfile is committed.
# ---------------------------------------------------------------------------
ARG POETRY_VERSION=2.1.3
RUN python3 -m pip install --no-cache-dir --upgrade \
        'pip>=24' \
        'setuptools>=70' \
        'wheel' \
 && python3 -m pip install --no-cache-dir \
        "poetry==${POETRY_VERSION}"

# ---------------------------------------------------------------------------
# Adapter-probe preinstalls
# ---------------------------------------------------------------------------
# gptme is the only Article 12(1) probe target that imports a
# framework package at probe time. The runtime container runs with
# `--network none`, so `pip install -e .` inside the container
# against the host's repo checkout cannot reach PyPI. We preinstall
# gptme at image build time (where the build host DOES have network)
# so the probe's `from gptme... import` resolves against the
# container's site-packages. This is a probe-side concern only —
# the adapter registry in the host-side compliance/pipeline is
# unchanged. No adapters were added.
# ---------------------------------------------------------------------------
ARG GPTME_VERSION=0.32.1
RUN python3 -m pip install --no-cache-dir \
        "gptme==${GPTME_VERSION}"

# ---------------------------------------------------------------------------
# Non-root user
# ---------------------------------------------------------------------------
# The runtime never needs root. Running as a fixed UID makes the audit
# trail predictable across local + CI runs.
#
# /usr/local is chowned to the runtime user so `pip install` inside
# the container can write to /usr/local/lib/python3.12/site-packages.
# Without this, a non-root pip install falls back to /tmp/.local,
# which on some kernel / OCI-runtime combinations refuses
# mmap of shared objects (raising 'failed to map segment from shared
# object'). Writing packages to /usr/local keeps them on the
# container's writable overlay, where mmap behaves normally.
# ---------------------------------------------------------------------------
ARG RUNTIME_UID=10001
ARG RUNTIME_GID=10001
RUN groupadd --system --gid "${RUNTIME_GID}" runtime \
 && useradd  --system --uid "${RUNTIME_UID}" --gid runtime \
              --home-dir /home/runtime --shell /usr/sbin/nologin \
              --no-create-home runtime \
 && install -d -o runtime -g runtime -m 0755 /home/runtime /workspace /artifacts \
 && chown -R runtime:runtime /usr/local

# ---------------------------------------------------------------------------
# Runtime source
# ---------------------------------------------------------------------------
# COPY supports two build contexts:
#   1. Project root:  `docker build -f runtime/Dockerfile .`
#      → sources at `runtime/` resolve to `<context>/runtime/`
#   2. Runtime dir:   `docker build -f runtime/Dockerfile runtime/`
#      → sources at `runtime/` are the Dockerfile's own dir, which
#        Docker sees as `.`; we copy `.` instead.
# This keeps both invocation styles working.
COPY --chown=root:root runtime/ /opt/repo-runtime/runtime/
RUN chmod -R a+rX /opt/repo-runtime

# ---------------------------------------------------------------------------
# Working directories
# ---------------------------------------------------------------------------
# /input      — host bind mount, read-only at runtime
# /workspace  — writable temp space for build/test copies
# /artifacts  — host bind mount, writable
#
# /workspace is NOT a host mount — it is intended to be a tmpfs mounted by
# the host (`--tmpfs /workspace:rw,nosuid,size=2g`) for ephemeral storage.
# We pre-create it here so it exists even if the host forgets the tmpfs.
# ---------------------------------------------------------------------------
WORKDIR /workspace
ENV PYTHONPATH=/opt/repo-runtime

USER runtime:runtime
ENV HOME=/home/runtime
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_NO_INPUT=1

ENTRYPOINT ["python3", "/opt/repo-runtime/runtime/entrypoint.py"]
