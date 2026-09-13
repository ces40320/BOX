"""Snapshot what each OpenSim pipeline pool worker is analyzing right now.

Reads live ``_run_analyze_subprocess.py --manifest`` processes under a
``run_opensim_pipeline.py`` parent and parses SETUP XML names::

    SETUP_SO_10kg_10bpm_6BC_preRiCTO.xml
    → tool=SO  condition=10kg_10bpm  cycle=6  section=BC  segment=6BC  app=preRiCTO

Usage
-----
::

    python monitor_pipeline_workers.py --namecode 260521_KJA
    python monitor_pipeline_workers.py --namecode 260519_KMJ,260521_JSY --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from typing import Any

SETUP_RE = re.compile(
    r"SETUP_(SO|JR|BK)_(.+)_(\d+)(AB|BC|CA)_([^.\\/]+)\.xml$",
    re.IGNORECASE,
)


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _cim_python_procs() -> list[dict[str, Any]]:
    """Return [{pid, ppid, cmd}, ...] for python.exe via CIM (Windows)."""
    if os.name != "nt":
        return []
    ps = r"""
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Select-Object ProcessId, ParentProcessId, CommandLine |
  ConvertTo-Json -Compress
"""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True, check=False,
    )
    if not r.stdout.strip():
        return []
    data = json.loads(r.stdout)
    if isinstance(data, dict):
        data = [data]
    out = []
    for row in data:
        cmd = row.get("CommandLine") or ""
        out.append({
            "pid": int(row["ProcessId"]),
            "ppid": int(row["ParentProcessId"]),
            "cmd": cmd,
        })
    return out


def _psutil_python_procs() -> list[dict[str, Any]] | None:
    try:
        import psutil  # type: ignore
    except ImportError:
        return None
    out: list[dict[str, Any]] = []
    for p in psutil.process_iter(["pid", "ppid", "name", "cmdline"]):
        try:
            name = (p.info.get("name") or "").lower()
            if "python" not in name:
                continue
            cmd = " ".join(p.info.get("cmdline") or [])
            out.append({
                "pid": int(p.info["pid"]),
                "ppid": int(p.info["ppid"]),
                "cmd": cmd,
            })
        except (psutil.Error, TypeError, ValueError):
            continue
    return out


def list_python_procs() -> list[dict[str, Any]]:
    return _psutil_python_procs() or _cim_python_procs()


def find_pipeline(procs: list[dict[str, Any]], namecode: str | None) -> dict | None:
    hits = []
    for p in procs:
        cmd = p["cmd"]
        if "run_opensim_pipeline.py" not in cmd:
            continue
        if namecode and namecode not in cmd:
            continue
        hits.append(p)
    if not hits:
        return None
    # Prefer the longest-lived / lowest pid if multiple (rare).
    hits.sort(key=lambda x: x["pid"])
    return hits[0]


def _descendants(root_pid: int, procs: list[dict[str, Any]]) -> set[int]:
    by_ppid: dict[int, list[int]] = {}
    for p in procs:
        by_ppid.setdefault(p["ppid"], []).append(p["pid"])
    seen: set[int] = set()
    stack = [root_pid]
    while stack:
        cur = stack.pop()
        for child in by_ppid.get(cur, []):
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return seen


def parse_setup(path: str) -> dict[str, str]:
    base = os.path.basename(path)
    m = SETUP_RE.search(base)
    if not m:
        return {
            "tool": "?",
            "condition": "?",
            "cycle": "?",
            "section": "?",
            "segment": "?",
            "app": "?",
            "setup": base,
        }
    tool, cond, cyc, sec, app = m.groups()
    return {
        "tool": tool.upper(),
        "condition": cond,
        "cycle": cyc,
        "section": sec.upper(),
        "segment": f"{cyc}{sec.upper()}",
        "app": app,
        "setup": base,
    }


def read_manifest(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"manifest not a list: {path}")
    return data


def collect_workers(
    *,
    namecode: str | None = None,
) -> dict[str, Any]:
    procs = list_python_procs()
    pipe = find_pipeline(procs, namecode)
    if pipe is None:
        return {
            "scanned_at": _ts(),
            "status": "NO_PIPELINE",
            "namecode": namecode,
            "pipeline_pid": None,
            "workers": [],
            "analyze_n": 0,
        }

    desc = _descendants(pipe["pid"], procs)
    # Pool workers: python children of pipeline that are NOT the analyze script
    # (ProcessPoolExecutor spawn workers typically have empty-ish or -c cmdline,
    # or re-exec of the main script). Analyze grandchildren have the manifest.
    analyzes = [
        p for p in procs
        if p["pid"] in desc and "_run_analyze_subprocess.py" in p["cmd"]
    ]

    # Worker identity = parent of analyze subprocess (pool worker pid).
    by_worker: dict[int, list[dict]] = {}
    for a in analyzes:
        by_worker.setdefault(a["ppid"], []).append(a)

    worker_pids = sorted(by_worker.keys())
    # Also include idle pool workers (children of pipeline with no analyze child).
    pool_like = [
        p for p in procs
        if p["ppid"] == pipe["pid"]
        and "_run_analyze_subprocess.py" not in p["cmd"]
        and "run_opensim_pipeline.py" not in p["cmd"]
    ]
    idle_pids = sorted(
        p["pid"] for p in pool_like if p["pid"] not in by_worker
    )

    rows: list[dict[str, Any]] = []
    w_idx = 0
    for wpid in worker_pids:
        w_idx += 1
        for a in by_worker[wpid]:
            man = None
            m = re.search(r"--manifest\s+(\S+)", a["cmd"])
            if m:
                man = m.group(1).strip('"')
            jobs_info: list[dict[str, str]] = []
            status = "BUSY"
            err = ""
            if man and os.path.isfile(man):
                try:
                    for job in read_manifest(man):
                        info = parse_setup(str(job.get("setup_xml", "")))
                        info["tool"] = str(job.get("tool", info["tool"])).upper()
                        jobs_info.append(info)
                except (OSError, json.JSONDecodeError, ValueError) as e:
                    err = str(e)
                    status = "MANIFEST_ERR"
            else:
                status = "NO_MANIFEST"
            if not jobs_info:
                jobs_info = [{
                    "tool": "?", "condition": "?", "cycle": "?",
                    "section": "?", "segment": "?", "app": "?",
                    "setup": err or "?",
                }]
            for info in jobs_info:
                rows.append({
                    "namecode": namecode or "",
                    "worker": f"W{w_idx:02d}",
                    "worker_pid": wpid,
                    "analyze_pid": a["pid"],
                    "status": status,
                    **info,
                })

    for wpid in idle_pids:
        w_idx += 1
        rows.append({
            "namecode": namecode or "",
            "worker": f"W{w_idx:02d}",
            "worker_pid": wpid,
            "analyze_pid": None,
            "status": "IDLE",
            "tool": "—",
            "condition": "—",
            "cycle": "—",
            "section": "—",
            "segment": "—",
            "app": "—",
            "setup": "—",
        })

    # Infer namecode from cmdline if not given.
    nc = namecode
    if not nc:
        m = re.search(r"--namecode\s+(\S+)", pipe["cmd"])
        if m:
            nc = m.group(1)
    for r in rows:
        if not r.get("namecode"):
            r["namecode"] = nc or ""

    return {
        "scanned_at": _ts(),
        "status": "RUNNING",
        "namecode": nc,
        "pipeline_pid": pipe["pid"],
        "pipeline_cmd": pipe["cmd"],
        "workers": rows,
        "analyze_n": len(analyzes),
        "busy_n": sum(1 for r in rows if r["status"] == "BUSY"),
        "idle_n": sum(1 for r in rows if r["status"] == "IDLE"),
    }


def collect_workers_multi(namecodes: list[str]) -> dict[str, Any]:
    """Snapshot several pipelines; tag each worker row with its namecode."""
    if len(namecodes) == 1:
        return collect_workers(namecode=namecodes[0])

    # One process listing for all subjects (CIM is expensive).
    procs = list_python_procs()
    subjects: list[dict[str, Any]] = []
    all_workers: list[dict[str, Any]] = []
    any_running = False
    for nc in namecodes:
        # Reuse already-fetched process list via a thin local path.
        pipe = find_pipeline(procs, nc)
        if pipe is None:
            subjects.append({
                "namecode": nc,
                "status": "NO_PIPELINE",
                "pipeline_pid": None,
                "busy_n": 0,
                "idle_n": 0,
                "analyze_n": 0,
            })
            continue
        any_running = True
        desc = _descendants(pipe["pid"], procs)
        analyzes = [
            p for p in procs
            if p["pid"] in desc and "_run_analyze_subprocess.py" in p["cmd"]
        ]
        by_worker: dict[int, list[dict]] = {}
        for a in analyzes:
            by_worker.setdefault(a["ppid"], []).append(a)
        worker_pids = sorted(by_worker.keys())
        pool_like = [
            p for p in procs
            if p["ppid"] == pipe["pid"]
            and "_run_analyze_subprocess.py" not in p["cmd"]
            and "run_opensim_pipeline.py" not in p["cmd"]
        ]
        idle_pids = sorted(
            p["pid"] for p in pool_like if p["pid"] not in by_worker
        )
        rows: list[dict[str, Any]] = []
        w_idx = 0
        for wpid in worker_pids:
            w_idx += 1
            for a in by_worker[wpid]:
                man = None
                m = re.search(r"--manifest\s+(\S+)", a["cmd"])
                if m:
                    man = m.group(1).strip('"')
                jobs_info: list[dict[str, str]] = []
                status = "BUSY"
                err = ""
                if man and os.path.isfile(man):
                    try:
                        for job in read_manifest(man):
                            info = parse_setup(str(job.get("setup_xml", "")))
                            info["tool"] = str(
                                job.get("tool", info["tool"])
                            ).upper()
                            jobs_info.append(info)
                    except (OSError, json.JSONDecodeError, ValueError) as e:
                        err = str(e)
                        status = "MANIFEST_ERR"
                else:
                    status = "NO_MANIFEST"
                if not jobs_info:
                    jobs_info = [{
                        "tool": "?", "condition": "?", "cycle": "?",
                        "section": "?", "segment": "?", "app": "?",
                        "setup": err or "?",
                    }]
                for info in jobs_info:
                    rows.append({
                        "namecode": nc,
                        "worker": f"W{w_idx:02d}",
                        "worker_pid": wpid,
                        "analyze_pid": a["pid"],
                        "status": status,
                        **info,
                    })
        for wpid in idle_pids:
            w_idx += 1
            rows.append({
                "namecode": nc,
                "worker": f"W{w_idx:02d}",
                "worker_pid": wpid,
                "analyze_pid": None,
                "status": "IDLE",
                "tool": "—",
                "condition": "—",
                "cycle": "—",
                "section": "—",
                "segment": "—",
                "app": "—",
                "setup": "—",
            })
        busy_n = sum(1 for r in rows if r["status"] == "BUSY")
        idle_n = sum(1 for r in rows if r["status"] == "IDLE")
        subjects.append({
            "namecode": nc,
            "status": "RUNNING",
            "pipeline_pid": pipe["pid"],
            "busy_n": busy_n,
            "idle_n": idle_n,
            "analyze_n": len(analyzes),
        })
        all_workers.extend(rows)

    return {
        "scanned_at": _ts(),
        "status": "RUNNING" if any_running else "NO_PIPELINE",
        "namecodes": namecodes,
        "subjects": subjects,
        "workers": all_workers,
        "busy_n": sum(1 for r in all_workers if r["status"] == "BUSY"),
        "idle_n": sum(1 for r in all_workers if r["status"] == "IDLE"),
        "analyze_n": sum(s.get("analyze_n", 0) for s in subjects),
    }


def print_table(snap: dict[str, Any]) -> None:
    if "subjects" in snap:
        print(
            f"[{snap['scanned_at']}] status={snap['status']}  "
            f"namecodes={snap.get('namecodes')}  "
            f"busy={snap.get('busy_n', 0)} idle={snap.get('idle_n', 0)}  "
            f"analyze={snap.get('analyze_n', 0)}",
            flush=True,
        )
        for s in snap.get("subjects") or []:
            print(
                f"  {s['namecode']}: {s['status']}  "
                f"pipeline={s.get('pipeline_pid')}  "
                f"busy={s.get('busy_n', 0)} idle={s.get('idle_n', 0)}  "
                f"analyze={s.get('analyze_n', 0)}",
                flush=True,
            )
        if snap["status"] == "NO_PIPELINE":
            print("NO_PIPELINE", flush=True)
            return
        headers = [
            "namecode", "worker", "status", "tool", "condition", "cycle",
            "section", "segment", "app", "worker_pid", "analyze_pid",
        ]
    else:
        print(f"[{snap['scanned_at']}] status={snap['status']}  "
              f"namecode={snap.get('namecode')}  "
              f"pipeline={snap.get('pipeline_pid')}  "
              f"busy={snap.get('busy_n', 0)} idle={snap.get('idle_n', 0)}  "
              f"analyze={snap.get('analyze_n', 0)}", flush=True)
        if snap["status"] == "NO_PIPELINE":
            print("NO_PIPELINE", flush=True)
            return
        headers = [
            "worker", "status", "tool", "condition", "cycle",
            "section", "segment", "app", "worker_pid", "analyze_pid",
        ]
    rows = snap["workers"]
    cols = {
        h: max(len(h), *(len(str(r.get(h, ""))) for r in rows))
        for h in headers
    } if rows else {h: len(h) for h in headers}
    print("  ".join(h.ljust(cols[h]) for h in headers), flush=True)
    print("  ".join("-" * cols[h] for h in headers), flush=True)
    for r in rows:
        print(
            "  ".join(str(r.get(h, "")).ljust(cols[h]) for h in headers),
            flush=True,
        )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--namecode", default=None,
        help="Comma-separated namecode(s) to monitor",
    )
    p.add_argument("--json", action="store_true",
                   help="Emit JSON snapshot instead of a table")
    args = p.parse_args()
    codes = (
        [x.strip() for x in args.namecode.split(",") if x.strip()]
        if args.namecode else [None]
    )
    if len(codes) == 1:
        snap = collect_workers(namecode=codes[0])
    else:
        snap = collect_workers_multi(codes)
    if args.json:
        print(json.dumps(snap, ensure_ascii=False, indent=2))
    else:
        print_table(snap)
    return 0 if snap["status"] != "NO_PIPELINE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
