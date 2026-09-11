"""Retry SO, JR, and BK for early-window failures in pipeline_trouble.json.

Kept out of ``run_opensim_pipeline.py`` on purpose. The main runner always
uses the TRC window. This script is the extra attempt for SO cases that
only succeed when analysis starts at 0.05 s. IK and ExtLoad are not edited,
so a later IK re-run cannot wipe the workaround. The logged app is ignored:
a failure on one app retries every protocol app that already has an
ExtLoad SETUP XML (MeasuredEHF, HeavyHand, preRiCTO, postRiCTO). Apps
without that XML are skipped. ``--manual`` ignores the sidecar and
runs the named trials (SO already at 0.05 s is padded, then JR and BK).

After SO, JR, and BK finish, every result ``.sto`` gets rows at 0.01, 0.02,
0.03, and 0.04 s, each a copy of the 0.05 s row. Downstream time grids
then match trials that ran from 0.01 s. Those four rows are a static hold,
not measured motion — discard them in analysis.

Interrupt / pool deaths (exit 3221225786, BrokenProcessPool) are not
treated as edge failures. They would likely succeed from 0.01 s, and
cutting them would invent early frames. Pass ``--include-interrupted``
to override.

A later ``run_opensim_pipeline.py`` without ``--skip-existing`` will
overwrite these results with a full-window attempt. Re-run this script
afterwards, or keep ``--skip-existing`` on.
"""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import get_context


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CODES_DIR = os.path.dirname(THIS_DIR)
if CODES_DIR not in sys.path:
    sys.path.append(CODES_DIR)

from PATH_RULE import ResultPaths
from SUB_Info import subjects
from opensim_pipeline_handlers import (
    prepare_bk_setup,
    prepare_jr_setup,
    prepare_so_setup,
    run_bk,
    run_jr,
    run_so,
)
from pipeline_rules import ik_suffix, jr_suffixes
from update_pipeline_progress import (
    load_troubles,
    record_trouble,
    refresh_progress_sheet,
    sub_number_for_namecode,
    trouble_entry_resolved,
)


EDGE_START_S = 0.05
PAD_TIMES_S: tuple[float, ...] = (0.01, 0.02, 0.03, 0.04)
_TIME_TOL = 5e-4
# Ctrl+C on Windows (0xC000013A) and pool deaths are not the 0.05 s failure.
_INTERRUPT_MARKERS = (
    "3221225786",
    "0xC000013A",
    "BrokenProcessPool",
    "KeyboardInterrupt",
)


def _log(msg: str) -> None:
    print(msg, flush=True)


def _near(a: float, b: float) -> bool:
    return abs(a - b) <= _TIME_TOL


def is_interrupt_error(error: str) -> bool:
    text = error or ""
    return any(marker in text for marker in _INTERRUPT_MARKERS)


def _case_key(entry: dict) -> tuple[str, str, str, str]:
    return (
        str(entry.get("namecode")),
        str(entry.get("condition")),
        str(entry.get("segment")),
        str(entry.get("app") or ""),
    )


def _seg_key(entry: dict) -> tuple[str, str, str]:
    return (
        str(entry.get("namecode")),
        str(entry.get("condition")),
        str(entry.get("segment")),
    )


def _matches_filters(
    entry: dict,
    *,
    namecodes: set[str] | None,
    conditions: set[str] | None,
    segments: set[str] | None,
) -> bool:
    if namecodes and str(entry.get("namecode")) not in namecodes:
        return False
    if conditions and str(entry.get("condition")) not in conditions:
        return False
    if segments and str(entry.get("segment")) not in segments:
        return False
    return True


def apps_with_extload_setup(
    namecode: str,
    condition: str,
    segment: str,
    apps_filter: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Protocol apps whose SO ExtLoad SETUP XML exists.

    Returns ``(included, excluded)``. Excluded apps have no
    ``SETUP_ExtLoad_*.xml`` and are not run. The logged trouble app is
    not special: MeasuredEHF / HeavyHand / preRiCTO / postRiCTO are
    decided only by that file.
    """
    rp = ResultPaths(namecode)
    cp = rp.for_condition(condition)
    included: list[str] = []
    excluded: list[str] = []
    for app in cp.apps:
        if apps_filter and app not in apps_filter:
            continue
        xml = cp.setup_extload_path(segment, app)
        if os.path.isfile(xml):
            included.append(app)
        else:
            excluded.append(app)
    return included, excluded


def select_edge_segments(
    entries: list[dict],
    *,
    include_interrupted: bool = False,
    namecodes: set[str] | None = None,
    conditions: set[str] | None = None,
    segments: set[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Group unresolved SO troubles by segment. The logged app is ignored.

    A segment is selected if any unresolved SO row is a real tool failure.
    Interrupt-only segments are skipped unless ``include_interrupted``.
    """
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for entry in entries:
        if str(entry.get("tool", "")).strip().lower() != "so":
            continue
        if not _matches_filters(
            entry,
            namecodes=namecodes,
            conditions=conditions,
            segments=segments,
        ):
            continue
        grouped.setdefault(_seg_key(entry), []).append(entry)

    selected: list[dict] = []
    skipped: list[dict] = []
    for key in sorted(grouped):
        rows = grouped[key]
        unresolved = [e for e in rows if not trouble_entry_resolved(e)]
        if not unresolved:
            skipped.append({**rows[0], "_skip": "already resolved"})
            continue
        edge = [
            e for e in unresolved
            if include_interrupted or not is_interrupt_error(str(e.get("error") or ""))
        ]
        if not edge:
            skipped.append({**unresolved[0], "_skip": "interrupt/pool, not edge"})
            continue
        selected.append(edge[0])
    return selected, skipped


def select_retry_cases(
    entries: list[dict],
    *,
    include_interrupted: bool = False,
    namecodes: set[str] | None = None,
    conditions: set[str] | None = None,
    segments: set[str] | None = None,
    apps: set[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Expand each edge segment to every app with an ExtLoad SETUP XML.

    The trouble row's app is not used. MeasuredEHF and HeavyHand are
    always retried together when both XMLs exist; preRiCTO / postRiCTO
    use the same rule. Apps without ``SETUP_ExtLoad_*.xml`` are skipped.

    Also includes segments that only have an ``edge-retry:`` JR or BK
    leftover (SO already finished, JR/BK still needs the truncated window).
    """
    triggers, skipped = select_edge_segments(
        entries,
        include_interrupted=include_interrupted,
        namecodes=namecodes,
        conditions=conditions,
        segments=segments,
    )
    seen_seg = {_seg_key(e) for e in triggers}
    for entry in entries:
        if str(entry.get("tool", "")).strip().lower() not in ("jr", "bk"):
            continue
        if "edge-retry:" not in str(entry.get("error") or ""):
            continue
        if not _matches_filters(
            entry,
            namecodes=namecodes,
            conditions=conditions,
            segments=segments,
        ):
            continue
        if trouble_entry_resolved(entry):
            continue
        if _seg_key(entry) in seen_seg:
            continue
        triggers.append(entry)
        seen_seg.add(_seg_key(entry))

    selected: list[dict] = []
    for entry in sorted(triggers, key=_seg_key):
        namecode, condition, segment = _seg_key(entry)
        included, excluded = apps_with_extload_setup(
            namecode, condition, segment, apps,
        )
        logged = str(entry.get("app") or "")
        for app in excluded:
            skipped.append({
                **entry,
                "app": app,
                "_skip": "no ExtLoad SETUP XML",
            })
        if not included:
            skipped.append({
                **entry,
                "_skip": "no app with ExtLoad SETUP XML",
            })
            continue
        for app in included:
            selected.append({
                **entry,
                "app": app,
                "_logged_app": logged,
            })
    selected.sort(key=_case_key)
    return selected, skipped


def manual_retry_cases(
    namecodes: set[str],
    conditions: set[str],
    segments: set[str],
    apps: set[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Build retry rows from explicit trial names, ignoring the sidecar.

    An SO file that already starts at the hold time is padded, not
    re-run. Missing JR/BK are run. A full-window result (rows before the
    hold that are not the pad) is still refused.
    """
    missing = [
        flag for flag, values in (
            ("--namecode", namecodes),
            ("--condition", conditions),
            ("--segments", segments),
        )
        if not values
    ]
    if missing:
        raise ValueError(
            "--manual requires --namecode, --condition, and --segments "
            f"(missing {', '.join(missing)})"
        )

    selected: list[dict] = []
    skipped: list[dict] = []
    for namecode in sorted(namecodes):
        if namecode not in subjects:
            raise KeyError(
                f"Unknown namecode {namecode!r}. Available: {list(subjects)}"
            )
        cond_keys = subjects[namecode]["conditions"]
        for condition in sorted(conditions):
            if condition not in cond_keys:
                raise KeyError(
                    f"Unknown condition {condition!r} for {namecode}. "
                    f"Available: {list(cond_keys)}"
                )
            rp = ResultPaths(namecode)
            cp = rp.for_condition(condition)
            known = set(cp.all_sections())
            for segment in sorted(segments):
                if segment not in known:
                    raise ValueError(
                        f"Unknown segment {segment!r} for {namecode} "
                        f"{condition}. Sample: {sorted(known)[:8]}"
                    )
                if segment in set(cp.error_log or []):
                    skipped.append({
                        "namecode": namecode,
                        "condition": condition,
                        "segment": segment,
                        "app": "",
                        "_skip": "in error_log",
                    })
                    continue
                included, excluded = apps_with_extload_setup(
                    namecode, condition, segment, apps,
                )
                stub = {
                    "namecode": namecode,
                    "condition": condition,
                    "segment": segment,
                    "tool": "so",
                    "app": "(manual)",
                }
                for app in excluded:
                    skipped.append({
                        **stub,
                        "app": app,
                        "_skip": "no ExtLoad SETUP XML",
                    })
                if not included:
                    skipped.append({
                        **stub,
                        "_skip": "no app with ExtLoad SETUP XML",
                    })
                    continue
                for app in included:
                    selected.append({**stub, "app": app, "_logged_app": "(manual)"})
    selected.sort(key=_case_key)
    return selected, skipped


def _split_header_body(text: str) -> tuple[str, str, str, list[str]]:
    """Split a ``.sto`` into ``(preamble, newline, col_header, data_lines)``."""
    newline = "\r\n" if "\r\n" in text else "\n"
    marker = "endheader"
    idx = text.find(marker)
    if idx < 0:
        raise ValueError("missing endheader")
    after = idx + len(marker)
    if text.startswith(newline, after):
        data_start = after + len(newline)
    elif text.startswith("\n", after):
        data_start = after + 1
    else:
        raise ValueError("endheader is not on its own line")
    preamble = text[:data_start]
    rest = text[data_start:]
    lines = rest.split(newline)
    # A trailing newline yields one empty last item.
    if lines and lines[-1] == "":
        lines = lines[:-1]
    if not lines:
        raise ValueError("no column header after endheader")
    col_header = lines[0]
    data_lines = [ln for ln in lines[1:] if ln.strip()]
    return preamble, newline, col_header, data_lines


def _parse_time(token: str) -> float:
    return float(token.strip())


def _format_time_like(src_token: str, t: float) -> str:
    stripped = src_token.strip()
    decimals = 0
    if "." in stripped:
        decimals = len(stripped.split(".", 1)[1])
    body = f"{t:.{decimals}f}"
    if len(src_token) >= len(body):
        return body.rjust(len(src_token))
    return body


def _row_time_and_rest(line: str) -> tuple[str, str]:
    if "\t" not in line:
        raise ValueError(f"expected tab-separated row, got: {line[:40]!r}")
    time_tok, rest = line.split("\t", 1)
    return time_tok, rest


def sto_has_pad(path: str, pad_times: tuple[float, ...] = PAD_TIMES_S) -> bool:
    """True when every pad time already has a row."""
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    _, _, _, data_lines = _split_header_body(text)
    times = [_parse_time(_row_time_and_rest(ln)[0]) for ln in data_lines]
    return all(any(_near(t, want) for t in times) for want in pad_times)


def sto_starts_at_hold(
    path: str,
    hold_time: float = EDGE_START_S,
) -> bool:
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    _, _, _, data_lines = _split_header_body(text)
    if not data_lines:
        return False
    t0 = _parse_time(_row_time_and_rest(data_lines[0])[0])
    return _near(t0, hold_time)


def pad_sto_hold_leading(
    path: str,
    *,
    pad_times: tuple[float, ...] = PAD_TIMES_S,
    hold_time: float = EDGE_START_S,
) -> str:
    """Insert missing ``pad_times`` rows by copying the ``hold_time`` row.

    Returns ``"padded"`` or ``"already"``. Does not invent a hold row.
    Raises if the file already has earlier rows that are not the pad set,
    or if ``hold_time`` is missing.
    """
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    preamble, newline, col_header, data_lines = _split_header_body(text)
    if not data_lines:
        raise ValueError(f"no data rows: {path}")

    parsed: list[tuple[float, str, str]] = []
    for ln in data_lines:
        time_tok, rest = _row_time_and_rest(ln)
        parsed.append((_parse_time(time_tok), time_tok, rest))

    hold = next((row for row in parsed if _near(row[0], hold_time)), None)
    if hold is None:
        raise ValueError(f"no row at t={hold_time} in {path}")
    _, hold_tok, hold_rest = hold
    n_cols = 1 + len(hold_rest.split("\t"))

    present = {t for t, _, _ in parsed}
    missing = [t for t in pad_times if not any(_near(t, have) for have in present)]
    if not missing:
        return "already"

    early_unexpected = [
        t for t, _, _ in parsed
        if t < hold_time - _TIME_TOL
        and not any(_near(t, want) for want in pad_times)
    ]
    if early_unexpected:
        raise ValueError(
            f"{path} already has rows before {hold_time} "
            f"that are not the pad set: {early_unexpected[:5]}"
        )

    new_rows = [
        (t, f"{_format_time_like(hold_tok, t)}\t{hold_rest}")
        for t in missing
    ]
    combined: list[tuple[float, str]] = [(t, f"{tok}\t{rest}") for t, tok, rest in parsed]
    combined.extend(new_rows)
    combined.sort(key=lambda item: item[0])

    for i, (t, line) in enumerate(combined):
        if i and _near(t, combined[i - 1][0]):
            raise ValueError(f"duplicate time {t} after pad: {path}")
        n_fields = len(line.split("\t"))
        if n_fields != n_cols:
            raise ValueError(
                f"column count {n_fields} != {n_cols} at t={t}: {path}"
            )

    body = newline.join(ln for _, ln in combined)
    if not preamble.endswith(newline):
        preamble += newline
    out = preamble + col_header + newline + body + newline

    lines_out = out.split(newline)
    replaced = False
    for i, ln in enumerate(lines_out):
        if ln.startswith("nRows="):
            lines_out[i] = f"nRows={len(combined)}"
            replaced = True
            break
    if not replaced:
        raise ValueError(f"nRows header missing: {path}")
    out = newline.join(lines_out)
    if text.endswith(newline) and not out.endswith(newline):
        out += newline

    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    return "padded"


def _so_sto_paths(cp, rp, seg: str, app: str) -> list[str]:
    folder = cp.so_dir(cp.seg_to_section(seg), app)
    prefix = f"{rp.sub_label}_{cp.cond}_{seg}_{app}_"
    if not os.path.isdir(folder):
        return []
    names = sorted(
        name for name in os.listdir(folder)
        if name.startswith(prefix) and name.endswith(".sto")
    )
    return [os.path.join(folder, name) for name in names]


def _jr_sto_paths(cp, seg: str, app: str) -> list[str]:
    return [cp.jr_path(seg, app, suffix) for suffix in jr_suffixes(app)]


def _bk_sto_paths(cp, rp, seg: str) -> list[str]:
    folder = cp.bk_dir(cp.seg_to_section(seg))
    prefix = f"{rp.sub_label}_{cp.cond}_{seg}_BodyKinematics_"
    if not os.path.isdir(folder):
        return []
    names = sorted(
        name for name in os.listdir(folder)
        if name.startswith(prefix) and name.endswith(".sto")
    )
    return [os.path.join(folder, name) for name in names]


def _require_files(paths: list[str], label: str) -> None:
    missing = [p for p in paths if not os.path.isfile(p)]
    if missing:
        shown = "\n  ".join(missing)
        raise FileNotFoundError(f"{label} output missing:\n  {shown}")


def _pad_paths(paths: list[str], *, hold_time: float) -> list[str]:
    padded: list[str] = []
    for path in paths:
        status = pad_sto_hold_leading(path, hold_time=hold_time)
        if status == "padded":
            padded.append(path)
            if not sto_has_pad(path):
                raise RuntimeError(f"pad wrote but times missing: {path}")
    return padded


def _delete_files(paths: list[str]) -> None:
    for path in paths:
        if os.path.isfile(path):
            os.remove(path)


def _ik_covers(ik_path: str, t: float) -> bool:
    with open(ik_path, encoding="utf-8", newline="") as f:
        text = f.read()
    _, _, _, data_lines = _split_header_body(text)
    if not data_lines:
        return False
    times = [_parse_time(_row_time_and_rest(ln)[0]) for ln in data_lines]
    return min(times) - _TIME_TOL <= t <= max(times) + _TIME_TOL


def _result_status(paths: list[str], hold_time: float) -> str:
    """``padded`` | ``hold_unpadded`` | ``missing`` | ``real_early``."""
    if not paths or any(not os.path.isfile(p) for p in paths):
        return "missing"
    if all(sto_has_pad(p) for p in paths):
        return "padded"
    if all(sto_starts_at_hold(p, hold_time) for p in paths):
        return "hold_unpadded"
    return "real_early"


def _ensure_tool_ready(
    *,
    label: str,
    required: list[str],
    extra_stos: list[str],
    hold_time: float,
    run,
) -> list[str]:
    """Run if needed, then pad. Returns newly padded paths.

    ``real_early`` is refused so a full-window result is not overwritten.
    On failure after a run, the result stos are deleted.
    """
    status = _result_status(required, hold_time)
    if status == "padded":
        _log(f"[SKIP] {label}  already padded")
        return []
    if status == "real_early":
        raise RuntimeError(
            f"{label} already has rows before {hold_time}; "
            "refusing to overwrite a full-window result"
        )

    if status == "missing":
        try:
            run()
        except Exception:
            _delete_files(required)
            raise
    # hold_unpadded: pad only, do not re-run OpenSim.
    targets = list(dict.fromkeys(required + extra_stos))
    _require_files(required, label)
    try:
        padded = _pad_paths(targets, hold_time=hold_time)
    except Exception:
        # An unpadded 0.05 s file would look "resolved" to the trouble
        # sheet (force.sto exists). Delete it so the case stays failed.
        _delete_files(targets)
        raise
    if not all(sto_has_pad(p) for p in required):
        _delete_files(targets)
        raise RuntimeError(f"{label} pad did not cover 0.01–0.04 s")
    _log(f"[PAD ] {label}  {len(padded)} file(s)")
    return padded


def retry_one_case(
    *,
    namecode: str,
    condition: str,
    segment: str,
    app: str,
    start_time: float = EDGE_START_S,
    dry_run: bool = False,
) -> dict:
    """Run SO then JR from ``start_time``, then pad leading rows.

    BK is segment-level and is run once after the app jobs, not here.

    On a pad failure the just-written ``.sto`` files are deleted so a
    later prune does not treat an unpadded 0.05 s file as success.
    """
    base = {
        "ok": False,
        "namecode": namecode,
        "condition": condition,
        "segment": segment,
        "app": app,
        "tool": "so",
        "error": "",
        "padded": [],
    }
    if namecode not in subjects:
        return {**base, "error": f"unknown namecode {namecode!r}"}
    if condition not in subjects[namecode]["conditions"]:
        return {**base, "error": f"unknown condition {condition!r} for {namecode}"}

    rp = ResultPaths(namecode)
    cp = rp.for_condition(condition)
    if segment in set(cp.error_log or []):
        return {**base, "ok": True, "error": "skipped error_log", "tool": "skip"}

    ik_path = cp.ik_path(segment, ik_suffix(app))
    if not os.path.isfile(ik_path):
        return {**base, "error": f"IK missing: {ik_path}"}
    if not _ik_covers(ik_path, start_time):
        return {
            **base,
            "error": f"IK does not cover t={start_time}: {ik_path}",
        }

    so_required = [
        cp.so_path(segment, app, "force"),
        cp.so_path(segment, app, "activation"),
    ]
    jr_required = _jr_sto_paths(cp, segment, app)
    tag = f"{segment} {app}"

    if dry_run:
        _log(
            f"[DRY ] {namecode} {condition} {tag}  "
            f"SO+JR start={start_time}  then pad {list(PAD_TIMES_S)}"
        )
        return {**base, "ok": True, "tool": "dry-run"}

    try:
        padded = _ensure_tool_ready(
            label=f"SO  {tag}",
            required=so_required,
            extra_stos=_so_sto_paths(cp, rp, segment, app),
            hold_time=start_time,
            run=lambda: (
                _log(f"[RUN ] SO  {namecode} {condition} {tag}  t0={start_time}"),
                prepare_so_setup(
                    cp=cp, rp=rp, seg=segment, app=app, start_time=start_time,
                ),
                run_so(cp=cp, rp=rp, seg=segment, app=app),
            ),
        )
        # Re-list after the run so a newly written sto is included.
        extra = [
            p for p in _so_sto_paths(cp, rp, segment, app)
            if p not in so_required and not sto_has_pad(p)
        ]
        if extra:
            padded.extend(_pad_paths(extra, hold_time=start_time))
        base["padded"].extend(padded)
    except Exception as exc:
        return {**base, "tool": "so", "error": f"edge-retry: {type(exc).__name__}: {exc}"}

    try:
        padded = _ensure_tool_ready(
            label=f"JR  {tag}",
            required=jr_required,
            extra_stos=[],
            hold_time=start_time,
            run=lambda: (
                _log(f"[RUN ] JR  {namecode} {condition} {tag}  t0={start_time}"),
                prepare_jr_setup(
                    cp=cp, rp=rp, seg=segment, app=app, start_time=start_time,
                ),
                run_jr(cp=cp, rp=rp, seg=segment, app=app),
            ),
        )
        base["padded"].extend(padded)
    except Exception as exc:
        return {**base, "tool": "jr", "error": f"edge-retry: {type(exc).__name__}: {exc}"}

    return {**base, "ok": True, "tool": "so+jr"}


def retry_bk_for_segment(
    *,
    namecode: str,
    condition: str,
    segment: str,
    start_time: float = EDGE_START_S,
    dry_run: bool = False,
    bk_ik_app: str = "MeasuredEHF",
) -> dict:
    """Run BodyKinematics once for the trial, then pad leading rows.

    BK has no app dimension. It uses the base IK and the same truncated
    window as SO/JR.
    """
    base = {
        "ok": False,
        "namecode": namecode,
        "condition": condition,
        "segment": segment,
        "app": "(shared)",
        "tool": "bk",
        "error": "",
        "padded": [],
    }
    if namecode not in subjects:
        return {**base, "error": f"unknown namecode {namecode!r}"}
    if condition not in subjects[namecode]["conditions"]:
        return {**base, "error": f"unknown condition {condition!r} for {namecode}"}

    rp = ResultPaths(namecode)
    cp = rp.for_condition(condition)
    if segment in set(cp.error_log or []):
        return {**base, "ok": True, "error": "skipped error_log", "tool": "skip"}

    ik_path = cp.ik_path(segment, ik_suffix(bk_ik_app))
    if not os.path.isfile(ik_path):
        return {**base, "error": f"IK missing: {ik_path}"}
    if not _ik_covers(ik_path, start_time):
        return {**base, "error": f"IK does not cover t={start_time}: {ik_path}"}

    required = [cp.bk_path(segment, "pos_global")]
    if dry_run:
        _log(
            f"[DRY ] {namecode} {condition} {segment}  "
            f"BK start={start_time}  then pad {list(PAD_TIMES_S)}"
        )
        return {**base, "ok": True, "tool": "dry-run"}

    try:
        padded = _ensure_tool_ready(
            label=f"BK  {segment}",
            required=required,
            extra_stos=_bk_sto_paths(cp, rp, segment),
            hold_time=start_time,
            run=lambda: (
                _log(f"[RUN ] BK  {namecode} {condition} {segment}  t0={start_time}"),
                prepare_bk_setup(
                    cp=cp, rp=rp, seg=segment, bk_ik_app=bk_ik_app,
                    start_time=start_time,
                ),
                run_bk(cp=cp, rp=rp, seg=segment),
            ),
        )
        extra = [
            p for p in _bk_sto_paths(cp, rp, segment)
            if p not in required and not sto_has_pad(p)
        ]
        if extra:
            padded.extend(_pad_paths(extra, hold_time=start_time))
        base["padded"].extend(padded)
    except Exception as exc:
        return {**base, "error": f"edge-retry: {type(exc).__name__}: {exc}"}
    return {**base, "ok": True}


def _retry_worker(payload: dict) -> dict:
    return retry_one_case(
        namecode=payload["namecode"],
        condition=payload["condition"],
        segment=payload["segment"],
        app=payload["app"],
        start_time=float(payload["start_time"]),
        dry_run=bool(payload["dry_run"]),
    )


def _parse_csv(raw: str | None) -> set[str] | None:
    if raw is None:
        return None
    items = {t.strip() for t in raw.split(",") if t.strip()}
    return items or None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retry SO, JR, and BK from 0.05 s for edge failures in "
                    "pipeline_trouble.json, then copy the 0.05 s row "
                    "onto 0.01–0.04 s. The logged app is ignored: every "
                    "protocol app with an ExtLoad SETUP XML is retried. "
                    "BK runs once per trial after that trial's SO/JR. "
                    "--manual ignores the sidecar and takes --namecode, "
                    "--condition, and --segments."
    )
    parser.add_argument(
        "--trouble-json", default=None,
        help="Override pipeline_trouble.json path",
    )
    parser.add_argument("--namecode", default=None)
    parser.add_argument("--condition", default=None)
    parser.add_argument("--segments", default=None)
    parser.add_argument(
        "--apps", default=None,
        help="Optional restriction. Default ignores the logged app and "
             "retries every protocol app that has SETUP_ExtLoad XML.",
    )
    parser.add_argument(
        "--start-time", type=float, default=EDGE_START_S,
        help="Analysis start for the retry (default 0.05)",
    )
    parser.add_argument(
        "--include-interrupted", action="store_true",
        help="Also retry Ctrl+C / BrokenProcessPool SO entries. "
             "Default skips them — those are not the 0.05 s failure.",
    )
    parser.add_argument(
        "--manual", action="store_true",
        help="Ignore pipeline_trouble.json. Requires --namecode, "
             "--condition, and --segments. Apps with SETUP_ExtLoad XML "
             "are run (SO already starting at 0.05 s is padded, not re-run).",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Parallel cases (default 1). Use 0 for os.cpu_count().",
    )
    parser.add_argument(
        "--no-trouble-sheet", action="store_true",
        help="Do not refresh the progress workbook after the retry",
    )
    args = parser.parse_args()

    namecodes = _parse_csv(args.namecode)
    conditions = _parse_csv(args.condition)
    segments = _parse_csv(args.segments)
    apps = _parse_csv(args.apps)
    if args.manual:
        selected, skipped = manual_retry_cases(
            namecodes or set(), conditions or set(), segments or set(), apps,
        )
        _log("[retry_so_edge] mode=manual  (sidecar ignored)")
    else:
        entries = load_troubles(args.trouble_json)
        selected, skipped = select_retry_cases(
            entries,
            include_interrupted=args.include_interrupted,
            namecodes=namecodes,
            conditions=conditions,
            segments=segments,
            apps=apps,
        )
    _log(f"[retry_so_edge] selected={len(selected)}  skipped_so={len(skipped)}")
    for entry in skipped:
        _log(
            f"[SKIP] {entry.get('namecode')} {entry.get('condition')} "
            f"{entry.get('segment')} {entry.get('app')}  {entry.get('_skip')}"
        )
    if not selected:
        _log("[retry_so_edge] nothing to do")
        return

    payloads = [
        {
            "namecode": e["namecode"],
            "condition": e["condition"],
            "segment": e["segment"],
            "app": e["app"],
            "start_time": args.start_time,
            "dry_run": args.dry_run,
        }
        for e in selected
    ]
    n = len(payloads)
    workers = args.workers
    if workers == 0:
        workers = os.cpu_count() or 1
    workers = max(1, min(int(workers), n))

    failures: list[dict] = []
    if workers == 1:
        for i, payload in enumerate(payloads, start=1):
            _log(f"\n===== ({i}/{n}) {payload['segment']} {payload['app']} =====")
            result = _retry_worker(payload)
            if result.get("ok"):
                _log(f"[OK  ] {payload['segment']} {payload['app']}")
            else:
                failures.append(result)
                _log(f"[FAIL] {payload['segment']} {payload['app']}  {result.get('error')}")
    else:
        ctx = get_context("spawn")
        with ProcessPoolExecutor(
            max_workers=workers, mp_context=ctx, max_tasks_per_child=1,
        ) as pool:
            futures = {pool.submit(_retry_worker, p): p for p in payloads}
            done_n = 0
            for fut in as_completed(futures):
                payload = futures[fut]
                done_n += 1
                try:
                    result = fut.result()
                except Exception as exc:
                    result = {
                        "ok": False,
                        "namecode": payload["namecode"],
                        "condition": payload["condition"],
                        "segment": payload["segment"],
                        "app": payload["app"],
                        "tool": "worker",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                if result.get("ok"):
                    _log(f"[OK  ] ({done_n}/{n}) {payload['segment']} {payload['app']}")
                else:
                    failures.append(result)
                    _log(
                        f"[FAIL] ({done_n}/{n}) {payload['segment']} "
                        f"{payload['app']}  {result.get('error')}"
                    )

    seen_seg: set[tuple[str, str, str]] = set()
    for payload in payloads:
        key = (payload["namecode"], payload["condition"], payload["segment"])
        if key in seen_seg:
            continue
        seen_seg.add(key)
        _log(f"\n===== BK {payload['segment']} =====")
        bk_result = retry_bk_for_segment(
            namecode=payload["namecode"],
            condition=payload["condition"],
            segment=payload["segment"],
            start_time=float(payload["start_time"]),
            dry_run=args.dry_run,
        )
        if bk_result.get("ok"):
            _log(f"[OK  ] BK {payload['segment']}")
        else:
            failures.append(bk_result)
            _log(f"[FAIL] BK {payload['segment']}  {bk_result.get('error')}")

    if not args.dry_run and not args.no_trouble_sheet:
        for result in failures:
            if result.get("tool") == "skip":
                continue
            try:
                record_trouble(
                    namecode=result["namecode"],
                    condition=result["condition"],
                    segment=result["segment"],
                    tool=str(result.get("tool") or "so"),
                    app=result.get("app"),
                    error=str(result.get("error") or ""),
                    path=args.trouble_json,
                )
            except Exception as exc:
                _log(f"[TROUBLE] failed to record: {type(exc).__name__}: {exc}")
        try:
            subs = sorted({
                sub_number_for_namecode(p["namecode"]) for p in payloads
            })
            out = refresh_progress_sheet(subs, trouble_path=args.trouble_json)
            _log(f"[TROUBLE] Detail sheet refreshed → {out}")
        except Exception as exc:
            _log(f"[TROUBLE] sheet refresh failed: {type(exc).__name__}: {exc}")

    _log(f"[retry_so_edge] DONE  failures={len(failures)}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
