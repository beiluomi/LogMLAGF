"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from loghetero.utils.seed import set_seed


@pytest.fixture(autouse=True)
def _seed_each_test() -> None:
    """Apply a fixed seed before every test for reproducibility."""
    set_seed(42)
