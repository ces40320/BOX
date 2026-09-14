# -*- coding: utf-8 -*-
"""CLI for e_statistics + manuscript figures (RiCTO Results report)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CODES = _HERE.parent
_RESULTS = _CODES / "d_Results_Analysis"
for _p in (str(_CODES), str(_RESULTS), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from stats_io import namecode_for_sub_label, suball_namecodes  # noqa: E402


def _run_subject(namecode: str, mode: str) -> dict:
    out: dict = {"namecode": namecode}
    if mode in ("fixed", "all", "report"):
        from stats_lmm import process_subject as lmm_subj

        out["lmm_fixed"] = lmm_subj(namecode)
    if mode in ("timing", "all", "report"):
        from stats_timing_error import process_subject as timing_subj

        out["timing"] = timing_subj(namecode)
    if mode in ("bland", "all", "report"):
        from stats_bland_altman import process_subject as bland_subj

        out["bland"] = bland_subj(namecode)
    if mode in ("anova", "all", "report"):
        from stats_rm_anova import process_subject as anova_subj

        out["anova"] = anova_subj(namecode)
    if mode in ("figures", "all", "report"):
        from manuscript_figures import process_subject as fig_subj

        out["figures"] = fig_subj(namecode)
    if mode in ("report", "all"):
        from render_stats_report import render_subject_report

        out["report_md"] = str(render_subject_report(namecode))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--namecode", default=None)
    ap.add_argument("--sub", default=None, help="e.g. SUB7")
    ap.add_argument(
        "--mode",
        choices=(
            "fixed",
            "lmm",
            "timing",
            "bland",
            "anova",
            "figures",
            "report",
            "all",
        ),
        default="all",
    )
    ap.add_argument(
        "--suball",
        action="store_true",
        help="Run for SUBALL roster (and fit LMM when mode is lmm/all)",
    )
    ap.add_argument(
        "--subjects",
        default=None,
        help="Comma-separated namecodes (overrides --suball list)",
    )
    args = ap.parse_args()

    namecodes: list[str] = []
    if args.subjects:
        namecodes = [s.strip() for s in args.subjects.split(",") if s.strip()]
    elif args.suball:
        namecodes = [r["namecode"] for r in suball_namecodes()]
        if not namecodes:
            namecodes = ["260519_SHY", "260521_KJA", "260526_PJH"]
    elif args.sub:
        nc = namecode_for_sub_label(args.sub)
        if not nc:
            raise SystemExit(f"unknown sub {args.sub}")
        namecodes = [nc]
    else:
        namecodes = [args.namecode or "260526_PJH"]

    run_lmm = args.mode in ("lmm", "all") and (
        args.suball or args.mode == "lmm"
    )
    if run_lmm:
        from render_stats_report import render_suball_report
        from stats_lmm import process_suball_lmm

        print("[LMM SUBALL]", process_suball_lmm())
        print("[report]", render_suball_report())
        if args.mode == "lmm":
            return

    for nc in namecodes:
        print(f"=== {nc} mode={args.mode} ===")
        print(_run_subject(nc, args.mode))


if __name__ == "__main__":
    main()
