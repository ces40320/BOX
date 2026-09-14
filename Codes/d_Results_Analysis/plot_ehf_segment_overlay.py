# -*- coding: utf-8 -*-
"""Single-segment EHF axis overlays (apps vs MeasuredEHF).

Writes FreeBox plot paths (``…_FreeBox_ehf_{axis}.png``) with legend label
**LoadShare**, and mirrors copies under ``Analysis/…/_figures/EHF/``.

Example::

    python plot_ehf_segment_overlay.py --namecode 260526_PJH \\
        --condition 7kg_10bpm --seg 1AB
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

_HERE = Path(__file__).resolve().parent
_CODES = _HERE.parent
for _p in (str(_CODES), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from analysis_utils import (  # noqa: E402
    APP_PLOT_STYLE,
    EHF_COMPARE_APPS,
    N_RESAMPLE,
    crop_by_time,
    ehf_components_from_mot,
    figures_dir,
    load_storage,
    measured_contact_window,
    resample_series,
    resolve_extload_mot,
    result_paths,
    rmse,
)
from export_ehf_marker_rect_heavyhand import heavyhand_dataframe  # noqa: E402


def _load_compare_apps(
    namecode: str,
    cond: str,
    seg: str,
    apps: Sequence[str],
) -> Tuple[Dict[str, object], List[str], List[str]]:
    """Return (app → DataFrame), found apps, missing apps.

    HeavyHand uses the BK + marker-rect estimator (same as ``run_ehf_analysis``);
    other apps load ExtLoad ``.mot`` (local then Dropbox).
    """
    found: Dict[str, object] = {}
    missing: List[str] = []
    for app in apps:
        try:
            if app == "HeavyHand":
                found[app] = heavyhand_dataframe(
                    namecode, cond, seg, use_markers=True
                )
            else:
                path = resolve_extload_mot(namecode, cond, seg, app)
                if path is None:
                    missing.append(app)
                    continue
                found[app] = load_storage(path)
        except Exception as e:
            print(f"[skip] {app}: {e}")
            missing.append(app)
    return found, list(found.keys()), missing


def _pack_hand_axes(
    df,
    hand: str,
    t_on: float,
    t_off: float,
    axes: Sequence[str],
) -> Dict[str, np.ndarray]:
    comp = ehf_components_from_mot(df, hand)
    cropped = crop_by_time(
        comp["time"],
        {k: comp[k] for k in axes},
        t_on,
        t_off,
    )
    return {ax: resample_series(cropped[ax]) for ax in axes}


def plot_segment_overlay(
    namecode: str,
    cond: str,
    seg: str,
    *,
    apps: Sequence[str] = EHF_COMPARE_APPS,
    axes: Sequence[str] = ("ML", "Vertical", "AP"),
) -> dict:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rp = result_paths(namecode)
    cp = rp.for_condition(cond)
    raw_by_app, present, missing = _load_compare_apps(namecode, cond, seg, apps)
    if "MeasuredEHF" not in raw_by_app:
        raise FileNotFoundError(
            f"MeasuredEHF ExtLoad missing for {namecode} {cond} {seg} "
            f"(needed for contact window / RMSE)."
        )

    t_on, t_off = measured_contact_window(raw_by_app["MeasuredEHF"])
    packs: Dict[str, Dict[str, Dict[str, np.ndarray]]] = {}
    for app, df in raw_by_app.items():
        packs[app] = {
            hand: _pack_hand_axes(df, hand, t_on, t_off, axes) for hand in ("L", "R")
        }

    x = np.linspace(0.0, 100.0, N_RESAMPLE)
    out_paths: List[str] = []
    rmse_rows: List[dict] = []
    fig_root = figures_dir("EHF")

    for ax in axes:
        fig, axes_lr = plt.subplots(1, 2, figsize=(12, 5), dpi=150, sharey=True)
        for i, hand in enumerate(("L", "R")):
            axp = axes_lr[i]
            for app in present:
                sty = APP_PLOT_STYLE.get(
                    app, {"color": "gray", "linestyle": "-", "label": app}
                )
                y = packs[app][hand][ax]
                axp.plot(
                    x,
                    y,
                    color=sty["color"],
                    linestyle=sty["linestyle"],
                    linewidth=2.0,
                    label=sty["label"],
                )
                if app != "MeasuredEHF":
                    rmse_rows.append(
                        {
                            "cond": cond,
                            "seg": seg,
                            "hand": hand,
                            "axis": ax,
                            "app": app,
                            "label": sty["label"],
                            "RMSE_full": rmse(packs["MeasuredEHF"][hand][ax], y),
                        }
                    )
            axp.set_title(f"{hand} hand", fontname="Arial", fontsize=13)
            axp.set_xlabel("Time (%)", fontname="Arial", fontsize=12)
            if i == 0:
                axp.set_ylabel(f"{ax} force (N)", fontname="Arial", fontsize=12)
            axp.tick_params(direction="in")
            for spine in ("top", "right"):
                axp.spines[spine].set_visible(False)
            axp.legend(frameon=False, prop={"family": "Arial", "size": 9})

        fig.suptitle(
            f"EHF {ax} — {rp.sub_label} {cond} {seg}",
            fontname="Arial",
            fontsize=14,
        )
        fig.tight_layout(rect=(0, 0, 1, 0.95))

        freebox_out = Path(cp.freebox_plot_path(seg, tag=f"ehf_{ax}"))
        freebox_out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(freebox_out)
        mirror = fig_root / f"{rp.sub_label}_{cond}_{seg}_ehf_{ax}.png"
        shutil.copy2(freebox_out, mirror)
        plt.close(fig)
        out_paths.extend([str(freebox_out), str(mirror)])

    return {
        "present": present,
        "missing": missing,
        "contact": (t_on, t_off),
        "paths": out_paths,
        "rmse": rmse_rows,
    }


def _print_rmse(rows: List[dict], focus_apps: Sequence[str] = ("FreeBox", "postRiCTO")) -> None:
    if not rows:
        return
    print("\nRMSE vs MeasuredEHF (N), contact-window % time:")
    hdr = f"{'app':12} {'hand':4} {'axis':10} {'RMSE':>8}"
    print(hdr)
    print("-" * len(hdr))
    focus = set(focus_apps)
    for r in rows:
        if focus and r["app"] not in focus:
            continue
        print(
            f"{r['label']:12} {r['hand']:4} {r['axis']:10} {r['RMSE_full']:8.2f}"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--namecode", default="260526_PJH")
    ap.add_argument("--condition", default="7kg_10bpm")
    ap.add_argument("--seg", default="1AB")
    ap.add_argument(
        "--apps",
        default=",".join(EHF_COMPARE_APPS),
        help="Comma-separated ExtLoad app keys",
    )
    args = ap.parse_args()
    apps = [a.strip() for a in args.apps.split(",") if a.strip()]
    result = plot_segment_overlay(
        args.namecode, args.condition, args.seg, apps=apps
    )
    print(f"[ok] apps: {', '.join(result['present'])}")
    if result["missing"]:
        print(f"[skip] missing: {', '.join(result['missing'])}")
    print(
        f"[contact] t_on={result['contact'][0]:.3f}s  "
        f"t_off={result['contact'][1]:.3f}s"
    )
    for p in result["paths"]:
        print(f"[png] {p}")
    _print_rmse(result["rmse"])


if __name__ == "__main__":
    main()
