# -*- coding: utf-8 -*-
"""Fill STATS_REPORT_TEMPLATE-style markdown from on-disk stats artifacts."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
_CODES = _HERE.parent
_RESULTS = _CODES / "d_Results_Analysis"
for _p in (str(_CODES), str(_RESULTS), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from analysis_utils import result_paths  # noqa: E402
from stats_io import (  # noqa: E402
    manuscript_figures_dir,
    stats_long_dir,
    stats_models_dir,
    stats_reports_dir,
)
from stats_lmm import anthropometry_row  # noqa: E402


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path)


def render_subject_report(namecode: str) -> Path:
    rp = result_paths(namecode)
    anthro = anthropometry_row(namecode)
    sub = rp.sub_label
    lines: list[str] = []

    lines.append(f"# Statistics report — {sub}")
    lines.append("")
    lines.append("## 1. Meta")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|--------|")
    lines.append("| Protocol | Asymmetric |")
    lines.append(f"| Subject | {sub} ({namecode}) |")
    lines.append("| Apps | MeasuredEHF, HeavyHand, preRiCTO, postRiCTO |")
    lines.append("| Contact window (GT) | `|Fy_L| + |Fy_R| ≥ 5 N` (vertical only) |")
    lines.append("| Min contact duration | 0.30 s |")
    lines.append("| Resample | 101 points |")
    lines.append(
        f"| body_mass_kg | {anthro.get('body_mass_kg')} |"
    )
    lines.append(f"| Report date | {date.today().isoformat()} |")
    lines.append("")

    lines.append("## 2. Methods snapshot")
    lines.append("")
    lines.append(
        "- RMSE vs MeasuredEHF on GT 5 N clock; Q1–Q4 quartiles.\n"
        "- Timing abs error: RiCTO / BoxMarker vs GT onset·offset.\n"
        "- L5S1 peaks: initial 0–50%, final 50–100% on Force_Resultant.\n"
        "- one-way rmANOVA within=app; LMM reserved for SUBALL.\n"
    )

    # Descriptives
    desc = _read_csv(Path(stats_long_dir().parent) / f"{sub}_rmse_by_factor.csv")
    if desc.empty:
        desc = _read_csv(stats_long_dir().parent / f"{sub}_rmse_by_factor.csv")
    lines.append("## 3. Descriptives")
    lines.append("")
    if not desc.empty:
        res = desc[desc["axis"] == "Resultant"] if "axis" in desc.columns else desc
        lines.append("### EHF Resultant RMSE (by app × mass × tempo × hand)")
        lines.append("")
        lines.append(res.head(40).to_markdown(index=False))
        lines.append("")
    else:
        lines.append("_No descriptives CSV found._")
        lines.append("")

    # Timing
    tsum = _read_csv(stats_long_dir() / f"timing_abserr_summary_{sub}.csv")
    lines.append("## 4. Agreement")
    lines.append("")
    lines.append("### Timing absolute error")
    lines.append("")
    if not tsum.empty:
        lines.append(tsum.to_markdown(index=False))
    else:
        lines.append("_No timing summary._")
    lines.append("")

    ba = _read_csv(stats_models_dir() / f"BlandAltman_timing_{sub}.csv")
    lines.append("### Bland–Altman (timing)")
    lines.append("")
    if not ba.empty:
        lines.append(ba.to_markdown(index=False))
    else:
        lines.append("_No Bland–Altman table._")
    lines.append("")

    # Inferential
    lines.append("## 5. Inferential")
    lines.append("")
    rm_txt = stats_models_dir() / f"rmANOVA_L5S1_report_{sub}.txt"
    lines.append("### one-way rmANOVA (L5S1 peaks)")
    lines.append("")
    if rm_txt.is_file():
        lines.append("```text")
        lines.append(rm_txt.read_text(encoding="utf-8").strip())
        lines.append("```")
    else:
        lines.append("_No rmANOVA report._")
    lines.append("")

    ols = stats_models_dir() / f"{sub}_OLS_Resultant_RMSE.txt"
    if not ols.is_file():
        ols = stats_long_dir().parent / f"{sub}_OLS_Resultant_RMSE.txt"
    lines.append("### OLS (Path B, Resultant RMSE)")
    lines.append("")
    if ols.is_file():
        text = ols.read_text(encoding="utf-8")
        # keep short: first 40 lines
        clip = "\n".join(text.splitlines()[:45])
        lines.append("```text")
        lines.append(clip)
        lines.append("```")
    else:
        lines.append("_No OLS file._")
    lines.append("")

    lines.append("### LMM")
    lines.append("")
    lines.append(
        "Single-subject report: see `SUBALL_stats_report.md` for MixedLM "
        "(SUBALL roster only)."
    )
    lines.append("")

    # Figures
    fig_dir = manuscript_figures_dir() / sub
    lines.append("## 6. Figures")
    lines.append("")
    lines.append("| ID | Path |")
    lines.append("|----|------|")
    for fig_id in (
        "Fig-RiCTO-1",
        "Fig-RiCTO-2",
        "Fig-EHF-1",
        "Fig-EHF-2",
        "Fig-EHF-3",
        "Fig-EHF-4",
        "Fig-L5S1-1",
        "Fig-L5S1-2",
    ):
        p = fig_dir / f"{fig_id}.png"
        rel = f"_figures/RiCTO_manuscript/{sub}/{fig_id}.png"
        status = "ok" if p.is_file() else "missing"
        lines.append(f"| {fig_id} | `{rel}` ({status}) |")
    lines.append("")

    # QC
    tlong = _read_csv(stats_long_dir() / f"timing_abserr_{sub}.csv")
    lines.append("## 7. QC")
    lines.append("")
    n_qc = 0
    if not tlong.empty and "abs_err_s" in tlong.columns:
        n_qc = int((tlong["abs_err_s"] > 0.30).sum())
    lines.append(f"- Timing rows with `|err| > 0.30 s`: **{n_qc}**")
    if not tlong.empty and "qc_warning" in tlong.columns:
        flagged = tlong["qc_warning"].dropna().astype(str)
        flagged = flagged[flagged.str.len() > 0]
        lines.append(f"- qc_warning non-empty rows: **{len(flagged)}**")
    lines.append("")

    out = stats_reports_dir() / f"{sub}_stats_report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def render_suball_report() -> Path:
    fe = stats_models_dir() / "LMM_EHF_Resultant_RMSE_SUBALL_FE.csv"
    lines = [
        "# Statistics report — SUBALL",
        "",
        f"Report date: {date.today().isoformat()}",
        "",
        "## LMM (EHF Resultant RMSE)",
        "",
        "Formula: `RMSE_full ~ C(app) + C(tempo_bpm) + mass_norm_z + (1|sub)`",
        "",
        "Cohort: SUBALL roster (pipeline all_done + analysis CSVs).",
        "",
        "Note: with current n_sub≈3 the random-intercept variance may be "
        "singular (boundary); interpret FE cautiously and prefer Path B / "
        "rmANOVA until more subjects complete.",
        "",
    ]
    if fe.is_file():
        df = pd.read_csv(fe)
        lines.append(df.to_markdown(index=False))
    else:
        lines.append("_LMM FE table missing — run `run_statistics.py --mode lmm --suball`._")
    re_path = stats_models_dir() / "LMM_EHF_Resultant_RMSE_SUBALL_RE.txt"
    if re_path.is_file():
        lines.append("")
        lines.append("### Random effects / summary (excerpt)")
        lines.append("")
        lines.append("```text")
        lines.append("\n".join(re_path.read_text(encoding="utf-8").splitlines()[:60]))
        lines.append("```")
    out = stats_reports_dir() / "SUBALL_stats_report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--namecode", default="260526_PJH")
    ap.add_argument("--suball", action="store_true")
    args = ap.parse_args()
    if args.suball:
        print(render_suball_report())
    else:
        print(render_subject_report(args.namecode))


if __name__ == "__main__":
    main()
