# -*- coding: utf-8 -*-
"""Figure layout for Asymmetric EHF / L5S1 / Residual.

Layout
------
```
Analysis/Asymmetric/_figures/{domain}/
  SUB{n}/
    SUB{n}_{stem}.png                 # all conditions pooled
    {cond}/
      SUB{n}_{cond}_{stem}.png        # per kg_bpm
  SUBALL/
    SUBALL_roster.xlsx                # as-of date, eligible SUBs, n per cond
    SUBALL_{stem}.png
    {cond}/
      SUBALL_{cond}_{stem}.png
```

Eligible SUBALL subjects: ``pipeline_progress.xlsx`` Summary ``all_done`` = done
mark (all 4 apps complete, no trouble), and on-disk analysis CSVs exist for
every app in ``EHF_APPS``.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_CODES = _HERE.parent
_RUN_TOOLS = _CODES / "c_Run_Tools"
for _p in (str(_CODES), str(_RUN_TOOLS), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import PATH_RULE as _path  # noqa: E402
from analysis_utils import (  # noqa: E402
    EHF_APPS,
    EHF_AXES,
    L5S1_FORCE_AXES,
    L5S1_MOMENT_AXES,
    P_COLS,
    RESIDUAL_AXES,
    SECTIONS,
    analysis_asymmetric_root,
    figures_dir,
    mean_std_plot,
    rows_to_matrix,
)

try:
    from update_pipeline_progress import (  # noqa: E402
        MARK_DONE,
        default_sheet_path,
    )
except Exception:  # pragma: no cover
    MARK_DONE = "☑"

    def default_sheet_path() -> str:
        return str(
            Path(_path.OPENSIM_DIR) / "Asymmetric" / "pipeline_progress.xlsx"
        )


L5S1_AXES = tuple(L5S1_FORCE_AXES) + tuple(L5S1_MOMENT_AXES)


def figures_subject_dir(domain: str, sub_label: str) -> Path:
    d = figures_dir(domain) / str(sub_label)
    d.mkdir(parents=True, exist_ok=True)
    return d


def figures_cond_dir(domain: str, sub_label: str, cond: str) -> Path:
    d = figures_subject_dir(domain, sub_label) / str(cond)
    d.mkdir(parents=True, exist_ok=True)
    return d


def figures_suball_dir(domain: str) -> Path:
    d = figures_dir(domain) / "SUBALL"
    d.mkdir(parents=True, exist_ok=True)
    return d


def figures_suball_cond_dir(domain: str, cond: str) -> Path:
    d = figures_suball_dir(domain) / str(cond)
    d.mkdir(parents=True, exist_ok=True)
    return d


def pipeline_progress_path() -> Path:
    return Path(default_sheet_path())


def load_pipeline_eligible_subjects(
    progress_xlsx: Optional[Path] = None,
) -> List[dict]:
    """Subjects with Summary all apps complete (no trouble).

    Prefer ``pct_% == 100`` and/or ``conditions_done`` like ``4/4``; also accept
    the pipeline DONE mark in ``all_done``.
    """
    path = Path(progress_xlsx) if progress_xlsx else pipeline_progress_path()
    if not path.is_file():
        return []
    try:
        df = pd.read_excel(path, sheet_name="Summary")
    except Exception:
        return []
    if df.empty:
        return []

    mask = pd.Series(False, index=df.index)
    if "pct_%" in df.columns:
        pct = pd.to_numeric(df["pct_%"], errors="coerce")
        mask = mask | (pct >= 100.0 - 1e-9)
    if "conditions_done" in df.columns:
        # e.g. "4/4"
        cd = df["conditions_done"].astype(str)
        parts = cd.str.split("/", n=1, expand=True)
        if parts.shape[1] == 2:
            a = pd.to_numeric(parts[0], errors="coerce")
            b = pd.to_numeric(parts[1], errors="coerce")
            mask = mask | ((a == b) & (b > 0))
    if "all_done" in df.columns:
        done = df["all_done"].astype(str).str.strip()
        mask = mask | done.eq(str(MARK_DONE)) | done.str.contains(
            "DONE", case=False, na=False
        )
        # Unicode ballot box with check U+2611
        mask = mask | done.map(lambda s: "\u2611" in s)

    hit = df.loc[mask].copy()
    out = []
    for _, r in hit.iterrows():
        sub = r.get("SUB")
        nc = r.get("namecode")
        if pd.isna(sub) or pd.isna(nc):
            continue
        sub_label = f"SUB{int(sub)}" if str(sub).isdigit() else str(sub)
        if not str(sub_label).upper().startswith("SUB"):
            sub_label = f"SUB{sub_label}"
        out.append(
            {
                "SUB": int(sub) if str(sub).isdigit() else sub,
                "sub_label": sub_label,
                "namecode": str(nc),
            }
        )
    return out


def _section_csv_path(
    domain: str,
    app: str,
    axis: str,
    sub_label: str,
    section: str,
    hand: Optional[str] = None,
) -> Path:
    root = analysis_asymmetric_root() / domain / app / axis
    if hand:
        return root / f"{sub_label}_{hand}_{section}.csv"
    return root / f"{sub_label}_{section}.csv"


def subject_has_all_apps_csv(
    domain: str,
    sub_label: str,
    *,
    axes: Sequence[str],
    hands: Optional[Sequence[str]] = None,
) -> bool:
    """True if at least one section CSV exists for every app."""
    section = SECTIONS[0]
    axis = axes[0]
    for app in EHF_APPS:
        if hands:
            ok_hand = False
            for hand in hands:
                if _section_csv_path(
                    domain, app, axis, sub_label, section, hand
                ).is_file():
                    ok_hand = True
                    break
            if not ok_hand:
                return False
        else:
            if not _section_csv_path(
                domain, app, axis, sub_label, section, None
            ).is_file():
                return False
    return True


def filter_eligible_with_analysis(
    domain: str,
    eligible: Sequence[dict],
    *,
    axes: Sequence[str],
    hands: Optional[Sequence[str]] = None,
) -> List[dict]:
    return [
        e
        for e in eligible
        if subject_has_all_apps_csv(
            domain, e["sub_label"], axes=axes, hands=hands
        )
    ]


def _rows_from_csv(
    path: Path, *, cond: Optional[str] = None
) -> List[dict]:
    if not path.is_file():
        return []
    df = pd.read_csv(path)
    if df.empty:
        return []
    if cond is not None and "cond" in df.columns:
        df = df[df["cond"].astype(str) == str(cond)]
    if df.empty:
        return []
    rows = []
    for _, r in df.iterrows():
        d = {"cond": r.get("cond"), "seg": r.get("seg")}
        for c in P_COLS:
            d[c] = float(r[c]) if c in r.index and pd.notna(r[c]) else float("nan")
        rows.append(d)
    return rows


def _stem(*, axis: str, section: str, hand: Optional[str] = None) -> str:
    if hand:
        return f"{axis}_{hand}_{section}"
    return f"{axis}_{section}"


def write_subject_figures_from_rows(
    domain: str,
    sub_label: str,
    *,
    series_rows: dict,
    apps: Sequence[str],
    axes: Sequence[str],
    sections: Sequence[str] = SECTIONS,
    hands: Optional[Sequence[str]] = None,
    title_prefix: str,
    ylabel_fn,
) -> int:
    """Write pooled + per-condition mean±std PNGs under ``_figures/{domain}/SUB#``.

    ``series_rows`` nesting:
      - with hands: [app][axis][hand][section] → list[row]
      - without:    [app][axis][section] → list[row]
    """
    n = 0
    sub_root = figures_subject_dir(domain, sub_label)
    hand_iter: Sequence[Optional[str]] = list(hands) if hands else [None]

    for axis in axes:
        for hand in hand_iter:
            for section in sections:
                # pooled (all conds)
                by_app: Dict[str, np.ndarray] = {}
                all_rows_for_conds: List[dict] = []
                for app in apps:
                    if hand is None:
                        rows = series_rows[app][axis][section]
                    else:
                        rows = series_rows[app][axis][hand][section]
                    all_rows_for_conds.extend(rows)
                    if rows:
                        by_app[app] = rows_to_matrix(rows)
                if by_app:
                    stem = _stem(axis=axis, section=section, hand=hand)
                    mean_std_plot(
                        by_app,
                        title=f"{title_prefix} {stem.replace('_', ' ')} ({sub_label})",
                        ylabel=ylabel_fn(axis),
                        out_path=sub_root / f"{sub_label}_{stem}.png",
                    )
                    n += 1

                # per condition
                conds = sorted(
                    {
                        str(r["cond"])
                        for r in all_rows_for_conds
                        if r.get("cond") is not None
                    }
                )
                for cond in conds:
                    by_app_c: Dict[str, np.ndarray] = {}
                    for app in apps:
                        if hand is None:
                            rows = [
                                r
                                for r in series_rows[app][axis][section]
                                if str(r.get("cond")) == cond
                            ]
                        else:
                            rows = [
                                r
                                for r in series_rows[app][axis][hand][section]
                                if str(r.get("cond")) == cond
                            ]
                        if rows:
                            by_app_c[app] = rows_to_matrix(rows)
                    if not by_app_c:
                        continue
                    stem = _stem(axis=axis, section=section, hand=hand)
                    out = (
                        figures_cond_dir(domain, sub_label, cond)
                        / f"{sub_label}_{cond}_{stem}.png"
                    )
                    mean_std_plot(
                        by_app_c,
                        title=(
                            f"{title_prefix} {stem.replace('_', ' ')} "
                            f"({sub_label} {cond})"
                        ),
                        ylabel=ylabel_fn(axis),
                        out_path=out,
                    )
                    n += 1
    return n


def write_suball_roster_xlsx(
    domain: str,
    *,
    subjects: Sequence[dict],
    sample_rows: Sequence[dict],
    as_of: Optional[str] = None,
) -> Path:
    """Simple workbook: which SUBs + n samples per condition."""
    as_of = as_of or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = figures_suball_dir(domain) / "SUBALL_roster.xlsx"
    roster = pd.DataFrame(
        [
            {
                "as_of": as_of,
                "SUB": s.get("SUB"),
                "sub_label": s["sub_label"],
                "namecode": s["namecode"],
                "source": "pipeline_progress.xlsx all_done + 4-app CSV",
            }
            for s in subjects
        ]
    )
    samples = pd.DataFrame(list(sample_rows)) if sample_rows else pd.DataFrame(
        columns=["condition", "section", "hand", "n_segments", "n_subjects"]
    )
    meta = pd.DataFrame(
        [
            {
                "as_of": as_of,
                "domain": domain,
                "n_subjects": len(subjects),
                "progress_xlsx": str(pipeline_progress_path()),
                "rule": (
                    "SUBALL = pipeline Summary all_done "
                    "(all 4 apps complete, no trouble) "
                    "AND analysis CSVs present for all apps"
                ),
            }
        ]
    )
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        meta.to_excel(writer, sheet_name="meta", index=False)
        roster.to_excel(writer, sheet_name="subjects", index=False)
        samples.to_excel(writer, sheet_name="n_samples", index=False)
    return out


def rebuild_suball_figures(
    domain: str,
    *,
    apps: Sequence[str] = EHF_APPS,
    axes: Sequence[str],
    sections: Sequence[str] = SECTIONS,
    hands: Optional[Sequence[str]] = None,
    title_prefix: str,
    ylabel_fn,
    progress_xlsx: Optional[Path] = None,
) -> dict:
    """Mean±std across eligible subjects → ``_figures/{domain}/SUBALL``."""
    eligible = load_pipeline_eligible_subjects(progress_xlsx)
    eligible = filter_eligible_with_analysis(
        domain, eligible, axes=axes, hands=hands
    )
    sample_rows: List[dict] = []
    n_plots = 0
    hand_iter: Sequence[Optional[str]] = list(hands) if hands else [None]

    # Discover conditions from MeasuredEHF CSVs of eligible subjects
    cond_set = set()
    for e in eligible:
        for section in sections:
            hand0 = hand_iter[0]
            path = _section_csv_path(
                domain,
                "MeasuredEHF",
                axes[0],
                e["sub_label"],
                section,
                hand0 if hands else None,
            )
            if path.is_file():
                df = pd.read_csv(path, usecols=["cond"])
                cond_set.update(df["cond"].astype(str).tolist())
    conds = sorted(cond_set)

    for axis in axes:
        for hand in hand_iter:
            for section in sections:
                # pooled across all conds & subjects
                by_app: Dict[str, List[np.ndarray]] = {a: [] for a in apps}
                n_seg_total = 0
                subs_used = set()
                for e in eligible:
                    for app in apps:
                        path = _section_csv_path(
                            domain,
                            app,
                            axis,
                            e["sub_label"],
                            section,
                            hand if hands else None,
                        )
                        rows = _rows_from_csv(path)
                        if not rows:
                            continue
                        mat = rows_to_matrix(rows)
                        if mat.size:
                            by_app[app].append(mat)
                            if app == "MeasuredEHF":
                                n_seg_total += mat.shape[0]
                                subs_used.add(e["sub_label"])
                by_app_m = {
                    a: np.vstack(chunks)
                    for a, chunks in by_app.items()
                    if chunks
                }
                if by_app_m:
                    stem = _stem(axis=axis, section=section, hand=hand)
                    mean_std_plot(
                        by_app_m,
                        title=(
                            f"{title_prefix} {stem.replace('_', ' ')} "
                            f"(SUBALL n={len(subs_used)})"
                        ),
                        ylabel=ylabel_fn(axis),
                        out_path=figures_suball_dir(domain)
                        / f"SUBALL_{stem}.png",
                    )
                    n_plots += 1
                    sample_rows.append(
                        {
                            "condition": "ALL",
                            "section": section,
                            "hand": hand or "",
                            "axis": axis,
                            "n_segments": int(n_seg_total),
                            "n_subjects": int(len(subs_used)),
                        }
                    )

                for cond in conds:
                    by_app_c: Dict[str, List[np.ndarray]] = {a: [] for a in apps}
                    n_seg = 0
                    subs_c = set()
                    for e in eligible:
                        for app in apps:
                            path = _section_csv_path(
                                domain,
                                app,
                                axis,
                                e["sub_label"],
                                section,
                                hand if hands else None,
                            )
                            rows = _rows_from_csv(path, cond=cond)
                            if not rows:
                                continue
                            mat = rows_to_matrix(rows)
                            if mat.size:
                                by_app_c[app].append(mat)
                                if app == "MeasuredEHF":
                                    n_seg += mat.shape[0]
                                    subs_c.add(e["sub_label"])
                    by_app_cm = {
                        a: np.vstack(chunks)
                        for a, chunks in by_app_c.items()
                        if chunks
                    }
                    if not by_app_cm:
                        continue
                    stem = _stem(axis=axis, section=section, hand=hand)
                    mean_std_plot(
                        by_app_cm,
                        title=(
                            f"{title_prefix} {stem.replace('_', ' ')} "
                            f"(SUBALL {cond} n={len(subs_c)})"
                        ),
                        ylabel=ylabel_fn(axis),
                        out_path=figures_suball_cond_dir(domain, cond)
                        / f"SUBALL_{cond}_{stem}.png",
                    )
                    n_plots += 1
                    sample_rows.append(
                        {
                            "condition": cond,
                            "section": section,
                            "hand": hand or "",
                            "axis": axis,
                            "n_segments": int(n_seg),
                            "n_subjects": int(len(subs_c)),
                        }
                    )

    roster = write_suball_roster_xlsx(
        domain, subjects=eligible, sample_rows=sample_rows
    )
    return {
        "domain": domain,
        "n_subjects": len(eligible),
        "subjects": [e["sub_label"] for e in eligible],
        "n_plots": n_plots,
        "roster": str(roster),
    }


def write_subject_figures_from_csv(
    domain: str,
    sub_label: str,
    *,
    apps: Sequence[str] = EHF_APPS,
    axes: Sequence[str],
    sections: Sequence[str] = SECTIONS,
    hands: Optional[Sequence[str]] = None,
    title_prefix: str,
    ylabel_fn,
) -> int:
    """Rebuild one subject's figures from on-disk analysis CSVs."""
    from collections import defaultdict

    if hands:
        series_rows: dict = defaultdict(
            lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        )
    else:
        series_rows = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for app in apps:
        for axis in axes:
            for section in sections:
                if hands:
                    for hand in hands:
                        path = _section_csv_path(
                            domain, app, axis, sub_label, section, hand
                        )
                        rows = _rows_from_csv(path)
                        series_rows[app][axis][hand][section] = rows
                else:
                    path = _section_csv_path(
                        domain, app, axis, sub_label, section, None
                    )
                    series_rows[app][axis][section] = _rows_from_csv(path)

    return write_subject_figures_from_rows(
        domain,
        sub_label,
        series_rows=series_rows,
        apps=apps,
        axes=axes,
        sections=sections,
        hands=hands,
        title_prefix=title_prefix,
        ylabel_fn=ylabel_fn,
    )


def rebuild_all_suball_figures(
    progress_xlsx: Optional[Path] = None,
) -> List[dict]:
    """Rebuild SUBALL for EHF, L5S1, Residual."""
    results = []
    results.append(
        rebuild_suball_figures(
            "EHF",
            axes=EHF_AXES,
            hands=("L", "R"),
            title_prefix="EHF",
            ylabel_fn=lambda ax: f"{ax} force (N)",
            progress_xlsx=progress_xlsx,
        )
    )
    results.append(
        rebuild_suball_figures(
            "L5S1",
            axes=L5S1_AXES,
            hands=None,
            title_prefix="L5S1",
            ylabel_fn=lambda ax: (
                f"{ax} (N·m)" if str(ax).startswith("Moment") else f"{ax} (N)"
            ),
            progress_xlsx=progress_xlsx,
        )
    )
    results.append(
        rebuild_suball_figures(
            "Residual",
            axes=RESIDUAL_AXES,
            hands=None,
            title_prefix="Residual",
            ylabel_fn=lambda ax: f"residual {ax} (N)",
            progress_xlsx=progress_xlsx,
        )
    )
    return results


def rebuild_subject_figures_from_csv(sub_label: str) -> dict:
    """Plot all three domains for one SUB from existing CSVs."""
    return {
        "EHF": write_subject_figures_from_csv(
            "EHF",
            sub_label,
            axes=EHF_AXES,
            hands=("L", "R"),
            title_prefix="EHF",
            ylabel_fn=lambda ax: f"{ax} force (N)",
        ),
        "L5S1": write_subject_figures_from_csv(
            "L5S1",
            sub_label,
            axes=L5S1_AXES,
            hands=None,
            title_prefix="L5S1",
            ylabel_fn=lambda ax: (
                f"{ax} (N·m)" if str(ax).startswith("Moment") else f"{ax} (N)"
            ),
        ),
        "Residual": write_subject_figures_from_csv(
            "Residual",
            sub_label,
            axes=RESIDUAL_AXES,
            hands=None,
            title_prefix="Residual",
            ylabel_fn=lambda ax: f"residual {ax} (N)",
        ),
    }
