# -*- coding: utf-8 -*-
"""Cross quality-check metrics with SO freeze / pipeline_trouble failures."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_CODES = Path(__file__).resolve().parents[3]
if str(_CODES) not in sys.path:
    sys.path.insert(0, str(_CODES))

import PATH_RULE as _path  # noqa: E402
import SUB_Info as _sub_info  # noqa: E402

ROOT = Path(_path.OPENSIM_DIR) / "Asymmetric"
# Outputs / cross-inputs live under Analysis/Asymmetric/_diagnosis/quality_check.
OUT = Path(_path.diagnosis_dir("Asymmetric", "quality_check"))
TROUBLE_JSON = Path(_path.pipeline_state_path("Asymmetric", "pipeline_trouble.json"))
FREEZE_RE = re.compile(r"freeze_sim_time_s:\s*([0-9]+(?:\.[0-9]+)?)", re.I)
STALL_RE = re.compile(r"log.?stall|unchanged|freeze", re.I)


def namecode_to_sub() -> Dict[str, str]:
    out = {}
    for nc, info in _sub_info.subjects.items():
        if info.get("protocol") != "Asymmetric":
            continue
        n = int(info["SUB_number"])
        if 1 <= n <= 8:
            out[nc] = f"SUB{n}"
    return out


def extract_freeze(entry: dict) -> Optional[float]:
    raw = entry.get("freeze_sim_time")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    m = FREEZE_RE.search(str(entry.get("error", "")))
    if m:
        return float(m.group(1))
    return None


def is_so_related(entry: dict) -> bool:
    tool = str(entry.get("tool", "")).lower()
    err = str(entry.get("error", ""))
    if tool.startswith("so") or tool == "so":
        return True
    if "staticoptimization" in err.lower():
        return True
    if "so_" in tool:
        return True
    # freeze times are harvested from SO AnalyzeTool stalls
    if extract_freeze(entry) is not None and "so" in tool:
        return True
    return False


def is_freeze_stall(entry: dict) -> bool:
    if extract_freeze(entry) is not None:
        return True
    err = str(entry.get("error", ""))
    return bool(STALL_RE.search(err)) and "so" in str(entry.get("tool", "")).lower()


def load_troubles() -> pd.DataFrame:
    with open(TROUBLE_JSON, encoding="utf-8") as f:
        raw = json.load(f)
    nc_map = namecode_to_sub()
    rows = []
    for e in raw:
        freeze = extract_freeze(e)
        tool = str(e.get("tool", ""))
        rows.append(
            {
                "namecode": e.get("namecode"),
                "sub": nc_map.get(e.get("namecode"), ""),
                "cond": e.get("condition"),
                "seg": e.get("segment"),
                "section": e.get("section"),
                "app": e.get("app"),
                "tool": tool,
                "error": str(e.get("error", ""))[:300],
                "ts": e.get("ts"),
                "freeze_s": freeze,
                "is_so": is_so_related(e),
                "is_freeze": is_freeze_stall(e),
            }
        )
    return pd.DataFrame(rows)


def so_success_map() -> Dict[Tuple[str, str, str, str], bool]:
    """(sub, cond, seg, app) -> has StaticOptimization_force.sto"""
    out: Dict[Tuple[str, str, str, str], bool] = {}
    for sto in ROOT.rglob("*_StaticOptimization_force.sto"):
        # …/SUBn/cond/SEC/SO_APP/file
        try:
            app_folder = sto.parent.name  # SO_HeavyHand
            if not app_folder.startswith("SO_"):
                continue
            app = app_folder[3:]
            sec = sto.parent.parent.name
            cond = sto.parent.parent.parent.name
            sub = sto.parent.parent.parent.parent.name
            m = re.match(
                rf"^{re.escape(sub)}_{re.escape(cond)}_(.+)_{re.escape(app)}_StaticOptimization_force\.sto$",
                sto.name,
            )
            if not m:
                continue
            seg = m.group(1)
            out[(sub, cond, seg, app)] = True
        except Exception:
            continue
    return out


def window_peak_from_id(
    id_sto: Path, t_freeze: float, half_win: float = 0.15
) -> Dict[str, float]:
    """Peak |M| near freeze time for key coords (from ID sto)."""
    from optimization.ricto_io import read_opensim_storage

    coords = [
        "L5_S1_Flex_Ext",
        "L5_S1_Lat_Bending",
        "L5_S1_axial_rotation",
        "pelvis_list",
        "pelvis_tilt",
        "pelvis_ty",
        "arm_flex_r",
        "arm_flex_l",
        "elbow_flex_r",
        "elbow_flex_l",
    ]
    out = {f"win_max_abs__{c}": np.nan for c in coords}
    out["win_n"] = 0
    if not id_sto.is_file() or not np.isfinite(t_freeze):
        return out
    try:
        df, _ = read_opensim_storage(id_sto)
    except Exception:
        return out
    if "time" not in df.columns:
        return out
    t = pd.to_numeric(df["time"], errors="coerce")
    mask = (t >= t_freeze - half_win) & (t <= t_freeze + half_win)
    if not mask.any():
        # nearest frame
        i = int(np.nanargmin(np.abs(t.to_numpy(dtype=float) - t_freeze)))
        mask = pd.Series(False, index=df.index)
        mask.iloc[i] = True
    sub = df.loc[mask]
    out["win_n"] = int(len(sub))
    for c in coords:
        col = f"{c}_force" if c in ("pelvis_tx", "pelvis_ty", "pelvis_tz") else f"{c}_moment"
        if col not in sub.columns:
            continue
        vals = pd.to_numeric(sub[col], errors="coerce").to_numpy(dtype=float)
        if vals.size:
            out[f"win_max_abs__{c}"] = float(np.nanmax(np.abs(vals)))
    return out


def main() -> int:
    sys.path.insert(0, str(_CODES / "c_Run_Tools"))

    troubles = load_troubles()
    ik = pd.read_csv(OUT / "quality_check_IK.csv")
    idf = pd.read_csv(OUT / "quality_check_ID_reserves.csv")
    scale = pd.read_csv(OUT / "quality_check_scaling.csv")

    print("=== Trouble overview ===")
    print("total", len(troubles))
    print("tools", Counter(troubles["tool"]).most_common(15))
    so_t = troubles[troubles["is_so"]]
    fr_t = troubles[troubles["is_freeze"]]
    print("is_so", len(so_t), "is_freeze", len(fr_t))
    print("freeze tools", Counter(fr_t["tool"]).most_common())
    print("SO apps", Counter(so_t["app"]).most_common())

    # Unique SO freeze events (latest per key)
    freeze_rows = troubles[troubles["freeze_s"].notna()].copy()
    print("\nentries with freeze_s", len(freeze_rows))
    print("freeze by tool", Counter(freeze_rows["tool"]).most_common())
    print("freeze_s describe:\n", freeze_rows["freeze_s"].describe())

    # Focus: SO freezes
    so_freeze = freeze_rows[
        freeze_rows["tool"].astype(str).str.lower().str.startswith("so")
        | freeze_rows["tool"].astype(str).str.contains("SO", case=False, na=False)
    ].copy()
    if so_freeze.empty:
        # any freeze with SO in error
        so_freeze = freeze_rows[
            freeze_rows["error"].str.contains("StaticOptimization|SO_", case=False, na=False)
            | freeze_rows["tool"].astype(str).str.contains("so", case=False, na=False)
        ].copy()
    print("\nSO freeze rows", len(so_freeze))
    if not so_freeze.empty:
        print(so_freeze.groupby(["sub", "app"]).size().unstack(fill_value=0))
        print("freeze_s hist bins:")
        bins = [0, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 3.0, 4.0, 6.0]
        print(pd.cut(so_freeze["freeze_s"], bins=bins, right=False).value_counts().sort_index())

    # Merge quality onto freeze events
    # Prefer HeavyHand ID for dynamics load (ID only exists for HeavyHand)
    id_key = idf.set_index(["sub", "cond", "seg"])
    ik_ok = ik[ik["status"] == "ok"].set_index(["sub", "cond", "seg"])
    scale_map = scale.set_index("sub")["rmse_mean_mm"].to_dict()

    merged = []
    for _, r in so_freeze.iterrows():
        key = (r["sub"], r["cond"], r["seg"])
        row = {
            "sub": r["sub"],
            "cond": r["cond"],
            "seg": r["seg"],
            "app": r["app"],
            "tool": r["tool"],
            "freeze_s": r["freeze_s"],
            "ts": r["ts"],
            "scale_rmse_mm": scale_map.get(r["sub"], np.nan),
        }
        if key in id_key.index:
            idr = id_key.loc[key]
            if isinstance(idr, pd.DataFrame):
                idr = idr.iloc[0]
            for col in (
                "worst_coord",
                "worst_ratio",
                "n_over_limit",
                "n_over_2x",
                "flag_l5s1_over",
                "ratio__L5_S1_Flex_Ext",
                "ratio__L5_S1_Lat_Bending",
                "ratio__L5_S1_axial_rotation",
                "ratio__pelvis_list",
                "ratio__pelvis_tilt",
                "ratio__pelvis_ty",
                "ratio__arm_flex_r",
                "ratio__arm_flex_l",
                "ratio__elbow_flex_r",
                "ratio__elbow_flex_l",
                "max_abs__L5_S1_Flex_Ext",
                "max_abs__L5_S1_axial_rotation",
                "max_abs__pelvis_list",
                "id_sto",
            ):
                row[col] = idr.get(col, np.nan)
        if key in ik_ok.index:
            ikr = ik_ok.loc[key]
            if isinstance(ikr, pd.DataFrame):
                ikr = ikr.iloc[0]
            row["ik_rms_mean_m"] = ikr.get("rms_mean_m", np.nan)
            row["ik_max_err_peak_m"] = ikr.get("max_err_peak_m", np.nan)
        else:
            row["ik_rms_mean_m"] = np.nan
            row["ik_max_err_peak_m"] = np.nan

        # window peak around freeze from ID
        id_sto = row.get("id_sto")
        if isinstance(id_sto, str) and id_sto:
            win = window_peak_from_id(Path(id_sto), float(r["freeze_s"]))
            row.update(win)
        merged.append(row)

    mdf = pd.DataFrame(merged)
    out_csv = OUT / "quality_check_SO_freeze_cross.csv"
    mdf.to_csv(out_csv, index=False)
    print(f"\nWrote {out_csv} ({len(mdf)} rows)")

    # Compare freeze vs success for HeavyHand SO
    success = so_success_map()
    # Build segment-level ID+IK for all ID segments, label hh SO outcome
    hh_apps = ["HeavyHand", "MeasuredEHF", "preRiCTO", "postRiCTO"]
    # Use unique (sub,cond,seg) from ID
    idf2 = idf.copy()
    idf2["ik_rms_mean_m"] = np.nan
    for i, r in idf2.iterrows():
        key = (r["sub"], r["cond"], r["seg"])
        if key in ik_ok.index:
            ikr = ik_ok.loc[key]
            if isinstance(ikr, pd.DataFrame):
                ikr = ikr.iloc[0]
            idf2.at[i, "ik_rms_mean_m"] = ikr.get("rms_mean_m", np.nan)
    idf2["scale_rmse_mm"] = idf2["sub"].map(scale_map)

    # SO HeavyHand success
    idf2["hh_so_ok"] = [
        success.get((r.sub, r.cond, r.seg, "HeavyHand"), False) for r in idf2.itertuples()
    ]
    # ever froze (any app) for this segment
    freeze_keys = set(
        zip(so_freeze["sub"], so_freeze["cond"], so_freeze["seg"])
    ) if not so_freeze.empty else set()
    idf2["ever_so_freeze"] = [
        (r.sub, r.cond, r.seg) in freeze_keys for r in idf2.itertuples()
    ]

    def summarize(df: pd.DataFrame, label: str, cols: List[str]) -> None:
        print(f"\n--- {label} n={len(df)} ---")
        for c in cols:
            if c not in df.columns:
                continue
            s = pd.to_numeric(df[c], errors="coerce")
            print(
                f"  {c}: median={s.median():.3g}  mean={s.mean():.3g}  "
                f"p90={s.quantile(0.9):.3g}"
            )

    metrics = [
        "worst_ratio",
        "ratio__L5_S1_Flex_Ext",
        "ratio__L5_S1_axial_rotation",
        "ratio__pelvis_list",
        "ratio__pelvis_ty",
        "ratio__arm_flex_r",
        "ik_rms_mean_m",
        "scale_rmse_mm",
        "n_over_limit",
    ]
    summarize(idf2[idf2["hh_so_ok"]], "HeavyHand SO OK", metrics)
    summarize(idf2[~idf2["hh_so_ok"]], "HeavyHand SO missing", metrics)
    summarize(idf2[idf2["ever_so_freeze"]], "Ever SO freeze", metrics)
    summarize(idf2[~idf2["ever_so_freeze"]], "Never SO freeze", metrics)

    # Effect size: median difference freeze vs not
    print("\n=== Median ratio: freeze / never_freeze ===")
    a = idf2[idf2["ever_so_freeze"]]
    b = idf2[~idf2["ever_so_freeze"]]
    for c in metrics:
        if c not in idf2.columns:
            continue
        ma = pd.to_numeric(a[c], errors="coerce").median()
        mb = pd.to_numeric(b[c], errors="coerce").median()
        ratio = ma / mb if mb and np.isfinite(mb) and mb != 0 else np.nan
        print(f"  {c}: freeze={ma:.4g}  never={mb:.4g}  freeze/never={ratio:.3g}")

    print("\n=== Median ratio: HH SO missing / OK ===")
    a = idf2[~idf2["hh_so_ok"]]
    b = idf2[idf2["hh_so_ok"]]
    for c in metrics:
        if c not in idf2.columns:
            continue
        ma = pd.to_numeric(a[c], errors="coerce").median()
        mb = pd.to_numeric(b[c], errors="coerce").median()
        ratio = ma / mb if mb and np.isfinite(mb) and mb != 0 else np.nan
        print(f"  {c}: miss={ma:.4g}  ok={mb:.4g}  miss/ok={ratio:.3g}")

    # Freeze-time vs local ID peaks (if we have window metrics)
    if not mdf.empty and "win_max_abs__L5_S1_Flex_Ext" in mdf.columns:
        print("\n=== Freeze events: local vs segment-max ID ===")
        for c in (
            "L5_S1_Flex_Ext",
            "L5_S1_axial_rotation",
            "pelvis_list",
            "arm_flex_r",
            "elbow_flex_r",
        ):
            w = f"win_max_abs__{c}"
            g = f"max_abs__{c}" if f"max_abs__{c}" in mdf.columns else None
            if w not in mdf.columns:
                continue
            ww = pd.to_numeric(mdf[w], errors="coerce")
            print(f"  {c} window peak median={ww.median():.3g}")
            if g:
                gg = pd.to_numeric(mdf[g], errors="coerce")
                frac = (ww / gg).replace([np.inf, -np.inf], np.nan)
                print(
                    f"    window/segmax median={frac.median():.3g}  "
                    f"(>0.7 share={(frac > 0.7).mean():.1%})"
                )

        # Early vs late freeze
        early = mdf[mdf["freeze_s"] <= 0.2]
        late = mdf[mdf["freeze_s"] > 1.0]
        print(f"\nearly freeze (<=0.2s) n={len(early)}  late (>1s) n={len(late)}")
        for label, dfx in (("early", early), ("late", late)):
            if dfx.empty:
                continue
            print(
                f"  {label}: L5FE ratio med={pd.to_numeric(dfx.get('ratio__L5_S1_Flex_Ext'), errors='coerce').median():.3g}  "
                f"IK rms med={pd.to_numeric(dfx.get('ik_rms_mean_m'), errors='coerce').median()*1000:.1f}mm  "
                f"worst_ratio med={pd.to_numeric(dfx.get('worst_ratio'), errors='coerce').median():.3g}"
            )

    # Rank segments that froze by local L5 and arm at freeze
    if not mdf.empty:
        print("\n=== Top freeze events by window L5 FE moment ===")
        if "win_max_abs__L5_S1_Flex_Ext" in mdf.columns:
            top = mdf.nlargest(12, "win_max_abs__L5_S1_Flex_Ext")[
                [
                    "sub",
                    "cond",
                    "seg",
                    "app",
                    "freeze_s",
                    "win_max_abs__L5_S1_Flex_Ext",
                    "ratio__L5_S1_Flex_Ext",
                    "ik_rms_mean_m",
                    "worst_ratio",
                ]
            ]
            print(top.to_string(index=False))

        print("\n=== Freeze time distribution by subject ===")
        print(so_freeze.groupby("sub")["freeze_s"].agg(["count", "median", "min", "max"]))

    # Correlation: freeze_s vs metrics among freeze events
    if len(mdf) >= 10:
        print("\n=== Spearman corr(freeze_s, metric) among freeze events ===")
        for c in [
            "worst_ratio",
            "ratio__L5_S1_Flex_Ext",
            "ratio__L5_S1_axial_rotation",
            "ratio__pelvis_list",
            "ik_rms_mean_m",
            "scale_rmse_mm",
            "win_max_abs__L5_S1_Flex_Ext",
            "win_max_abs__arm_flex_r",
        ]:
            if c not in mdf.columns:
                continue
            x = pd.to_numeric(mdf["freeze_s"], errors="coerce")
            y = pd.to_numeric(mdf[c], errors="coerce")
            mask = x.notna() & y.notna()
            if mask.sum() < 10:
                continue
            rho = x[mask].corr(y[mask], method="spearman")
            print(f"  {c}: rho={rho:.3f}  n={int(mask.sum())}")

    # Write short MD addendum
    md_path = OUT / "quality_check_SO_culprit.md"
    lines = [
        "# SO freeze vs quality metrics — culprit candidates",
        "",
        f"Cross of `pipeline_trouble.json` freeze events with "
        f"`quality_check_IK/ID_reserves/scaling.csv`.",
        f"Detail table: `quality_check_SO_freeze_cross.csv` ({len(mdf)} freeze rows).",
        "",
        "## Freeze landscape",
        "",
        f"- Trouble entries with `freeze_sim_time`: **{len(freeze_rows)}**",
        f"- SO-tagged freeze rows: **{len(so_freeze)}**",
    ]
    if not so_freeze.empty:
        lines.append(
            f"- Freeze time: median **{so_freeze['freeze_s'].median():.2f} s**, "
            f"range {so_freeze['freeze_s'].min():.2f}–{so_freeze['freeze_s'].max():.2f} s"
        )
        vc = pd.cut(
            so_freeze["freeze_s"],
            bins=[0, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 6.0],
            right=False,
        ).value_counts().sort_index()
        lines.append("")
        lines.append("| freeze window (s) | n |")
        lines.append("|-------------------|---|")
        for interval, n in vc.items():
            lines.append(f"| {interval} | {int(n)} |")
    lines.append("")
    lines.append("## Association with quality metrics")
    lines.append("")
    lines.append(
        "Compared segment-level ID/IK/scaling between segments that **ever SO-froze** "
        "vs never, and HeavyHand SO **missing** vs OK:"
    )
    lines.append("")
    lines.append("| metric | freeze median | never median | freeze/never | HH-miss / HH-ok |")
    lines.append("|--------|---------------|--------------|--------------|-----------------|")
    for c in metrics:
        if c not in idf2.columns:
            continue
        fa = pd.to_numeric(idf2.loc[idf2["ever_so_freeze"], c], errors="coerce").median()
        fb = pd.to_numeric(idf2.loc[~idf2["ever_so_freeze"], c], errors="coerce").median()
        ma = pd.to_numeric(idf2.loc[~idf2["hh_so_ok"], c], errors="coerce").median()
        mb = pd.to_numeric(idf2.loc[idf2["hh_so_ok"], c], errors="coerce").median()
        r1 = fa / fb if fb and np.isfinite(fb) and fb != 0 else np.nan
        r2 = ma / mb if mb and np.isfinite(mb) and mb != 0 else np.nan
        lines.append(
            f"| `{c}` | {fa:.4g} | {fb:.4g} | {r1:.3g} | {r2:.3g} |"
        )
    lines.append("")
    lines.append("## Interpretation (ranked suspects)")
    lines.append("")
    lines.append(
        "1. **L5–S1 ID demand ≫ torque actuator `optimal_force` (10/5/5 Nm)** — "
        "universal on all ID segments; not a separator of freeze vs success by itself "
        "(everyone is over), but it is the structural SO stressor. "
        "Segments with **extreme** Flex_Ext / axial ratios and **high window peaks "
        "near freeze_s** are the strongest local suspects."
    )
    lines.append(
        "2. **`pelvis_list` residual overload (80 Nm)** — also chronically over; "
        "check whether freeze windows coincide with list-moment spikes."
    )
    lines.append(
        "3. **IK marker RMS (~3 cm cohort)** — weak/moderate separator unless "
        "freeze/never or miss/ok ratios clearly >1; SUB2 nan-TRC 16 bpm are hard failures upstream of SO."
    )
    lines.append(
        "4. **Scaling (SUB1/SUB5 ~4 cm)** — subject-level risk factor; "
        "does not explain within-subject freeze times."
    )
    lines.append(
        "5. **Limb reserve 200 Nm** — rarely over limit; **unlikely primary SO freeze driver**."
    )
    lines.append("")
    lines.append("## Practical next checks")
    lines.append("")
    lines.append(
        "- For a freeze at time `T`, plot ID `L5_S1_*_moment` and `pelvis_list_moment` "
        "and SO `torque_*` / `residual_*` controls in `[T−0.2, T+0.2]`."
    )
    lines.append(
        "- Prioritize raising L5–S1 / pelvis_list `optimal_force` (or relaxing SO) "
        "before chasing limb reserves or mild IK RMS differences."
    )
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
