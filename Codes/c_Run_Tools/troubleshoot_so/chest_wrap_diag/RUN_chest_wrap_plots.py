"""Plot Chest wrap diagnosis CSVs (OpenSim not required).

Reads ``Analysis/.../chest_wrap/<SUB>/diag/chest_diag_*.csv`` and writes PNGs
to ``…/diag/plots/``.

Example::

    python RUN_chest_wrap_plots.py --namecode 260526_PJM
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _ts_paths  # noqa: E402,F401

from PATH_RULE import ResultPaths  # noqa: E402
from chest_diag_lib import chest_out_dir, cycle_percent  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

FAIL_COLORS = {
    "ok": "#888888",
    "pierce": "#d62728",
    "wrong_side": "#ff7f0e",
    "unwrap_rewrap": "#9467bd",
    "tangent_jump": "#2ca02c",
    "endpoint_inside": "#8c564b",
    "length_jump": "#e377c2",
}


def _load_diag(namecode: str) -> pd.DataFrame:
    diag_dir = chest_out_dir(namecode, "diag")
    paths = sorted(glob.glob(os.path.join(diag_dir, "chest_diag_*.csv")))
    paths = [p for p in paths if "chest_diag_all_" not in os.path.basename(p)]
    if not paths:
        allp = os.path.join(
            diag_dir, f"chest_diag_all_{ResultPaths(namecode).sub_label}.csv",
        )
        if os.path.isfile(allp):
            return pd.read_csv(allp)
        return pd.DataFrame()
    return pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)


def plot_length_by_muscle(df: pd.DataFrame, out_dir: str, max_muscles: int = 12) -> None:
    import matplotlib.pyplot as plt

    muscles = (
        df.groupby("muscle")["failure_type"]
        .apply(lambda s: (s != "ok").sum())
        .sort_values(ascending=False)
        .head(max_muscles)
        .index.tolist()
    )
    for mus in muscles:
        g = df[df["muscle"] == mus].sort_values(["condition", "segment", "time_s"])
        if g.empty:
            continue
        fig, ax = plt.subplots(figsize=(10, 3.5))
        for (cond, seg), gg in g.groupby(["condition", "segment"]):
            t = gg["time_s"].to_numpy(dtype=float)
            cp = cycle_percent(t)
            ax.plot(cp, gg["length_m"], color="#aaaaaa", lw=0.8, alpha=0.5)
            for ftype, color in FAIL_COLORS.items():
                if ftype == "ok":
                    continue
                m = gg["failure_type"] == ftype
                if not m.any():
                    continue
                ax.scatter(
                    cp[m.to_numpy()],
                    gg.loc[m, "length_m"],
                    s=12, c=color, label=ftype, zorder=3,
                )
        ax.set_title(f"{mus} length vs cycle % (failures highlighted)")
        ax.set_xlabel("cycle %")
        ax.set_ylabel("length (m)")
        handles, labels = ax.get_legend_handles_labels()
        by = dict(zip(labels, handles))
        if by:
            ax.legend(by.values(), by.keys(), fontsize=7, loc="best")
        fig.tight_layout()
        fig.savefig(os.path.join(out_dir, f"length_{mus}.png"), dpi=120)
        plt.close(fig)


def plot_q_scatter(df: pd.DataFrame, out_dir: str) -> None:
    import matplotlib.pyplot as plt

    qfe, qlb = "q_L5_S1_Flex_Ext", "q_L5_S1_Lat_Bending"
    if qfe not in df.columns or qlb not in df.columns:
        return
    fig, ax = plt.subplots(figsize=(6, 5))
    ok = df["failure_type"] == "ok"
    ax.scatter(
        np.rad2deg(df.loc[ok, qfe]), np.rad2deg(df.loc[ok, qlb]),
        s=4, c="#bbbbbb", alpha=0.3, label="ok",
    )
    fail = df[~ok]
    for ftype, color in FAIL_COLORS.items():
        if ftype == "ok":
            continue
        m = fail["failure_type"] == ftype
        if not m.any():
            continue
        ax.scatter(
            np.rad2deg(fail.loc[m, qfe]), np.rad2deg(fail.loc[m, qlb]),
            s=10, c=color, label=ftype, alpha=0.8,
        )
    ax.set_xlabel("L5–S1 flex/ext (deg)")
    ax.set_ylabel("L5–S1 lat bend (deg)")
    ax.set_title("Failure loci in L5–S1 angle plane")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "q_scatter_flex_lat.png"), dpi=120)
    plt.close(fig)


def plot_contact_local(df: pd.DataFrame, out_dir: str) -> None:
    import matplotlib.pyplot as plt

    need = ["contact_local_x", "contact_local_y", "contact_local_z"]
    if any(c not in df.columns for c in need):
        return
    g = df.dropna(subset=need)
    if g.empty:
        return
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    pairs = (("x", "y"), ("x", "z"), ("y", "z"))
    for ax, (a, b) in zip(axes, pairs):
        for ftype, color in FAIL_COLORS.items():
            m = g["failure_type"] == ftype
            if not m.any():
                continue
            ax.scatter(
                g.loc[m, f"contact_local_{a}"],
                g.loc[m, f"contact_local_{b}"],
                s=6, c=color, alpha=0.5, label=ftype,
            )
        ax.set_xlabel(a)
        ax.set_ylabel(b)
        ax.set_title(f"contact local {a}-{b}")
        ax.set_aspect("equal", adjustable="datalim")
    handles, labels = axes[0].get_legend_handles_labels()
    by = dict(zip(labels, handles))
    fig.legend(by.values(), by.keys(), loc="upper center", ncol=4, fontsize=7)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(os.path.join(out_dir, "contact_local_projections.png"), dpi=120)
    plt.close(fig)


def plot_heatmap(df: pd.DataFrame, out_dir: str) -> None:
    import matplotlib.pyplot as plt

    if "time_s" not in df.columns:
        return
    rows = []
    for (mus, cond, seg), g in df.groupby(["muscle", "condition", "segment"]):
        t = g["time_s"].to_numpy(dtype=float)
        cp = cycle_percent(t)
        fail = (g["failure_type"] != "ok").to_numpy()
        bins = np.linspace(0, 100, 21)
        for i in range(len(bins) - 1):
            m = (cp >= bins[i]) & (cp < bins[i + 1])
            if not m.any():
                continue
            rows.append({
                "muscle": mus,
                "bin": 0.5 * (bins[i] + bins[i + 1]),
                "fail_frac": float(fail[m].mean()),
            })
    if not rows:
        return
    hdf = pd.DataFrame(rows)
    # average across trials
    piv = hdf.groupby(["muscle", "bin"])["fail_frac"].mean().unstack("bin")
    fig, ax = plt.subplots(figsize=(10, max(4, 0.25 * len(piv))))
    im = ax.imshow(piv.to_numpy(dtype=float), aspect="auto", vmin=0, vmax=1,
                   cmap="magma")
    ax.set_yticks(range(len(piv.index)))
    ax.set_yticklabels(list(piv.index), fontsize=7)
    ax.set_xticks(range(len(piv.columns)))
    ax.set_xticklabels([f"{c:.0f}" for c in piv.columns], fontsize=7)
    ax.set_xlabel("cycle % bin center")
    ax.set_title("Failure fraction heatmap (muscle × cycle %)")
    fig.colorbar(im, ax=ax, fraction=0.02)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "fail_heatmap_cycle.png"), dpi=120)
    plt.close(fig)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--namecode", required=True)
    args = p.parse_args()
    df = _load_diag(args.namecode)
    if df.empty:
        print("[plots] no diagnosis CSV found — run RUN_chest_wrap_diagnose.py first")
        return 1
    out_dir = chest_out_dir(args.namecode, "diag", "plots")
    plot_length_by_muscle(df, out_dir)
    plot_q_scatter(df, out_dir)
    plot_contact_local(df, out_dir)
    plot_heatmap(df, out_dir)
    print(f"[plots] → {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
