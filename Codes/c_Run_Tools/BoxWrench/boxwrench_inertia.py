"""Box mass / inertia from BOX.osim (XML), with condition-kg scaling."""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, Optional, Tuple

try:
    from . import boxwrench_config as cfg
except ImportError:  # script / flat import path
    import boxwrench_config as cfg


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def parse_box_inertial(
    osim_path: str,
    *,
    body_name: str = cfg.DEFAULT_BOX_BODY_NAME,
) -> Dict[str, float]:
    """Read mass, mass_center, diagonal+product inertia from an OpenSim model XML."""
    if not os.path.isfile(osim_path):
        raise FileNotFoundError(osim_path)
    root = ET.parse(osim_path).getroot()
    body = None
    for el in root.iter():
        if _local(el.tag) == "Body" and el.attrib.get("name") == body_name:
            body = el
            break
    if body is None:
        raise KeyError(f"Body {body_name!r} not found in {osim_path}")

    def _text(child: str) -> str:
        for el in body:
            if _local(el.tag) == child and el.text:
                return el.text.strip()
        raise KeyError(f"{child} missing on body {body_name!r}")

    mass = float(_text("mass"))
    mc = [float(x) for x in _text("mass_center").split()]
    if len(mc) != 3:
        raise ValueError(f"mass_center expected 3 values, got {mc}")
    # OpenSim Vec6: Ixx Iyy Izz Ixy Ixz Iyz
    iner = [float(x) for x in _text("inertia").split()]
    if len(iner) != 6:
        raise ValueError(f"inertia expected 6 values, got {iner}")
    return {
        "mass": mass,
        "com_x": mc[0],
        "com_y": mc[1],
        "com_z": mc[2],
        "Ixx": iner[0],
        "Iyy": iner[1],
        "Izz": iner[2],
        "Ixy": iner[3],
        "Ixz": iner[4],
        "Iyz": iner[5],
        "osim_path": os.path.abspath(osim_path),
        "body_name": body_name,
    }


def scale_inertial_to_mass(
    props: Dict[str, float],
    target_mass_kg: float,
    *,
    ref_mass: Optional[float] = None,
) -> Dict[str, float]:
    """Uniform density scale: I ∝ m (same geometry). COM offsets unchanged."""
    m0 = float(ref_mass if ref_mass is not None else props["mass"])
    m1 = float(target_mass_kg)
    if m0 <= 0:
        raise ValueError(f"reference mass must be >0, got {m0}")
    s = m1 / m0
    out = dict(props)
    out["mass"] = m1
    out["scale_from_ref"] = s
    for k in ("Ixx", "Iyy", "Izz", "Ixy", "Ixz", "Iyz"):
        out[k] = float(props[k]) * s
    return out


def load_box_props_for_condition(
    condition_or_mass,
    *,
    osim_path: str = cfg.DEFAULT_BOX_OSIM,
    body_name: str = cfg.DEFAULT_BOX_BODY_NAME,
) -> Dict[str, float]:
    """Parse condition ``Nkg_...`` or a float mass, scale shipped BOX.osim."""
    if isinstance(condition_or_mass, (int, float)):
        mass = float(condition_or_mass)
    else:
        m = re.match(r"(\d+)\s*kg", str(condition_or_mass), flags=re.IGNORECASE)
        if not m:
            raise ValueError(f"Cannot parse kg from {condition_or_mass!r}")
        mass = float(m.group(1))
    base = parse_box_inertial(osim_path, body_name=body_name)
    return scale_inertial_to_mass(base, mass, ref_mass=base["mass"])


def principal_inertia_diag(props: Dict[str, float]) -> Tuple[float, float, float]:
    """Vendor ExtForceGen uses only Ixx,Iyy,Izz (products ignored)."""
    return float(props["Ixx"]), float(props["Iyy"]), float(props["Izz"])
