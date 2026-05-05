"""Phase 0 smoke tests — verify the project skeleton imports and basic utilities work."""

from __future__ import annotations

import importlib
import random


def test_import_root() -> None:
    mod = importlib.import_module("loghetero")
    assert hasattr(mod, "__version__")
    assert mod.__version__ == "0.0.0"


def test_import_cli() -> None:
    importlib.import_module("loghetero.cli")


def test_import_utils() -> None:
    importlib.import_module("loghetero.utils.seed")
    importlib.import_module("loghetero.utils.logging")


def test_set_seed_reproducible() -> None:
    from loghetero.utils.seed import set_seed

    set_seed(123)
    a = [random.random() for _ in range(5)]
    set_seed(123)
    b = [random.random() for _ in range(5)]
    assert a == b


def test_logger_singleton_no_duplicate_handlers() -> None:
    from loghetero.utils.logging import get_logger

    log1 = get_logger("loghetero.tests.smoke")
    log2 = get_logger("loghetero.tests.smoke")
    assert log1 is log2
    assert len(log1.handlers) == 1


def test_cli_app_callable() -> None:
    from loghetero.cli import app

    assert callable(app)
