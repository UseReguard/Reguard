"""AI Act requirement tests.

Importing this package triggers self-registration of every concrete
requirement test in REQUIREMENT_REGISTRY.
"""
from __future__ import annotations

from . import article_12_1  # noqa: F401  triggers register_requirement()
from .article_12_1 import Article121AutomaticLoggingTest

__all__ = ["Article121AutomaticLoggingTest", "article_12_1"]