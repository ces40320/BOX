"""
통합 진입점 — C3D + RigidBody CSV → TRC/MOT 변환 파이프라인.

Usage
-----
    python run_get_exp_data.py                                 # 모든 피험자 처리
    python run_get_exp_data.py 240124_PJH                      # 특정 피험자만
    python run_get_exp_data.py 240124_PJH 260306_KTH           # 여러 피험자
    python run_get_exp_data.py --dry-run                       # 파일 탐색만, 실제 처리 안 함
    python run_get_exp_data.py 260306_KTH --dry-run            # 특정 피험자 + 탐색만

세그먼트 분할 방식
------------------
    protocol        method          pipeline 함수
    -------------   ------------    -----------------------------------
    Symmetric       findpeaks       process_condition_findpeaks     (TODO)
    Asymmetric      manual_window   process_condition_manual_window (구현)
    Asymmetric      bpm_window      process_condition_bpm_window    (TODO)

설정 파일 의존 관계
-------------------
    SUB_Info.py            → 피험자 메타데이터 (protocol, conditions, body_mass 등)
    PATH_RULE.py           → 입출력 경로 관리 (ResultPaths / ConditionPaths 클래스,
                             DATA_DIR, OPENSIM_DIR, DATA_SUB_NAMECODE_li 등)
    config_methods.py      → 프로토콜별 APP 목록, segment_style, 세그먼트 분할 파라미터
    config_exp_settings.py → 장비 상수 (로드셀 부호/오프셋, 필터 cutoff, threshold,
                             좌표계 회전, 박스/손가락 마커 이름 등)
    lifting_io.py          → C3D/CSV 읽기, 필터링, ExtLoad 조립, TRC/MOT 쓰기
"""

import os
import re
import sys
import glob
import argparse

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import PATH_RULE as _path
import config_exp_settings as _lcfg
import lifting_io as _io


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


# ── 매뉴얼 윈도우 분할 보조 함수 ───────────────────────────────

def _extract_bpm_from_condition(condition_key):
    """Condition key에서 BPM(분당 비트수) 정수를 추출.

    Examples
    --------
    >>> _extract_bpm_from_condition("7kg_10bpm")
    10
    >>> _extract_bpm_from_condition("15kg_16bpm_trial2")
    16
    """
    m = re.search(r"(\d+)\s*bpm", condition_key, flags=re.IGNORECASE)
    if not m:
        raise ValueError(
            f"Condition key에서 BPM 추출 실패: {condition_key!r}"
        )
    return int(m.group(1))


def _detect_contact_starts(force_time, hand3_fy, hand4_fy,
                           threshold_n, min_dur_sec):
    """양손 |Fy| 합이 threshold를 넘는 접촉 구간의 시작 시점 리스트.

    `min_dur_sec` 이상 지속된 접촉만 채택.
    """
    hand_total = np.abs(hand3_fy) + np.abs(hand4_fy)
    contact = hand_total > threshold_n

    diffs = np.diff(contact.astype(int))
    starts = np.where(diffs == 1)[0] + 1
    ends = np.where(diffs == -1)[0] + 1

    contact_starts = []
    for s, e in zip(starts, ends):
        dur = float(force_time[e] - force_time[s])
        if dur >= min_dur_sec:
            contact_starts.append(float(force_time[s]))
    return contact_starts


def _slice_markers_by_time(markers, t_start, t_end):
    """markers dict을 [t_start, t_end] 구간으로 자르고 time을 0 기준 정규화."""
    time_m = markers["time"]
    mask = (time_m >= t_start) & (time_m <= t_end)
    out = {"time": (time_m[mask] - t_start)}
    for key, val in markers.items():
        if key == "time":
            continue
        out[key] = val[mask]
    return out


def _slice_extload_by_time(ext, t_start, t_end):
    """ExtLoad dict (time + f/p/m × 4 plates)을 구간 슬라이스 + time 0 정규화."""
    time_f = ext["time"]
    mask = (time_f >= t_start) & (time_f <= t_end)
    out = {"time": (time_f[mask] - t_start)}
    for key, val in ext.items():
        if key == "time":
            continue
        out[key] = val[mask]
    return out


def _normalize_errorlog_scetions(error_log):
    """Normalize error_log entries to uppercase section labels.
    Role: 7ab -> 7AB, 12bc -> 12BC, etc."""
    return {str(x).strip().upper() for x in (error_log or []) if str(x).strip()}


def _build_extload_for_app(app, forces, markers, rigid):
    """APP 이름에 대응되는 ExtLoad dict 생성. 미구현 APP는 None."""
    if app == "MeasuredEHF":
        return _io.transform_ExtLoad_MeasuredEHF(forces, rigid, _lcfg)
    if app == "HeavyHand":
        return _io.transform_ExtLoad_HeavyHand(forces)
    if app == "AddBox":
        return _io.transform_ExtLoad_AddBox(forces, markers, _lcfg)
    return None


# ── 매뉴얼 윈도우 분할 파이프라인 ─────────────────────────────────

def process_condition_manual_window(rp, cp, c3d_path, rigid_csv_path):
    """수동(고정 윈도우) 세그먼트 분할 → TRC/MOT 출력.

    findpeaks 같은 marker peak 검출 대신, 양손 외력 threshold로 접촉
    시점만 잡고 BPM 기반 고정 윈도우(예: 10bpm → 6.0 s)로 cycle을
    n_phases 등분(ABC → 3등분)한다.

    파이프라인 흐름
    ---------------
    1. C3D 읽기 (마커 100 Hz, 외력 1000 Hz, ``rotations=None``).
    2. RigidBody CSV 읽기.
    3. 마커 Butterworth 저역 필터링.
    4. 프로토콜 APP 별 ExtLoad 조립(``transform_ExtLoad_*``) → Butterworth.
    5. 양손 |Fy| 합 threshold로 접촉 시작점 검출 → 3개씩 묶어 cycle 시작.
    6. cycle별로 ``CYCLE_OFFSET_SEC + lift_j * BPM_DURATION`` 윈도우 생성.
    7. 각 세그먼트를 ``cp.trc_path / cp.extload_path`` 경로에 저장.

    Parameters
    ----------
    rp : _path.ResultPaths
    cp : _path.ConditionPaths
    c3d_path : str
    rigid_csv_path : str
    """
    seg_cfg = rp.segmentation
    if seg_cfg.get("method") != "manual_window":
        raise ValueError(
            f"manual_window는 method='bpm_window'에서 호출되어야 합니다. "
            f"(received: {seg_cfg.get('method')!r})"
        )

    bpm = _extract_bpm_from_condition(cp.cond)
    bpm_duration_map = seg_cfg["BPM_DURATION"]
    if bpm not in bpm_duration_map:
        raise ValueError(
            f"BPM {bpm} not in BPM_DURATION map: "
            f"{sorted(bpm_duration_map.keys())}"
        )
    seg_duration = float(bpm_duration_map[bpm])
    cycle_offset = float(seg_cfg["CYCLE_OFFSET_SEC"])
    contact_th_n = float(seg_cfg["CONTACT_THRESHOLD_N"])
    contact_min_dur = float(seg_cfg["CONTACT_MIN_DUR_SEC"])
    error_segments = _normalize_errorlog_scetions(cp.error_log)

    print(f"    [manual_window] BPM={bpm} window={seg_duration}s "
          f"offset={cycle_offset}s apps={rp.apps}")

    # ── 1) 데이터 로드 (회전 없음 — Motive Y-up 가정) ──────────
    markers = _io.read_c3d_markers(c3d_path, rotations=None)
    forces = _io.read_c3d_force_platforms(c3d_path, rotations=None)
    rigid = _io.read_rigid_body_csv(
        rigid_csv_path, skiprow_num=_lcfg.RIGID_BODY_SKIPROWS,
    )

    marker_time = markers["time"]
    force_time = forces["time"]
    if len(marker_time) < 2 or len(force_time) < 2:
        print("    [SKIP] insufficient frames in C3D.")
        return
    marker_rate = 1.0 / float(np.mean(np.diff(marker_time)))    # marker_rate = 100Hz
    force_rate = 1.0 / float(np.mean(np.diff(force_time)))      # force_rate = 1000Hz
    rigid = _io.upsample_rigid_to_rate(rigid, target_rate_hz=force_rate)

    # ── 2) 마커 필터링 ─────────────────────────────────────────
    for key in list(markers.keys()):
        if key == "time":
            continue
        markers[key] = _io.butterworth_filter(
            markers[key], fs_hz=marker_rate,
            cutoff_hz=_lcfg.MARKER_FILTER_HZ, order=_lcfg.FILTER_ORDER,
        )

    # ── 3) APP별 ExtLoad 조립 + 필터링 ─────────────────────────
    ext_by_app = {}
    for app in rp.apps:
        ext = _build_extload_for_app(app, forces, markers, rigid)
        if ext is None:
            print(f"    [WARN] APP {app!r} not implemented for "
                  f"manual_window. Skipping ExtLoad.")
            continue
        for key in list(ext.keys()):
            if key == "time":
                continue
            ext[key] = _io.butterworth_filter(
                ext[key], fs_hz=force_rate,
                cutoff_hz=_lcfg.FORCE_FILTER_HZ, order=_lcfg.FILTER_ORDER,
            )
        ext_by_app[app] = ext

    # ── 4) 접촉 시작점 → cycle 시작점 ───────────────────────────
    if "f3" not in forces or "f4" not in forces:
        raise KeyError(
            "manual_window requires hand load-cell plates 'f3', 'f4' in C3D."
        )
    f3_y = forces["f3"][:, 1]
    f4_y = forces["f4"][:, 1]
    contact_starts = _detect_contact_starts(
        force_time, f3_y, f4_y,
        threshold_n=contact_th_n, min_dur_sec=contact_min_dur,
    )

    # n_sections 개씩 묶어 cycle 시작 (ABC → 3개, UpDown → 2개)
    section_segs = cp.section_segments()         # {"AB":[...], "BC":[...], ...}
    section_order = list(section_segs.keys())
    n_phases = len(section_order)
    cycle_starts = contact_starts[::n_phases]
    print(f"    contacts={len(contact_starts)}  cycles={len(cycle_starts)} "
          f"(n_phases={n_phases})")

    # ── 5) 디렉토리 트리 생성 ──────────────────────────────────
    cp.build_tree()

    # ── 6) 세그먼트 분할 + 파일 출력 ───────────────────────────
    t_min = float(force_time[0])
    t_max = float(force_time[-1])

    written = 0
    for cyc_i, cs in enumerate(cycle_starts, start=1):
        for lift_j in range(n_phases):
            section = section_order[lift_j]
            section_list = section_segs[section]
            if cyc_i - 1 >= len(section_list):
                continue
            seg_label = section_list[cyc_i - 1]   # e.g. 1AB, 1BC, 1CA, 2AB …
            seg_key = str(seg_label).strip().upper()

            if seg_key in error_segments:
                print(f"      [SKIP] {seg_label}  listed in error_log")
                continue

            ps = float(cs) + cycle_offset + lift_j * seg_duration
            pe = ps + seg_duration

            if ps < t_min or pe > t_max:
                print(f"      [SKIP] {seg_label}  out-of-range "
                      f"({ps:.2f}~{pe:.2f}s, data {t_min:.2f}~{t_max:.2f}s)")
                continue

            mark_seg = _slice_markers_by_time(markers, ps, pe)
            if len(mark_seg["time"]) == 0:
                print(f"      [SKIP] {seg_label}  empty marker slice")
                continue
            trc_path = cp.trc_path(seg_label)
            _io.write_trc(
                trc_path, mark_seg["time"],
                {k: v for k, v in mark_seg.items() if k != "time"},
            )

            for app, ext in ext_by_app.items():
                ext_seg = _slice_extload_by_time(ext, ps, pe)
                if len(ext_seg["time"]) == 0:
                    print(f"      [WARN] {seg_label} {app}: empty MOT slice")
                    continue
                _io.write_extload_mot(
                    cp.extload_path(seg_label, app), ext_seg,
                )

            written += 1
            print(f"      seg{written:03d}  {seg_label}  cyc{cyc_i}L{lift_j+1}  "
                  f"{ps:.2f}~{pe:.2f}s")

    print(f"    [Done] {written} segments → {cp.cond_dir}")


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
    "findpeaks":     process_condition_findpeaks,
    "manual_window": process_condition_manual_window,
    "bpm_window":    process_condition_bpm_window,
}

_IMPLEMENTED_APPS = {"MeasuredEHF", "HeavyHand", "AddBox"}


# ── dry-run 계획 리포트 ─────────────────────────────────────────

def _list_matches(directory, condition_key, ext):
    """condition_key 포함 + *ext* 확장자인 후보 파일 전체 목록을 반환."""
    if not os.path.isdir(directory):
        return []
    cands = sorted(glob.glob(os.path.join(directory, f"*{ext}")))
    return [p for p in cands if condition_key in os.path.basename(p)]


def _report_dry_run_plan(rp, cp, cond_val, c3d_path, rigid_csv_path):
    """--dry-run 에서 condition 하나에 대한 계획을 출력.

    단계별로 진행하다가 근본적 문제(디렉토리 없음, 매칭 실패 등)를
    만나면 즉시 종료하여 잡음을 줄인다.
    """
    # 1) 입력 파일 후보 (디렉토리 존재 체크는 _list_matches에서 처리됨.
    #    단, subject 레벨에서 이미 걸러지지 않은 경우를 위해 한 번 더 검증)
    if not os.path.isdir(rp.c3d_dir):
        print(f"    [ERROR] C3D directory does not exist: {rp.c3d_dir}")
        return
    if not os.path.isdir(rp.rigid_dir):
        print(f"    [ERROR] Rigid directory does not exist: {rp.rigid_dir}")
        return

    c3d_cands = _list_matches(rp.c3d_dir, cp.cond, ".c3d")
    rigid_cands = _list_matches(rp.rigid_dir, cp.cond, ".csv")

    if not c3d_cands:
        print(f"    [ERROR] No C3D file matched '{cp.cond}' in {rp.c3d_dir}")
        return
    if not rigid_cands:
        print(f"    [ERROR] No Rigid CSV matched '{cp.cond}' in {rp.rigid_dir}")
        return

    # 여기부터는 입력이 확보된 경우만 상세 리포트
    print(f"    ── dry-run plan ──")
    print(f"    C3D candidates ({len(c3d_cands)}):")
    for p in c3d_cands:
        mark = "  <- selected" if p == c3d_path else ""
        print(f"      {os.path.basename(p)}{mark}")
    print(f"    Rigid candidates ({len(rigid_cands)}):")
    for p in rigid_cands:
        mark = "  <- selected" if p == rigid_csv_path else ""
        print(f"      {os.path.basename(p)}{mark}")

    # 2) 세그먼트 설정 검증
    seg_cfg = rp.segmentation
    method = seg_cfg.get("method")
    issues = []
    if method in ("manual_window", "bpm_window"):
        try:
            bpm = _extract_bpm_from_condition(cp.cond)
            print(f"    BPM extracted: {bpm}")
            if "BPM_DURATION" in seg_cfg:
                if bpm not in seg_cfg["BPM_DURATION"]:
                    issues.append(
                        f"BPM {bpm} not in BPM_DURATION map "
                        f"{sorted(seg_cfg['BPM_DURATION'].keys())}"
                    )
                else:
                    print(f"    Window duration: "
                          f"{seg_cfg['BPM_DURATION'][bpm]}s")
        except ValueError as exc:
            issues.append(str(exc))

    # 3) APP 구현 여부
    apps_ok = [a for a in rp.apps if a in _IMPLEMENTED_APPS]
    apps_missing = [a for a in rp.apps if a not in _IMPLEMENTED_APPS]
    if apps_missing:
        issues.append(
            f"APPs not implemented (MOT will be skipped): {apps_missing}"
        )

    # 4) 예상 생성 파일
    segments = cp.all_segments()
    section_segs = cp.section_segments()
    n_trc = len(segments)
    n_mot = n_trc * len(apps_ok)

    print(f"    Planned outputs: {n_trc} TRC + {n_mot} MOT "
          f"({len(apps_ok)}/{len(rp.apps)} APPs implemented)")
    for section, labels in section_segs.items():
        print(f"      section {section}: {labels}")

    if segments:
        ex = segments[0]
        print(f"    Example paths for seg={ex!r}:")
        print(f"      TRC : {cp.trc_path(ex)}")
        for app in apps_ok:
            print(f"      MOT : {cp.extload_path(ex, app)}")
        for app in apps_missing:
            print(f"      MOT : [SKIP]  {app}  (not implemented)")

    # 5) 이슈 요약
    if len(c3d_cands) > 1:
        issues.append(f"{len(c3d_cands)} C3D candidates matched "
                      f"(first selected)")
    if len(rigid_cands) > 1:
        issues.append(f"{len(rigid_cands)} Rigid candidates matched "
                      f"(first selected)")
    for w in issues:
        print(f"    [WARN] {w}")
    if not issues:
        print(f"    [OK] Inputs matched, config valid.")


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

    subject_root = os.path.join(_path.DATA_DIR, namecode)
    if not os.path.isdir(subject_root):
        print(f"  [ERROR] Subject data directory does not exist: "
              f"{subject_root}")
        return
    if not os.path.isdir(rp.c3d_dir):
        print(f"  [ERROR] C3D directory does not exist: {rp.c3d_dir}")
        return
    if not os.path.isdir(rp.rigid_dir):
        print(f"  [ERROR] Rigid directory does not exist: {rp.rigid_dir}")
        return

    conditions_sorted = sorted(
        rp.conditions.items(),
        key=lambda kv: kv[1]["order"],
    )

    for cond_key, cond_val in conditions_sorted:
        cp = rp.for_condition(cond_key)
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
            _report_dry_run_plan(rp, cp, cond_val, c3d_path, rigid_csv_path)
            continue
        if not c3d_path:
            print(f"    [SKIP] No C3D file found for '{cond_key}'")
            continue
        if not rigid_csv_path:
            print(f"    [SKIP] No RigidBody CSV found for '{cond_key}'")
            continue

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
