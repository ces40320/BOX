"""Plot MeasuredEHF vs preRiCTO vs postRiCTO hand forces from ExtLoad MOTs.

Lab frame (OpenSim Y-up): subjects face −Z, so
  vx → ML,  vy → vertical,  vz → AP.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .ricto_io import read_opensim_storage

APPS_DEFAULT: tuple[str, ...] = ("MeasuredEHF", "preRiCTO", "postRiCTO")
HANDS: tuple[tuple[str, str], ...] = (
    ("L (force3)", "hand_force3"),
    ("R (force4)", "hand_force4"),
)
# OpenSim component → anatomical label (subject faces −Z).
AXES: tuple[tuple[str, str], ...] = (
    ("vx", "ML"),
    ("vy", "Vertical"),
    ("vz", "AP"),
)
STYLES = {
    "MeasuredEHF": {"color": "black", "ls": "--", "lw": 1.2, "label": "MeasuredEHF"},
    "preRiCTO": {"color": "red", "ls": "-", "lw": 1.1, "label": "pre-RiCTO"},
    "postRiCTO": {"color": "blue", "ls": "-", "lw": 1.1, "label": "post-RiCTO"},
}


def _load_hand_forces(mot_path: str | Path) -> pd.DataFrame:
    df, _ = read_opensim_storage(mot_path)
    cols = ["time"]
    for _, prefix in HANDS:
        for ax, _anat in AXES:
            cols.append(f"{prefix}_{ax}")
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(f"{mot_path}: missing {missing}")
    return df[cols].copy()


def plot_ehf_compare(
    *,
    namecode: str,
    condition: str,
    seg: str,
    apps: Sequence[str] = APPS_DEFAULT,
    out_path: Optional[str | Path] = None,
    show: bool = False,
) -> str:
    """Overlay hand forces: MeasuredEHF / pre-RiCTO / post-RiCTO.

    Saves under ``ConditionPaths.ricto_plot_path(seg, tag='ehf_compare')`` by default.
    """
    import PATH_RULE as _path

    rp = _path.ResultPaths(namecode)
    cp = rp.for_condition(condition)

    series: dict[str, pd.DataFrame] = {}
    for app in apps:
        path = cp.extload_path(seg, app)
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        series[app] = _load_hand_forces(path)

    fig, axes = plt.subplots(
        len(HANDS),
        len(AXES),
        figsize=(12.5, 6.5),
        sharex=True,
        constrained_layout=True,
    )
    if len(HANDS) == 1:
        axes = np.asarray([axes])

    for i, (hand_lab, prefix) in enumerate(HANDS):
        for j, (ax_name, anat) in enumerate(AXES):
            ax = axes[i, j]
            col = f"{prefix}_{ax_name}"
            for app, df in series.items():
                st = STYLES.get(app, {"color": "gray", "ls": "-", "lw": 1.0, "label": app})
                ax.plot(
                    df["time"].to_numpy(dtype=float),
                    df[col].to_numpy(dtype=float),
                    color=st["color"],
                    linestyle=st["ls"],
                    linewidth=st["lw"],
                    label=st["label"],
                )
            ax.set_title(f"{hand_lab}  {anat} ({ax_name})")
            ax.set_ylabel("Force (N)")
            if i == len(HANDS) - 1:
                ax.set_xlabel("time (s)")

    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=len(apps), frameon=False)
    fig.suptitle(
        f"EHF compare  {rp.sub_label}  {condition}  {seg}  ({namecode})"
        "  |  face −Z: vx=ML, vy=Vertical, vz=AP",
        fontsize=11,
    )

    if out_path is None:
        out_path = cp.ricto_plot_path(seg, tag="ehf_compare")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    if show:
        plt.show()
    else:
        plt.close(fig)
    return str(out_path)


def plot_ehf_compare_many(
    *,
    namecode: str,
    condition: str,
    segments: Iterable[str],
    apps: Sequence[str] = APPS_DEFAULT,
) -> list[str]:
    written = []
    for seg in segments:
        written.append(
            plot_ehf_compare(
                namecode=namecode,
                condition=condition,
                seg=seg,
                apps=apps,
            )
        )
    return written
