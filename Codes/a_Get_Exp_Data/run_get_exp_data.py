"""
통합 진입점 — C3D + RigidBody CSV → TRC/MOT 변환 파이프라인.

Usage
-----
    python run_get_exp_data.py                        # 모든 피험자 처리
    python run_get_exp_data.py 240124_PJH             # 특정 피험자만
    python run_get_exp_data.py 240124_PJH 260306_KTH  # 여러 피험자
    python run_get_exp_data.py --dry-run               # 파일 탐색만, 실제 처리 안 함

설정 파일 의존 관계
-------------------
    SUB_Info.py        → 피험자 메타데이터 (protocol, conditions, body_mass 등)
    PATH_RULE.py       → 경로 관리 (get_c3d_dir, get_sub_dir, get_result_dir 등)
    config_methods.py  → 프로토콜별 APP 목록, 세그먼트 분할 방식/파라미터
    lifting_config.py  → 장비 상수 (로드셀 부호, 오프셋, 필터, threshold)
"""

import os
import sys
import glob
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import PATH_RULE as _path
import config_exp_settings as _lcfg           # noqa: F401  (파이프라인 구현 시 사용)


# ── 파일 탐색 ────────────────────────────────────────────────────

def find_c3d_for_condition(c3d_dir, condition_key):
    """C3D 디렉토리에서 *condition_key* 문자열이 포함된 .c3d 파일 반환.

    Returns
    -------
    str or None
        매칭 파일의 절대경로. 없으면 None.
    """
    candidates = glob.glob(os.path.join(c3d_dir, "*.c3d"))
    matched = [
        f for f in candidates
        if condition_key in os.path.basename(f)
    ]
    if len(matched) == 1:
        return matched[0]
    if len(matched) > 1:
        print(f"    [WARN] Multiple C3D files match '{condition_key}': "
              f"{[os.path.basename(f) for f in matched]}")
        return matched[0]
    return None


def find_rigid_csv_for_condition(rigid_dir, condition_key):
    """RigidBody 디렉토리에서 *condition_key* 문자열이 포함된 .csv 파일 반환.

    Returns
    -------
    str or None
        매칭 파일의 절대경로. 없으면 None.
    """
    candidates = glob.glob(os.path.join(rigid_dir, "*.csv"))
    matched = [
        f for f in candidates
        if condition_key in os.path.basename(f)
    ]
    if len(matched) == 1:
        return matched[0]
    if len(matched) > 1:
        print(f"    [WARN] Multiple RigidBody CSVs match '{condition_key}': "
              f"{[os.path.basename(f) for f in matched]}")
        return matched[0]
    return None


# ── 프로토콜별 파이프라인 (구현 대기) ────────────────────────────

def process_condition_findpeaks(rp, cp, c3d_path, rigid_csv_path):
    """findpeaks 기반 세그먼트 분할 → TRC/MOT 출력.

    Symmetric / Asymmetric_Pilot 프로토콜에서 사용.

    파이프라인 흐름
    ---------------
    1. C3D 읽기 (opensim.C3DFileAdapter) → 마커(100Hz) + 외력(1000Hz)
    2. RigidBody CSV 읽기 → 박스 회전/위치 (1000Hz)
    3. 마커 Butterworth 필터링 (10Hz, 4th)
    4. 박스 마커(LTA_BOX, RTA_BOX) Y좌표 평균 → findpeaks로 Up/Down 이벤트 검출
    5. 세그먼트 분할 (grip ~ deposit 구간)
    6. 각 세그먼트에 대해:
       a. TRC 파일 출력 (마커 → m, `write_trc` Units=m)
       b. APP1 MOT: 로드셀 force/moment/COP 회전변환 + 지면반력
       c. APP2 MOT: 지면반력만 (로드셀 → 0)
       d. APP3 MOT: 손가락 마커 COP (LFN2, RFN2)
       e. APP4 MOT: (확장용)
    Parameters
    ----------
    rp : _path.ResultPaths
    cp : _path.ConditionPaths
    """
    # TODO: lifting_io.py, segment_symmetric.py 구현 후 연결
    raise NotImplementedError(
        "findpeaks pipeline not yet implemented. "
        "Requires: lifting_io.py, segment_symmetric.py"
    )


def process_condition_bpm_window(rp, cp, c3d_path, rigid_csv_path):
    """BPM 기반 고정 윈도우 세그먼트 분할 → TRC/MOT 출력.

    Parameters
    ----------
    rp : _path.ResultPaths
    cp : _path.ConditionPaths
    """
    # TODO: lifting_io.py, segment_asymmetric.py 구현 후 연결
    raise NotImplementedError(
        "bpm_window pipeline not yet implemented. "
        "Requires: lifting_io.py, segment_asymmetric.py"
    )


_METHOD_DISPATCH = {
    "findpeaks":  process_condition_findpeaks,
    "bpm_window": process_condition_bpm_window,
}


# ── 피험자 단위 처리 ─────────────────────────────────────────────

def process_subject(namecode, dry_run=False):
    """한 명의 피험자에 대해 전체 파이프라인 수행."""
    rp = _path.ResultPaths(namecode)

    print(f"\n{'='*60}")
    print(f"[{namecode}]  {rp.sub_label}  protocol={rp.protocol}  "
          f"method={rp.segmentation['method']}")
    print(f"  C3D dir : {rp.c3d_dir}")
    print(f"  Rigid dir: {rp.rigid_dir}")
    print(f"  Output  : {rp.sub_dir}")
    print(f"  APPs    : {rp.apps}")
    print(f"{'='*60}")

    pipeline_fn = _METHOD_DISPATCH.get(rp.segmentation["method"])
    if pipeline_fn is None:
        print(f"  [ERROR] Unknown segment method: "
              f"{rp.segmentation['method']!r}")
        return

    conditions_sorted = sorted(
        rp.conditions.items(),
        key=lambda kv: kv[1]["order"],
    )

    for cond_key, cond_val in conditions_sorted:
        c3d_path = find_c3d_for_condition(rp.c3d_dir, cond_key)
        rigid_csv_path = find_rigid_csv_for_condition(rp.rigid_dir, cond_key)

        c3d_ok   = "OK" if c3d_path else "MISSING"
        rigid_ok = "OK" if rigid_csv_path else "MISSING"
        print(f"\n  [{cond_key}]  C3D={c3d_ok}  Rigid={rigid_ok}"
              f"  cycles={cond_val['cycles']}")
        if c3d_path:
            print(f"    C3D  : {os.path.basename(c3d_path)}")
        if rigid_csv_path:
            print(f"    Rigid: {os.path.basename(rigid_csv_path)}")
        if cond_val.get("error_log"):
            print(f"    error_log: {cond_val['error_log']}")

        if dry_run:
            print("    [DRY-RUN] Skipping processing.")
            continue
        if not c3d_path:
            print(f"    [SKIP] No C3D file found for '{cond_key}'")
            continue
        if not rigid_csv_path:
            print(f"    [SKIP] No RigidBody CSV found for '{cond_key}'")
            continue

        cp = rp.for_condition(cond_key)
        pipeline_fn(rp, cp, c3d_path, rigid_csv_path)


# ── CLI 엔트리포인트 ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="C3D + RigidBody CSV → TRC/MOT 변환 파이프라인",
    )
    parser.add_argument(
        "subjects", nargs="*",
        help="처리할 피험자 namecode (생략 시 전체 처리)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="파일 탐색만 수행, 실제 변환 생략",
    )
    args = parser.parse_args()

    available = _path.DATA_SUB_NAMECODE_li

    if args.subjects:
        namecodes = args.subjects
        for nc in namecodes:
            if nc not in available:
                parser.error(
                    f"Unknown namecode: {nc!r}\n  Available: {available}"
                )
    else:
        namecodes = available

    print(f"=== run_get_exp_data.py ===")
    print(f"Subjects ({len(namecodes)}): {namecodes}")
    if args.dry_run:
        print("[DRY-RUN MODE]")

    for namecode in namecodes:
        try:
            process_subject(namecode, dry_run=args.dry_run)
        except NotImplementedError as e:
            print(f"    [NOT IMPLEMENTED] {e}")
        except Exception as e:
            print(f"    [ERROR] {namecode}: {e}")
            raise

    print(f"\n{'='*60}")
    print("Done.")


if __name__ == "__main__":
    main()
