"""Bake reserve / residual / torque ``CoordinateActuator`` set into an osim.

이 모듈은 b_Build_Model 단계에서 SO·JR 가 곧바로 사용할 수 있도록
reserve / residual / torque 액추에이터를 각 osim 파일에 더해 둔다.
파일명은 변하지 않는다 (``SUB{n}_Scaled.osim`` 및 HeavyHand / WeldBox /
SplitBox 파생 모델 모두 in-place).

- pelvis_*               → ``residual_pelvis_*`` (translation 100/200/100,
                           rotation 80)
- L5_S1_* (lumbar)       → ``torque_L5_S1_*`` (10 / 5 / 5)
- arm_*/elbow/wrist/...  → ``reserve_<coord>`` (200)

기존 ``c_Run_Tools/opensim_pipeline_handlers.py`` 안의 ``_add_reserve`` /
``_build_actuator_model`` 로직을 이쪽으로 이관한 것이며, 향후 SO setup
XML 은 ``_Actuator`` 접미사 없이 동일 모델을 가리키게 된다.
"""

from __future__ import annotations

import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CODES_DIR = os.path.dirname(THIS_DIR)
if CODES_DIR not in sys.path:
    sys.path.insert(0, CODES_DIR)

_OSIM_DLL_DIR = "C:/OpenSim 4.5/bin"
if hasattr(os, "add_dll_directory") and os.path.isdir(_OSIM_DLL_DIR):
    os.add_dll_directory(_OSIM_DLL_DIR)

import opensim as osim

import SUB_Info as _sub_info
from PATH_RULE import ResultPaths


# ──────────────────────────────────────────────────────────────────
# Reserve specs
#
# (coord_name, optimal_force).  Naming convention follows the OLD pipeline:
#   - pelvis_*      → residual_<coord>
#   - L5_S1_*       → torque_<coord>      (also any 'lumbar*' if present)
#   - everything else → reserve_<coord>
# ──────────────────────────────────────────────────────────────────
_PELVIS_RESERVES: tuple[tuple[str, float], ...] = (
    ("pelvis_tx", 100.0),
    ("pelvis_ty", 200.0),
    ("pelvis_tz", 100.0),
    ("pelvis_tilt", 80.0),
    ("pelvis_list", 80.0),
    ("pelvis_rotation", 80.0),
)
_LUMBAR_RESERVES: tuple[tuple[str, float], ...] = (
    ("L5_S1_Flex_Ext", 10.0),
    ("L5_S1_Lat_Bending", 5.0),
    ("L5_S1_axial_rotation", 5.0),
)
_SIDED_RESERVE_COORDS: tuple[str, ...] = (
    "arm_flex", "arm_add", "arm_rot",
    "elbow_flex", "pro_sup",
    "wrist_flex", "wrist_dev",
    "hip_rotation", "hip_flexion", "hip_adduction",
    "knee_angle", "ankle_angle",
)
_SIDED_RESERVE_FORCE: float = 200.0

# Sentinel actuator name used for idempotency check.  If the model's
# ForceSet already contains this exact name we assume the full reserve
# block has been baked in.
_SENTINEL_ACTUATOR_NAME: str = "residual_pelvis_tx"


# ──────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────
def _coord_exists(model: "osim.Model", coord: str) -> bool:
    coord_set = model.getCoordinateSet()
    for i in range(coord_set.getSize()):
        if coord_set.get(i).getName() == coord:
            return True
    return False


def _force_exists(model: "osim.Model", force_name: str) -> bool:
    force_set = model.getForceSet()
    for i in range(force_set.getSize()):
        if force_set.get(i).getName() == force_name:
            return True
    return False


def _actuator_name_for(coord: str) -> str:
    if coord.startswith("lumbar") or coord.startswith("L5"):
        return f"torque_{coord}"
    if coord.startswith("pelvis"):
        return f"residual_{coord}"
    return f"reserve_{coord}"


def _add_reserve(model: "osim.Model", coord: str, optimal_force: float) -> bool:
    """Add one ``CoordinateActuator`` if the coord exists and isn't already added.

    Returns True if a new actuator was appended.
    """
    if not _coord_exists(model, coord):
        # Don't silently produce a broken model: surface the missing coord
        # but keep going for the rest.
        print(f"  [WARN] Coordinate not found in model, skipping reserve: {coord}")
        return False

    name = _actuator_name_for(coord)
    if _force_exists(model, name):
        return False

    actu = osim.CoordinateActuator(coord)
    actu.setName(name)
    actu.setMinControl(-10000.0)
    actu.setMaxControl(10000.0)
    actu.setOptimalForce(float(optimal_force))
    model.addForce(actu)
    return True


# ──────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────
def has_reserve_actuators(model_path: str) -> bool:
    """``True`` iff the osim at ``model_path`` already has the sentinel actuator."""
    if not os.path.isfile(model_path):
        return False
    model = osim.Model(model_path)
    return _force_exists(model, _SENTINEL_ACTUATOR_NAME)


def add_reserve_actuators(model_path: str,
                          *, overwrite: bool = False) -> str:
    """Inject reserve/residual/torque actuators into an osim file in place.

    Parameters
    ----------
    model_path : str
        Absolute path to the ``.osim`` file (read + overwrite).
    overwrite : bool, default False
        If False and the sentinel actuator already exists, this is a no-op
        (idempotent — safe to call again).  If True, missing reserves are
        appended even when the sentinel is present (existing reserves keep
        their current optimal_force; only truly missing ones are added).

    Returns
    -------
    str
        ``model_path`` (echoed for chaining).
    """
    if not os.path.isfile(model_path):
        raise FileNotFoundError(model_path)

    model = osim.Model(model_path)
    sentinel_present = _force_exists(model, _SENTINEL_ACTUATOR_NAME)
    if sentinel_present and not overwrite:
        print(f"[SKIP] Reserves already baked: {os.path.basename(model_path)}")
        return model_path

    added = 0
    for coord, force in _PELVIS_RESERVES:
        added += int(_add_reserve(model, coord, force))
    for coord, force in _LUMBAR_RESERVES:
        added += int(_add_reserve(model, coord, force))
    for side in ("_l", "_r"):
        for base in _SIDED_RESERVE_COORDS:
            added += int(_add_reserve(model, f"{base}{side}", _SIDED_RESERVE_FORCE))

    model.finalizeConnections()
    model.printToXML(model_path)
    print(f"[Reserves] {os.path.basename(model_path)}: +{added} actuators")
    return model_path


def add_reserve_actuators_for_subject(namecode: str,
                                      *, overwrite: bool = False) -> str | None:
    """피험자 1명의 ``SUB{n}_Scaled.osim`` 에 reserves 주입."""
    rp = ResultPaths(namecode)
    path = rp.model_path()
    if not os.path.isfile(path):
        print(f"[MISSING] {namecode}: {path}")
        return None
    return add_reserve_actuators(path, overwrite=overwrite)


def add_reserve_actuators_all(namecodes: list[str] | None = None,
                              *, overwrite: bool = False) -> dict[str, str | None]:
    """모든 피험자 일괄."""
    if namecodes is None:
        namecodes = list(_sub_info.subjects.keys())
    return {nc: add_reserve_actuators_for_subject(nc, overwrite=overwrite)
            for nc in namecodes}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namecode", default=None,
                        help="단일 피험자 namecode (생략 시 전체 일괄)")
    parser.add_argument("--overwrite", action="store_true",
                        help="이미 reserves 가 있어도 부족분 보충 시도")
    args = parser.parse_args()

    if args.namecode:
        add_reserve_actuators_for_subject(args.namecode, overwrite=args.overwrite)
    else:
        add_reserve_actuators_all(overwrite=args.overwrite)
