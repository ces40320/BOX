"""Pipeline policy rules for ``c_Run_Tools``.

Centralized policy for:

- kg-aware OpenSim model variant selection per ``(app, stage)``
- IK template / IK folder suffix per app
- JR ground-frame option per app

References (source of truth):

- ``OpenSim_Process/STRUCTURE_PLAN.md``  (Notes on kg-aware model resolution)
- ``Codes/c_Run_Tools/REFAC_RUN_TOOLS_PLAN.md``  (§3.4, §4.3)
- ``Codes/b_Build_Model/`` (which actually generates the model variants)

This module is pure policy: it depends only on ``os`` and the ``rp`` /
``ResultPaths`` instance passed in. No OpenSim, numpy, or pandas imports.
"""

from __future__ import annotations

import os


VALID_STAGES: tuple[str, ...] = ("ik", "so", "jr")


# ──────────────────────────────────────────────────────────────────
# (app, stage) → model variant suffix template
#
# Empty string means base model (``SUB{n}_Scaled.osim``).
# ``{w}`` is substituted with the integer kg parsed from the condition key.
#
# Rationale:
#   - IK is mass-independent kinematics: only ``AddBox`` (which adds box
#     geometry) needs a different model. ``HeavyHand`` only changes mass,
#     so IK uses the base model — matches ``STRUCTURE_PLAN.md`` which
#     only defines ``IK/`` and ``IK_AddBox/`` folders.
#   - SO/JR depend on inertial properties:
#       HeavyHand → HeavyHand_{w}kg
#       AddBox    → SplitBox_{w}kg  (per user policy)
#   - preRiCTO / postRiCTO use the base model; their differentiation is
#     handled at the ExtLoad / setup level, not the model level
#     (see STRUCTURE_PLAN.md Notes table).
# ──────────────────────────────────────────────────────────────────
MODEL_VARIANT_BY_APP_STAGE: dict[str, dict[str, str]] = {
    "MeasuredEHF": {"ik": "",                "so": "",                "jr": ""},
    "HeavyHand":   {"ik": "",                "so": "HeavyHand_{w}kg", "jr": "HeavyHand_{w}kg"},
    "AddBox":      {"ik": "WeldBox_{w}kg",   "so": "SplitBox_{w}kg",  "jr": "SplitBox_{w}kg"},
    "preRiCTO":    {"ik": "",                "so": "",                "jr": ""},
    "postRiCTO":   {"ik": "",                "so": "",                "jr": ""},
}


def box_kg_from_cond(cond: str) -> int:
    """Extract integer kg from a condition key.

    Parameters
    ----------
    cond : str
        e.g. ``'7kg_10bpm'`` → ``7``, ``'15kg_16bpm'`` → ``15``.

    Raises
    ------
    ValueError
        If the first underscore-separated token is not ``'<int>kg'``.
    """
    prefix = cond.split("_", 1)[0]
    if not (prefix.endswith("kg") and prefix[:-2].isdigit()):
        raise ValueError(
            f"Cannot extract box kg from condition {cond!r}; "
            "expected first token like '7kg', '10kg', '15kg'."
        )
    return int(prefix[:-2])


def resolve_model_type(app: str, w_kg: int, stage: str) -> str:
    """Resolve the ``model_type`` string passed to ``ResultPaths.model_path()``.

    Returns ``""`` for the base model, otherwise e.g. ``'HeavyHand_7kg'`` or
    ``'WeldBox_15kg'``.
    """
    if stage not in VALID_STAGES:
        raise ValueError(
            f"Unknown stage {stage!r}. Valid: {VALID_STAGES}"
        )
    if app not in MODEL_VARIANT_BY_APP_STAGE:
        raise KeyError(
            f"Unknown app {app!r} for model resolution. "
            f"Known apps: {sorted(MODEL_VARIANT_BY_APP_STAGE)}"
        )
    template = MODEL_VARIANT_BY_APP_STAGE[app][stage]
    return template.format(w=w_kg) if template else ""


def resolve_model_path(rp, cond: str, app: str, stage: str,
                       *, must_exist: bool = True) -> str:
    """Return the absolute ``.osim`` path for ``(cond, app, stage)``.

    Parameters
    ----------
    rp : ResultPaths
        Subject path context.
    cond : str
        Condition key (e.g. ``'7kg_10bpm'``).
    app : str
        App label (``MeasuredEHF`` / ``HeavyHand`` / ``AddBox`` / ``preRiCTO`` / ``postRiCTO``).
    stage : {'ik', 'so', 'jr'}
    must_exist : bool, default True
        If True, raise ``FileNotFoundError`` when the resolved file is absent.
        Use ``False`` for dry-run / preview logging.
    """
    w_kg = box_kg_from_cond(cond)
    model_type = resolve_model_type(app, w_kg, stage)
    path = rp.model_path(model_type)
    if must_exist and not os.path.isfile(path):
        raise FileNotFoundError(
            f"Required osim missing: {path}\n"
            f"  app={app}, stage={stage}, cond={cond} (w_kg={w_kg}).\n"
            f"  Run Codes/b_Build_Model/b_Main.ipynb first to generate "
            f"model variants (rename → HeavyHand → WeldBox/SplitBox)."
        )
    return path


# ──────────────────────────────────────────────────────────────────
# JR ground-frame policy
#
# Only ``AddBox`` produces an extra ``_ground`` JR result file
# (per user policy / STRUCTURE_PLAN.md Asymmetric SUB1 example).
# ──────────────────────────────────────────────────────────────────
def jr_suffixes(app: str) -> list[str]:
    """JR result suffixes per app.

    Returns
    -------
    list[str]
        ``['']`` for most apps; ``['', 'ground']`` for ``AddBox``.
        Each suffix becomes the ``suffix`` argument of
        ``ConditionPaths.jr_path(seg, app, suffix)``.
    """
    return ["", "ground"] if app == "AddBox" else [""]


# ──────────────────────────────────────────────────────────────────
# IK folder / template policy
# ──────────────────────────────────────────────────────────────────
def ik_suffix(app: str) -> str:
    """IK folder suffix: AddBox → ``'AddBox'`` (=> ``IK_AddBox/``), else ``''``."""
    return "AddBox" if app == "AddBox" else ""


def ik_template(app: str, *, default: str, addbox: str) -> str:
    """Pick IK template path per app."""
    return addbox if app == "AddBox" else default
