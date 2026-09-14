# -*- coding: utf-8 -*-
"""Shared paths under Analysis/Asymmetric/_stats/."""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CODES = _HERE.parent
_RESULTS = _CODES / "d_Results_Analysis"
for _p in (str(_CODES), str(_RESULTS), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from analysis_utils import analysis_asymmetric_root  # noqa: E402


def stats_root() -> Path:
    d = analysis_asymmetric_root() / "_stats"
    d.mkdir(parents=True, exist_ok=True)
    return d


def stats_long_dir() -> Path:
    d = stats_root() / "long"
    d.mkdir(parents=True, exist_ok=True)
    return d


def stats_models_dir() -> Path:
    d = stats_root() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def stats_reports_dir() -> Path:
    d = stats_root() / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def manuscript_figures_dir() -> Path:
    d = analysis_asymmetric_root() / "_figures" / "RiCTO_manuscript"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ricto_summary_xlsx(sub_label: str) -> Path:
    return analysis_asymmetric_root() / "RiCTO" / "Summary" / f"{sub_label}_RiCTO_report.xlsx"


def namecode_for_sub_label(sub_label: str) -> str | None:
    import SUB_Info as _sub_info

    want = str(sub_label).upper().replace("SUB", "")
    for nc, info in _sub_info.subjects.items():
        if str(info.get("SUB_number")) == want:
            return nc
    return None


def suball_namecodes() -> list[dict]:
    """Eligible SUBALL subjects with on-disk EHF CSVs when filter available."""
    try:
        from figure_outputs import (
            filter_eligible_with_analysis,
            load_pipeline_eligible_subjects,
        )

        els = load_pipeline_eligible_subjects()
        try:
            return filter_eligible_with_analysis(els)
        except TypeError:
            return els
    except Exception:
        return []
