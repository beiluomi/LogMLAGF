"""Deterministic seed utilities — call ``set_seed`` at the top of every entry script."""

from __future__ import annotations

import os
import random


def set_seed(seed: int = 42, deterministic: bool = True) -> None:
    """Fix seeds for ``random`` / NumPy / PyTorch (if installed) and CuDNN.

    Args:
        seed: Seed value to use across all RNGs.
        deterministic: If ``True``, force CuDNN into deterministic mode. Slower
            but required for paper-grade reproducibility.
    """
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch

        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        if deterministic:
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
    except ImportError:
        pass
