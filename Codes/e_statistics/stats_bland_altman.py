# -*- coding: utf-8 -*-
"""Bland–Altman plots and bias/LoA tables for timing errors."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_CODES = _HERE.parent
_RESULTS = _CODES / "d_Results_Analysis"
for _p in (str(_CODES), str(_RESULTS), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from analysis_utils import result_paths  # noqa: E402
from stats_io import manuscript_figures_dir, stats_long_dir, stats_models_dir  # noqa: E402
from stats_timing_error import build_timing_abserr, process_subject as build_timing  # noqa: E402


def bland_altman_stats(diff: np.ndarray) -> dict:
    d = np.asarray(diff, dtype=float)
    d = d[np.isfinite(d)]
    if d.size == 0:
        return {
            "n": 0,
            "bias": float("nan"),
            "sd": float("nan"),
            "loa_low": float("nan"),
            "loa_high": float("nan"),
        }
    bias = float(np.mean(d))
    sd = float(np.std(d, ddof=1)) if d.size > 1 else 0.0
    return {
        "n": int(d.size),
        "bias": bias,
        "sd": sd,
        "loa_low": bias - 1.96 * sd,
        "loa_high": bias + 1.96 * sd,
    }


def plot_bland_altman(
    mean_vals: np.ndarray,
    diff: np.ndarray,
    *,
    title: str,
    out_path: Path,
    xlabel: str = "Mean of methods (s)",
    ylabel: str = "Difference (s)",
    dpi: int = 300,
) -> Optional[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    stats = bland_altman_stats(diff)
    if stats["n"] == 0:
        return None
    fig, ax = plt.subplots(figsize=(8, 6), dpi=dpi)
    ax.scatter(mean_vals, diff, c="0.3", s=28, alpha=0.75, edgecolors="none")
    ax.axhline(stats["bias"], color="black", lw=1.5, label=f"bias={stats['bias']:.3f}")
    ax.axhline(stats["loa_low"], color="red", ls="--", lw=1.2, label="95% LoA")
    ax.axhline(stats["loa_high"], color="red", ls="--", lw=1.2)
    ax.set_xlabel(xlabel, fontname="Arial", fontsize=14)
    ax.set_ylabel(ylabel, fontname="Arial", fontsize=14)
    ax.set_title(title, fontname="Arial", fontsize=14)
    ax.legend(frameon=False, prop={"family": "Arial", "size": 11})
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(direction="in")
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)
    return out_path


def process_subject(namecode: str, *, dpi: int = 300) -> dict:
    rp = result_paths(namecode)
    long_path = stats_long_dir() / f"timing_abserr_{rp.sub_label}.csv"
    if not long_path.is_file():
        build_timing(namecode)
    df = pd.read_csv(long_path)
    # Rebuild from by_segment for mean of methods (GT and method times)
    from stats_io import ricto_summary_xlsx

    bs = pd.read_excel(ricto_summary_xlsx(rp.sub_label), sheet_name="by_segment")
    rows = []
    fig_paths = []
    model_dir = stats_models_dir()
    fig_dir = manuscript_figures_dir() / rp.sub_label
    fig_dir.mkdir(parents=True, exist_ok=True)

    contrasts = [
        ("RiCTO", "Grip", "ricto_onset", "gt_onset", "err_onset_s"),
        ("RiCTO", "Deposit", "ricto_offset", "gt_offset", "err_offset_s"),
        ("BoxMarker", "Grip", "marker_onset", "gt_onset", "err_marker_onset_s"),
        ("BoxMarker", "Deposit", "marker_offset", "gt_offset", "err_marker_offset_s"),
    ]
    for method, event, mcol, gcol, ecol in contrasts:
        sub = bs[[mcol, gcol, ecol]].dropna()
        if sub.empty:
            continue
        method_t = sub[mcol].to_numpy(dtype=float)
        gt_t = sub[gcol].to_numpy(dtype=float)
        diff = sub[ecol].to_numpy(dtype=float)
        mean_t = 0.5 * (method_t + gt_t)
        st = bland_altman_stats(diff)
        rows.append(
            {
                "sub": rp.sub_label,
                "contrast": f"{method} - GT",
                "event": event,
                **st,
            }
        )
        tag = f"BlandAltman_{method}_{event}_{rp.sub_label}"
        png = fig_dir / f"{tag}.png"
        plot_bland_altman(
            mean_t,
            diff,
            title=f"{rp.sub_label} {method} vs GT ({event})",
            out_path=png,
            dpi=dpi,
        )
        # also copy stats-side png
        model_png = model_dir / f"{tag}.png"
        plot_bland_altman(
            mean_t,
            diff,
            title=f"{rp.sub_label} {method} vs GT ({event})",
            out_path=model_png,
            dpi=dpi,
        )
        fig_paths.append(str(png))

    out_csv = model_dir / f"BlandAltman_timing_{rp.sub_label}.csv"
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    return {"table": str(out_csv), "figures": fig_paths, "n_contrasts": len(rows)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--namecode", default="260526_PJH")
    args = ap.parse_args()
    print(process_subject(args.namecode))


if __name__ == "__main__":
    main()
