"""Attach CAD/ADDBOX box markers to free-joint BOX.osim (XML or OpenSim API).

Writes ``OpenSim_Process/Model/Design_Box/BOX_with_markers.osim`` by default.
Marker locations come from ``Codes/c_Run_Tools/FreeBox/freebox_markers.py``
(excel + ADDBOX / workflow step 8) — not invented.

ASSUMPTION: free ``BOX`` body frame matches the welded left-half CAD frame used
by ADDBOX (R corners transformed via weld offset Δ). Validate against a static
pose / TRC before trusting box IK residuals.
"""

from __future__ import annotations

import argparse
import os
import sys
import xml.etree.ElementTree as ET
from typing import Dict, Optional, Tuple

_THIS = os.path.dirname(os.path.abspath(__file__))
_CODES = os.path.dirname(_THIS)
_FREEBOX = os.path.join(_CODES, "c_Run_Tools", "FreeBox")
for _p in (_CODES, _FREEBOX, _THIS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import PATH_RULE as _path  # noqa: E402
from freebox_config import (  # noqa: E402
    DEFAULT_BOX_BODY_NAME,
    DEFAULT_BOX_OSIM,
    HANDLE_L_NOM,
    HANDLE_R_NOM,
)
from freebox_markers import markers_in_left_half_frame  # noqa: E402


def _marker_xml(name: str, body: str, loc: Tuple[float, float, float]) -> str:
    x, y, z = loc
    return (
        f'\t\t\t\t<Marker name="{name}">\n'
        f"\t\t\t\t\t<!--Path to a Component that satisfies the Socket 'parent_frame' "
        f"of type PhysicalFrame.-->\n"
        f"\t\t\t\t\t<socket_parent_frame>/bodyset/{body}</socket_parent_frame>\n"
        f"\t\t\t\t\t<!--Location of the station in the parent frame expressed "
        f"in OpenSim meters.-->\n"
        f"\t\t\t\t\t<location>{x:.8f} {y:.8f} {z:.8f}</location>\n"
        f"\t\t\t\t</Marker>\n"
    )


def build_marker_table(
    *,
    include_handles: bool = True,
) -> Dict[str, Tuple[float, float, float]]:
    """Corner markers (+ optional handle centers relative to marker cloud mean)."""
    corners = markers_in_left_half_frame()
    out = dict(corners)
    if include_handles:
        import numpy as np

        mean = np.mean(np.asarray(list(corners.values()), dtype=float), axis=0)
        # CAD body frame: ML on Z (same as HANDLE_*_NOM)
        out["LHANDLE_BOX"] = tuple(float(x) for x in (mean + np.asarray(HANDLE_L_NOM)))
        out["RHANDLE_BOX"] = tuple(float(x) for x in (mean + np.asarray(HANDLE_R_NOM)))
    return out


def attach_markers_xml(
    src_osim: str,
    dst_osim: str,
    *,
    body_name: str = DEFAULT_BOX_BODY_NAME,
    include_handles: bool = True,
) -> str:
    """Insert / replace MarkerSet via text edit (no OpenSim Python required)."""
    with open(src_osim, "r", encoding="utf-8") as f:
        text = f.read()
    if "<MarkerSet" in text:
        raise ValueError(f"{src_osim} already has a MarkerSet; refuse to double-attach")

    markers = build_marker_table(include_handles=include_handles)
    block = ['\t\t<MarkerSet name="markerset">\n', "\t\t\t<objects>\n"]
    for name, loc in markers.items():
        block.append(_marker_xml(name, body_name, loc))
    block.append("\t\t\t</objects>\n")
    block.append("\t\t\t<groups />\n")
    block.append("\t\t</MarkerSet>\n")
    marker_block = "".join(block)

    # Insert before closing </Model>
    needle = "\t</Model>"
    if needle not in text:
        needle = "</Model>"
        marker_block = marker_block.replace("\t\t", "  ")
    if needle not in text:
        raise ValueError("Cannot find </Model> in osim")
    text = text.replace(needle, marker_block + needle, 1)

    os.makedirs(os.path.dirname(os.path.abspath(dst_osim)) or ".", exist_ok=True)
    with open(dst_osim, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return dst_osim


def attach_markers_opensim_api(
    src_osim: str,
    dst_osim: str,
    *,
    body_name: str = DEFAULT_BOX_BODY_NAME,
    include_handles: bool = True,
) -> str:
    """Prefer OpenSim API when the package is importable."""
    import opensim as osim  # type: ignore

    model = osim.Model(src_osim)
    body = model.getBodySet().get(body_name)
    for name, loc in build_marker_table(include_handles=include_handles).items():
        m = osim.Marker()
        m.setName(name)
        m.setParentFrame(body)
        m.set_location(osim.Vec3(*loc))
        model.addMarker(m)
    model.finalizeConnections()
    os.makedirs(os.path.dirname(os.path.abspath(dst_osim)) or ".", exist_ok=True)
    model.printToXML(dst_osim)
    return dst_osim


def build(
    src_osim: Optional[str] = None,
    dst_osim: Optional[str] = None,
    *,
    prefer_api: bool = True,
    include_handles: bool = True,
) -> str:
    src = src_osim or DEFAULT_BOX_OSIM
    dst = dst_osim or _path.freebox_box_osim_path(with_markers=True)
    if prefer_api:
        try:
            return attach_markers_opensim_api(
                src, dst, include_handles=include_handles
            )
        except Exception as exc:  # noqa: BLE001 — fall back to XML
            print(
                f"[build_freebox_model_with_markers] OpenSim API unavailable ({exc}); "
                "XML edit"
            )
    return attach_markers_xml(src, dst, include_handles=include_handles)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Attach box markers to Design_Box/BOX.osim → BOX_with_markers.osim"
    )
    p.add_argument("--src", default=DEFAULT_BOX_OSIM)
    p.add_argument("--dst", default=_path.freebox_box_osim_path(with_markers=True))
    p.add_argument("--xml-only", action="store_true")
    p.add_argument("--no-handles", action="store_true")
    args = p.parse_args(argv)
    out = build(
        args.src,
        args.dst,
        prefer_api=not args.xml_only,
        include_handles=not args.no_handles,
    )
    # Quick sanity: parse XML and count markers
    root = ET.parse(out).getroot()
    n = sum(1 for el in root.iter() if el.tag.endswith("Marker") or el.tag == "Marker")
    print(f"Wrote {out} ({n} Marker elements)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
