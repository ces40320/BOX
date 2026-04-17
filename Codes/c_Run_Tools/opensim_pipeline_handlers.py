import os
from lxml import etree


def _maybe_add_opensim_dll_dir() -> None:
    """Add OpenSim DLL directory on Windows if available."""
    add_dll = getattr(os, "add_dll_directory", None)
    if add_dll is None:
        return
    dll_dir = "C:/OpenSim 4.5/bin"
    if os.path.isdir(dll_dir):
        add_dll(dll_dir)


def prepare_extload_setup(
    *,
    cp,
    seg: str,
    app: str,
    extload_template_path: str,
    dry_run: bool = False,
) -> str:
    """Create ExtLoad setup XML under the planned condition/section structure."""
    setup_xml_path = cp.setup_extload_path(seg, app)
    extload_mot_path = cp.extload_path(seg, app)

    if dry_run:
        return setup_xml_path

    tree = etree.parse(extload_template_path)
    root = tree.getroot()
    datafile_element = root.find(".//datafile")
    if datafile_element is None:
        raise ValueError(f"Template missing <datafile>: {extload_template_path}")

    datafile_element.text = extload_mot_path
    os.makedirs(os.path.dirname(setup_xml_path), exist_ok=True)
    tree.write(setup_xml_path, pretty_print=True, encoding="UTF-8", xml_declaration=True)
    return setup_xml_path


def run_ik(
    *,
    cp,
    rp,
    seg: str,
    app: str,
    ik_template_default: str,
    ik_template_addbox: str,
    dry_run: bool = False,
) -> str:
    """Run IK and write setup/result files to planned structure."""
    trc_path = cp.trc_path(seg)
    model_type = "" if app == "MeasuredEHF" else app
    model_path = rp.model_path(model_type)
    ik_suffix = "AddBox" if app == "AddBox" else ""
    setup_ik_path = cp.setup_ik_path(seg, ik_suffix)
    ik_output_path = cp.ik_path(seg, ik_suffix)
    ik_template = ik_template_addbox if app == "AddBox" else ik_template_default

    if dry_run:
        return setup_ik_path

    _maybe_add_opensim_dll_dir()
    import numpy as np
    import pandas as pd
    import opensim as osim

    df = pd.read_csv(trc_path, sep="\t", skiprows=4)
    trcdata = np.array(df)

    model = osim.Model(model_path)
    ik = osim.InverseKinematicsTool(ik_template)
    ik.setName(rp.sub_label)
    ik.set_marker_file(trc_path)
    ik.setModel(model)
    ik.setStartTime(trcdata[1, 1])
    ik.setEndTime(trcdata[-1, 1])
    ik.setOutputMotionFileName(ik_output_path)

    os.makedirs(os.path.dirname(setup_ik_path), exist_ok=True)
    ik.printToXML(setup_ik_path)
    ik.run()
    return setup_ik_path
