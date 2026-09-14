"""Standalone RUN-phase helper for OpenSim ``AnalyzeTool`` setup XMLs.

이 스크립트는 ``run_opensim_pipeline.py`` 가 RUN 단계를 **별도 Python
프로세스** 로 분리 실행할 때 사용된다.

배경
----
OpenSim Python 바인딩에는 동일 인터프리터 안에서 ``AnalyzeTool`` 을
세팅(SET)하여 ``printToXML(...)`` 까지 마친 직후 또 다른 ``AnalyzeTool``
을 ``.run()`` 하면 분석이 조용히 미수행되는 알려진 문제가 있다.
OLD 파이프라인 (``OLD/OneCycle_ANALYZE_SO_SET.py`` ↔ ``OLD/OneCycle_ANALYZE_SO_RUN.py``)
이 두 개의 별도 스크립트로 분리되어 있었던 것은 정확히 이 문제를 회피하기
위함이다 (사용자 확인).

이 스크립트는 setup XML 만 받아 ``osim.AnalyzeTool(xml).run()`` 하는
순수 RUN 단계이며, SET 단계의 in-process 상태와 완전히 격리된다.

Manifest 포맷
--------------
JSON 파일 1개 (``--manifest`` 인자) 안에 작업 리스트:

```
[
  {
    "tool":        "so" | "bk" | "jr",
    "setup_xml":   "/abs/path/SETUP_*.xml",
    "model_path":  "/abs/path/SUB{n}_Scaled[_variant].osim",
    "rename_after": [["/abs/src.sto", "/abs/dst.sto"], ...]   // 옵션
  },
  ...
]
```

각 작업은 다음을 수행한다.

1. ``osim.Model(model_path)`` 로 모델 로드
2. ``osim.AnalyzeTool(setup_xml)`` 로 도구 로드
3. ``setModel`` / ``setModelFilename`` 으로 모델 바인딩 (XML 의 ``model_file``
   필드가 다른 절대경로를 가리키더라도 명시적으로 덮어쓴다)
4. ``.run()`` 수행 — 반환값이 False 면 즉시 비-0 종료
5. (옵션) ``rename_after`` 의 (src→dst) 쌍을 차례로 이동 — JR 의
   ``ground`` 결과 파일이 후속 ``child`` 실행에 덮어쓰이지 않도록 사이에 끼움

CLI
---
``python _run_analyze_subprocess.py --manifest <manifest.json>``

App-agnostic: MeasuredEHF / HeavyHand / preRiCTO / postRiCTO / FreeBox
all flow through the same AnalyzeTool RUN path once SETUP XML + model
paths are in the manifest.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def _maybe_add_opensim_dll_dir() -> None:
    add_dll = getattr(os, "add_dll_directory", None)
    if add_dll is None:
        return
    dll_dir = "C:/OpenSim 4.5/bin"
    if os.path.isdir(dll_dir):
        add_dll(dll_dir)


def _validate_job(idx: int, job: dict) -> None:
    for k in ("tool", "setup_xml", "model_path"):
        if k not in job:
            raise ValueError(f"job[{idx}] missing required key: {k!r}")
    if not os.path.isfile(job["setup_xml"]):
        raise FileNotFoundError(
            f"job[{idx}] setup_xml missing: {job['setup_xml']}"
        )
    if not os.path.isfile(job["model_path"]):
        raise FileNotFoundError(
            f"job[{idx}] model_path missing: {job['model_path']}"
        )


def _apply_renames(rename_after: list[list[str]]) -> None:
    for pair in rename_after:
        if len(pair) != 2:
            raise ValueError(f"rename_after entry must be [src, dst], got {pair!r}")
        src, dst = pair
        if not os.path.isfile(src):
            print(f"  [WARN] rename src missing, skipping: {src}", flush=True)
            continue
        if os.path.isfile(dst):
            os.remove(dst)
        os.rename(src, dst)
        print(f"  [RENAMED] {os.path.basename(src)} -> {os.path.basename(dst)}",
              flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True,
                        help="JSON manifest file with job list")
    args = parser.parse_args()

    with open(args.manifest, "r", encoding="utf-8") as f:
        jobs = json.load(f)
    if not isinstance(jobs, list) or not jobs:
        print(f"[ERROR] manifest empty or not a list: {args.manifest}",
              file=sys.stderr)
        return 2

    for idx, job in enumerate(jobs):
        _validate_job(idx, job)

    _maybe_add_opensim_dll_dir()
    import opensim as osim

    for idx, job in enumerate(jobs):
        tool        = job["tool"]
        setup_xml   = job["setup_xml"]
        model_path  = job["model_path"]
        rename_after = job.get("rename_after", []) or []

        print(f"[RUN {idx+1}/{len(jobs)}] tool={tool} "
              f"setup={os.path.basename(setup_xml)} "
              f"model={os.path.basename(model_path)}", flush=True)

        model = osim.Model(model_path)
        analyze = osim.AnalyzeTool(setup_xml)
        analyze.setModel(model)
        analyze.setModelFilename(model_path)

        ok = analyze.run()
        # AnalyzeTool.run() returns a bool in pyOpenSim; False == failure.
        if ok is False:
            print(f"[ERROR] AnalyzeTool.run() returned False for {setup_xml}",
                  file=sys.stderr)
            return 3

        _apply_renames(rename_after)

    print(f"[RUN DONE] {len(jobs)} job(s) completed.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
