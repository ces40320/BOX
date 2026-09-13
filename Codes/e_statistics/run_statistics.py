# -*- coding: utf-8 -*-
"""CLI entry for e_statistics (fixed effects + LMM skeleton)."""

from __future__ import annotations

import argparse

from stats_lmm import process_subject


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--namecode", default="260526_PJH")
    ap.add_argument(
        "--mode",
        choices=("fixed", "lmm", "all"),
        default="all",
        help="fixed/all run descriptives+OLS; lmm writes skeleton only (needs n_sub>=2 to fit)",
    )
    args = ap.parse_args()
    print(process_subject(args.namecode))


if __name__ == "__main__":
    main()
