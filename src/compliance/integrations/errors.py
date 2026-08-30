"""Integration-layer error types.

These errors are raised by the config-driven integration layer
(`reguard.yml` resolution, Recipe / Observer / Normalizer
selection). They are deliberately distinct from `RequirementTest`
errors — the integration layer must NEVER raise errors that
look like compliance verdicts.
"""
from __future__ import annotations


class IntegrationConfigError(ValueError):
    """Raised when `reguard.yml` (or a built-in integration manifest)
    fails structural validation.

    This is a config problem, not a compliance problem.
    """


class UnknownRecipeError(IntegrationConfigError):
    """Raised when a config references a recipe id that is not
    registered in the RecipeRegistry."""


class UnknownObserverError(IntegrationConfigError):
    """Raised when a config references an observer id that is not
    registered in the ObserverRegistry."""


class UnknownNormalizerError(IntegrationConfigError):
    """Raised when a config references a normalizer id that is not
    registered in the NormalizerRegistry."""


class UnsupportedSchemaVersionError(IntegrationConfigError):
    """Raised when the `schema_version` of a `reguard.yml` is
    newer than the installed Reguard supports."""


class UnsupportedScenarioError(IntegrationConfigError):
    """Raised when a config selects a scenario that the chosen
    recipe does not advertise as supported."""


class ForbiddenEnvError(IntegrationConfigError):
    """Raised when a config requests an environment variable that
    is in the forbidden-env allow-list for this recipe."""


class EntrypointResolutionError(IntegrationConfigError):
    """Raised when an entrypoint string cannot be resolved against
    the selected recipe's package root."""
