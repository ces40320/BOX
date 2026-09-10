"""Scan OpenSim result files and update the Asymmetric pipeline progress sheet.

Does **not** run OpenSim tools. Only checks whether PATH_RULE-expected
outputs already exist on disk (safe while a pipeline job is running).

Writes:
  ``OpenSim_Process/_Main_/Asymmetric/pipeline_progress.xlsx``

Runtime tool failures from ``run_opensim_pipeline.py`` are stored in a
sidecar JSON (``pipeline_trouble.json``) and merged into Detail/Matrix as
``mark=☒`` so they survive a full sheet refresh. When the canonical result
file reappears on disk, ``refresh_progress_sheet`` / this script prune that
entry so ``failed_segments`` and ``☒`` clear automatically.

Usage
-----
::

    python update_pipeline_progress.py
    python update_pipeline_progress.py --sub 1,2,3
    python update_pipeline_progress.py --out D:/tmp/progress.xlsx
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CODES_DIR = os.path.dirname(THIS_DIR)
if CODES_DIR not in sys.path:
    sys.path.insert(0, CODES_DIR)

from SUB_Info import subjects  # noqa: E402
from PATH_RULE import OPENSIM_DIR, ResultPaths  # noqa: E402
import config_methods as _cfg  # noqa: E402

if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)
from pipeline_rules import jr_suffixes as _jr_suffixes  # noqa: E402


PROTOCOL = "Asymmetric"
DEFAULT_SUB_NUMBERS: tuple[int, ...] = tuple(range(1, 9))
APPS: tuple[str, ...] = ("MeasuredEHF", "HeavyHand", "preRiCTO", "postRiCTO")
SECTIONS: tuple[str, ...] = ("AB", "BC", "CA")
TOOLS_PER_APP: tuple[str, ...] = ("extload", "so", "jr")  # IK/BK are app-shared
SHARED_DETAIL_TOOLS: tuple[str, ...] = ("ik", "bk")

MARK_DONE = "☑"
MARK_PARTIAL = "◐"
MARK_EMPTY = "☐"
MARK_TROUBLE = "☒"

FILL_DONE = PatternFill("solid", fgColor="C6EFCE")
FILL_PARTIAL = PatternFill("solid", fgColor="FFEB9C")
FILL_EMPTY = PatternFill("solid", fgColor="FFC7CE")
FILL_TROUBLE = PatternFill("solid", fgColor="FF6B6B")
FILL_HEADER = PatternFill("solid", fgColor="305496")
FILL_SUBHDR = PatternFill("solid", fgColor="D6DCE4")
FONT_HEADER = Font(color="FFFFFF", bold=True)
FONT_BOLD = Font(bold=True)
THIN = Border(
    left=Side(style="thin", color="B0B0B0"),
    right=Side(style="thin", color="B0B0B0"),
    top=Side(style="thin", color="B0B0B0"),
    bottom=Side(style="thin", color="B0B0B0"),
)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


def default_sheet_path() -> str:
    return os.path.join(OPENSIM_DIR, PROTOCOL, "pipeline_progress.xlsx")


def default_trouble_path() -> str:
    return os.path.join(OPENSIM_DIR, PROTOCOL, "pipeline_trouble.json")


def asymmetric_subjects(
    sub_numbers: Iterable[int] = DEFAULT_SUB_NUMBERS,
) -> list[tuple[int, str, dict]]:
    """Return ``[(SUB_number, namecode, info), ...]`` sorted by SUB_number."""
    wanted = set(sub_numbers)
    out: list[tuple[int, str, dict]] = []
    for namecode, info in subjects.items():
        if info.get("protocol") != PROTOCOL:
            continue
        n = info.get("SUB_number")
        if n in wanted:
            out.append((n, namecode, info))
    out.sort(key=lambda t: t[0])
    missing = wanted - {n for n, _, _ in out}
    if missing:
        raise KeyError(
            f"No Asymmetric subject(s) for SUB_number={sorted(missing)}"
        )
    return out


def sub_number_for_namecode(namecode: str) -> int:
    """Return SUB_number for a ``SUB_Info`` namecode."""
    info = subjects.get(namecode)
    if info is None:
        raise KeyError(f"Unknown namecode: {namecode!r}")
    return int(info["SUB_number"])


def _expected_segments(info: dict, cond: str, section: str) -> list[str]:
    cv = info["conditions"][cond]
    n_cycles = cv["cycles"]
    error_log = set(cv.get("error_log") or [])
    segs = _cfg.section_segment_labels(n_cycles, "ABC")[section]
    return [s for s in segs if s not in error_log]


def _result_file(rp: ResultPaths, cond: str, seg: str, tool: str,
                 app: str) -> str:
    """Absolute path of the canonical result file (no mkdir)."""
    section = rp.seg_to_section(seg)
    base = os.path.join(rp.sub_dir, cond, section)
    if tool == "ik":
        return os.path.join(base, "IK", rp.ik_name(cond, seg))
    if tool == "bk":
        return os.path.join(
            base, "BK", rp.bk_name(cond, seg, "pos_global")
        )
    if tool == "extload":
        return os.path.join(base, "ExtLoad", rp.extload_name(cond, seg, app))
    if tool == "so":
        return os.path.join(
            base, f"SO_{app}", rp.so_name(cond, seg, app, "force")
        )
    if tool == "jr":
        return os.path.join(
            base, f"JR_{app}", rp.jr_name(cond, seg, app, "")
        )
    raise ValueError(f"Unknown tool: {tool!r}")


def _count_present(rp: ResultPaths, cond: str, segs: list[str], tool: str,
                   app: str) -> tuple[int, int, list[str]]:
    """Return ``(n_present, n_expected, missing_segs)``."""
    missing: list[str] = []
    present = 0
    for seg in segs:
        path = _result_file(rp, cond, seg, tool, app)
        if os.path.isfile(path):
            present += 1
        else:
            missing.append(seg)
    return present, len(segs), missing


def _mark(present: int, expected: int) -> str:
    if expected == 0:
        return "—"
    if present >= expected:
        return MARK_DONE
    if present <= 0:
        return MARK_EMPTY
    return MARK_PARTIAL


def _fill_for_mark(mark: str) -> PatternFill | None:
    if mark == MARK_DONE:
        return FILL_DONE
    if mark == MARK_PARTIAL:
        return FILL_PARTIAL
    if mark == MARK_EMPTY:
        return FILL_EMPTY
    if mark == MARK_TROUBLE:
        return FILL_TROUBLE
    return None


# ── Runtime trouble sidecar ─────────────────────────────────────

def _normalize_trouble_app(tool: str, app: str | None) -> str:
    tool_l = tool.strip().lower()
    if tool_l in SHARED_DETAIL_TOOLS:
        return "(shared)"
    return (app or "(shared)").strip()


def _trouble_entry_key(entry: dict) -> tuple[str, str, str, str, str]:
    return (
        str(entry["namecode"]),
        str(entry["condition"]),
        str(entry["segment"]),
        _normalize_trouble_app(str(entry["tool"]), entry.get("app")),
        str(entry["tool"]).strip().lower(),
    )


def load_troubles(path: str | None = None) -> list[dict]:
    """Load trouble entries from sidecar JSON (empty list if missing)."""
    path = path or default_trouble_path()
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Trouble file must be a JSON list: {path}")
    return data


def save_troubles(entries: list[dict], path: str | None = None) -> str:
    path = path or default_trouble_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    return path


def record_trouble(
    *,
    namecode: str,
    condition: str,
    segment: str,
    tool: str,
    app: str | None = None,
    error: str = "",
    path: str | None = None,
) -> dict:
    """Append/upsert a runtime failure; returns the stored entry."""
    tool_l = tool.strip().lower()
    app_n = _normalize_trouble_app(tool_l, app)
    rp = ResultPaths(namecode)
    section = rp.seg_to_section(segment)
    entry = {
        "namecode": namecode,
        "condition": condition,
        "segment": segment,
        "section": section,
        "app": app_n,
        "tool": tool_l,
        "error": str(error),
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    path = path or default_trouble_path()
    entries = load_troubles(path)
    key = _trouble_entry_key(entry)
    kept = [e for e in entries if _trouble_entry_key(e) != key]
    kept.append(entry)
    save_troubles(kept, path)
    return entry


def _paths_for_trouble_entry(entry: dict) -> list[str]:
    """Canonical outputs that mean this trouble is resolved on disk."""
    namecode = str(entry["namecode"])
    cond = str(entry["condition"])
    seg = str(entry["segment"])
    tool = str(entry["tool"]).strip().lower()
    app = str(entry.get("app") or "(shared)")
    rp = ResultPaths(namecode)

    if tool == "extload":
        # Pipeline output is SETUP XML (``.mot`` is experimental input).
        if app == "(shared)":
            raise ValueError(f"extload trouble missing app: {entry!r}")
        return [rp.for_condition(cond).setup_extload_path(seg, app)]
    if tool == "ik":
        return [_result_file(rp, cond, seg, "ik", APPS[0])]
    if tool == "bk":
        return [_result_file(rp, cond, seg, "bk", APPS[0])]
    if tool in ("so", "jr"):
        if app == "(shared)":
            raise ValueError(f"{tool} trouble missing app: {entry!r}")
        if tool == "so":
            return [_result_file(rp, cond, seg, "so", app)]
        # JR: require all expected suffixes (AddBox includes ground).
        cp = rp.for_condition(cond)
        return [cp.jr_path(seg, app, sfx) for sfx in _jr_suffixes(app)]
    raise ValueError(f"Unknown trouble tool: {tool!r}")


def trouble_entry_resolved(entry: dict) -> bool:
    """True when every canonical result for this trouble exists on disk."""
    try:
        paths = _paths_for_trouble_entry(entry)
    except Exception:
        return False
    return bool(paths) and all(os.path.isfile(p) for p in paths)


def prune_resolved_troubles(
    path: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Drop sidecar entries whose results now exist.

    Returns ``(kept, removed)``. Rewrites the JSON only when something is
    removed so ``failed_segments`` / ``☒`` clear on the next sheet refresh.
    """
    path = path or default_trouble_path()
    entries = load_troubles(path)
    kept: list[dict] = []
    removed: list[dict] = []
    for e in entries:
        if trouble_entry_resolved(e):
            removed.append(e)
        else:
            kept.append(e)
    if removed:
        save_troubles(kept, path)
    return kept, removed


def clear_trouble(
    *,
    namecode: str,
    condition: str,
    segment: str,
    tool: str,
    app: str | None = None,
    path: str | None = None,
) -> bool:
    """Remove one trouble entry by key. Returns True if something was removed."""
    path = path or default_trouble_path()
    tool_l = tool.strip().lower()
    app_n = _normalize_trouble_app(tool_l, app)
    key = (namecode, condition, segment, app_n, tool_l)
    entries = load_troubles(path)
    kept = [e for e in entries if _trouble_entry_key(e) != key]
    if len(kept) == len(entries):
        return False
    save_troubles(kept, path)
    return True


def _troubles_by_detail_key(
    troubles: list[dict],
) -> dict[tuple[str, str, str, str, str], list[str]]:
    """Map (namecode, condition, section, app, tool) → failed segments."""
    out: dict[tuple[str, str, str, str, str], list[str]] = {}
    for e in troubles:
        tool_l = str(e["tool"]).strip().lower()
        app_n = _normalize_trouble_app(tool_l, e.get("app"))
        key = (
            str(e["namecode"]),
            str(e["condition"]),
            str(e.get("section") or ""),
            app_n,
            tool_l,
        )
        segs = out.setdefault(key, [])
        seg = str(e["segment"])
        if seg not in segs:
            segs.append(seg)
    for segs in out.values():
        segs.sort()
    return out


def apply_troubles_to_report(report: dict, troubles: list[dict]) -> dict:
    """Override marks with ``☒`` where runtime troubles exist."""
    by_key = _troubles_by_detail_key(troubles)

    for row in report["detail"]:
        tool_l = str(row["tool"]).strip().lower()
        key = (
            str(row["namecode"]),
            str(row["condition"]),
            str(row["section"]),
            str(row["app"]),
            tool_l,
        )
        failed = by_key.get(key, [])
        row["failed_segments"] = ", ".join(failed)
        if failed:
            row["mark"] = MARK_TROUBLE

    for row in report["matrix"]:
        ik_key = (
            str(row["namecode"]),
            str(row["condition"]),
            str(row["section"]),
            "(shared)",
            "ik",
        )
        if by_key.get(ik_key):
            row["IK"] = MARK_TROUBLE
        for app in APPS:
            for tool in TOOLS_PER_APP:
                tkey = (
                    str(row["namecode"]),
                    str(row["condition"]),
                    str(row["section"]),
                    app,
                    tool,
                )
                if by_key.get(tkey):
                    row[f"{app}_{tool}"] = MARK_TROUBLE

    report["troubles"] = troubles
    return report


def refresh_progress_sheet(
    sub_numbers: Iterable[int] | None = None,
    *,
    out_path: str | None = None,
    trouble_path: str | None = None,
) -> str:
    """Rescan disk, prune resolved troubles, merge remainder, write workbook."""
    subs = list(sub_numbers) if sub_numbers is not None else list(
        DEFAULT_SUB_NUMBERS
    )
    report = scan_progress(subs)
    kept, removed = prune_resolved_troubles(trouble_path)
    if removed:
        print(
            f"[pipeline_progress] pruned {len(removed)} resolved trouble(s) "
            f"(result files present again)",
            flush=True,
        )
        for e in removed[:20]:
            print(
                f"  - {e.get('namecode')} / {e.get('condition')} / "
                f"seg={e.get('segment')}  tool={e.get('tool')}  "
                f"app={e.get('app')}",
                flush=True,
            )
        if len(removed) > 20:
            print(f"  ... and {len(removed) - 20} more", flush=True)
    apply_troubles_to_report(report, kept)
    path = write_workbook(report, out_path or default_sheet_path())
    return path


def scan_progress(
    sub_numbers: Iterable[int] = DEFAULT_SUB_NUMBERS,
) -> dict:
    """Scan disk and return a nested progress report dict."""
    rows_matrix: list[dict] = []
    rows_detail: list[dict] = []
    missing_rows: list[dict] = []

    for sub_n, namecode, info in asymmetric_subjects(sub_numbers):
        rp = ResultPaths(namecode)
        for cond in info["conditions"]:
            for section in SECTIONS:
                segs = _expected_segments(info, cond, section)
                # IK is shared across apps (same IK/ folder & files).
                ik_p, ik_e, ik_miss = _count_present(
                    rp, cond, segs, "ik", APPS[0]
                )
                cell = {
                    "SUB": sub_n,
                    "namecode": namecode,
                    "condition": cond,
                    "section": section,
                    "n_expected": ik_e,
                    "IK": _mark(ik_p, ik_e),
                    "IK_count": f"{ik_p}/{ik_e}",
                }
                rows_detail.append({
                    "SUB": sub_n,
                    "namecode": namecode,
                    "condition": cond,
                    "section": section,
                    "app": "(shared)",
                    "tool": "ik",
                    "mark": _mark(ik_p, ik_e),
                    "present": ik_p,
                    "expected": ik_e,
                    "count": f"{ik_p}/{ik_e}",
                    "failed_segments": "",
                })
                if ik_miss:
                    missing_rows.append({
                        "SUB": sub_n,
                        "namecode": namecode,
                        "condition": cond,
                        "section": section,
                        "app": "(shared)",
                        "tool": "IK",
                        "missing": ", ".join(ik_miss),
                        "present": ik_p,
                        "expected": ik_e,
                    })

                bk_p, bk_e, bk_miss = _count_present(
                    rp, cond, segs, "bk", APPS[0]
                )
                rows_detail.append({
                    "SUB": sub_n,
                    "namecode": namecode,
                    "condition": cond,
                    "section": section,
                    "app": "(shared)",
                    "tool": "bk",
                    "mark": _mark(bk_p, bk_e),
                    "present": bk_p,
                    "expected": bk_e,
                    "count": f"{bk_p}/{bk_e}",
                    "failed_segments": "",
                })
                if bk_miss:
                    missing_rows.append({
                        "SUB": sub_n,
                        "namecode": namecode,
                        "condition": cond,
                        "section": section,
                        "app": "(shared)",
                        "tool": "BK",
                        "missing": ", ".join(bk_miss),
                        "present": bk_p,
                        "expected": bk_e,
                    })

                for app in APPS:
                    for tool in TOOLS_PER_APP:
                        p, e, miss = _count_present(
                            rp, cond, segs, tool, app
                        )
                        key = f"{app}_{tool}"
                        mark = _mark(p, e)
                        cell[key] = mark
                        cell[f"{key}_count"] = f"{p}/{e}"
                        rows_detail.append({
                            "SUB": sub_n,
                            "namecode": namecode,
                            "condition": cond,
                            "section": section,
                            "app": app,
                            "tool": tool,
                            "mark": mark,
                            "present": p,
                            "expected": e,
                            "count": f"{p}/{e}",
                            "failed_segments": "",
                        })
                        if miss:
                            missing_rows.append({
                                "SUB": sub_n,
                                "namecode": namecode,
                                "condition": cond,
                                "section": section,
                                "app": app,
                                "tool": tool.upper(),
                                "missing": ", ".join(miss),
                                "present": p,
                                "expected": e,
                            })
                rows_matrix.append(cell)

    return {
        "matrix": rows_matrix,
        "detail": rows_detail,
        "missing": missing_rows,
        "scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _summary_from_matrix(matrix_rows: list[dict]) -> list[dict]:
    by_sub: dict[int, dict] = {}
    for row in matrix_rows:
        sub = row["SUB"]
        bucket = by_sub.setdefault(
            sub,
            {
                "SUB": sub,
                "namecode": row["namecode"],
                "cells_done": 0,
                "cells_total": 0,
                "conds": set(),
                "conds_complete": set(),
            },
        )
        # Count every status cell: IK + 3 tools × 4 apps
        marks = [row["IK"]]
        for app in APPS:
            for tool in TOOLS_PER_APP:
                marks.append(row[f"{app}_{tool}"])
        done = sum(1 for m in marks if m == MARK_DONE)
        total = sum(1 for m in marks if m != "—")
        bucket["cells_done"] += done
        bucket["cells_total"] += total
        bucket["conds"].add(row["condition"])

    # condition complete = all sections × all marks DONE for that cond
    by_sub_cond: dict[tuple[int, str], list[dict]] = {}
    for row in matrix_rows:
        by_sub_cond.setdefault((row["SUB"], row["condition"]), []).append(row)

    for (sub, cond), rows in by_sub_cond.items():
        ok = True
        for row in rows:
            marks = [row["IK"]] + [
                row[f"{app}_{tool}"]
                for app in APPS
                for tool in TOOLS_PER_APP
            ]
            if any(m not in (MARK_DONE, "—") for m in marks):
                ok = False
                break
        if ok and rows:
            by_sub[sub]["conds_complete"].add(cond)

    out = []
    for sub in sorted(by_sub):
        b = by_sub[sub]
        total = b["cells_total"]
        done = b["cells_done"]
        pct = (100.0 * done / total) if total else 0.0
        n_cond = len(b["conds"])
        n_done = len(b["conds_complete"])
        out.append({
            "SUB": sub,
            "namecode": b["namecode"],
            "conditions_done": f"{n_done}/{n_cond}",
            "cells_done": f"{done}/{total}",
            "pct": round(pct, 1),
            "all_done": MARK_DONE if (total and done == total) else (
                MARK_PARTIAL if done else MARK_EMPTY
            ),
        })
    return out


def _style_header(cell, *, sub: bool = False) -> None:
    cell.font = FONT_HEADER if not sub else FONT_BOLD
    cell.fill = FILL_HEADER if not sub else FILL_SUBHDR
    cell.alignment = CENTER
    cell.border = THIN


def _write_status_cell(ws, row: int, col: int, mark: str,
                       count: str | None = None) -> None:
    cell = ws.cell(row=row, column=col)
    cell.value = f"{mark}\n{count}" if count else mark
    cell.alignment = CENTER
    cell.border = THIN
    fill = _fill_for_mark(mark)
    if fill is not None:
        cell.fill = fill


def write_workbook(report: dict, out_path: str) -> str:
    wb = Workbook()

    # ── Legend ────────────────────────────────────────────────
    ws_leg = wb.active
    ws_leg.title = "Legend"
    legend_lines = [
        ("pipeline_progress.xlsx", "Asymmetric OpenSim pipeline checkbox sheet"),
        ("Updated", report["scanned_at"]),
        ("Root", os.path.join(OPENSIM_DIR, PROTOCOL)),
        ("", ""),
        ("Mark", "Meaning"),
        (MARK_DONE, "All expected segments present (error_log excluded)"),
        (MARK_PARTIAL, "Some expected files present"),
        (MARK_EMPTY, "No expected files present"),
        (MARK_TROUBLE, "Runtime tool failure recorded (see failed_segments)"),
        ("—", "No expected segments (n_cycles / error_log edge case)"),
        ("", ""),
        ("IK", "Shared across apps → …/<section>/IK/*_IK.mot"),
        ("BK", "Shared BodyKinematics → …/<section>/BK/*_pos_global.sto"),
        ("ExtLoad", "…/<section>/ExtLoad/*_ExtLoad_<app>.mot"),
        ("SO", "…/<section>/SO_<app>/*_StaticOptimization_force.sto"),
        ("JR", "…/<section>/JR_<app>/*_JointReaction_ReactionLoads.sto"),
        ("", ""),
        ("How to refresh",
         "python Codes/c_Run_Tools/update_pipeline_progress.py"),
    ]
    for r, (a, b) in enumerate(legend_lines, start=1):
        ws_leg.cell(row=r, column=1, value=a).font = FONT_BOLD
        ws_leg.cell(row=r, column=2, value=b)
        if a in (MARK_DONE, MARK_PARTIAL, MARK_EMPTY, MARK_TROUBLE):
            fill = _fill_for_mark(a)
            if fill:
                ws_leg.cell(row=r, column=1).fill = fill
    ws_leg.column_dimensions["A"].width = 14
    ws_leg.column_dimensions["B"].width = 72

    # ── Summary ───────────────────────────────────────────────
    ws_sum = wb.create_sheet("Summary")
    sum_headers = [
        "SUB", "namecode", "all_done", "conditions_done",
        "cells_done", "pct_%",
    ]
    for c, h in enumerate(sum_headers, start=1):
        cell = ws_sum.cell(row=1, column=c, value=h)
        _style_header(cell)

    for r, row in enumerate(_summary_from_matrix(report["matrix"]), start=2):
        vals = [
            row["SUB"], row["namecode"], row["all_done"],
            row["conditions_done"], row["cells_done"], row["pct"],
        ]
        for c, v in enumerate(vals, start=1):
            cell = ws_sum.cell(row=r, column=c, value=v)
            cell.alignment = CENTER
            cell.border = THIN
            if c == 3:
                fill = _fill_for_mark(str(v))
                if fill:
                    cell.fill = fill
    for c in range(1, len(sum_headers) + 1):
        ws_sum.column_dimensions[get_column_letter(c)].width = 16
    ws_sum.column_dimensions["B"].width = 18
    ws_sum.freeze_panes = "A2"

    # ── Matrix ────────────────────────────────────────────────
    ws = wb.create_sheet("Matrix")
    # Row 1: group headers; Row 2: tool headers
    # Columns: SUB | namecode | condition | section | n_exp | IK |
    #          then per app: ExtLoad | SO | JR
    meta = ["SUB", "namecode", "condition", "section", "n_exp", "IK"]
    app_tools = [(app, tool) for app in APPS for tool in TOOLS_PER_APP]

    # header row 1
    for c, h in enumerate(meta, start=1):
        cell = ws.cell(row=1, column=c, value=h if h != "IK" else "IK (shared)")
        _style_header(cell)
        ws.merge_cells(start_row=1, start_column=c, end_row=2, end_column=c)

    col = len(meta) + 1
    for app in APPS:
        start = col
        for tool in TOOLS_PER_APP:
            cell = ws.cell(row=2, column=col, value=tool.upper())
            _style_header(cell, sub=True)
            col += 1
        end = col - 1
        cell = ws.cell(row=1, column=start, value=app)
        _style_header(cell)
        if end > start:
            ws.merge_cells(
                start_row=1, start_column=start, end_row=1, end_column=end
            )
        for c in range(start, end + 1):
            ws.cell(row=1, column=c).fill = FILL_HEADER
            ws.cell(row=1, column=c).font = FONT_HEADER
            ws.cell(row=1, column=c).alignment = CENTER
            ws.cell(row=1, column=c).border = THIN

    for r, row in enumerate(report["matrix"], start=3):
        meta_vals = [
            row["SUB"], row["namecode"], row["condition"],
            row["section"], row["n_expected"],
        ]
        for c, v in enumerate(meta_vals, start=1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.alignment = CENTER
            cell.border = THIN
        _write_status_cell(ws, r, 6, row["IK"], row["IK_count"])
        c = 7
        for app, tool in app_tools:
            key = f"{app}_{tool}"
            _write_status_cell(ws, r, c, row[key], row[f"{key}_count"])
            c += 1

    widths = {
        "A": 6, "B": 16, "C": 14, "D": 8, "E": 8, "F": 10,
    }
    for letter, w in widths.items():
        ws.column_dimensions[letter].width = w
    for c in range(7, 7 + len(app_tools)):
        ws.column_dimensions[get_column_letter(c)].width = 10
    ws.row_dimensions[1].height = 22
    ws.row_dimensions[2].height = 18
    ws.freeze_panes = "G3"

    # ── Detail ────────────────────────────────────────────────
    ws_d = wb.create_sheet("Detail")
    d_headers = [
        "SUB", "namecode", "condition", "section", "app", "tool",
        "mark", "present", "expected", "count", "failed_segments",
    ]
    for c, h in enumerate(d_headers, start=1):
        cell = ws_d.cell(row=1, column=c, value=h)
        _style_header(cell)
    for r, row in enumerate(report["detail"], start=2):
        vals = [row.get(h, "") for h in d_headers]
        for c, v in enumerate(vals, start=1):
            cell = ws_d.cell(row=r, column=c, value=v)
            cell.alignment = CENTER
            cell.border = THIN
            if c == 7:
                fill = _fill_for_mark(str(v))
                if fill:
                    cell.fill = fill
    for c in range(1, len(d_headers) + 1):
        ws_d.column_dimensions[get_column_letter(c)].width = 14
    ws_d.column_dimensions["B"].width = 16
    ws_d.column_dimensions["K"].width = 28
    ws_d.freeze_panes = "A2"

    # ── Missing ───────────────────────────────────────────────
    ws_m = wb.create_sheet("Missing")
    m_headers = [
        "SUB", "namecode", "condition", "section", "app", "tool",
        "present", "expected", "missing_segments",
    ]
    for c, h in enumerate(m_headers, start=1):
        cell = ws_m.cell(row=1, column=c, value=h)
        _style_header(cell)
    for r, row in enumerate(report["missing"], start=2):
        vals = [
            row["SUB"], row["namecode"], row["condition"], row["section"],
            row["app"], row["tool"], row["present"], row["expected"],
            row["missing"],
        ]
        for c, v in enumerate(vals, start=1):
            cell = ws_m.cell(row=r, column=c, value=v)
            cell.alignment = Alignment(
                horizontal="center" if c < 9 else "left",
                vertical="center",
                wrap_text=True,
            )
            cell.border = THIN
    for c in range(1, len(m_headers)):
        ws_m.column_dimensions[get_column_letter(c)].width = 14
    ws_m.column_dimensions["B"].width = 16
    ws_m.column_dimensions["I"].width = 60
    ws_m.freeze_panes = "A2"

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    wb.save(out_path)
    return out_path


def _ascii_mark(mark: str) -> str:
    return {
        MARK_DONE: "[DONE]",
        MARK_PARTIAL: "[PARTIAL]",
        MARK_EMPTY: "[EMPTY]",
        MARK_TROUBLE: "[x]",
    }.get(mark, mark)


def _print_console_summary(report: dict) -> None:
    print(f"[pipeline_progress] scanned_at = {report['scanned_at']}")
    for row in _summary_from_matrix(report["matrix"]):
        print(
            f"  SUB{row['SUB']} ({row['namecode']}): "
            f"{_ascii_mark(row['all_done'])}  cond {row['conditions_done']}  "
            f"cells {row['cells_done']}  ({row['pct']}%)"
        )
    n_miss = len(report["missing"])
    print(f"  incomplete tool-cells: {n_miss}")
    n_trouble = sum(
        1 for r in report["detail"] if r.get("mark") == MARK_TROUBLE
    )
    if n_trouble:
        print(f"  trouble mark [x] cells: {n_trouble}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update Asymmetric pipeline progress checkbox sheet "
                    "by checking PATH_RULE result files on disk."
    )
    parser.add_argument(
        "--sub", default=None,
        help="Comma-separated SUB_number list (default: 1..8)",
    )
    parser.add_argument(
        "--out", default=None,
        help="Output xlsx path (default: "
             "OpenSim_Process/_Main_/Asymmetric/pipeline_progress.xlsx)",
    )
    args = parser.parse_args()

    if args.sub:
        sub_numbers = [int(x.strip()) for x in args.sub.split(",") if x.strip()]
    else:
        sub_numbers = list(DEFAULT_SUB_NUMBERS)

    out_path = args.out or default_sheet_path()
    out_path = refresh_progress_sheet(sub_numbers, out_path=out_path)
    # Re-load summary bits for console (refresh already wrote file).
    report = scan_progress(sub_numbers)
    apply_troubles_to_report(report, load_troubles())
    _print_console_summary(report)
    print(f"[pipeline_progress] wrote: {out_path}")


if __name__ == "__main__":
    main()
