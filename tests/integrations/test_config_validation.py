"""Tests for the reguard.yml schema loader and validator."""
from __future__ import annotations

import textwrap

import pytest

from compliance.integrations.config import (
    load_reguard_yml,
    render_default_reguard_yml,
    config_summary,
)
from compliance.integrations.errors import IntegrationConfigError
from compliance.integrations.integration import (
    IntegrationResolver,
    _build_integration,
    validate_env,
)
from compliance.integrations.recipe import (
    EntrypointKind,
    PackageStrategy,
    RecipeConfig,
)


def test_render_default_reguard_yml_is_minimal():
    rendered = render_default_reguard_yml()
    assert "schema_version: 1" in rendered
    assert "recipe: langgraph-state" in rendered
    assert "langgraph-state.callback-observer" in rendered


def test_load_reguard_yml_minimal(tmp_path):
    p = tmp_path / "reguard.yml"
    p.write_text(textwrap.dedent("""
        schema_version: 1
        integration:
          recipe: langgraph-state
          recipe_version: 1.0.0
          package_root: .
          entrypoint:
            target: x:y
            mode: sync
          model:
            strategy: deterministic_stub
          observers:
            - langgraph-state.callback-observer
          normalizer:
            id: langgraph-state.canonical-normalizer
        scenarios:
          - compliance.article12_1.simple
    """).strip())
    yml = load_reguard_yml(p)
    assert yml.schema_version == "1"
    assert yml.integration_block["recipe"] == "langgraph-state"
    assert yml.scenarios == ("compliance.article12_1.simple",)


def test_load_reguard_yml_rejects_unknown_schema(tmp_path):
    p = tmp_path / "reguard.yml"
    p.write_text("schema_version: 99\n")
    with pytest.raises(IntegrationConfigError):
        load_reguard_yml(p)


def test_load_reguard_yml_rejects_non_mapping(tmp_path):
    p = tmp_path / "reguard.yml"
    p.write_text("- a\n- b\n")
    with pytest.raises(IntegrationConfigError):
        load_reguard_yml(p)


def test_build_integration_rejects_unknown_recipe(tmp_path):
    cfg = {
        "schema_version": "1",
        "integration": {
            "recipe": "no-such-recipe",
            "recipe_version": "1.0.0",
            "package_root": ".",
            "entrypoint": {"target": "x:y", "mode": "sync"},
            "model": {"strategy": "deterministic_stub"},
            "observers": ["langgraph-state.callback-observer"],
            "normalizer": {"id": "langgraph-state.canonical-normalizer"},
        },
        "scenarios": ["compliance.article12_1.simple"],
    }
    from compliance.integrations.errors import UnknownRecipeError
    with pytest.raises(UnknownRecipeError):
        _build_integration(
            full_name="x/y",
            cfg=cfg,
            source=None,
            config_path=None,
        )


def test_build_integration_rejects_unknown_observer(tmp_path):
    cfg = {
        "schema_version": "1",
        "integration": {
            "recipe": "langgraph-state",
            "recipe_version": "1.0.0",
            "package_root": ".",
            "entrypoint": {"target": "x:y", "mode": "sync"},
            "model": {"strategy": "deterministic_stub"},
            "observers": ["nope-observer"],
            "normalizer": {"id": "langgraph-state.canonical-normalizer"},
        },
        "scenarios": ["compliance.article12_1.simple"],
    }
    from compliance.integrations.errors import UnknownObserverError
    with pytest.raises(UnknownObserverError):
        _build_integration(
            full_name="x/y",
            cfg=cfg,
            source=None,
            config_path=None,
        )


def test_build_integration_rejects_unknown_normalizer(tmp_path):
    cfg = {
        "schema_version": "1",
        "integration": {
            "recipe": "langgraph-state",
            "recipe_version": "1.0.0",
            "package_root": ".",
            "entrypoint": {"target": "x:y", "mode": "sync"},
            "model": {"strategy": "deterministic_stub"},
            "observers": ["langgraph-state.callback-observer"],
            "normalizer": {"id": "nope-normalizer"},
        },
        "scenarios": ["compliance.article12_1.simple"],
    }
    from compliance.integrations.errors import UnknownNormalizerError
    with pytest.raises(UnknownNormalizerError):
        _build_integration(
            full_name="x/y",
            cfg=cfg,
            source=None,
            config_path=None,
        )


def test_build_integration_rejects_unsupported_scenario(tmp_path):
    cfg = {
        "schema_version": "1",
        "integration": {
            "recipe": "langgraph-state",
            "recipe_version": "1.0.0",
            "package_root": ".",
            "entrypoint": {"target": "x:y", "mode": "sync"},
            "model": {"strategy": "deterministic_stub"},
            "observers": ["langgraph-state.callback-observer"],
            "normalizer": {"id": "langgraph-state.canonical-normalizer"},
        },
        "scenarios": ["compliance.something.not-supported"],
    }
    from compliance.integrations.errors import UnsupportedScenarioError
    with pytest.raises(UnsupportedScenarioError):
        _build_integration(
            full_name="x/y",
            cfg=cfg,
            source=None,
            config_path=None,
        )


def test_build_integration_rejects_provider_model_strategy():
    cfg = {
        "schema_version": "1",
        "integration": {
            "recipe": "langgraph-state",
            "recipe_version": "1.0.0",
            "package_root": ".",
            "entrypoint": {"target": "x:y", "mode": "sync"},
            "model": {"strategy": "openai_gpt4"},
            "observers": ["langgraph-state.callback-observer"],
            "normalizer": {"id": "langgraph-state.canonical-normalizer"},
        },
        "scenarios": ["compliance.article12_1.simple"],
    }
    with pytest.raises(IntegrationConfigError):
        _build_integration(
            full_name="x/y",
            cfg=cfg,
            source=None,
            config_path=None,
        )


def test_validate_env_rejects_provider_key():
    cfg = RecipeConfig(
        recipe_id="x",
        recipe_version="1.0.0",
        package_root=".",
        entrypoint_target="x:y",
    )
    with pytest.raises(Exception):
        validate_env(cfg, {"OPENAI_API_KEY": "secret"})


def test_validate_env_accepts_clean_env():
    cfg = RecipeConfig(
        recipe_id="x",
        recipe_version="1.0.0",
        package_root=".",
        entrypoint_target="x:y",
    )
    validate_env(cfg, {"PATH": "/usr/bin"})


def test_resolver_falls_back_to_unsupported():
    resolver = IntegrationResolver(builtin_manifests={})
    outcome = resolver.resolve(
        full_name="nope/no-such",
        repo_path=None,
        explicit_config=None,
    )
    assert outcome.integration is None
    assert outcome.source.value == "none"
    assert "no compatible integration" in (outcome.unsupported_reason or "")
