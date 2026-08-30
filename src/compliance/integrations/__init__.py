"""Config-driven integration layer for Reguard Core v0.1.

The integration layer contains three first-class reusable
abstractions:

    RepositoryIntegration
        ↓
    ExecutionRecipe           # what to run + how to invoke it
        ↓
    ObserverSet               # what native observations to capture
        ↓
    Normalizer                # how to translate native observations
                              # into canonical Reguard Evidence

These abstractions contain NO Article 12(1) (or any other
legal-requirement) verdict logic. They are pure engineering
shapes. Requirement tests (lives elsewhere) decide PASS/FAIL.

The legacy `RepoAdapter` (per-framework Python class) is still
supported via `LegacyAdapterCompat` and remains the dispatch path
for the five frozen Article 12(1) adapters. New integrations
should be authored as Recipe + ObserverSet + Normalizer.
"""
from __future__ import annotations

from .recipe import (
    ExecutionRecipe,
    RecipeConfig,
    RecipeResolution,
    PackageStrategy,
    EntrypointKind,
    InvocationDriver,
    ModelInjectionStrategy,
    ToolInjectionStrategy,
)
from .observer import (
    ObserverSet,
    NativeObservation,
    ObserverContext,
)
from .normalizer import (
    Normalizer,
    NormalizerResult,
)
from .integration import (
    RepositoryIntegration,
    IntegrationResolver,
    ResolutionSource,
)
from .errors import (
    IntegrationConfigError,
    UnknownRecipeError,
    UnknownObserverError,
    UnknownNormalizerError,
    UnsupportedScenarioError,
    ForbiddenEnvError,
)

REGUARD_YML_SCHEMA_VERSION = "1"

__all__ = [
    "REGUARD_YML_SCHEMA_VERSION",
    # recipe
    "ExecutionRecipe",
    "RecipeConfig",
    "RecipeResolution",
    "PackageStrategy",
    "EntrypointKind",
    "InvocationDriver",
    "ModelInjectionStrategy",
    "ToolInjectionStrategy",
    # observer
    "ObserverSet",
    "NativeObservation",
    "ObserverContext",
    # normalizer
    "Normalizer",
    "NormalizerResult",
    # integration
    "RepositoryIntegration",
    "IntegrationResolver",
    "ResolutionSource",
    # errors
    "IntegrationConfigError",
    "UnknownRecipeError",
    "UnknownObserverError",
    "UnknownNormalizerError",
    "UnsupportedScenarioError",
    "ForbiddenEnvError",
]
