"""RepositoryIntegration — the resolved (Recipe, ObserverSet,
Normalizer) tuple ready to drive one run.

The `IntegrationResolver` turns a `reguard.yml` (or built-in
manifest) plus the optional `--config` CLI flag into a
RepositoryIntegration. Resolution precedence:

    1. explicit --config <path>
    2. repository-local reguard.yml
    3. built-in integration manifest (integrations/<repo>.yml)
    4. legacy RepoAdapter (ADAPTER_REGISTRY fallback, for the
       five frozen Article 12(1) repos only)
    5. UNSUPPORTED
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .recipe import ExecutionRecipe, RecipeConfig
from .observer import ObserverSet
from .normalizer import Normalizer
from .errors import (
    IntegrationConfigError,
    UnknownRecipeError,
    UnknownObserverError,
    UnknownNormalizerError,
    ForbiddenEnvError,
    UnsupportedScenarioError,
)
from .observer import get_observer
from .normalizer import get_normalizer
from .recipe import get_recipe


class ResolutionSource(str, Enum):
    EXPLICIT_CONFIG = "explicit_config"
    REPO_LOCAL_YML = "repo_local_yml"
    BUILTIN_MANIFEST = "builtin_manifest"
    LEGACY_ADAPTER = "legacy_adapter"
    NONE = "none"


@dataclass(frozen=True)
class RepositoryIntegration:
    """The resolved (recipe, observers, normalizer) for one repo."""

    full_name: str
    recipe: ExecutionRecipe
    recipe_config: RecipeConfig
    observers: tuple[ObserverSet, ...]
    normalizer: Normalizer
    source: ResolutionSource
    config_path: Path | None = None
    legacy_adapter_name: str | None = None

    def is_legacy(self) -> bool:
        return self.source == ResolutionSource.LEGACY_ADAPTER


@dataclass(frozen=True)
class BuiltinManifest:
    """The minimal built-in integration manifest.

    Mirrors the `reguard.yml` schema but lives in
    `integrations/<repo>.yml` and is shipped with Reguard.
    """

    full_name: str
    integration_block: dict


@dataclass(frozen=True)
class ResolverOutcome:
    """The outcome of resolution: either a RepositoryIntegration,
    or a structured UNSUPPORTED."""

    integration: RepositoryIntegration | None
    unsupported_reason: str | None = None
    source: ResolutionSource = ResolutionSource.NONE


class IntegrationResolver:
    """Resolves a target repository to a RepositoryIntegration.

    Resolution order:
        1. explicit_config (--config <path>)
        2. repo_local_yml (<repo_path>/reguard.yml)
        3. builtin_manifest (integrations/<repo>.yml)
        4. legacy_adapter (ADAPTER_REGISTRY fallback)
        5. UNSUPPORTED
    """

    def __init__(
        self,
        *,
        builtin_manifests: dict[str, dict] | None = None,
        legacy_registry_getter=None,
    ):
        self._builtins = dict(builtin_manifests or {})
        self._legacy_registry_getter = legacy_registry_getter

    def register_builtin(self, full_name: str, manifest: dict) -> None:
        self._builtins[full_name] = manifest

    def resolve(
        self,
        *,
        full_name: str,
        repo_path: Path | None,
        explicit_config: Path | None,
    ) -> ResolverOutcome:
        if explicit_config is not None:
            if not explicit_config.exists():
                return ResolverOutcome(
                    integration=None,
                    unsupported_reason=(
                        f"explicit config {explicit_config!s} not found"
                    ),
                    source=ResolutionSource.EXPLICIT_CONFIG,
                )
            cfg = _load_yml(explicit_config)
            try:
                integration = _build_integration(
                    full_name=full_name, cfg=cfg,
                    source=ResolutionSource.EXPLICIT_CONFIG,
                    config_path=explicit_config,
                )
                return ResolverOutcome(integration=integration)
            except IntegrationConfigError as exc:
                return ResolverOutcome(
                    integration=None,
                    unsupported_reason=f"invalid explicit config: {exc}",
                    source=ResolutionSource.EXPLICIT_CONFIG,
                )

        if repo_path is not None:
            local_yml = repo_path / "reguard.yml"
            if local_yml.exists():
                cfg = _load_yml(local_yml)
                try:
                    integration = _build_integration(
                        full_name=full_name, cfg=cfg,
                        source=ResolutionSource.REPO_LOCAL_YML,
                        config_path=local_yml,
                    )
                    return ResolverOutcome(integration=integration)
                except IntegrationConfigError as exc:
                    return ResolverOutcome(
                        integration=None,
                        unsupported_reason=f"invalid reguard.yml: {exc}",
                        source=ResolutionSource.REPO_LOCAL_YML,
                    )

        if full_name in self._builtins:
            cfg = self._builtins[full_name]
            try:
                integration = _build_integration(
                    full_name=full_name, cfg=cfg,
                    source=ResolutionSource.BUILTIN_MANIFEST,
                    config_path=None,
                )
                return ResolverOutcome(integration=integration)
            except IntegrationConfigError as exc:
                return ResolverOutcome(
                    integration=None,
                    unsupported_reason=(
                        f"invalid built-in manifest for {full_name}: {exc}"
                    ),
                    source=ResolutionSource.BUILTIN_MANIFEST,
                )

        if self._legacy_registry_getter is not None:
            try:
                self._legacy_registry_getter(full_name)
                return ResolverOutcome(
                    integration=None,
                    unsupported_reason=(
                        f"repository {full_name!r} has a legacy adapter "
                        "and no reguard.yml; legacy adapters are still "
                        "available via the existing CLI "
                        "(scripts/compliance-check.py)"
                    ),
                    source=ResolutionSource.LEGACY_ADAPTER,
                )
            except KeyError:
                pass

        return ResolverOutcome(
            integration=None,
            unsupported_reason=(
                f"no compatible integration found for {full_name!r}; "
                "add reguard.yml or select a supported recipe"
            ),
            source=ResolutionSource.NONE,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_yml(path: Path) -> dict:
    """Load a YAML file. Imported lazily so PyYAML is only needed
    when YAML configs are actually used."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise IntegrationConfigError(
            "PyYAML is required to load YAML configs; "
            "install with `pip install pyyaml`"
        ) from exc
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise IntegrationConfigError(
            f"{path!s}: top-level must be a mapping, got {type(data).__name__}"
        )
    return data


def _build_integration(
    *,
    full_name: str,
    cfg: dict,
    source: ResolutionSource,
    config_path: Path | None,
) -> RepositoryIntegration:
    schema_version = str(cfg.get("schema_version", ""))
    if schema_version and schema_version != "1":
        raise IntegrationConfigError(
            f"unsupported schema_version {schema_version!r}; "
            f"this build supports '1'"
        )

    integration_block = cfg.get("integration")
    if not isinstance(integration_block, dict):
        raise IntegrationConfigError(
            "missing or invalid 'integration:' block"
        )

    recipe_id = integration_block.get("recipe")
    if not recipe_id or not isinstance(recipe_id, str):
        raise IntegrationConfigError(
            "integration.recipe must be a non-empty string"
        )
    recipe_version = integration_block.get("recipe_version") or None

    try:
        recipe = get_recipe(recipe_id, recipe_version)
    except KeyError as exc:
        raise UnknownRecipeError(str(exc)) from exc

    observer_ids = integration_block.get("observers") or ()
    if not isinstance(observer_ids, (list, tuple)) or not observer_ids:
        raise IntegrationConfigError(
            "integration.observers must be a non-empty list"
        )
    observers: list[ObserverSet] = []
    for entry in observer_ids:
        if isinstance(entry, str):
            oid, over = entry, None
        elif isinstance(entry, dict):
            oid = entry.get("id")
            over = entry.get("version")
        else:
            raise IntegrationConfigError(
                f"invalid observer entry: {entry!r}"
            )
        if not oid or not isinstance(oid, str):
            raise IntegrationConfigError(
                "each observer entry must have a string id"
            )
        try:
            observers.append(get_observer(oid, over))
        except KeyError as exc:
            raise UnknownObserverError(str(exc)) from exc
    observers_tuple = tuple(observers)

    normalizer_entry = integration_block.get("normalizer")
    if not isinstance(normalizer_entry, dict):
        raise IntegrationConfigError(
            "integration.normalizer must be a mapping with 'id'"
        )
    nid = normalizer_entry.get("id")
    if not nid or not isinstance(nid, str):
        raise IntegrationConfigError(
            "integration.normalizer.id must be a non-empty string"
        )
    nver = normalizer_entry.get("version")
    try:
        normalizer = get_normalizer(nid, nver)
    except KeyError as exc:
        raise UnknownNormalizerError(str(exc)) from exc

    entrypoint = integration_block.get("entrypoint") or {}
    if not isinstance(entrypoint, dict):
        raise IntegrationConfigError(
            "integration.entrypoint must be a mapping"
        )
    entrypoint_target = entrypoint.get("target")
    if not entrypoint_target or not isinstance(entrypoint_target, str):
        raise IntegrationConfigError(
            "integration.entrypoint.target is required"
        )
    entrypoint_mode = entrypoint.get("mode", "sync")
    async_mode = entrypoint_mode == "async"

    package_root = integration_block.get("package_root", ".")
    if package_root in (".", "") and config_path is not None:
        package_root = str(config_path.parent.resolve())
    elif config_path is not None and not Path(package_root).is_absolute():
        package_root = str((config_path.parent / package_root).resolve())

    model = integration_block.get("model") or {}
    if not isinstance(model, dict):
        raise IntegrationConfigError(
            "integration.model must be a mapping"
        )
    model_strategy_raw = model.get("strategy", "deterministic_stub")
    if model_strategy_raw != "deterministic_stub":
        raise IntegrationConfigError(
            "integration.model.strategy must be 'deterministic_stub' "
            "in v0.1; provider-keyed models are not supported"
        )

    scenarios = cfg.get("scenarios") or ()
    if not isinstance(scenarios, (list, tuple)) or not scenarios:
        raise IntegrationConfigError(
            "scenarios must be a non-empty list"
        )

    required_env = tuple(integration_block.get("required_env") or ())
    forbidden_env = tuple(
        integration_block.get("forbidden_env")
        or (
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GOOGLE_API_KEY",
            "GEMINI_API_KEY",
            "VERTEXAI_PROJECT",
            "AZURE_OPENAI_API_KEY",
            "HUGGINGFACEHUB_API_TOKEN",
            "COHERE_API_KEY",
            "MISTRAL_API_KEY",
            "GROQ_API_KEY",
        )
    )

    recipe_config = RecipeConfig(
        recipe_id=recipe.recipe_id,
        recipe_version=recipe.recipe_version,
        package_root=package_root,
        entrypoint_target=entrypoint_target,
        async_mode=async_mode,
        required_env=required_env,
        forbidden_env=forbidden_env,
        observer_ids=tuple(o.observer_id for o in observers_tuple),
        supported_scenarios=tuple(scenarios),
        params=integration_block.get("params") or {},
    )

    if recipe_config.entrypoint_target:
        try:
            recipe.resolve(recipe_config)
        except ValueError as exc:
            raise IntegrationConfigError(
                f"recipe rejected entrypoint: {exc}"
            ) from exc

    for scenario in scenarios:
        if scenario not in recipe.supported_scenarios:
            raise UnsupportedScenarioError(
                f"recipe {recipe.recipe_id}@{recipe.recipe_version} "
                f"does not support scenario {scenario!r}; "
                f"supported: {list(recipe.supported_scenarios)}"
            )

    return RepositoryIntegration(
        full_name=full_name,
        recipe=recipe,
        recipe_config=recipe_config,
        observers=observers_tuple,
        normalizer=normalizer,
        source=source,
        config_path=config_path,
    )


from pathlib import Path  # noqa: E402


def validate_env(recipe_config: RecipeConfig, env: dict[str, str]) -> None:
    """Refuse to run if any forbidden env var is set or any
    required env var is missing.

    Raises ForbiddenEnvError. This is a config-level check, not a
    compliance verdict."""
    for forbidden in recipe_config.forbidden_env:
        if env.get(forbidden):
            raise ForbiddenEnvError(
                f"forbidden env var {forbidden!r} is set in the "
                "harness environment; recipes must not run when a "
                "provider key is present"
            )
    for required in recipe_config.required_env:
        if not env.get(required):
            raise ForbiddenEnvError(
                f"required env var {required!r} is not set"
            )
