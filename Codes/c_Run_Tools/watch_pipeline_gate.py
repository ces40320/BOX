"""Poll pipeline progress until a gate job finishes, then start the next run.

Safe while another ``run_opensim_pipeline`` is active: only scans/writes the
progress sheet (or scan-only if the xlsx is locked), then launches the next
command once gate cells are done **and** the gate process has exited.

Example
-------
::

    python watch_pipeline_gate.py ^
      --wait-namecode 260519_SHY --wait-tools so,jr --wait-apps preRiCTO,postRiCTO ^
      --interval 600 ^
      --next-namecode 260521_KJA --next-tools so,jr --next-apps preRiCTO,postRiCTO ^
      --next-workers 12 --next-skip-existing
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Iterable

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CODES_DIR = os.path.dirname(THIS_DIR)
if CODES_DIR not in sys.path:
    sys.path.insert(0, CODES_DIR)
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

from update_pipeline_progress import (  # noqa: E402
    MARK_DONE,
    MARK_TROUBLE,
    _ascii_mark,
    apply_troubles_to_report,
    load_troubles,
    prune_resolved_troubles,
    refresh_progress_sheet,
    scan_progress,
    sub_number_for_namecode,
)


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log(msg: str) -> None:
    print(f"[{_ts()}] {msg}", flush=True)


def _split_csv(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def _pipeline_pids(namecode: str) -> list[int]:
    """PIDs of ``run_opensim_pipeline.py`` whose cmdline contains *namecode*."""
    try:
        import psutil  # type: ignore
    except ImportError:
        psutil = None

    needle = "run_opensim_pipeline"
    out: list[int] = []
    if psutil is not None:
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmd = " ".join(p.info.get("cmdline") or [])
            except (psutil.Error, TypeError):
                continue
            if needle in cmd and namecode in cmd:
                out.append(int(p.info["pid"]))
        return out

    # Fallback: WMIC / PowerShell-free via tasklist is weak; use ctypes-free
    # subprocess query on Windows.
    if os.name == "nt":
        ps = (
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
            "Where-Object { $_.CommandLine -match 'run_opensim_pipeline' -and "
            f"$_.CommandLine -match '{namecode}' }} | "
            "Select-Object -ExpandProperty ProcessId"
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, check=False,
        )
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                out.append(int(line))
    return out


def _gate_cells(
    report: dict,
    *,
    namecode: str,
    tools: Iterable[str],
    apps: Iterable[str],
) -> list[dict]:
    tools_l = {t.lower() for t in tools}
    apps_s = set(apps)
    return [
        row for row in report["detail"]
        if row.get("namecode") == namecode
        and str(row.get("tool", "")).lower() in tools_l
        and row.get("app") in apps_s
    ]


def _summarize_cells(cells: list[dict]) -> tuple[int, int, int, int]:
    """Return (done, trouble, other_incomplete, total)."""
    done = sum(1 for c in cells if c.get("mark") == MARK_DONE)
    trouble = sum(1 for c in cells if c.get("mark") == MARK_TROUBLE)
    other = sum(
        1 for c in cells
        if c.get("mark") not in (MARK_DONE, MARK_TROUBLE)
    )
    return done, trouble, other, len(cells)


def _refresh_or_scan(sub_n: int) -> dict:
    """Prefer full sheet refresh; fall back to scan-only if xlsx is locked."""
    try:
        refresh_progress_sheet([sub_n])
        _log(f"refreshed progress sheet for SUB{sub_n}")
    except PermissionError as e:
        _log(f"xlsx locked — scan-only ({e})")
    except OSError as e:
        _log(f"sheet write failed — scan-only ({e})")

    report = scan_progress([sub_n])
    kept, removed = prune_resolved_troubles()
    if removed:
        _log(f"pruned {len(removed)} resolved trouble(s)")
    apply_troubles_to_report(report, kept if kept is not None else load_troubles())
    return report


def _build_next_cmd(args: argparse.Namespace) -> list[str]:
    py = args.python or sys.executable
    script = os.path.join(THIS_DIR, "run_opensim_pipeline.py")
    cmd = [
        py, script,
        "--namecode", args.next_namecode,
        "--tools", args.next_tools,
        "--apps", args.next_apps,
        "--workers", str(args.next_workers),
    ]
    if args.next_skip_existing:
        cmd.append("--skip-existing")
    if args.next_extra:
        cmd.extend(args.next_extra)
    return cmd


def main() -> int:
    p = argparse.ArgumentParser(
        description="Wait for a subject's tool/app cells to finish, "
                    "then start the next OpenSim pipeline run."
    )
    p.add_argument("--wait-namecode", required=True)
    p.add_argument("--wait-tools", default="so,jr")
    p.add_argument("--wait-apps", required=True)
    p.add_argument("--interval", type=int, default=600,
                   help="Seconds between checks (default: 600 = 10 min)")
    p.add_argument("--next-namecode", required=True)
    p.add_argument("--next-tools", default="so,jr")
    p.add_argument("--next-apps", required=True)
    p.add_argument("--next-workers", type=int, default=12)
    p.add_argument("--next-skip-existing", action="store_true")
    p.add_argument(
        "--next-extra", nargs=argparse.REMAINDER, default=[],
        help="Extra args after -- passed to run_opensim_pipeline",
    )
    p.add_argument(
        "--python", default=None,
        help="Interpreter for the next run (default: this process)",
    )
    p.add_argument(
        "--once", action="store_true",
        help="Check once and exit (no loop); exit 0 if started, 2 if waiting",
    )
    args = p.parse_args()

    wait_tools = _split_csv(args.wait_tools)
    wait_apps = _split_csv(args.wait_apps)
    sub_n = sub_number_for_namecode(args.wait_namecode)
    next_cmd = _build_next_cmd(args)

    _log(
        f"GATE wait {args.wait_namecode} (SUB{sub_n}) "
        f"tools={wait_tools} apps={wait_apps} every {args.interval}s"
    )
    _log(f"NEXT cmd: {' '.join(next_cmd)}")

    while True:
        report = _refresh_or_scan(sub_n)
        cells = _gate_cells(
            report,
            namecode=args.wait_namecode,
            tools=wait_tools,
            apps=wait_apps,
        )
        done, trouble, other, total = _summarize_cells(cells)
        pids = _pipeline_pids(args.wait_namecode)
        _log(
            f"{args.wait_namecode} gate cells: "
            f"{done}/{total} done, {trouble} trouble, {other} incomplete; "
            f"pipeline_pids={pids or 'none'}"
        )

        if total == 0:
            _log("ERROR: no matching gate cells — check apps/tools")
            return 1

        # "Code finished": gate process gone and no still-generating cells.
        # Trouble (x) alone does not block the next subject.
        process_gone = not pids
        no_inflight = other == 0
        gate_ok = process_gone and no_inflight

        if gate_ok:
            if trouble:
                _log(
                    f"WARNING: {trouble} trouble cell(s) remain on gate; "
                    "starting next subject anyway"
                )
            # Avoid double-start if next job already launched.
            if _pipeline_pids(args.next_namecode):
                _log(
                    f"{args.next_namecode} pipeline already running — "
                    "nothing to start; exiting"
                )
                return 0

            _log("GATE CLEAR — starting next pipeline")
            # Detach so this watcher can exit; child keeps running.
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            log_path = os.path.join(
                THIS_DIR,
                f"watch_gate_next_{args.next_namecode}.log",
            )
            log_f = open(log_path, "a", encoding="utf-8")
            log_f.write(f"\n===== {_ts()} START =====\n")
            log_f.write(" ".join(next_cmd) + "\n")
            log_f.flush()
            proc = subprocess.Popen(
                next_cmd,
                cwd=os.path.dirname(CODES_DIR),
                stdout=log_f,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
                close_fds=False,
            )
            _log(f"started pid={proc.pid}  log={log_path}")
            return 0

        if process_gone and not no_inflight:
            _log("gate process exited but incomplete cells remain — wait")
        elif (not process_gone) and no_inflight:
            _log("cells quiet but gate pipeline still running — wait")
        else:
            # Sample a few incomplete cells for the console.
            samples = [
                c for c in cells
                if c.get("mark") != MARK_DONE
            ][:5]
            for c in samples:
                mark = _ascii_mark(str(c.get("mark", "")))
                _log(
                    f"  incomplete: {c['condition']}/{c['section']} "
                    f"{c['app']}/{c['tool']} {c.get('count')} "
                    f"mark={mark}"
                )

        if args.once:
            return 2

        time.sleep(max(30, int(args.interval)))


if __name__ == "__main__":
    raise SystemExit(main())
