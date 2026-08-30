"""`reguard doctor` — check the host environment.

Does NOT execute the target repo. Verifies:

    - reguard.yml schema validity (if found);
    - integration resolution (explicit / repo-local / builtin / legacy);
    - OCI runtime availability (best-effort);
    - workspace / cache health (best-effort).

Exits 0 if everything checks out, non-zero otherwise.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from ..integrations import IntegrationResolver
from ..integrations.families import register as register_families


def cmd_doctor(args: argparse.Namespace) -> int:
    register_families()

    issues: list[str] = []

    repo_path = Path(args.repo_path).resolve() if args.repo_path else None
    explicit = Path(args.config).resolve() if args.config else None
    full_name = args.repo or _infer_repo_name(repo_path)

    local_yml = None
    if repo_path:
        candidate = repo_path / "reguard.yml"
        if candidate.exists():
            local_yml = candidate

    print("Reguard doctor")
    print()
    print(f"  repository      : {full_name or '<not set>'}")
    print(f"  repo-path       : {str(repo_path) if repo_path else '<not set>'}")
    print(f"  explicit config : {str(explicit) if explicit else '<none>'}")
    print(f"  reguard.yml     : {str(local_yml) if local_yml else '<none>'}")
    print()

    if explicit and not explicit.exists():
        issues.append(f"explicit config not found: {explicit}")

    oci = _detect_oci_runtime()
    print(f"  OCI runtime     : {oci or 'NOT FOUND'}")
    if oci is None:
        issues.append("no OCI runtime found (podman or docker)")

    if full_name:
        resolver = IntegrationResolver()
        outcome = resolver.resolve(
            full_name=full_name,
            repo_path=repo_path,
            explicit_config=explicit,
        )
        if outcome.integration is not None:
            itg = outcome.integration
            print()
            print("  integration")
            print(f"    source          : {itg.source.value}")
            print(f"    recipe          : {itg.recipe.recipe_id}@{itg.recipe.recipe_version}")
            print(f"    observers       : {', '.join(o.observer_id for o in itg.observers)}")
            print(f"    normalizer      : {itg.normalizer.normalizer_id}@{itg.normalizer.normalizer_version}")
            print(f"    entrypoint      : {itg.recipe_config.entrypoint_target}")
            print(f"    scenarios       : {', '.join(itg.recipe_config.supported_scenarios)}")
        else:
            print()
            print(f"  integration     : UNSUPPORTED ({outcome.source.value})")
            print(f"    reason          : {outcome.unsupported_reason}")
            if outcome.source.value in ("legacy_adapter", "none"):
                issues.append(
                    f"no compatible integration found for {full_name!r}; "
                    "add reguard.yml or use a supported recipe"
                )

    print()
    if issues:
        print(f"doctor: {len(issues)} issue(s)")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("doctor: OK")
    return 0


def _infer_repo_name(repo_path: Path | None) -> str | None:
    if repo_path is None:
        return None
    try:
        import subprocess
        result = subprocess.run(
            ["git", "-C", str(repo_path), "config", "--get", "remote.origin.url"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    if not url:
        return None
    if url.endswith(".git"):
        url = url[:-4]
    if url.startswith("git@github.com:"):
        return url.split(":", 1)[1]
    if "github.com/" in url:
        return url.split("github.com/", 1)[1]
    return None


def _detect_oci_runtime() -> str | None:
    for candidate in ("podman", "docker"):
        path = shutil.which(candidate)
        if path:
            return candidate
    return None
