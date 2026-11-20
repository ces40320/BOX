# -*- coding: utf-8 -*-
"""Compare ID L5/pelvis moments vs SO torque/residual forces on successful SO trials.

Hypothesis: ID can look >> optimal_force, but successful SO may keep
actual CoordinateActuator forces nearer the intended capacity — or it may
also use large forces (control >> 1). Check both.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_CODES = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(_CODES), str(_CODES / "c_Run_Tools")]

import PATH_RULE as _path  # noqa: E402
from optimization.ricto_io import read_opensim_storage  # noqa: E402

ROOT = Path(_path.OPENSIM_DIR) / "Asymmetric"
# Outputs / cross-inputs live under Analysis/Asymmetric/_diagnosis/quality_check.
OUT = Path(_path.diagnosis_dir("Asymmetric", "quality_check"))

# coord -> (id_col, so_col, optimal_force)
SPECS = [
    ("L5_S1_Flex_Ext", "L5_S1_Flex_Ext_moment", "torque_L5_S1_Flex_Ext", 10.0),
    ("L5_S1_Lat_Bending", "L5_S1_Lat_Bending_moment", "torque_L5_S1_Lat_Bending", 5.0),
    ("L5_S1_axial_rotation", "L5_S1_axial_rotation_moment", "torque_L5_S1_axial_rotation", 5.0),
    ("pelvis_list", "pelvis_list_moment", "residual_pelvis_list", 80.0),
    ("pelvis_tilt", "pelvis_tilt_moment", "residual_pelvis_tilt", 80.0),
    ("pelvis_ty", "pelvis_ty_force", "residual_pelvis_ty", 200.0),
    ("arm_flex_r", "arm_flex_r_moment", "reserve_arm_flex_r", 200.0),
]


def discover_pairs(app: str = "HeavyHand") -> list[dict]:
    """Match successful SO force.sto to ID InverseDynamics.sto."""
    pairs = []
    for so in ROOT.rglob(f"*_{app}_StaticOptimization_force.sto"):
        folder = so.parent.name
        if folder != f"SO_{app}":
            continue
        try:
            sec = so.parent.parent.name
            cond = so.parent.parent.parent.name
            sub = so.parent.parent.parent.parent.name
        except Exception:
            continue
        m = re.match(
            rf"^{re.escape(sub)}_{re.escape(cond)}_(.+)_{re.escape(app)}_StaticOptimization_force\.sto$",
            so.name,
        )
        if not m:
            continue
        seg = m.group(1)
        idp = (
            ROOT
            / sub
            / cond
            / sec
            / "ID_HeavyHand"
            / f"{sub}_{cond}_{seg}_HeavyHand_InverseDynamics.sto"
        )
        if not idp.is_file():
            continue
        pairs.append(
            {
                "sub": sub,
                "cond": cond,
                "seg": seg,
                "app": app,
                "so_path": so,
                "id_path": idp,
            }
        )
    return pairs


def max_abs(df: pd.DataFrame, col: str) -> float:
    if col not in df.columns:
        return np.nan
    v = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
    return float(np.nanmax(np.abs(v))) if v.size else np.nan


def analyze(app: str = "HeavyHand", limit: int | None = None) -> pd.DataFrame:
    pairs = discover_pairs(app)
    print(f"[{app}] paired SO+ID: {len(pairs)}")
    rows = []
    for i, p in enumerate(pairs):
        if limit is not None and i >= limit:
            break
        try:
            so_df, _ = read_opensim_storage(p["so_path"])
            id_df, _ = read_opensim_storage(p["id_path"])
        except Exception as exc:
            rows.append({**{k: p[k] for k in ("sub", "cond", "seg", "app")}, "status": f"fail:{exc}"})
            continue
        row = {
            "sub": p["sub"],
            "cond": p["cond"],
            "seg": p["seg"],
            "app": p["app"],
            "status": "ok",
        }
        for name, id_col, so_col, lim in SPECS:
            id_m = max_abs(id_df, id_col)
            so_f = max_abs(so_df, so_col)
            row[f"id_max__{name}"] = id_m
            row[f"so_max__{name}"] = so_f
            row[f"limit__{name}"] = lim
            row[f"id_ratio__{name}"] = id_m / lim if lim and np.isfinite(id_m) else np.nan
            row[f"so_ratio__{name}"] = so_f / lim if lim and np.isfinite(so_f) else np.nan
            # implied |control| if force = control * optimal_force
            row[f"so_ctrl__{name}"] = so_f / lim if lim and np.isfinite(so_f) else np.nan
            row[f"so_over_id__{name}"] = (
                so_f / id_m if np.isfinite(so_f) and np.isfinite(id_m) and id_m > 1e-9 else np.nan
            )
        rows.append(row)
        if (i + 1) % 100 == 0:
            print(f"  …{i+1}/{len(pairs)}")
    return pd.DataFrame(rows)


def summarize(df: pd.DataFrame, label: str) -> None:
    ok = df[df["status"] == "ok"]
    print(f"\n=== {label} n={len(ok)} ===")
    print(
        f"{'coord':<22} {'limit':>6} {'ID med':>8} {'ID p95':>8} {'SO med':>8} {'SO p95':>8} "
        f"{'IDr med':>8} {'SOr med':>8} {'SO>lim%':>8} {'SO/ID':>7}"
    )
    for name, _, _, lim in SPECS:
        idm = ok[f"id_max__{name}"]
        som = ok[f"so_max__{name}"]
        idr = ok[f"id_ratio__{name}"]
        sor = ok[f"so_ratio__{name}"]
        so_over = (som > lim).mean() * 100
        so_id = ok[f"so_over_id__{name}"]
        print(
            f"{name:<22} {lim:6.0f} {idm.median():8.1f} {idm.quantile(0.95):8.1f} "
            f"{som.median():8.1f} {som.quantile(0.95):8.1f} "
            f"{idr.median():8.2f} {sor.median():8.2f} {so_over:7.1f}% {so_id.median():7.2f}"
        )


def main() -> int:
    # HeavyHand: fair compare (ID is HeavyHand-only)
    hh = analyze("HeavyHand")
    out = OUT / "quality_check_ID_vs_SO_reserves.csv"
    hh.to_csv(out, index=False)
    print(f"Wrote {out} ({len(hh)} rows)")
    summarize(hh, "HeavyHand SO success")

    # Also a MeasuredEHF sample if many exist (ID still HeavyHand)
    me = analyze("MeasuredEHF")
    out2 = OUT / "quality_check_ID_vs_SO_reserves_MeasuredEHF.csv"
    me.to_csv(out2, index=False)
    print(f"Wrote {out2} ({len(me)} rows)")
    summarize(me, "MeasuredEHF SO success (ID=HeavyHand)")

    # Brief MD
    ok = hh[hh["status"] == "ok"]
    lines = [
        "# ID moment vs SO actuator force (successful SO only)",
        "",
        "Question: ID L5–S1 moments look ≫ `optimal_force` (10/5/5 Nm). "
        "On trials where SO **finished**, do the SO `torque_L5_S1_*` / "
        "`residual_pelvis_*` forces stay near those limits, or do they also go large?",
        "",
        f"Pairs: HeavyHand SO + HeavyHand ID → `{out.name}` (n={len(ok)}).",
        "",
        "## Result (HeavyHand)",
        "",
        "| coord | limit | ID max median | SO force median | ID/limit | SO/limit | % SO>limit |",
        "|-------|-------|---------------|-----------------|----------|----------|------------|",
    ]
    for name, _, _, lim in SPECS:
        idm = ok[f"id_max__{name}"].median()
        som = ok[f"so_max__{name}"].median()
        idr = ok[f"id_ratio__{name}"].median()
        sor = ok[f"so_ratio__{name}"].median()
        pct = (ok[f"so_max__{name}"] > lim).mean() * 100
        lines.append(
            f"| {name} | {lim:g} | {idm:.1f} | {som:.1f} | {idr:.2f} | {sor:.2f} | {pct:.0f}% |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- OpenSim SO `*_force.sto` columns for CoordinateActuators are "
            "**actuator forces** ≈ `control × optimal_force`. "
            "So `so_ratio = so_max/limit` is approximately **|control|**.",
            "- If SO stayed “within intended capacity”, SO/limit would cluster near ≤1. "
            "If SO also exceeds, the optimizer is freely using |control|≫1 "
            "(allowed by min/max_control=±10000) — ID’s large moments are then "
            "**real demand**, not an ID-only artifact.",
            "",
        ]
    )
    # auto fill based on L5 FE
    l5_so_r = ok["so_ratio__L5_S1_Flex_Ext"].median()
    l5_id_r = ok["id_ratio__L5_S1_Flex_Ext"].median()
    if np.isfinite(l5_so_r):
        if l5_so_r > 2:
            lines.append(
                f"**Finding:** On successful HeavyHand SO, median SO `torque_L5_S1_Flex_Ext` "
                f"force is **{ok['so_max__L5_S1_Flex_Ext'].median():.0f} Nm** "
                f"(~{l5_so_r:.1f}× the 10 Nm `optimal_force`), comparable in order to "
                f"ID median max **{ok['id_max__L5_S1_Flex_Ext'].median():.0f} Nm** "
                f"(~{l5_id_r:.1f}×). So successful SO does **not** stay inside the 10 Nm "
                "nominal torque budget — it absorbs the large ID demand with large controls."
            )
        else:
            lines.append(
                f"**Finding:** Successful SO keeps L5 FE near the limit "
                f"(SO/limit median={l5_so_r:.2f}) while ID/limit={l5_id_r:.2f} — "
                "muscles would then be carrying most of the ID moment."
            )
    lines.append("")
    lines.append(f"MeasuredEHF companion table: `{out2.name}`.")
    lines.append("")
    md = OUT / "quality_check_ID_vs_SO_reserves.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
