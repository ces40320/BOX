"""Write ExtLoad.mot for BoxWrench (pipeline-compatible).

Skeleton: intended to reuse ``optimization.ricto_io`` for MOT I/O and
RiCTO weight curves for contact gating. Numerical fill is blocked until
Approach-5 + box model assets arrive.

Policy (documented defaults):
- Template: HeavyHand MOT (GRF kept).
- hand3 = left, hand4 = right.
- Torques zero unless vendor method requires otherwise
  (``FORCE_ZERO_HAND_TORQUE``).
- No MeasuredEHF hand-column copy.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from .boxwrench_config import (
    BLOCKED_REASON,
    FORCE_ZERO_HAND_TORQUE,
    RICTO_WEIGHT_MODE,
)


def apply_ricto_gate(
    forces_l: np.ndarray,
    forces_r: np.ndarray,
    weight: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Multiply L/R hand forces by RiCTO contact weight (shared helper)."""
    w = np.asarray(weight, dtype=float).reshape(-1, 1)
    return np.asarray(forces_l, dtype=float) * w, np.asarray(forces_r, dtype=float) * w


def build_boxwrench_extload(*_args: Any, **_kwargs: Any) -> Dict[str, np.ndarray]:
    """Assemble ExtLoad dict (GRF from template + BoxWrench hands).

    Raises
    ------
    NotImplementedError
        Always in this scaffolding pass.
    """
    raise NotImplementedError(
        f"{BLOCKED_REASON} "
        f"(torque_zero={FORCE_ZERO_HAND_TORQUE}, "
        f"ricto_weight={RICTO_WEIGHT_MODE!r})"
    )


def write_boxwrench_mot(
    out_path: str,
    *_args: Any,
    **_kwargs: Any,
) -> str:
    """Write ``ExtLoad_BoxWrench.mot`` — stub.

    Parameters
    ----------
    out_path :
        Destination path (typically ``ConditionPaths.extload_path(seg, 'BoxWrench')``).
    """
    raise NotImplementedError(
        f"{BLOCKED_REASON} (would write {out_path!r})"
    )


def assert_no_measured_leak(
    boxwrench_df: Any,
    measured_df: Optional[Any] = None,
    *,
    atol: float = 1e-6,
) -> Dict[str, bool]:
    """Placeholder QC API mirroring RiCTO; real checks after MOT write exists."""
    raise NotImplementedError(BLOCKED_REASON)
