"""Subcommand implementations for repo-runtime.

Each module exposes:

    def run(*, repo_path, artifacts_dir, timeout_seconds, **kwargs) -> Result:
        ...

`repo_path` is the read-only host checkout. `artifacts_dir` is the
writable directory where the runtime writes result.json plus per-command
stdout/stderr logs.
"""
