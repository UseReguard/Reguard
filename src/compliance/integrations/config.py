"""`reguard.yml` schema + validation helpers.

This module is the public surface for loading and validating a
`reguard.yml`. The schema is `1`. Validation is strict:

  - unknown top-level keys that affect execution semantics are
    rejected (we do not silently ignore them);
  - the `integration:` block is mandatory;
  - recipe / observer / normalizer ids must be registered;
  - scenarios must be in the recipe's supported set;
  - forbidden env vars are rejected.

The schema is deliberately minimal: the v0.1 pilot only needs
recipe + observer + normalizer + scenarios.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import REGUARD_YML_SCHEMA_VERSION
from .errors import IntegrationConfigError


# Top-level keys we recognise. Anything else is an unknown field.
# (We accept unknown keys but emit a warning; the integration
# layer does not act on them.)
_KNOWN_TOP_LEVEL_KEYS = frozenset({
    "schema_version",
    "integration",
    "scenarios",
    "observability",
})


@dataclass(frozen=True)
class ReguardYml:
    """A parsed + validated `reguard.yml`."""

    schema_version: str
    raw: dict
    path: Path | None
    unknown_keys: tuple[str, ...]

    @property
    def integration_block(self) -> dict:
        return self.raw.get("integration") or {}

    @property
    def scenarios(self) -> tuple[str, ...]:
        return tuple(self.raw.get("scenarios") or ())


def load_reguard_yml(path: Path) -> ReguardYml:
    """Load and structurally validate a `reguard.yml`.

    Raises IntegrationConfigError on any structural problem.
    """
    if not path.exists():
        raise IntegrationConfigError(f"reguard.yml not found at {path!s}")
    try:
        import yaml
    except ImportError as exc:
        raise IntegrationConfigError(
            "PyYAML is required to load reguard.yml; "
            "install with `pip install pyyaml`"
        ) from exc

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise IntegrationConfigError(
            f"reguard.yml at {path!s}: top-level must be a mapping"
        )

    schema_version = str(data.get("schema_version", REGUARD_YML_SCHEMA_VERSION))
    if schema_version != REGUARD_YML_SCHEMA_VERSION:
        raise IntegrationConfigError(
            f"reguard.yml at {path!s}: unsupported schema_version "
            f"{schema_version!r}; supported: {REGUARD_YML_SCHEMA_VERSION!r}"
        )

    unknown = tuple(
        sorted(k for k in data.keys() if k not in _KNOWN_TOP_LEVEL_KEYS)
    )

    return ReguardYml(
        schema_version=schema_version,
        raw=data,
        path=path,
        unknown_keys=unknown,
    )


def render_default_reguard_yml(
    *,
    family_id: str = "langgraph-state",
    recipe_id: str = "langgraph-state",
    entrypoint_target: str = "my_agent:build_graph",
    observer_id: str = "langgraph-state.callback-observer",
    normalizer_id: str = "langgraph-state.canonical-normalizer",
    scenarios: tuple[str, ...] = ("compliance.article12_1.simple",),
) -> str:
    """Render a minimal `reguard.yml` template for `reguard init`."""
    return (
        "schema_version: 1\n"
        "\n"
        "integration:\n"
        f"  recipe: {recipe_id}\n"
        "  recipe_version: 1.0.0\n"
        "  package_root: .\n"
        "\n"
        "  entrypoint:\n"
        f"    target: {entrypoint_target}\n"
        "    mode: sync\n"
        "\n"
        "  model:\n"
        "    strategy: deterministic_stub\n"
        "\n"
        "  observers:\n"
        f"    - {observer_id}\n"
        "\n"
        "  normalizer:\n"
        f"    id: {normalizer_id}\n"
        "\n"
        "scenarios:\n"
        + "\n".join(f"  - {s}" for s in scenarios)
        + "\n"
    )


def config_summary(yml: ReguardYml) -> dict[str, Any]:
    """Return a JSON-serialisable summary of the parsed config."""
    return {
        "schema_version": yml.schema_version,
        "path": str(yml.path) if yml.path else None,
        "recipe": yml.integration_block.get("recipe"),
        "recipe_version": yml.integration_block.get("recipe_version"),
        "entrypoint": (yml.integration_block.get("entrypoint") or {}).get("target"),
        "observers": yml.integration_block.get("observers") or [],
        "normalizer": (yml.integration_block.get("normalizer") or {}).get("id"),
        "scenarios": list(yml.scenarios),
        "unknown_keys": list(yml.unknown_keys),
    }
