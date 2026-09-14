"""Force/moment equilibrium allocation (Approach-5 style) for BoxWrench.

Stub only — do not invent allocation equations from the paper text alone.
Integrate vendor Approach-5 allocation after sources arrive; map outputs to
hand3=left, hand4=right.
"""

from __future__ import annotations

from typing import Any, Dict

from .boxwrench_config import BLOCKED_REASON


def allocate_hand_loads(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Allocate box net wrench to left/right hand forces (and optional moments).

    Raises
    ------
    NotImplementedError
        Always until Approach-5 allocation sources are integrated.
    """
    raise NotImplementedError(BLOCKED_REASON)
