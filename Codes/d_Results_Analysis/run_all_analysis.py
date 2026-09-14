# -*- coding: utf-8 -*-
"""Run full Asymmetric analysis stack for one subject (default: 260526_PJH)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CODES = _HERE.parent
_STATS = _CODES / "e_statistics"
for _p in (str(_CODES), str(_HERE), str(_STATS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from run_ehf_analysis import process_subject as run_ehf  # noqa: E402
from run_l5s1_analysis import process_subject as run_l5s1  # noqa: E402
from run_residual_analysis import process_subject as run_residual  # noqa: E402
from run_ricto_report_sheets import build_subject_report  # noqa: E402
from figure_outputs import rebuild_all_suball_figures  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--namecode", default="260526_PJH")
    ap.add_argument("--conditions", default=None)
    ap.add_argument("--plot", action="store_true", help="Also write mean±std PNGs")
    ap.add_argument("--no-plot", action="store_true")
    ap.add_argument("--skip-stats", action="store_true")
    ap.add_argument("--skip-ricto-report", action="store_true")
    ap.add_argument(
        "--suball-only",
        action="store_true",
        help="Only rebuild SUBALL figures from existing CSVs (no subject re-analysis)",
    )
    ap.add_argument(
        "--figures-from-csv",
        action="store_true",
        help="Rebuild subject + SUBALL figures from existing CSVs (no re-analysis)",
    )
    args = ap.parse_args()
    conds = (
        [c.strip() for c in args.conditions.split(",") if c.strip()]
        if args.conditions
        else None
    )
    do_plot = bool(args.plot) and not bool(args.no_plot)

    if args.suball_only:
        print("=== SUBALL figures ===")
        for r in rebuild_all_suball_figures():
            print(r)
        return

    if args.figures_from_csv:
        from analysis_utils import result_paths
        from figure_outputs import rebuild_subject_figures_from_csv

        sub = result_paths(args.namecode).sub_label
        print(f"=== Subject figures from CSV ({sub}) ===")
        print(rebuild_subject_figures_from_csv(sub))
        print("=== SUBALL figures ===")
        for r in rebuild_all_suball_figures():
            print(r)
        return

    print("=== EHF ===")
    print(run_ehf(args.namecode, conditions=conds, plot=do_plot))
    print("=== L5S1 ===")
    print(run_l5s1(args.namecode, conditions=conds, plot=do_plot))
    print("=== Residual ===")
    print(run_residual(args.namecode, conditions=conds, plot=do_plot))
    if do_plot:
        # Final SUBALL pass after all domains have fresh CSVs
        print("=== SUBALL figures (refresh) ===")
        for r in rebuild_all_suball_figures():
            print(r)
    if not args.skip_ricto_report:
        print("=== RiCTO report ===")
        try:
            print(build_subject_report(args.namecode))
        except Exception as e:
            print(f"[ricto report fail] {e}")
    if not args.skip_stats:
        print("=== Stats (e_statistics) ===")
        try:
            from stats_lmm import process_subject as run_stats

            print(run_stats(args.namecode))
        except Exception as e:
            print(f"[stats deferred/fail] {e}")


if __name__ == "__main__":
    main()
