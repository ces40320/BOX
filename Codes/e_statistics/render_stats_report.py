# -*- coding: utf-8 -*-
"""Jamovi-style statistics markdown reports for RiCTO / Asymmetric Results.

Primary audience: read ``Analysis/Asymmetric/_stats/reports/*.md`` only.
Folder glossary: ``Analysis/Asymmetric/_stats/README.md``.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import numpy as np
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


def _fmt_p(p: float) -> str:
    if not np.isfinite(p):
        return "—"
    if p < 0.001:
        return "< .001"
    return f"{p:.3f}"


def _sig_word(sig: str, p: float | None = None) -> str:
    if sig in ("***", "**", "*"):
        return f"significant ({sig})"
    if p is not None and np.isfinite(p) and p < 0.05:
        return "significant"
    return "non-significant"


def _md_table(df: pd.DataFrame, floatfmt: str = ".4g") -> str:
    if df.empty:
        return "_*(empty)*_"
    try:
        return df.to_markdown(index=False, floatfmt=floatfmt)
    except TypeError:
        return df.to_markdown(index=False)


def render_subject_report(namecode: str) -> Path:
    rp = result_paths(namecode)
    anthro = anthropometry_row(namecode)
    sub = rp.sub_label
    models = stats_models_dir()
    lines: list[str] = []

    # ----- Title -----
    lines += [
        f"# Statistics report — {sub}",
        "",
        f"**Date:** {date.today().isoformat()}  ",
        f"**Subject:** {sub} (`{namecode}`)  ",
        f"**Body mass:** {anthro.get('body_mass_kg')} kg  ",
        "",
        "> 이 파일만 읽으면 됩니다. 폴더/약어 설명은 "
        "[`../README.md`](../README.md) 참고.",
        "",
        "유의성 표기: `***` p<.001 · `**` p<.01 · `*` p<.05 · `ns` 비유의",
        "",
    ]

    # ----- At a glance -----
    lines += ["## 0. 한눈에 보기 (At a glance)", ""]

    glance_rows: list[dict] = []

    # Timing: which method closer to GT
    tsum = _read_csv(stats_long_dir() / f"timing_abserr_summary_{sub}.csv")
    if not tsum.empty:
        for event in ("Grip", "Deposit"):
            sube = tsum[tsum["event"] == event]
            if sube.empty:
                continue
            best = sube.loc[sube["abs_err_mean"].idxmin()]
            glance_rows.append(
                {
                    "Analysis": f"Timing |{event} error| vs GT 5 N",
                    "Result": (
                        f"{best['method']} smaller abs error "
                        f"(mean={best['abs_err_mean']:.3f} s)"
                    ),
                    "sig": "descriptive",
                }
            )

    # rmANOVA
    anova = _read_csv(models / f"rmANOVA_L5S1_peaks_{sub}.csv")
    if not anova.empty:
        for _, r in anova.iterrows():
            p = float(r.get("p", float("nan")))
            glance_rows.append(
                {
                    "Analysis": f"rmANOVA L5S1 · {r.get('label', r.get('outcome'))}",
                    "Result": (
                        f"F({float(r['ddof1']):.2f}, {float(r['ddof2']):.2f}) = "
                        f"{float(r['F']):.3g}, p = {_fmt_p(p)}"
                    ),
                    "sig": _sig_word(str(r.get("significant", "")), p)
                    if "significant" in r
                    else _sig_word("", p),
                }
            )

    # OLS omnibus / significant
    ols_omni = _read_csv(models / f"{sub}_OLS_Resultant_RMSE_Omnibus.csv")
    if not ols_omni.empty:
        for _, r in ols_omni.iterrows():
            effect = str(r.get("Effect", ""))
            if effect.lower().startswith("residual"):
                continue
            p = float(r.get("PR(>F)", float("nan")))
            glance_rows.append(
                {
                    "Analysis": f"OLS Omnibus · EHF RMSE · {effect}",
                    "Result": f"F = {float(r.get('F', float('nan'))):.3g}, p = {_fmt_p(p)}",
                    "sig": str(r.get("sig", _sig_word("", p))),
                }
            )
    else:
        ols_sig = _read_csv(models / f"{sub}_OLS_Resultant_RMSE_significant.csv")
        if not ols_sig.empty:
            glance_rows.append(
                {
                    "Analysis": "OLS · EHF Resultant RMSE (significant terms)",
                    "Result": ", ".join(
                        f"{n} ({s})" for n, s in zip(ols_sig["Names"], ols_sig["sig"])
                    )[:200],
                    "sig": "see §5",
                }
            )

    if glance_rows:
        lines.append(_md_table(pd.DataFrame(glance_rows)))
    else:
        lines.append("_통계 산출물이 아직 없습니다. `run_statistics.py --mode all` 실행._")
    lines += ["", "---", ""]

    # ----- Model / methods meta -----
    lines += [
        "## 1. Model Info",
        "",
        "| Info | Value |",
        "|------|--------|",
        "| Protocol | Asymmetric |",
        "| Apps | MeasuredEHF (GT), HeavyHand, preRiCTO, postRiCTO |",
        "| Contact window (GT) | vertical `|Fy_L|+|Fy_R| ≥ 5 N` |",
        "| Resample | 101 pts over GT window |",
        "| Single-subject models | OLS (RMSE); one-way rmANOVA (L5S1 peaks) |",
        "| Multi-subject LMM | see `SUBALL_stats_report.md` |",
        "",
        "## 2. Methods snapshot",
        "",
        "- **RMSE**: MeasuredEHF 대비 손외력 궤적 오차 (Resultant 중심).",
        "- **Timing abs error**: Grip/Deposit vs GT 5 N 창 (RiCTO · BoxMarker).",
        "- **Bland–Altman**: 방법−GT 편향·95% LoA.",
        "- **L5S1 peaks**: initial 0–50%, final 50–100% (Force_Resultant); within=app rmANOVA.",
        "- **OLS**: `RMSE_full ~ app × tempo × mass + hand` (MeasuredEHF 제외).",
        "",
    ]

    # ----- Descriptives compact -----
    desc = _read_csv(stats_long_dir() / f"{sub}_rmse_by_factor.csv")
    lines += ["## 3. Descriptives — EHF Resultant RMSE (mean)", ""]
    if not desc.empty:
        res = desc[desc["axis"] == "Resultant"].copy()
        # pivot-like summary by app
        by_app = (
            res.groupby("app", as_index=False)
            .agg(n=("n", "sum"), RMSE_mean=("RMSE_mean", "mean"), RMSE_std=("RMSE_std", "mean"))
            .sort_values("RMSE_mean")
        )
        lines.append("앱별 평균 RMSE (조건·손 평균):")
        lines.append("")
        lines.append(_md_table(by_app))
        lines.append("")
        lines.append("<details><summary>조건별 상세 표 (펼치기)</summary>")
        lines.append("")
        lines.append(_md_table(res))
        lines.append("")
        lines.append("</details>")
        lines.append("")
    else:
        lines.append("_No descriptives._")
        lines.append("")

    # ----- Agreement -----
    lines += ["## 4. Agreement (타이밍)", ""]
    lines.append("### Absolute error summary")
    lines.append("")
    if not tsum.empty:
        show = tsum.copy()
        show["abs_err_mean"] = show["abs_err_mean"].map(lambda x: round(float(x), 4))
        show["abs_err_std"] = show["abs_err_std"].map(lambda x: round(float(x), 4))
        lines.append(_md_table(show))
        lines.append("")
        # narrative
        for event in ("Grip", "Deposit"):
            sube = tsum[tsum["event"] == event]
            if len(sube) >= 2:
                best = sube.loc[sube["abs_err_mean"].idxmin()]
                worst = sube.loc[sube["abs_err_mean"].idxmax()]
                lines.append(
                    f"- **{event}**: `{best['method']}` mean |err| = "
                    f"{best['abs_err_mean']:.3f} s < `{worst['method']}` "
                    f"{worst['abs_err_mean']:.3f} s"
                )
        lines.append("")
    else:
        lines.append("_No timing summary._")
        lines.append("")

    ba = _read_csv(models / f"BlandAltman_timing_{sub}.csv")
    lines.append("### Bland–Altman")
    lines.append("")
    if not ba.empty:
        ba2 = ba.copy()
        for c in ("bias", "sd", "loa_low", "loa_high"):
            if c in ba2.columns:
                ba2[c] = ba2[c].map(lambda x: round(float(x), 4))
        lines.append(_md_table(ba2))
    else:
        lines.append("_No Bland–Altman table._")
    lines.append("")

    # ----- Inferential rmANOVA -----
    lines += ["## 5. Inferential", ""]
    lines.append("### 5.1 Repeated Measures ANOVA — L5S1 peaks (within = app)")
    lines.append("")
    lines.append(
        "구형성 위반 시 Greenhouse–Geisser(GG) p. "
        "Symmetric AddBiomech / jamovi rmANOVA 보고 형식과 동일."
    )
    lines.append("")
    if not anova.empty:
        disp = anova.copy()
        if "p" in disp.columns:
            disp["p_fmt"] = [_fmt_p(float(x)) for x in disp["p"]]
            disp["verdict"] = [
                _sig_word(str(s), float(p))
                for s, p in zip(disp.get("significant", [""] * len(disp)), disp["p"])
            ]
        cols = [c for c in ("label", "ddof1", "ddof2", "F", "p_fmt", "p_correction", "verdict") if c in disp.columns]
        lines.append(_md_table(disp[cols]))
        lines.append("")
        # text block like jamovi txt
        rm_txt = models / f"rmANOVA_L5S1_report_{sub}.txt"
        if rm_txt.is_file():
            lines.append("```text")
            lines.append(rm_txt.read_text(encoding="utf-8").strip())
            lines.append("```")
            lines.append("")
    else:
        lines.append("_No rmANOVA table._")
        lines.append("")

    post = _read_csv(models / f"rmANOVA_L5S1_posthoc_{sub}.csv")
    if not post.empty:
        lines.append("#### Post Hoc (Bonferroni)")
        lines.append("")
        post2 = post.copy()
        if "p_corr" in post2.columns:
            post2["p_fmt"] = [_fmt_p(float(x)) if pd.notna(x) else "—" for x in post2["p_corr"]]
            post2["sig"] = [
                "***" if pd.notna(p) and float(p) < 0.001 else
                "**" if pd.notna(p) and float(p) < 0.01 else
                "*" if pd.notna(p) and float(p) < 0.05 else "ns"
                for p in post2["p_corr"]
            ]
        # only significant pairs in main view
        sig_post = post2[post2.get("sig", pd.Series(dtype=str)).isin(["*", "**", "***"])]
        if not sig_post.empty:
            lines.append("유의 쌍만:")
            lines.append("")
            show_cols = [c for c in ("outcome", "A", "B", "mean_diff", "p_fmt", "sig") if c in sig_post.columns]
            lines.append(_md_table(sig_post[show_cols].head(40)))
        else:
            lines.append("_Bonferroni 후 유의한 쌍 없음 (또는 표 비어 있음)._")
        lines.append("")
        lines.append("<details><summary>전체 post-hoc</summary>")
        lines.append("")
        lines.append(_md_table(post2.head(80)))
        lines.append("")
        lines.append("</details>")
        lines.append("")

    # ----- OLS -----
    lines.append("### 5.2 OLS — EHF Resultant RMSE (single subject)")
    lines.append("")
    lines.append(
        "고정효과만 (피험자 랜덤효과 없음). "
        "jamovi ANOVA Omnibus에 해당하는 Type II 표 + 유의 계수."
    )
    lines.append("")
    if not ols_omni.empty:
        lines.append("#### Fixed Effects Omnibus Tests (Type II)")
        lines.append("")
        om = ols_omni.copy()
        om = om[~om["Effect"].astype(str).str.lower().eq("residual")]
        if "PR(>F)" in om.columns:
            om["p_fmt"] = [_fmt_p(float(x)) if pd.notna(x) else "—" for x in om["PR(>F)"]]
        cols = [c for c in ("Effect", "sum_sq", "df", "F", "p_fmt", "sig") if c in om.columns]
        lines.append(_md_table(om[cols]))
        lines.append("")
        sig_om = om[om.get("sig", pd.Series(dtype=str)).isin(["*", "**", "***"])]
        if not sig_om.empty:
            lines.append(
                "**유의한 효과:** "
                + ", ".join(f"{e} ({s})" for e, s in zip(sig_om["Effect"], sig_om["sig"]))
            )
            lines.append("")

    ols_sig = _read_csv(models / f"{sub}_OLS_Resultant_RMSE_significant.csv")
    lines.append("#### Significant parameter estimates")
    lines.append("")
    if not ols_sig.empty:
        lines.append(_md_table(ols_sig))
    else:
        lines.append("_p<.05 계수 없음 또는 표 미생성._")
    lines.append("")
    lines.append(
        f"전체 OLS 요약: `models/{sub}_OLS_Resultant_RMSE.txt`"
    )
    lines.append("")

    lines += [
        "### 5.3 LMM",
        "",
        "단피험자 보고서에는 LMM을 넣지 않습니다. "
        "다피험자(SUBALL) jamovi형 LMM → "
        "[`SUBALL_stats_report.md`](SUBALL_stats_report.md).",
        "",
    ]

    # Figures
    fig_dir = manuscript_figures_dir() / sub
    lines += ["## 6. Figures", ""]
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
    lines += ["## 7. QC", ""]
    n_qc = int((tlong["abs_err_s"] > 0.30).sum()) if not tlong.empty and "abs_err_s" in tlong.columns else 0
    lines.append(f"- Timing rows with `|err| > 0.30 s`: **{n_qc}**")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "References style: jamovi / GAMLj mixed & rmANOVA reports "
        "(Gallucci; Symmetric AddBiomech ANOVA txt)."
    )
    lines.append("")

    out = stats_reports_dir() / f"{sub}_stats_report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def render_suball_report() -> Path:
    """Jamovi GAMLj Mixed Model style report for SUBALL LMM."""
    models = stats_models_dir()
    prefix = "LMM_EHF_Resultant_RMSE_SUBALL"
    lines: list[str] = [
        "# Statistics report — SUBALL (Linear Mixed Model)",
        "",
        f"**Date:** {date.today().isoformat()}  ",
        "",
        "> jamovi GAMLj *Mixed Model* 리포트 구조에 맞춤 "
        "(Model Info → Fit/Omnibus → Parameter Estimates → Random Components).  ",
        "> 효과변인: **app**, **tempo_bpm**, **mass_norm** (체중 정규화 박스질량) "
        "+ 2-way interactions. Random: `(1 | sub)`.",
        "",
        "유의성: `***` p<.001 · `**` p<.01 · `*` p<.05 · `ns` 비유의",
        "",
        "## 0. 한눈에 보기",
        "",
    ]

    omnibus = _read_csv(models / f"{prefix}_Omnibus.csv")
    sig_fe = _read_csv(models / f"{prefix}_SignificantFE.csv")
    if not omnibus.empty:
        lines.append("### Fixed Effects Omnibus")
        lines.append("")
        om = omnibus.copy()
        if "p" in om.columns:
            om["p_fmt"] = [_fmt_p(float(x)) if pd.notna(x) else "—" for x in om["p"]]
            om["verdict"] = [
                _sig_word(str(s), float(p) if pd.notna(p) else None)
                for s, p in zip(om.get("sig", [""] * len(om)), om["p"])
            ]
        cols = [c for c in ("Effect", "chi2", "df", "p_fmt", "sig", "verdict") if c in om.columns]
        lines.append(_md_table(om[cols]))
        lines.append("")
        sig_om = om[om.get("sig", pd.Series(dtype=str)).isin(["*", "**", "***"])]
        if not sig_om.empty:
            lines.append(
                "**유의한 Omnibus 효과:** "
                + ", ".join(f"{e} ({s})" for e, s in zip(sig_om["Effect"], sig_om["sig"]))
            )
        else:
            lines.append("**유의한 Omnibus 효과 없음** (또는 Wald 표 비어 있음).")
        lines.append("")
    elif not sig_fe.empty:
        lines.append("유의한 고정효과 계수:")
        lines.append("")
        lines.append(_md_table(sig_fe))
        lines.append("")
    else:
        lines.append("_LMM 결과 없음 — `python run_statistics.py --mode lmm --suball`_")
        lines.append("")

    # Model Info
    lines += ["---", "", "## 1. Model Info", ""]
    info = _read_csv(models / f"{prefix}_ModelInfo.csv")
    if not info.empty:
        lines.append(_md_table(info))
    else:
        lines.append("_ModelInfo.csv missing._")
    lines.append("")

    re_txt = models / f"{prefix}_RE.txt"
    if re_txt.is_file() and "singular" in re_txt.read_text(encoding="utf-8").lower()[:400]:
        lines += [
            "> **Warning (jamovi와 동일 계열):** Random effect가 "
            "singular/boundary일 수 있음. Fixed Effects 해석에 주의. "
            "피험자 수가 늘면 완화되는 경우가 많음.",
            "",
        ]

    # Omnibus detail
    lines += ["## 2. Fixed Effects Omnibus Tests", ""]
    if not omnibus.empty:
        lines.append(_md_table(omnibus))
    else:
        lines.append("_Omnibus table missing._")
    lines.append("")

    # Parameter estimates
    lines += ["## 3. Parameter Estimates (Fixed coefficients)", ""]
    fe = _read_csv(models / f"{prefix}_FE.csv")
    if not fe.empty:
        fe2 = fe.copy()
        if "p" in fe2.columns:
            fe2["p_fmt"] = [_fmt_p(float(x)) if pd.notna(x) else "—" for x in fe2["p"]]
        cols = [c for c in ("Names", "Estimate", "SE", "z", "p_fmt", "sig", "Lower", "Upper") if c in fe2.columns]
        lines.append(_md_table(fe2[cols]))
        lines.append("")
        if not sig_fe.empty:
            lines.append("### Significant coefficients only")
            lines.append("")
            lines.append(_md_table(sig_fe))
            lines.append("")
    else:
        lines.append("_FE table missing._")
        lines.append("")

    # Random
    lines += ["## 4. Random Components", ""]
    re_c = _read_csv(models / f"{prefix}_RandomComponents.csv")
    if not re_c.empty:
        lines.append(_md_table(re_c))
    else:
        lines.append("_RandomComponents.csv missing._")
    lines.append("")
    lines.append("Note. Groups = `sub` (피험자). Residual = within-subject 잔차 분산.")
    lines.append("")

    lines += [
        "## 5. How to read (우리 연구 매핑)",
        "",
        "| jamovi (러닝슈트 예) | 본 연구 |",
        "|----------------------|---------|",
        "| Device | **app** (HeavyHand / preRiCTO / postRiCTO; GT=MeasuredEHF는 RMSE 기준) |",
        "| Speed | **tempo_bpm** (10 vs 16) |",
        "| (추가 공변량) | **mass_norm** = box_mass / body_mass (z) |",
        "| subject | **sub** |",
        "| Upperbody AM … | **EHF Resultant RMSE_full** |",
        "",
        "단피험자 피크·타이밍은 각 `SUB*_stats_report.md` 참고.",
        "",
        "---",
        "",
        "References: jamovi; GAMLj (Gallucci); statsmodels MixedLM.",
        "",
    ]

    out = stats_reports_dir() / "SUBALL_stats_report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def render_all_available() -> list[str]:
    """Regenerate subject reports for any SUB* with timing or RMSE long files."""
    written = []
    import SUB_Info as _sub_info

    # discover subjects from long timing files or RMSE
    subs = set()
    for p in stats_long_dir().glob("timing_abserr_SUB*.csv"):
        subs.add(p.stem.replace("timing_abserr_", ""))
    for p in stats_long_dir().glob("lmm_long_template_EHF_RMSE_SUB*.csv"):
        subs.add(p.stem.replace("lmm_long_template_EHF_RMSE_", ""))
    for sub in sorted(subs):
        nc = None
        want = sub.upper().replace("SUB", "")
        for k, info in _sub_info.subjects.items():
            if str(info.get("SUB_number")) == want:
                nc = k
                break
        if nc:
            written.append(str(render_subject_report(nc)))
    written.append(str(render_suball_report()))
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--namecode", default=None)
    ap.add_argument("--suball", action="store_true")
    ap.add_argument("--all-reports", action="store_true", help="Refresh every available SUB + SUBALL")
    args = ap.parse_args()
    if args.all_reports:
        print(render_all_available())
    elif args.suball:
        print(render_suball_report())
    else:
        print(render_subject_report(args.namecode or "260526_PJH"))


if __name__ == "__main__":
    main()
