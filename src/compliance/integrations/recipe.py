"""ExecutionRecipe — versioned, declarative description of how to
exercise one agent system.

A recipe is a *named* Python class (not arbitrary executable source
in YAML). The recipe decides:

  - which invocation driver to use (subprocess / container);
  - how to inject a deterministic stub model;
  - how to inject probe tools;
  - which observer ids to attach;
  - which scenarios are supported.

Recipe parameters are passed via a `RecipeConfig` dataclass that
the integration resolver builds from `reguard.yml`. The recipe
contains NO Article-number logic and does not decide PASS/FAIL.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class PackageStrategy(str, Enum):
    """How the target repository's package is installed into the
    probe runtime."""

    EDITABLE = "editable"           # pip install -e .
    WHEEL = "wheel"                 # pip install . (build wheel first)
    POETRY = "poetry"               # poetry install
    UV = "uv"                       # uv sync / uv pip install -e .
    NONE = "none"                   # no install (use system Python)


class EntrypointKind(str, Enum):
    """How the recipe should locate the agent entrypoint."""

    PYTHON_DOTTED = "python_dotted"   # "package.module:Class"
    PYTHON_CALLABLE = "python_callable"  # "package.module:function"
    CLI_COMMAND = "cli_command"       # "package-cli --arg"


class InvocationDriver(str, Enum):
    """Where the probe runs."""

    SUBPROCESS = "subprocess"        # fresh venv on host
    OCI_CONTAINER = "oci_container"  # frozen repo-runtime container


class ModelInjectionStrategy(str, Enum):
    """How the deterministic stub model is wired into the target
    framework."""

    CONSTRUCTOR_ARG = "constructor_arg"   # pass stub at __init__
    FACTORY_OVERRIDE = "factory_override" # monkey-patch create_chat_model
    GLOBAL_CONFIG = "global_config"       # patch a config module's value
    ENV_VAR = "env_var"                   # set LLM_PROVIDER=stub


class ToolInjectionStrategy(str, Enum):
    """How probe tools are wired into the target framework."""

    CONSTRUCTOR_LIST = "constructor_list"  # tools=[t1, t2]
    REGISTRY = "registry"                  # @controller.action(...)
    ACTION_SET = "action_set"              # Role.set_actions([...])
    PIPELINE_COMPONENT = "pipeline_component"  # Pipeline().add_component


@dataclass(frozen=True)
class RecipeConfig:
    """Parameter object passed into ExecutionRecipe.run().

    Built by the IntegrationResolver from `reguard.yml` plus a
    built-in manifest. Immutable.
    """

    recipe_id: str
    recipe_version: str
    package_strategy: PackageStrategy = PackageStrategy.EDITABLE
    package_root: str = "."

    entrypoint_kind: EntrypointKind = EntrypointKind.PYTHON_DOTTED
    entrypoint_target: str = ""

    invocation_driver: InvocationDriver = InvocationDriver.SUBPROCESS

    model_injection_strategy: ModelInjectionStrategy = (
        ModelInjectionStrategy.CONSTRUCTOR_ARG
    )
    tool_injection_strategy: ToolInjectionStrategy = (
        ToolInjectionStrategy.CONSTRUCTOR_LIST
    )

    async_mode: bool = False

    required_env: tuple[str, ...] = ()
    """Environment variable NAMES that must be set for the recipe
    to run. Empty env names are forbidden. Recipe declares these;
    the integration resolver enforces them."""

    forbidden_env: tuple[str, ...] = (
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
    """Environment variable NAMES that the recipe forbids passing
    through. The integration resolver will refuse to run a
    recipe if any of these are present in the harness environment,
    even if the user set them."""

    observer_ids: tuple[str, ...] = ()
    supported_scenarios: tuple[str, ...] = (
        "compliance.article12_1.simple",
    )

    params: Mapping[str, Any] = field(default_factory=dict)
    """Free-form recipe-specific parameters (e.g. import_path for
    factory_override). Recipe-defined. The integration resolver
    passes this through verbatim."""


@dataclass(frozen=True)
class RecipeResolution:
    """The fully-resolved recipe ready for execution.

    Returned by ExecutionRecipe.resolve(). Holds the parsed
    RecipeConfig plus any recipe-specific computed artifacts
    (e.g. the entrypoint import path, the resolved python version).
    """

    config: RecipeConfig
    entrypoint_module: str
    entrypoint_attr: str
    extra: dict = field(default_factory=dict)


class ExecutionRecipe:
    """Base class for a named, versioned execution recipe.

    Subclasses declare their static identity (recipe_id, version,
    default supported_scenarios) and implement `resolve()` and
    `run()`.

    Recipes must NEVER:
      - return a PASS/FAIL verdict;
      - import or reference any Article number;
      - invent events to manufacture a PASS.
    """

    recipe_id: str = "UNSET"
    recipe_version: str = "0.0.0"
    supported_scenarios: tuple[str, ...] = ()

    def resolve(self, config: RecipeConfig) -> RecipeResolution:
        """Validate the RecipeConfig for this recipe and return a
        RecipeResolution. Subclasses override to enforce
        recipe-specific invariants."""
        if not config.entrypoint_target:
            raise ValueError(
                f"{self.recipe_id}: entrypoint_target is required"
            )
        if config.entrypoint_kind == EntrypointKind.PYTHON_DOTTED:
            if ":" not in config.entrypoint_target:
                raise ValueError(
                    f"{self.recipe_id}: entrypoint_target must be "
                    "'module:attr' for python_dotted entrypoints; "
                    f"got {config.entrypoint_target!r}"
                )
            module, _, attr = config.entrypoint_target.partition(":")
            return RecipeResolution(
                config=config,
                entrypoint_module=module.strip(),
                entrypoint_attr=attr.strip(),
            )
        if config.entrypoint_kind == EntrypointKind.PYTHON_CALLABLE:
            if ":" not in config.entrypoint_target:
                raise ValueError(
                    f"{self.recipe_id}: entrypoint_target must be "
                    "'module:callable' for python_callable entrypoints; "
                    f"got {config.entrypoint_target!r}"
                )
            module, _, attr = config.entrypoint_target.partition(":")
            return RecipeResolution(
                config=config,
                entrypoint_module=module.strip(),
                entrypoint_attr=attr.strip(),
            )
        if config.entrypoint_kind == EntrypointKind.CLI_COMMAND:
            return RecipeResolution(
                config=config,
                entrypoint_module="",
                entrypoint_attr=config.entrypoint_target.strip(),
            )
        raise ValueError(
            f"{self.recipe_id}: unsupported entrypoint_kind "
            f"{config.entrypoint_kind!r}"
        )

    def run(
        self,
        resolution: RecipeResolution,
        scenario: Any,
    ) -> Any:
        """Execute the recipe. Returns an opaque runner-output object
        that the ObserverSet and Normalizer will consume.

        Subclasses MUST implement. The base class raises so a
        partial subclass cannot accidentally pass."""
        raise NotImplementedError(
            f"{self.recipe_id}@{self.recipe_version}: run() not implemented"
        )


# ---------------------------------------------------------------------------
# Recipe registry — populated by recipes/__init__.py and families/<family>/
# ---------------------------------------------------------------------------
_RECIPE_REGISTRY: dict[tuple[str, str], ExecutionRecipe] = {}


def register_recipe(recipe: ExecutionRecipe) -> ExecutionRecipe:
    """Register a recipe instance. Idempotent on (recipe_id,
    recipe_version)."""
    key = (recipe.recipe_id, recipe.recipe_version)
    if key in _RECIPE_REGISTRY:
        return _RECIPE_REGISTRY[key]
    _RECIPE_REGISTRY[key] = recipe
    return recipe


def get_recipe(recipe_id: str, recipe_version: str | None = None) -> ExecutionRecipe:
    """Look up a registered recipe.

    If `recipe_version` is None, return the lexicographically
    highest registered version for `recipe_id`.
    """
    candidates = [
        (ver, recipe) for (rid, ver), recipe in _RECIPE_REGISTRY.items()
        if rid == recipe_id
    ]
    if not candidates:
        raise KeyError(f"no recipe registered for id {recipe_id!r}")
    if recipe_version is not None:
        for ver, recipe in candidates:
            if ver == recipe_version:
                return recipe
        raise KeyError(
            f"no recipe registered for {recipe_id}@{recipe_version}"
        )
    candidates.sort(key=lambda kv: kv[0])
    return candidates[-1][1]


def all_recipes() -> list[ExecutionRecipe]:
    """Return all registered recipes, sorted by (recipe_id, version)."""
    out = sorted(
        _RECIPE_REGISTRY.values(),
        key=lambda r: (r.recipe_id, r.recipe_version),
    )
    return out


def reset_recipe_registry() -> None:
    """Test helper. Wipes the registry."""
    _RECIPE_REGISTRY.clear()
