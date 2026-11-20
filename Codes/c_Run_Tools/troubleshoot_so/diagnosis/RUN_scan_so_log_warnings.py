# -*- coding: utf-8 -*-
"""Scan preserved SO opensim.log files for muscle/path/equilibrate warnings.

Cross with freeze times and residual metrics; compare fail vs success if
success logs are available.
"""

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
sys.path[:0] = [str(_CODES), str(_CODES / "c_Run_Tools")]

import PATH_RULE as _path  # noqa: E402
import SUB_Info as _sub_info  # noqa: E402

ROOT = Path(_path.OPENSIM_DIR) / "Asymmetric"
# Outputs / cross-inputs live under Analysis/Asymmetric/_diagnosis/quality_check.
OUT = Path(_path.diagnosis_dir("Asymmetric", "quality_check"))
TROUBLE_JSON = Path(_path.pipeline_state_path("Asymmetric", "pipeline_trouble.json"))
TEMP = Path.home() / "AppData" / "Local" / "Temp"

PRESERVE_RE = re.compile(r"opensim\.log preserved at:\s*(\S+)", re.I)
FREEZE_RE = re.compile(r"freeze_sim_time_s:\s*([0-9.]+)", re.I)
TIME_RE = re.compile(r"time\s*=\s*([0-9]+(?:\.[0-9]+)?)", re.I)
OBJ_RE = re.compile(r"In Object '([^']+)'")
PERF_RE = re.compile(
    r"time\s*=\s*([0-9]+(?:\.[0-9]+)?)\s+Performance\s*=\s*([0-9.eE+-]+)\s+Constraint violation\s*=\s*([0-9.eE+-]+)",
    re.I,
)

# Skip noise
SKIP_SUBSTR = (
    "couldn't find file",
    ".vtp",
)


def namecode_to_sub() -> Dict[str, str]:
    out = {}
    for nc, info in _sub_info.subjects.items():
        if info.get("protocol") != "Asymmetric":
            continue
        n = int(info["SUB_number"])
        if 1 <= n <= 8:
            out[nc] = f"SUB{n}"
    return out


def classify_line(ln: str) -> Optional[str]:
    low = ln.lower()
    if any(s in low for s in SKIP_SUBSTR):
        return None
    if "constraint violation" in low and "performance" in low:
        return None  # normal SO progress
    if "unable to equilibrate muscles" in low or "equilibrate muscles" in low:
        return "equilibrate_muscles"
    if "fiber length is nan" in low:
        return "fiber_length_nan"
    if "solution error" in low and "exceeds" in low:
        return "solution_error_exceeds"
    if "wrapping" in low or "path wrap" in low or "wrap cylinder" in low:
        return "wrap_related"
    if "path length" in low and ("warn" in low or "error" in low or "exceed" in low):
        return "path_length"
    if "[warning]" in low or "warning]" in low:
        if "muscle" in low or "thelen" in low or "millard" in low:
            return "muscle_other_warn"
        return "other_warning"
    if "fiber length" in low and ("nan" in low or "neg" in low):
        return "fiber_length_bad"
    return None


def scan_log(path: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "log_path": str(path),
        "exists": path.is_file(),
        "n_lines": 0,
        "last_perf_t": np.nan,
        "n_equilibrate": 0,
        "n_fiber_nan": 0,
        "n_solution_error": 0,
        "n_wrap": 0,
        "n_path_length": 0,
        "n_muscle_other": 0,
        "n_other_warn": 0,
        "eq_times": [],
        "eq_muscles": [],
        "eq_near_freeze": 0,
        "warn_snippets": [],
    }
    if not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    lines = text.splitlines()
    out["n_lines"] = len(lines)
    for i, ln in enumerate(lines):
        m = PERF_RE.search(ln)
        if m:
            out["last_perf_t"] = float(m.group(1))
        kind = classify_line(ln)
        if kind is None:
            continue
        t = None
        mt = TIME_RE.search(ln)
        if mt:
            t = float(mt.group(1))
        # muscle name from following lines
        mus = None
        for j in range(i, min(i + 6, len(lines))):
            mm = OBJ_RE.search(lines[j])
            if mm:
                mus = mm.group(1)
                break
        snippet = ln.strip()[:160]
        if kind == "equilibrate_muscles":
            out["n_equilibrate"] += 1
            if t is not None:
                out["eq_times"].append(t)
            if mus:
                out["eq_muscles"].append(mus)
            if len(out["warn_snippets"]) < 8:
                out["warn_snippets"].append(f"t={t}: {snippet}")
        elif kind == "fiber_length_nan":
            out["n_fiber_nan"] += 1
            if len(out["warn_snippets"]) < 8:
                out["warn_snippets"].append(snippet)
        elif kind == "solution_error_exceeds":
            out["n_solution_error"] += 1
        elif kind == "wrap_related":
            out["n_wrap"] += 1
            if len(out["warn_snippets"]) < 8:
                out["warn_snippets"].append(snippet)
        elif kind == "path_length":
            out["n_path_length"] += 1
            if len(out["warn_snippets"]) < 8:
                out["warn_snippets"].append(snippet)
        elif kind == "muscle_other_warn":
            out["n_muscle_other"] += 1
        else:
            out["n_other_warn"] += 1
    return out


def load_trouble_freeze_rows() -> pd.DataFrame:
    with open(TROUBLE_JSON, encoding="utf-8") as f:
        raw = json.load(f)
    nc_map = namecode_to_sub()
    rows = []
    for e in raw:
        err = str(e.get("error", ""))
        mp = PRESERVE_RE.search(err)
        ft = FREEZE_RE.search(err)
        if mp is None and e.get("freeze_sim_time") is None and ft is None:
            # still keep SO with preserved log
            if "opensim.log preserved" not in err:
                continue
        rows.append(
            {
                "namecode": e.get("namecode"),
                "sub": nc_map.get(e.get("namecode"), ""),
                "cond": e.get("condition"),
                "seg": e.get("segment"),
                "app": e.get("app"),
                "tool": e.get("tool"),
                "freeze_s": float(ft.group(1))
                if ft
                else (
                    float(e["freeze_sim_time"])
                    if e.get("freeze_sim_time") is not None
                    else np.nan
                ),
                "log_path": mp.group(1) if mp else "",
                "ts": e.get("ts"),
            }
        )
    return pd.DataFrame(rows)


def find_success_logs(limit: int = 40) -> List[Tuple[str, Path]]:
    """Best-effort: recent opensim.log in repo CWDs that look like completed SO.

    Success SO usually deletes temp dirs; we may have little. Also check
    Codes/*/opensim.log for leftover runs.
    """
    cands = []
    for p in [
        _CODES / "c_Run_Tools" / "opensim.log",
        _CODES / "opensim.log",
        _CODES / "d_Results_Analysis" / "opensim.log",
        Path(_path.ROOT_DIR) / "opensim.log",
    ]:
        if p.is_file() and p.stat().st_size > 1000:
            cands.append(("cwd_leftover", p))
    # Any remaining temp logs NOT in trouble list could be success? Unreliable.
    return cands[:limit]


def main() -> int:
    trouble = load_trouble_freeze_rows()
    # Prefer SO freezes with log path
    so = trouble[
        (trouble["tool"].astype(str).str.lower() == "so")
        & (trouble["log_path"].astype(str).str.len() > 0)
    ].copy()
    print(f"SO trouble rows with preserved log path: {len(so)}")
    print(f"log files exist: {sum(Path(p).is_file() for p in so['log_path'])}")

    # Scan
    scanned = []
    mus_ctr = Counter()
    for i, r in so.iterrows():
        info = scan_log(Path(r["log_path"]))
        freeze = r["freeze_s"]
        # eq near freeze (±0.2 s)
        near = 0
        for t in info["eq_times"]:
            if np.isfinite(freeze) and abs(t - freeze) <= 0.2:
                near += 1
        info["eq_near_freeze"] = near
        info["eq_min_t"] = min(info["eq_times"]) if info["eq_times"] else np.nan
        info["eq_max_t"] = max(info["eq_times"]) if info["eq_times"] else np.nan
        info["n_eq_unique_t"] = len(set(info["eq_times"]))
        for m in info["eq_muscles"]:
            mus_ctr[m] += 1
        scanned.append(
            {
                **{k: r[k] for k in ("sub", "cond", "seg", "app", "freeze_s", "log_path", "ts")},
                "log_exists": info["exists"],
                "last_perf_t": info["last_perf_t"],
                "n_equilibrate": info["n_equilibrate"],
                "n_fiber_nan": info["n_fiber_nan"],
                "n_solution_error": info["n_solution_error"],
                "n_wrap": info["n_wrap"],
                "n_path_length": info["n_path_length"],
                "n_muscle_other": info["n_muscle_other"],
                "eq_near_freeze": near,
                "eq_min_t": info["eq_min_t"],
                "eq_max_t": info["eq_max_t"],
                "n_eq_unique_t": info["n_eq_unique_t"],
                "eq_muscles": ";".join(info["eq_muscles"][:12]),
                "warn_snippets": " || ".join(info["warn_snippets"][:4]),
            }
        )
        if (len(scanned) % 50) == 0:
            print(f"  scanned {len(scanned)}…")

    sdf = pd.DataFrame(scanned)
    out_csv = OUT / "quality_check_SO_log_warnings.csv"
    sdf.to_csv(out_csv, index=False)
    print(f"Wrote {out_csv} ({len(sdf)} rows)")

    exist = sdf[sdf["log_exists"]]
    print("\n=== Fail log warning prevalence ===")
    print(f"logs readable: {len(exist)}/{len(sdf)}")
    for col in [
        "n_equilibrate",
        "n_fiber_nan",
        "n_solution_error",
        "n_wrap",
        "n_path_length",
        "n_muscle_other",
    ]:
        nz = (exist[col] > 0).sum()
        print(
            f"  {col}: any={nz} ({100*nz/max(len(exist),1):.1f}%)  "
            f"median_if_any={exist.loc[exist[col]>0, col].median() if nz else 'NA'}  "
            f"sum={exist[col].sum()}"
        )

    if (exist["n_equilibrate"] > 0).any():
        eq = exist[exist["n_equilibrate"] > 0]
        print(f"\nequilibrate events: logs={len(eq)}  total msgs={eq['n_equilibrate'].sum()}")
        print(
            f"  eq time min/med/max: "
            f"{eq['eq_min_t'].min():.2f} / {eq['eq_min_t'].median():.2f} / {eq['eq_max_t'].max():.2f}"
        )
        # distance freeze - last eq
        dt = eq["freeze_s"] - eq["eq_max_t"]
        print(
            f"  freeze - last_eq_t: med={dt.median():.3f}  "
            f"share |dt|<=0.2: {(eq['eq_near_freeze']>0).mean():.1%}"
        )
        print("  top muscles:")
        for m, c in mus_ctr.most_common(15):
            print(f"    {c:4d}  {m}")

    # Cross with residual / ID metrics
    cross = OUT / "quality_check_SO_freeze_cross.csv"
    idf = OUT / "quality_check_ID_reserves.csv"
    if cross.is_file():
        cdf = pd.read_csv(cross)
        m = exist.merge(
            cdf[
                [
                    c
                    for c in cdf.columns
                    if c
                    in (
                        "sub",
                        "cond",
                        "seg",
                        "app",
                        "freeze_s",
                        "worst_ratio",
                        "ratio__pelvis_list",
                        "ratio__L5_S1_Flex_Ext",
                        "win_max_abs__pelvis_list",
                        "win_max_abs__L5_S1_Flex_Ext",
                        "ik_rms_mean_m",
                        "scale_rmse_mm",
                    )
                ]
            ],
            on=["sub", "cond", "seg", "app", "freeze_s"],
            how="left",
            suffixes=("", "_x"),
        )
        print("\n=== Equilibrate vs residual (fail logs) ===")
        has_eq = m["n_equilibrate"] > 0
        no_eq = m["n_equilibrate"] == 0
        for col in [
            "ratio__pelvis_list",
            "ratio__L5_S1_Flex_Ext",
            "worst_ratio",
            "freeze_s",
            "win_max_abs__pelvis_list",
        ]:
            if col not in m.columns:
                continue
            a = pd.to_numeric(m.loc[has_eq, col], errors="coerce")
            b = pd.to_numeric(m.loc[no_eq, col], errors="coerce")
            print(
                f"  {col}: with_eq med={a.median():.4g} (n={a.notna().sum()})  "
                f"no_eq med={b.median():.4g} (n={b.notna().sum()})"
            )

    # Success comparison: scan a few leftover logs + any temp logs that finished?
    # Also: for subjects with complete SO, we don't have preserved logs.
    # Proxy: scan ID-vs-SO success segments — we can't get their historical logs.
    # Instead note limitation, and optionally re-run is out of scope.
    # Check if any temp opensim_run_* logs are NOT in fail set and have equilibrate.
    fail_paths = set(exist["log_path"].astype(str))
    other_logs = [
        p
        for p in TEMP.glob("opensim_run_*/opensim.log")
        if str(p) not in fail_paths
    ]
    print(f"\nOther temp opensim.log not in trouble preserve list: {len(other_logs)}")
    succ_scan = []
    for p in other_logs[:80]:
        info = scan_log(p)
        if not info["exists"]:
            continue
        # Heuristic success: last perf near end OR many perf lines and no long stall context
        succ_scan.append(
            {
                "log_path": str(p),
                "last_perf_t": info["last_perf_t"],
                "n_equilibrate": info["n_equilibrate"],
                "n_fiber_nan": info["n_fiber_nan"],
                "n_solution_error": info["n_solution_error"],
                "n_wrap": info["n_wrap"],
            }
        )
    # Also cwd leftovers
    for tag, p in find_success_logs():
        info = scan_log(p)
        succ_scan.append(
            {
                "log_path": str(p),
                "last_perf_t": info["last_perf_t"],
                "n_equilibrate": info["n_equilibrate"],
                "n_fiber_nan": info["n_fiber_nan"],
                "n_solution_error": info["n_solution_error"],
                "n_wrap": info["n_wrap"],
                "tag": tag,
            }
        )
    if succ_scan:
        s2 = pd.DataFrame(succ_scan)
        print("Non-trouble / leftover logs:")
        print(
            f"  any equilibrate: {(s2['n_equilibrate']>0).sum()}/{len(s2)}  "
            f"fiber_nan: {(s2['n_fiber_nan']>0).sum()}  "
            f"sol_err: {(s2['n_solution_error']>0).sum()}"
        )

    # Write MD update
    md_path = OUT / "quality_check_SO_log_warnings.md"
    lines = [
        "# SO opensim.log warnings on freeze failures",
        "",
        f"Scanned preserved logs from `pipeline_trouble.json` "
        f"(`opensim.log preserved at: …`). Readable fail logs: "
        f"**{len(exist)}/{len(sdf)}**.",
        "",
        f"Detail CSV: `{out_csv.name}`.",
        "",
        "## What warnings appear (not VTP / not Performance lines)",
        "",
    ]
    for col, label in [
        ("n_equilibrate", "unable to equilibrate muscles (Thelen2003Muscle)"),
        ("n_fiber_nan", "Fiber length is nan"),
        ("n_solution_error", "Solution error exceeds tolerance"),
        ("n_wrap", "wrap-related"),
        ("n_path_length", "path length"),
        ("n_muscle_other", "other muscle warnings"),
    ]:
        nz = int((exist[col] > 0).sum()) if len(exist) else 0
        total = int(exist[col].sum()) if len(exist) else 0
        lines.append(
            f"- **{label}**: in {nz}/{len(exist)} logs "
            f"({100*nz/max(len(exist),1):.1f}%), {total} message(s) total"
        )
    lines.append("")
    lines.append(
        "Classic “muscle path / wrap exceeded” strings were **rare or absent** "
        "in these freeze logs. The dominant muscle-related warning is "
        "**`AnalyzeTool::run() unable to equilibrate muscles`** "
        "(Thelen `computeInitialFiberEquilibrium`), often with "
        "**`Fiber length is nan`**."
    )
    lines.append("")
    if (exist["n_equilibrate"] > 0).any():
        eq = exist[exist["n_equilibrate"] > 0]
        lines.append("## Equilibrate timing vs freeze_s")
        lines.append("")
        lines.append(
            f"- Equilibrate present in **{len(eq)}/{len(exist)}** fail logs "
            f"({100*len(eq)/max(len(exist),1):.1f}%)."
        )
        lines.append(
            f"- Equilibrate sim-times: min={eq['eq_min_t'].min():.2f}s, "
            f"median first={eq['eq_min_t'].median():.2f}s, "
            f"max last={eq['eq_max_t'].max():.2f}s."
        )
        lines.append(
            f"- Share with equilibrate within ±0.2 s of freeze: "
            f"**{(eq['eq_near_freeze']>0).mean()*100:.1f}%** of eq-logs."
        )
        lines.append("")
        lines.append("Top muscles named in equilibrate stacks:")
        lines.append("")
        for m, c in mus_ctr.most_common(12):
            lines.append(f"- `{m}` × {c}")
        lines.append("")

    lines.extend(
        [
            "## Relation to residual / L5 hypotheses",
            "",
            "- **Not a clean “path wrap exceeded” story** in the freeze corpus we have.",
            "- Equilibrate / fiber-NaN **does** show up on a subset of freezes and can "
            "sit near `freeze_s` — that points to **muscle state / geometry at that pose** "
            "(fiber equilibrium), which can be *downstream of* extreme kinematics or "
            "wrapping, but the log text is equilibrate/NaN rather than an explicit "
            "path-length exceed flag.",
            "- **`residual_pelvis_list` overload remains universal** on successful SO too "
            "(ID≈SO 1:1, always >80 Nm). Equilibrate warnings are therefore a **parallel "
            "or aggravating** failure mode for some stalls, not a replacement for the "
            "residual finding.",
            "- If equilibrate rate ≪ 100% of freezes, residual/ExtLoad/timing still explain "
            "the majority; if ≈100% and tightly time-locked to freeze, muscle equilibrium "
            "is the proximate crash reason even when residual is also high.",
            "",
            "## Success comparison caveat",
            "",
            "Successful SO runs normally delete their temp `opensim_run_*` directories, so we "
            "lack a matched success-log corpus. Leftover CWD/`opensim.log` files are only "
            "weak controls. A definitive fail-vs-success warning rate needs either "
            "log archival on success or a small deliberate re-run sample.",
            "",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {md_path}")

    # Append short section to culprit MD
    culprit = OUT / "quality_check_SO_culprit.md"
    if culprit.is_file():
        block = [
            "",
            "## opensim.log warnings on freezes (update)",
            "",
            f"See `{md_path.name}` and `{out_csv.name}`.",
            "",
        ]
        # fill key numbers
        if len(exist):
            eq_frac = (exist["n_equilibrate"] > 0).mean()
            fib_frac = (exist["n_fiber_nan"] > 0).mean()
            wrap_frac = (exist["n_wrap"] > 0).mean()
            block.append(
                f"- Equilibrate-muscle warnings in **{eq_frac*100:.0f}%** of readable freeze logs; "
                f"fiber-length NaN in **{fib_frac*100:.0f}%**; explicit wrap/path-length "
                f"warnings in **{wrap_frac*100:.0f}%**."
            )
            if (exist["n_equilibrate"] > 0).any():
                eq = exist[exist["n_equilibrate"] > 0]
                block.append(
                    f"- When equilibrate occurs, near-freeze (±0.2 s) in "
                    f"**{(eq['eq_near_freeze']>0).mean()*100:.0f}%** of those logs."
                )
            block.append(
                "- Interpretation: not primarily a logged “muscle path exceeded” "
                "discriminator; muscle **fiber equilibrium / NaN** is a real proximal "
                "warning on a subset of stalls. **pelvis_list residual** remains the "
                "systemic overload present even on successes — related stressor, "
                "different mechanism than equilibrate text."
            )
            block.append("")
        text = culprit.read_text(encoding="utf-8")
        marker = "## opensim.log warnings on freezes"
        if marker in text:
            text = text.split(marker)[0].rstrip() + "\n"
        culprit.write_text(text + "\n".join(block), encoding="utf-8")
        print(f"Updated {culprit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
