"""Time2Vec edge-time encoder (Phase 3 / Checkpoint 7 deliverable).

Implements the periodic time embedding from Kazemi et al. (2019),
"Time2Vec: Learning a Vector Representation of Time"
(https://arxiv.org/abs/1907.05321), used by LogHetero to encode the
``edge_attr_time`` channel of the heterogeneous provenance graph before it
flows into the HTGN temporal-graph stack.

Math
----
For an input scalar timestamp ``t`` and embedding dimension ``d``::

    phi(t) = [
        omega_0 * t + phi_0,                    # 0-th component: LINEAR
        sin(omega_1 * t + phi_1),               # 1..d-1:        SIN
        sin(omega_2 * t + phi_2),
        ...
        sin(omega_{d-1} * t + phi_{d-1}),
    ]

All ``omega_i`` and ``phi_i`` are learnable; there is no fixed-frequency
variant (locked design parameter for Phase 3).

Parameter layout
----------------
We keep the linear (component 0) and the sinusoidal (components 1..d-1)
parameters as separate ``nn.Parameter`` tensors. The split makes the
gradient-flow test trivial to write (each component's gradient lands in
its own buffer) and matches the math above 1-to-1.

* ``omega_0`` — scalar ``nn.Parameter`` for the linear component.
* ``phi_0``   — scalar ``nn.Parameter`` for the linear component bias.
* ``omega``   — ``nn.Parameter`` of shape ``[dim - 1]``, sin frequencies.
* ``phi``     — ``nn.Parameter`` of shape ``[dim - 1]``, sin phases.

Initialisation
--------------
All four parameters use a small uniform draw from ``U(-0.1, 0.1)``. A
small init keeps the sin arguments inside the near-linear regime of
``sin`` at the start of training, which empirically yields more stable
gradients than the default PyTorch ``U(-1, 1)`` for tiny tensors. The
specific bound (0.1) is the value used in the reference Time2Vec
implementation by the paper's authors; we keep it for reproducibility.

Timestamp normalisation (caller's responsibility)
-------------------------------------------------
**Important.** Upstream timestamps from
:mod:`loghetero.data.parsers.base` are UTC nanoseconds (int64, magnitudes
~1.5e18). Passing those raw into Time2Vec would push the sin arguments
far outside any usable range and saturate the gradient.

The caller MUST normalise the timestamp before invoking ``forward``
(e.g. divide by ``NS_PER_HOUR = 3.6e12`` so 1 unit = 1 hour). Time2Vec
itself intentionally does NOT normalise internally — the choice of unit
(hour vs. minute vs. delta-from-window-start) belongs to the data
pipeline, not the encoder.

Tests
-----
Covered by ``tests/test_time2vec.py``:

* Forward shape ``[N, 1] -> [N, dim]`` for ``dim`` in ``{16, 32, 64}``.
* Determinism: same input twice yields cosine-similarity 1.0.
* Discrimination: distinct inputs yield cosine-similarity < 1.0.
* Gradient flow: ``omega``, ``phi``, ``omega_0``, ``phi_0`` all receive
  non-zero gradients on a forward + backward pass.
"""

from __future__ import annotations

import torch
from torch import nn


class Time2Vec(nn.Module):
    """Learnable Time2Vec edge-time encoder.

    Args:
        dim: Output embedding dimension. Default ``32`` matches the locked
            Phase-3 design parameter; the sweep space ``[16, 32, 64]`` is
            reserved for the Phase 11 ablation.

    Shape:
        * input: ``[*, 1]`` where ``*`` is any leading batch shape
          (typically ``[E, 1]`` for ``E`` edges).
        * output: ``[*, dim]``.

    Note:
        The caller is responsible for scaling timestamps to a sane range
        before invoking ``forward``. See the module docstring's
        "Timestamp normalisation" section.
    """

    def __init__(self, dim: int = 32) -> None:
        super().__init__()
        if dim < 2:
            raise ValueError(f"Time2Vec requires dim >= 2 (got {dim}); need 1 linear + >=1 sin.")
        self.dim = dim

        # Linear component (index 0): two scalar parameters.
        self.omega_0 = nn.Parameter(torch.empty(1))
        self.phi_0 = nn.Parameter(torch.empty(1))

        # Sinusoidal components (indices 1..dim-1).
        self.omega = nn.Parameter(torch.empty(dim - 1))
        self.phi = nn.Parameter(torch.empty(dim - 1))

        self.reset_parameters()

    def reset_parameters(self) -> None:
        """Re-initialise all four parameter groups to ``U(-0.1, 0.1)``."""
        bound = 0.1
        nn.init.uniform_(self.omega_0, -bound, bound)
        nn.init.uniform_(self.phi_0, -bound, bound)
        nn.init.uniform_(self.omega, -bound, bound)
        nn.init.uniform_(self.phi, -bound, bound)

    def forward(self, t: torch.Tensor) -> torch.Tensor:
        """Encode a tensor of (already-normalised) timestamps.

        Args:
            t: Tensor of shape ``[*, 1]``. Dtype must be a floating-point
                type (``float32`` recommended); the caller is responsible
                for any prior unit conversion (see module docstring).

        Returns:
            Tensor of shape ``[*, dim]``: ``[linear, sin_1, ..., sin_{dim-1}]``.
        """
        if t.shape[-1] != 1:
            raise ValueError(f"Time2Vec expects last input dim = 1 (got shape {tuple(t.shape)}).")

        # Linear component: shape [*, 1].
        linear = self.omega_0 * t + self.phi_0

        # Sin components: broadcast t [*, 1] against omega/phi [dim-1] -> [*, dim-1].
        sin_args = self.omega * t + self.phi
        sin_part = torch.sin(sin_args)

        return torch.cat([linear, sin_part], dim=-1)
