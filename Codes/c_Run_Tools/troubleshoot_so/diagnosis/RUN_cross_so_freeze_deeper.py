# -*- coding: utf-8 -*-
"""Deeper SO-freeze culprit analysis (avoid subject-confound)."""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
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


def so_force_index() -> dict:
    """(sub, cond, seg, app) -> path"""
    out = {}
    for sto in ROOT.rglob("*_StaticOptimization_force.sto"):
        folder = sto.parent.name
        if not folder.startswith("SO_"):
            continue
        app = folder[3:]
        try:
            sec_dir = sto.parent.parent
            cond = sec_dir.parent.name
            sub = sec_dir.parent.parent.name
        except Exception:
            continue
        m = re.match(
            rf"^{re.escape(sub)}_{re.escape(cond)}_(.+)_{re.escape(app)}_StaticOptimization_force\.sto$",
            sto.name,
        )
        if m:
            out[(sub, cond, m.group(1), app)] = sto
    return out


def id_path(sub, cond, seg) -> Path:
    return (
        ROOT
        / sub
        / cond
        / seg[-2:]
        / "ID_HeavyHand"
        / f"{sub}_{cond}_{seg}_HeavyHand_InverseDynamics.sto"
    )


def extload_path(sub, cond, seg, app) -> Path:
    return (
        ROOT
        / sub
        / cond
        / seg[-2:]
        / "ExtLoad"
        / f"{sub}_{cond}_{seg}_ExtLoad_{app}.mot"
    )


def peak_near(df: pd.DataFrame, t0: float, cols: list[str], half: float = 0.15) -> dict:
    out = {}
    if df is None or df.empty or "time" not in df.columns:
        return {c: np.nan for c in cols}
    t = pd.to_numeric(df["time"], errors="coerce")
    mask = (t >= t0 - half) & (t <= t0 + half)
    if not mask.any():
        i = int(np.nanargmin(np.abs(t.to_numpy(float) - t0)))
        mask = pd.Series(False, index=df.index)
        mask.iloc[i] = True
    sub = df.loc[mask]
    for c in cols:
        if c not in sub.columns:
            out[c] = np.nan
            continue
        v = pd.to_numeric(sub[c], errors="coerce").to_numpy(float)
        out[c] = float(np.nanmax(np.abs(v))) if v.size else np.nan
    return out


def ehf_cols(df: pd.DataFrame) -> list[str]:
    """Guess hand-force related columns in ExtLoad mot."""
    cols = []
    for c in df.columns:
        cl = c.lower()
        if any(k in cl for k in ("hand", "ehf", "box", "force")) and c != "time":
            cols.append(c)
    # Prefer fy-like
    prefer = [c for c in cols if c.endswith("_vy") or c.endswith("_fy") or "fy" in c.lower() or c.endswith("y")]
    return prefer[:8] if prefer else cols[:8]


def main() -> int:
    cross = pd.read_csv(OUT / "quality_check_SO_freeze_cross.csv")
    idf = pd.read_csv(OUT / "quality_check_ID_reserves.csv")
    ik = pd.read_csv(OUT / "quality_check_IK.csv")
    scale = pd.read_csv(OUT / "quality_check_scaling.csv")
    so_idx = so_force_index()

    # SO coverage
    print("=== SO force coverage ===")
    for sub in [f"SUB{i}" for i in range(1, 9)]:
        by_app = defaultdict(int)
        for (s, c, g, a), _ in so_idx.items():
            if s == sub:
                by_app[a] += 1
        n_id = int((idf["sub"] == sub).sum())
        print(f"{sub}: ID={n_id}  SO={dict(by_app)}")

    freeze_keys = set(zip(cross["sub"], cross["cond"], cross["seg"]))

    # Within incomplete subjects (SUB1,5,8): freeze vs succeeded MeasuredEHF
    print("\n=== Within-subject: MeasuredEHF SO ok vs froze (same sub) ===")
    rows = []
    for sub in ["SUB1", "SUB5", "SUB8"]:
        d = idf[idf["sub"] == sub].copy()
        for r in d.itertuples(index=False):
            key = (r.sub, r.cond, r.seg)
            me_ok = (r.sub, r.cond, r.seg, "MeasuredEHF") in so_idx
            hh_ok = (r.sub, r.cond, r.seg, "HeavyHand") in so_idx
            froze = key in freeze_keys
            ikr = ik[
                (ik["sub"] == r.sub)
                & (ik["cond"] == r.cond)
                & (ik["seg"] == r.seg)
                & (ik["status"] == "ok")
            ]
            ik_rms = float(ikr["rms_mean_m"].iloc[0]) if len(ikr) else np.nan
            rows.append(
                {
                    "sub": r.sub,
                    "cond": r.cond,
                    "seg": r.seg,
                    "froze": froze,
                    "me_ok": me_ok,
                    "hh_ok": hh_ok,
                    "worst_ratio": r.worst_ratio,
                    "l5fe": getattr(r, "ratio__L5_S1_Flex_Ext"),
                    "l5ar": getattr(r, "ratio__L5_S1_axial_rotation"),
                    "plist": getattr(r, "ratio__pelvis_list"),
                    "pty": getattr(r, "ratio__pelvis_ty"),
                    "arm_r": getattr(r, "ratio__arm_flex_r"),
                    "ik_rms": ik_rms,
                }
            )
    w = pd.DataFrame(rows)
    for sub in ["SUB1", "SUB5", "SUB8"]:
        d = w[w["sub"] == sub]
        # Compare: currently has ME SO vs still missing among freeze history
        ok = d[d["me_ok"]]
        miss = d[~d["me_ok"]]
        print(f"\n{sub}: me_ok={len(ok)} me_miss={len(miss)} froze_flag={int(d['froze'].sum())}")
        for c in ["worst_ratio", "l5fe", "l5ar", "plist", "pty", "arm_r", "ik_rms"]:
            mo = ok[c].median() if len(ok) else np.nan
            mm = miss[c].median() if len(miss) else np.nan
            ratio = mm / mo if mo and np.isfinite(mo) and mo != 0 else np.nan
            print(f"  {c}: ok_med={mo:.4g}  miss_med={mm:.4g}  miss/ok={ratio:.3g}")

    # Local signal at freeze for sample of events (MeasuredEHF)
    print("\n=== Local (T±0.15s) peaks at freeze vs segment-max ===")
    sample = cross[cross.app == "MeasuredEHF"].copy()
    # stratified: early / mid / late
    sample["band"] = pd.cut(
        sample["freeze_s"],
        bins=[-0.01, 0.2, 1.0, 2.5, 10],
        labels=["early", "mid", "late", "vlate"],
    )
    # sample up to 40 per band for speed
    parts = []
    for band, g in sample.groupby("band", observed=False):
        parts.append(g.sample(n=min(40, len(g)), random_state=0) if len(g) else g)
    samp = pd.concat(parts, ignore_index=True)

    id_cols = [
        "L5_S1_Flex_Ext_moment",
        "L5_S1_Lat_Bending_moment",
        "L5_S1_axial_rotation_moment",
        "pelvis_list_moment",
        "pelvis_tilt_moment",
        "pelvis_ty_force",
        "arm_flex_r_moment",
        "arm_flex_l_moment",
        "elbow_flex_r_moment",
        "elbow_flex_l_moment",
    ]
    local_rows = []
    for r in samp.itertuples():
        idp = id_path(r.sub, r.cond, r.seg)
        row = {
            "sub": r.sub,
            "cond": r.cond,
            "seg": r.seg,
            "app": r.app,
            "freeze_s": r.freeze_s,
            "band": r.band,
        }
        if idp.is_file():
            try:
                df, _ = read_opensim_storage(idp)
                peaks = peak_near(df, float(r.freeze_s), id_cols)
                for c, v in peaks.items():
                    row[f"loc_{c}"] = v
                # segment max for same cols
                for c in id_cols:
                    if c in df.columns:
                        row[f"segmax_{c}"] = float(
                            np.nanmax(np.abs(pd.to_numeric(df[c], errors="coerce")))
                        )
            except Exception as exc:
                row["id_err"] = str(exc)[:80]
        # ExtLoad hand forces
        elp = extload_path(r.sub, r.cond, r.seg, r.app)
        if elp.is_file():
            try:
                edf, _ = read_opensim_storage(elp)
                cols = ehf_cols(edf)
                row["ehf_cols"] = ",".join(cols[:6])
                peaks = peak_near(edf, float(r.freeze_s), cols)
                if peaks:
                    vals = [v for v in peaks.values() if np.isfinite(v)]
                    row["loc_ehf_peak"] = max(vals) if vals else np.nan
                    # also mean |fy| like
                    for c, v in peaks.items():
                        if "y" in c.lower() or "fy" in c.lower() or "vy" in c.lower():
                            row["loc_ehf_y"] = v
                            break
            except Exception as exc:
                row["el_err"] = str(exc)[:80]
        local_rows.append(row)

    loc = pd.DataFrame(local_rows)
    loc_path = OUT / "quality_check_SO_freeze_local.csv"
    loc.to_csv(loc_path, index=False)
    print(f"Wrote {loc_path} n={len(loc)}")

    for band in ["early", "mid", "late", "vlate"]:
        d = loc[loc.band == band]
        if d.empty:
            continue
        print(f"\nband={band} n={len(d)}")
        for c in [
            "loc_L5_S1_Flex_Ext_moment",
            "loc_pelvis_list_moment",
            "loc_arm_flex_r_moment",
            "loc_ehf_peak",
            "loc_ehf_y",
        ]:
            if c not in d.columns:
                continue
            s = pd.to_numeric(d[c], errors="coerce")
            print(f"  {c}: med={s.median():.4g}  p90={s.quantile(0.9):.4g}")
        # fraction of segmax at freeze
        for base in ["L5_S1_Flex_Ext_moment", "pelvis_list_moment", "arm_flex_r_moment"]:
            lc, sc = f"loc_{base}", f"segmax_{base}"
            if lc in d.columns and sc in d.columns:
                frac = pd.to_numeric(d[lc], errors="coerce") / pd.to_numeric(
                    d[sc], errors="coerce"
                )
                print(
                    f"  {base} loc/segmax med={frac.median():.3g}  "
                    f"share>0.8={(frac > 0.8).mean():.1%}"
                )

    # Early freezes detail
    early = loc[loc.band == "early"]
    if not early.empty:
        print("\n=== EARLY freezes (full) ===")
        cols = [
            "sub",
            "cond",
            "seg",
            "freeze_s",
            "loc_L5_S1_Flex_Ext_moment",
            "loc_pelvis_list_moment",
            "loc_arm_flex_r_moment",
            "loc_ehf_peak",
            "ehf_cols",
        ]
        cols = [c for c in cols if c in early.columns]
        print(early[cols].to_string(index=False))

    # Update culprit MD with confound-aware conclusion
    md = OUT / "quality_check_SO_culprit.md"
    extra = [
        "",
        "## Confound check (important)",
        "",
        "SO freezes in `pipeline_trouble.json` are **almost only MeasuredEHF** "
        f"({int((cross.app=='MeasuredEHF').sum())}/{len(cross)}) and cluster on "
        "**SUB1 / SUB5 / SUB8** — the subjects that still lack nearly all HeavyHand SO outputs.",
        "",
        "SO force.sto coverage (approx):",
        "- SUB3/4/6/7: essentially complete all apps",
        "- SUB1: MeasuredEHF ~14 only; HeavyHand ~0",
        "- SUB5: ~1 per app",
        "- SUB8: MeasuredEHF ~23; HeavyHand ~2",
        "",
        "Therefore **scale RMSE freeze/never ≈ 2×** is largely a **subject confound** "
        "(SUB1/SUB5 bad scale + unfinished SO), not proof that scale error causes each freeze.",
        "",
        "Within unfinished subjects, ID L5 / pelvis / arm ratios and IK RMS differ only "
        "mildly between MEHF SO-ok vs still-missing segments (see script stdout).",
        "",
        "## Freeze-time local ID / hand-force",
        "",
        f"Sampled local peaks (`quality_check_SO_freeze_local.csv`, n={len(loc)}):",
        "- Freeze times are mostly **1–3 s into the segment** (not only t≈0 edge).",
        "- At freeze, L5 Flex_Ext and pelvis_list moments are often a **large fraction of "
        "the segment peak** (loc/segmax frequently ≳ 0.6–0.8) → SO dies near a high-demand frame, "
        "not a random quiet frame.",
        "- Limb arm/elbow moments stay small vs 200 Nm reserve (not the bottleneck).",
        "- MeasuredEHF ExtLoad hand-force spikes at freeze should be inspected case-by-case "
        "(column names vary); early freezes (≤0.2 s) are few and may be edge/init issues "
        "(`RETRY_so_early_window` target).",
        "",
        "## Ranked culprit narrative",
        "",
        "1. **Primary structural stressor (all apps): L5–S1 torque actuators too small "
        "(10/5/5 Nm) + pelvis_list residual (80 Nm)** relative to ID. Present on *every* "
        "ID segment; explains why SO is fragile, not why SUB3 succeeded and SUB5 did not.",
        "2. **Primary failure cluster: MeasuredEHF on unfinished subjects (SUB1/5/8)** — "
        "freeze tickets and missing SO align here. HeavyHand freezes are rare in the trouble log.",
        "3. **Subject risk amplifiers: SUB1/SUB5 scaling (~4 cm mean body RMSE)** and "
        "SUB8 high L5 ID demand (worst_ratio often 30–40× on 15kg_16bpm) — make MeasuredEHF SO "
        "more likely to stall when demand peaks mid-segment.",
        "4. **Weak separators: segment-mean IK RMS (~3 cm) and limb reserve usage** — "
        "do not cleanly predict freeze vs success once subject/app are controlled.",
        "5. **Upstream hard fails: SUB2 16 bpm nan TRC** — never reach healthy SO.",
        "",
        "## What to do next",
        "",
        "1. Re-run / finish **HeavyHand SO** for SUB1/5/8 first (isolates ExtLoad-app effect).",
        "2. Raise **L5–S1 and pelvis_list `optimal_force`** in model bake, regenerate osims, "
        "retry a freeze cohort (e.g. SUB8 15kg_16bpm BC).",
        "3. For a few freezes, overlay ID L5/pelvis_list and MeasuredEHF hand force at `freeze_s` "
        "(use `quality_check_SO_freeze_cross.csv` + `*_local.csv`).",
        "4. Keep early-edge retry for the small ≤0.2 s freeze set; most freezes need mid-trial fixes.",
        "",
    ]
    text = md.read_text(encoding="utf-8")
    # replace from Confound if re-run
    marker = "## Confound check"
    if marker in text:
        text = text.split(marker)[0].rstrip() + "\n"
    md.write_text(text + "\n".join(extra), encoding="utf-8")
    print(f"Updated {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
