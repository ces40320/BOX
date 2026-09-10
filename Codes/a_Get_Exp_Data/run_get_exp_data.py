"""
통합 진입점 — C3D + RigidBody CSV → TRC/MOT 변환 파이프라인.

피험자 처리 시 ``Labeled`` 폴더의 ``Static.c3d`` / ``static.c3d`` 를 찾아
``Model_osim/static.trc`` 로 먼저 변환한다. 해당 C3D 가 없으면 오류 메시지만 출력하고
조건별 lifting C3D 처리는 계속한다.

Usage
-----
    python run_get_exp_data.py                                                # 모든 피험자
    python run_get_exp_data.py 240124_PJH                                     # 특정 피험자만
    python run_get_exp_data.py 240124_PJH 260306_KTH                          # 여러 피험자
    python run_get_exp_data.py --dry-run                                      # 파일 탐색만
    python run_get_exp_data.py 260306_KTH --dry-run                           # 특정 피험자 + 탐색만
    python run_get_exp_data.py 260423_CES --t-tap-offset -0.5                 # 모든 cond 에 동일 offset
    python run_get_exp_data.py 260423_CES --t-tap-offset 7kg_10bpm=-2.3 \
                                          7kg_16bpm=-1.5                       # cond 별 offset
    python run_get_exp_data.py 260423_CES --t-tap-offset -2.0 \
                                          7kg_16bpm=-1.5                       # default + override
    python run_get_exp_data.py 260423_CES --interactive-tap                   # tap 을 GUI 에서 클릭 선택
    python run_get_exp_data.py 260423_CES --interactive-tap --dry-run         # 인터랙티브 + 탐색만

Notebook (예: ``_a_Main.ipynb``) 에서는:
    # 모든 condition 에 동일 offset
    process_subject("260423_CES", dry_run=False, t_tap_offset=-0.5)
    # condition 별로 다른 offset
    process_subject("260512_KCH", dry_run=False, t_tap_offset={
        "7kg_10bpm":  -2.30,
        "7kg_16bpm":  -1.50,
        "15kg_10bpm": -2.45,
    })
    # default + 일부만 override
    process_subject("260512_KCH", dry_run=False, t_tap_offset={
        "_default":  -2.00,
        "7kg_16bpm": -1.50,
    })
    # 인터랙티브 (cond 마다 GUI 창이 뜸; t_tap_offset 은 초기 선택 위치)
    process_subject("260423_CES", dry_run=False, interactive_tap=True)
    # 주피터의 경우 인터랙티브 창이 별도로 뜨려면 셀 상단에 ``%matplotlib qt``
    # 또는 ``%matplotlib tk`` 가 설정되어 있어야 한다 (기본 ``inline`` 은 GUI 미지원).

세그먼트 분할 방식 -> 구현 후 이주 개별 py파일로 예정
------------------
    protocol        method          pipeline 함수
    -------------   ------------    -----------------------------------
    Symmetric       findpeaks       process_condition_findpeaks     (TODO)
    Asymmetric      manual_window   process_condition_manual_window (구현)
    Asymmetric      bpm_window      process_condition_bpm_window    (구현)

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
from scipy.signal import find_peaks

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
    # TODO: split_lifting_trial2section_findpeaks.py 구현 후 이주
    raise NotImplementedError(
        "findpeaks pipeline not yet implemented. "
        "Requires: lifting_io.py, split_lifting_trial2section_findpeaks.py"
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


# ── 외력 채널 안전장치 ──────────────────────────────────────────

# Canonical force keys produced by ``_io.read_c3d_force_platforms``.
# 4-source / 7-source 레이아웃 모두 lifting_io 단계에서 1=L발 / 2=R발 /
# 3=L손 / 4=R손 으로 정규화되므로, 이 외 키가 등장하면 ExtLoad 조립 시
# 손-발 채널이 뒤바뀌었을 가능성이 있다는 신호다.
_CANONICAL_FORCE_KEYS = (
    {"time"}
    | {f"f{i}" for i in (1, 2, 3, 4)}
    | {f"p{i}" for i in (1, 2, 3, 4)}
    | {f"m{i}" for i in (1, 2, 3, 4)}
)


def _assert_canonical_force_keys(forces, c3d_path):
    """``read_c3d_force_platforms`` 출력이 4-plate 표준 키만 갖는지 검증.

    ``lifting_io.read_c3d_force_platforms`` 가 4-source / 7-source 두
    레이아웃을 모두 ``f1..f4`` 로 정규화하지만, 만약 새로운 source 개수가
    들어오거나 매핑 누락이 생기면 ``f5/f6/f7`` 같은 키가 살아남을 수 있다.
    그 경우 ``_extract_fp`` 가 잘못된 채널을 무성으로 0 처리하여 손-발
    데이터가 뒤섞일 수 있으므로, 여기서 강제 fail-fast 한다.
    """
    keys = set(forces.keys())
    extras = sorted(keys - _CANONICAL_FORCE_KEYS)
    missing = sorted(_CANONICAL_FORCE_KEYS - keys)
    if extras or missing:
        raise RuntimeError(
            f"Force channel keys are not canonical for {c3d_path!r}.\n"
            f"  unexpected keys: {extras}\n"
            f"  missing keys   : {missing}\n"
            f"  → lifting_io.read_c3d_force_platforms 의 source 매핑을 "
            f"확인하세요 (4-source / 7-source 외 레이아웃일 가능성)."
        )


def _print_force_source_warning_banner(exc, namecode, cond_key=None):
    """``UnsupportedForceSourceCountError`` 발생 시 사용자 안내 배너 출력.

    호출 측은 출력 직후 ``sys.exit(1)`` 등으로 즉시 실행을 종료하는 것을
    가정한다 (잘못된 source 매핑으로 손-발 채널이 섞이는 사고 방지).
    """
    bar = "=" * 70
    where = f"{namecode}" + (f" / {cond_key}" if cond_key else "")
    print()
    print(bar)
    print(f"[STOP] 외력 source 개수가 비정상입니다.  ({where})")
    print(bar)
    print(f"  세부: detected {exc.n_sources} sources "
          f"(found indices {sorted(exc.found_indices)})")
    print(f"        c3d = {exc.c3d_path}")
    print()
    print("  ▶ Motive Software 에서 External Hand Force source 가 정상적으로")
    print("    기록되어 있는지 확인하세요.")
    print("    - 정상 케이스: 4 sources (왼발, 오른발, 왼손, 오른손).")
    print("    - 자동 보정 가능: 7 sources (불필요한 3개 source 가 켜진 상태).")
    print("    - 그 외 개수는 채널 매핑이 불가능하므로 처리 불가.")
    print(bar)


# ── bpm_window 전용 보조 함수 ─────────────────────────────────────

def _force_plate_norm(forces, plate_idx):
    """force plate ``f{plate_idx}`` 의 합력 norm 시계열 ‖F‖ = √(Fx²+Fy²+Fz²)."""
    f = forces[f"f{plate_idx}"]
    return np.linalg.norm(f, axis=1)


def _detect_first_tap_onset(force_time, norm3, norm4, *,
                            height_n, prominence_n, min_dist_sec,
                            onset_thr_n, quantize_hz=100.0):
    """양손 로드셀 ‖F‖ 시계열에서 첫 tap onset 시점 검출 (bpm_window 전용).

    메트로놈 첫 박자에 한쪽 로드셀(f3 OR f4)을 친 단발성 임펄스를
    ``scipy.signal.find_peaks`` 로 찾고, 그 피크에서 시간 역방향으로
    ‖F‖ 가 ``onset_thr_n`` 위로 처음 올라간 샘플을 onset 으로 채택한다.
    onset 시간은 ``quantize_hz`` Hz 그리드(기본 100 Hz → 0.01 s)로
    **정수 인덱스 경유** 양자화하여 부동소수점 누적 오류를 차단한다.

    Parameters
    ----------
    force_time : (N,) ndarray
    norm3, norm4 : (N,) ndarray
        FP3(왼손) / FP4(오른손) 로드셀의 합력 norm 시계열 (raw, 1000 Hz).
    height_n, prominence_n : float
        ``find_peaks`` 절대 임계 / prominence (둘 다 적용).
    min_dist_sec : float
        같은 채널 내 인접 피크 최소 시간 간격 (초).
    onset_thr_n : float
        peak → onset 역추적 임계.  onset_idx 는 ‖F‖ ≥ onset_thr_n 가
        시간 순으로 처음 시작된 샘플(피크 직전 가장 가까운).
    quantize_hz : float
        onset 시각 양자화 그리드(Hz). 기본 100 Hz.

    Returns
    -------
    dict
        ``"t_tap"`` (양자화된 onset 시간, s),
        ``"tap_idx_grid"`` (정수 인덱스, t_tap = idx / quantize_hz),
        ``"side"`` (``"f3"`` 또는 ``"f4"``),
        ``"onset_idx"`` / ``"peak_idx"`` (1000 Hz 그리드 인덱스),
        ``"peak_value"`` (선택된 채널의 ‖F‖[peak_idx]),
        ``"peaks3"`` / ``"peaks4"`` (전체 검출 피크, 디버그용).
    """
    if len(force_time) < 2:
        raise ValueError("force_time too short for tap detection.")
    fs = 1.0 / float(np.mean(np.diff(force_time)))
    distance = max(int(round(fs * float(min_dist_sec))), 1)

    peaks3, _ = find_peaks(
        norm3, height=height_n, prominence=prominence_n, distance=distance,
    )
    peaks4, _ = find_peaks(
        norm4, height=height_n, prominence=prominence_n, distance=distance,
    )

    # 각 채널의 첫 피크만 비교 (가장 빠른 쪽이 tap).
    candidates = []
    if len(peaks3):
        candidates.append((int(peaks3[0]), "f3", norm3))
    if len(peaks4):
        candidates.append((int(peaks4[0]), "f4", norm4))
    if not candidates:
        raise RuntimeError(
            f"No tap peak detected on f3/f4 with "
            f"height>={height_n}, prominence>={prominence_n}. "
            f"임계값 또는 신호 확인 필요."
        )
    candidates.sort(key=lambda x: x[0])
    peak_idx, side, peak_signal = candidates[0]

    # 피크에서 시간 역방향 — peak_signal[i-1] 이 onset_thr_n 미만이 되면 정지.
    # 결과 onset_idx 는 ‖F‖ ≥ onset_thr_n 가 처음 만족된 샘플(시간 순).
    i = peak_idx
    while i > 0 and peak_signal[i - 1] >= onset_thr_n:
        i -= 1
    onset_idx = i

    t_raw = float(force_time[onset_idx])
    tap_idx_grid = int(round(t_raw * float(quantize_hz)))
    t_tap = tap_idx_grid / float(quantize_hz)

    return {
        "t_tap": t_tap,
        "tap_idx_grid": tap_idx_grid,
        "side": side,
        "onset_idx": int(onset_idx),
        "peak_idx": int(peak_idx),
        "peak_value": float(peak_signal[peak_idx]),
        "peaks3": peaks3,
        "peaks4": peaks4,
    }


def _plot_tap_onset_check(out_path, force_time, norm3, norm4,
                          tap_info, onset_thr_n,
                          bpm_duration=None, seg_labels=None):
    """tap onset 검출 결과 확인용 PNG 저장.

    - 두 로드셀의 ‖F‖ 시계열을 한 축에 같이 플롯.
    - 채택된 onset 위치에 빈 동그라미(face=none)로 강조.
    - 검출된 모든 피크는 작은 cross 마커로 같이 표시 (튜닝 참조).
    - ``onset_thr_n`` 가로 점선.
    - ``bpm_duration`` / ``seg_labels`` 주어지면 segment 경계를 phase별
      색의 vline 으로 그리고, 각 segment 중앙 상단에 라벨(예: ``1AB``) 표기.

    Parameters
    ----------
    seg_labels : list[str] or None
        segment 라벨 (예: ``["1AB","1BC","1CA","2AB",…]``). 스케줄 순서 유지.
    """
    # pyplot 을 거치지 않고 Figure + Agg 캔버스를 직접 생성한다.
    # 이유: Jupyter 에서 ``%matplotlib tk`` / ``qt`` 를 켜면 interactive
    # mode 가 되어 ``plt.subplots()`` 만으로도 GUI 창이 즉시 뜨고, 바로
    # ``savefig`` → ``close`` 되면서 창이 깜빡이며 열리고 닫힌다.  Agg 캔버스에
    # 직접 그리면 backend / interactive 상태와 무관하게 파일만 저장된다.
    import matplotlib
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.lines import Line2D

    side = tap_info["side"]
    t_tap = tap_info["t_tap"]                                # offset 보정 후 anchor
    t_tap_raw = tap_info.get("t_tap_raw", t_tap)             # 검출 직후 (offset 미적용)
    offset = float(tap_info.get("t_tap_offset", 0.0))
    onset_idx = tap_info["onset_idx"]
    peak_idx = tap_info["peak_idx"]
    peak_val = tap_info["peak_value"]

    fig = Figure(figsize=(11.0, 4.5))
    FigureCanvasAgg(fig)                 # pyplot 미등록 → GUI 창 안 뜸
    ax = fig.subplots()
    ax.plot(force_time, norm3, color="#1f77b4", lw=0.7, alpha=0.7,
            label="‖F3‖ (left)")
    ax.plot(force_time, norm4, color="#d62728", lw=0.7, alpha=0.7,
            label="‖F4‖ (right)")

    if len(tap_info["peaks3"]):
        ax.plot(force_time[tap_info["peaks3"]], norm3[tap_info["peaks3"]],
                "x", color="#1f77b4", ms=5, alpha=0.5)
    if len(tap_info["peaks4"]):
        ax.plot(force_time[tap_info["peaks4"]], norm4[tap_info["peaks4"]],
                "x", color="#d62728", ms=5, alpha=0.5)

    chosen_signal = norm3 if side == "f3" else norm4
    chosen_color = "#1f77b4" if side == "f3" else "#d62728"
    onset_label = (f"onset_raw (t_tap_raw={t_tap_raw:.2f}s)"
                   if offset != 0.0 else f"onset (t_tap={t_tap:.2f}s)")
    ax.plot(force_time[onset_idx], chosen_signal[onset_idx],
            "o", mfc="none", mec=chosen_color, ms=12, mew=2.0,
            label=onset_label)
    ax.plot(force_time[peak_idx], chosen_signal[peak_idx],
            "*", color=chosen_color, ms=10, alpha=0.8,
            label=f"peak ({peak_val:.1f}N)")

    # offset 가 있으면 보정된 anchor 위치를 보라색 점선으로 추가 표시
    if offset != 0.0:
        ax.axvline(t_tap, color="purple", ls="--", lw=1.0, alpha=0.8,
                   label=f"t_tap (offset {offset:+.2f}s) = {t_tap:.2f}s")

    ax.axhline(onset_thr_n, color="gray", ls="--", lw=0.7,
               label=f"onset_thr={onset_thr_n}N")

    # ── segment 경계: phase별 색 + 중앙 상단 라벨 ──────────────
    phase_handles = []
    if bpm_duration is not None and seg_labels:
        t_min = float(force_time[0])
        t_max = float(force_time[-1])

        # 라벨 위치용 y 범위 확보 (15% 여유).
        y_max = float(max(np.nanmax(norm3), np.nanmax(norm4)))
        ax.set_ylim(top=y_max * 1.15)
        y_label = y_max * 1.08

        # phase suffix → 색 매핑 (등장 순서대로 tab10 할당).
        cmap = matplotlib.colormaps["tab10"]
        phase_colors: dict[str, tuple] = {}
        for label in seg_labels:
            phase = re.sub(r"^\d+", "", str(label))
            if phase and phase not in phase_colors:
                phase_colors[phase] = cmap(len(phase_colors) % 10)

        for k, label in enumerate(seg_labels):
            phase = re.sub(r"^\d+", "", str(label))
            color = phase_colors.get(phase, (0.3, 0.3, 0.3, 1.0))
            ps = t_tap + (1 + k) * float(bpm_duration)
            pe = ps + float(bpm_duration)
            if pe < t_min or ps > t_max:
                continue
            ax.axvline(ps, color=color, ls=":", lw=0.9, alpha=0.85)
            ax.text((ps + pe) / 2.0, y_label, str(label),
                    ha="center", va="bottom", fontsize=7,
                    color=color, alpha=0.95)

        # 마지막 segment 끝(다음 segment 시작점)도 회색 vline 으로 닫기.
        ps_end = t_tap + (1 + len(seg_labels)) * float(bpm_duration)
        if t_min <= ps_end <= t_max:
            ax.axvline(ps_end, color="gray", ls=":", lw=0.6, alpha=0.6)

        phase_handles = [
            Line2D([0], [0], color=c, ls=":", lw=1.5, label=p)
            for p, c in phase_colors.items()
        ]

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("‖F‖ (N)")
    if offset != 0.0:
        title = (
            f"tap_onset_check  side={side}  "
            f"t_tap_raw={t_tap_raw:.2f}s  offset={offset:+.2f}s  "
            f"→ t_tap={t_tap:.2f}s  peak={peak_val:.1f}N"
        )
    else:
        title = (
            f"tap_onset_check  side={side}  t_tap={t_tap:.2f}s  "
            f"peak={peak_val:.1f}N"
        )
    ax.set_title(title)
    main_legend = ax.legend(loc="upper right", fontsize=8)
    if phase_handles:
        ax.add_artist(main_legend)
        ax.legend(handles=phase_handles, loc="upper left", fontsize=8,
                  title="Phases")
    ax.grid(False)
    fig.tight_layout()

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=120)
    # pyplot 에 등록되지 않은 Figure 라 close() 불필요 — 참조 해제로 정리됨.


def _select_t_tap_interactive(force_time, norm3, norm4, tap_info_auto, *,
                              onset_thr_n, bpm_duration=None, seg_labels=None,
                              quantize_hz=100.0, initial_t_tap=None,
                              window_title=None):
    """[INTERACTIVE] matplotlib GUI 창에서 마우스 클릭으로 ``t_tap`` 직접 선택.

    창이 열리면 자동 검출 결과(회색 점선)와 현재 선택(보라색 실선) 이 함께
    표시된다. 사용자는 그래프 영역을 좌클릭해 anchor 를 옮길 수 있고,
    클릭 위치는 ``quantize_hz`` 그리드(기본 100 Hz → 0.01 s)로 스냅된다.
    창을 닫거나 Enter 를 누르면 현재 선택값이 확정되어 반환된다.

    Keyboard shortcuts
    ------------------
    Left / Right         : ``±1/quantize_hz`` 초 단위 미세 조정
    Shift+Left / Right   : ``±10/quantize_hz`` 초 단위 조정
    r                    : 자동 검출값(``t_tap_auto``)으로 reset
    Enter / Space        : 현재 선택값으로 확정 후 창 닫기
    창 X 클릭            : 현재 선택값으로 확정

    Bounds
    ------
    오른쪽은 데이터 끝(``force_time[-1]``). 왼쪽은 ``t_tap`` 이 음수로
    넘어갈 수 있게 열어 두되, 1AB 시작
    (``t_tap + bpm_duration``) 이 0 초 미만이 되지 않는 지점
    (``t_tap >= -bpm_duration``) 까지만 허용한다. ``bpm_duration`` 이
    없으면 기존처럼 데이터 시작(``force_time[0]``) 에서 자른다.

    Parameters
    ----------
    force_time, norm3, norm4 : ndarray
        1000 Hz 시간축과 두 손 로드셀의 ‖F‖ 시계열.
    tap_info_auto : dict
        ``_detect_first_tap_onset`` 가 반환한 dict (자동 검출 결과를
        참조용 시각화에 사용).
    onset_thr_n : float
        가로 점선으로 표시할 onset threshold (N).
    bpm_duration : float or None
        segment 폭(초). 주어지면 선택된 ``t_tap`` 기준 segment 경계선을
        실시간으로 함께 그려준다.
    seg_labels : list[str] or None
        segment 라벨 (예: ``["1AB","1BC","1CA","2AB",…]``).
    quantize_hz : float
        선택 위치를 정렬할 그리드 (기본 100 Hz).
    initial_t_tap : float or None
        창이 열릴 때 초기 선택값. None 이면 ``tap_info_auto["t_tap"]``.
        ``--t-tap-offset`` 같은 사전 보정을 초기값으로 넣고 추가 미세조정을
        하고 싶을 때 사용.
    window_title : str or None
        OS 창 제목 (다중 condition 처리 시 어느 trial 인지 식별용).

    Returns
    -------
    float
        확정된 ``t_tap`` (``quantize_hz`` 그리드로 양자화된 값).

    Notes
    -----
    - 헤드리스 환경(또는 ``MPLBACKEND=Agg``)에서는 GUI 창이 열리지 않으므로
      ``--interactive-tap`` 옵션을 사용해선 안 된다.
    - Jupyter 에선 기본 ``%matplotlib inline`` 이 GUI 를 지원하지 않으므로
      셀 상단에 ``%matplotlib qt`` 또는 ``%matplotlib tk`` 를 먼저 실행해야
      별도 창이 뜬다.
    """
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    t_tap_auto = float(tap_info_auto["t_tap"])
    if initial_t_tap is None:
        initial_t_tap = t_tap_auto
    initial_idx = int(round(float(initial_t_tap) * float(quantize_hz)))
    initial_t_tap_q = initial_idx / float(quantize_hz)

    side = tap_info_auto["side"]
    onset_idx = tap_info_auto["onset_idx"]
    peak_idx = tap_info_auto["peak_idx"]
    peak_val = tap_info_auto["peak_value"]

    grid_step = 1.0 / float(quantize_hz)
    t_min = float(force_time[0])
    t_max = float(force_time[-1])
    # 1AB start = t_tap + 1*bpm_duration. Allow t_tap < 0 so 1AB can
    # be pulled left, but not past trial t=0.
    if bpm_duration is not None:
        t_tap_lo = -float(bpm_duration)
        t_tap_lo = int(round(t_tap_lo * float(quantize_hz))) / float(quantize_hz)
    else:
        t_tap_lo = t_min
    if initial_t_tap_q < t_tap_lo:
        initial_t_tap_q = t_tap_lo
    state = {"t_tap": initial_t_tap_q}

    fig, ax = plt.subplots(figsize=(13.0, 5.5))
    if window_title:
        try:
            fig.canvas.manager.set_window_title(window_title)
        except Exception:
            pass

    # ── 기본 신호 / 검출 시각화 (저장용 plot 과 동일 톤) ────────
    ax.plot(force_time, norm3, color="#1f77b4", lw=0.7, alpha=0.7,
            label="‖F3‖ (left)")
    ax.plot(force_time, norm4, color="#d62728", lw=0.7, alpha=0.7,
            label="‖F4‖ (right)")

    if len(tap_info_auto["peaks3"]):
        ax.plot(force_time[tap_info_auto["peaks3"]],
                norm3[tap_info_auto["peaks3"]],
                "x", color="#1f77b4", ms=5, alpha=0.5)
    if len(tap_info_auto["peaks4"]):
        ax.plot(force_time[tap_info_auto["peaks4"]],
                norm4[tap_info_auto["peaks4"]],
                "x", color="#d62728", ms=5, alpha=0.5)

    chosen_signal = norm3 if side == "f3" else norm4
    chosen_color = "#1f77b4" if side == "f3" else "#d62728"
    ax.plot(force_time[onset_idx], chosen_signal[onset_idx],
            "o", mfc="none", mec=chosen_color, ms=12, mew=2.0,
            label="auto onset")
    ax.plot(force_time[peak_idx], chosen_signal[peak_idx],
            "*", color=chosen_color, ms=10, alpha=0.8,
            label=f"peak ({peak_val:.1f}N)")

    ax.axhline(onset_thr_n, color="gray", ls="--", lw=0.7,
               label=f"onset_thr={onset_thr_n}N")

    # 자동 검출 reference (회색 점선) + 사용자 선택 (보라 실선).
    ax.axvline(t_tap_auto, color="gray", ls=":", lw=1.0, alpha=0.8,
               label=f"auto t_tap = {t_tap_auto:.2f}s")
    sel_vline = ax.axvline(state["t_tap"], color="purple", lw=2.0, alpha=0.9)

    # t=0 가이드 + 음수 구간이 보이도록 xlim 을 t_tap_lo 까지 확장.
    ax.axvline(0.0, color="k", ls="-", lw=0.6, alpha=0.25, zorder=0)
    x_pad = max(0.3, 0.02 * max(t_max - t_tap_lo, 1.0))
    ax.set_xlim(t_tap_lo - x_pad, t_max)

    y_max_val = float(max(np.nanmax(norm3), np.nanmax(norm4)))
    ax.set_ylim(top=y_max_val * 1.15)
    y_label_pos = y_max_val * 1.08

    # phase suffix → 색 매핑 (저장용 plot 과 동일 규칙).
    phase_colors: dict[str, tuple] = {}
    if seg_labels:
        cmap = plt.get_cmap("tab10")
        for label in seg_labels:
            phase = re.sub(r"^\d+", "", str(label))
            if phase and phase not in phase_colors:
                phase_colors[phase] = cmap(len(phase_colors) % 10)

    seg_artists = {"lines": [], "texts": []}

    def _redraw_segments(t_tap):
        # 이전 segment artifacts 제거 → 새 위치로 다시 그림.
        for a in seg_artists["lines"]:
            a.remove()
        for a in seg_artists["texts"]:
            a.remove()
        seg_artists["lines"].clear()
        seg_artists["texts"].clear()

        if bpm_duration is None or not seg_labels:
            return

        for k, label in enumerate(seg_labels):
            phase = re.sub(r"^\d+", "", str(label))
            color = phase_colors.get(phase, (0.3, 0.3, 0.3, 1.0))
            ps = t_tap + (1 + k) * float(bpm_duration)
            pe = ps + float(bpm_duration)
            if pe < t_min or ps > t_max:
                continue
            line = ax.axvline(ps, color=color, ls=":", lw=0.9, alpha=0.85)
            txt = ax.text((ps + pe) / 2.0, y_label_pos, str(label),
                          ha="center", va="bottom", fontsize=7,
                          color=color, alpha=0.95)
            seg_artists["lines"].append(line)
            seg_artists["texts"].append(txt)

        ps_end = t_tap + (1 + len(seg_labels)) * float(bpm_duration)
        if t_min <= ps_end <= t_max:
            line = ax.axvline(ps_end, color="gray", ls=":", lw=0.6, alpha=0.6)
            seg_artists["lines"].append(line)

    def _set_title(t_tap):
        diff = t_tap - t_tap_auto
        extra = ""
        if bpm_duration is not None:
            t_ab0 = t_tap + float(bpm_duration)
            extra = (f"   1AB start = {t_ab0:.2f}s"
                     f"  (floor 0.00s,  t_tap lo = {t_tap_lo:.2f}s)")
        ax.set_title(
            f"[MANUAL TAP]  Left-click: set t_tap (snap {grid_step:.2f}s)   "
            f"←/→: ±{grid_step:.2f}s   Shift+←/→: ±{10 * grid_step:.2f}s   "
            f"r: reset   Enter / close window: confirm\n"
            f"selected t_tap = {t_tap:.2f}s   "
            f"(auto = {t_tap_auto:.2f}s,  diff = {diff:+.2f}s)"
            f"{extra}"
        )

    def _apply_t_tap(t_new):
        # 1AB 시작 ≥ 0 이 되는 범위로 clip → 그리드 양자화 → 시각 업데이트.
        t_clipped = max(t_tap_lo, min(t_max, float(t_new)))
        idx = int(round(t_clipped * float(quantize_hz)))
        t_q = idx / float(quantize_hz)
        if t_q < t_tap_lo:
            t_q = t_tap_lo
        state["t_tap"] = t_q
        sel_vline.set_xdata([t_q, t_q])
        _redraw_segments(t_q)
        _set_title(t_q)
        fig.canvas.draw_idle()

    def on_click(event):
        if event.inaxes != ax or event.xdata is None:
            return
        if event.button != 1:
            return
        _apply_t_tap(float(event.xdata))

    def on_key(event):
        k = event.key
        if k in ("enter", " "):
            plt.close(fig)
        elif k == "r":
            _apply_t_tap(t_tap_auto)
        elif k == "left":
            _apply_t_tap(state["t_tap"] - grid_step)
        elif k == "right":
            _apply_t_tap(state["t_tap"] + grid_step)
        elif k == "shift+left":
            _apply_t_tap(state["t_tap"] - 10 * grid_step)
        elif k == "shift+right":
            _apply_t_tap(state["t_tap"] + 10 * grid_step)

    fig.canvas.mpl_connect("button_press_event", on_click)
    fig.canvas.mpl_connect("key_press_event", on_key)

    _redraw_segments(state["t_tap"])
    _set_title(state["t_tap"])
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("‖F‖ (N)")

    main_legend = ax.legend(loc="upper right", fontsize=8)
    if phase_colors:
        phase_handles = [Line2D([0], [0], color=c, ls=":", lw=1.5, label=p)
                         for p, c in phase_colors.items()]
        ax.add_artist(main_legend)
        ax.legend(handles=phase_handles, loc="upper left", fontsize=8,
                  title="Phases")
    ax.grid(False)
    fig.tight_layout()

    # ── 창이 닫힐 때까지 대기 (반드시 blocking 이어야 함) ─────────
    # 일반 python 스크립트: ``plt.show(block=True)`` 가 mainloop 를 돌려 차단.
    # Jupyter (``%matplotlib tk`` / ``qt``): 매직이 interactive mode 를 켜므로
    # 기본 ``plt.show()`` 는 즉시 반환된다 → 사용자가 클릭하기도 전에
    # 초깃값이 반환되어 TRC/MOT 생성이 시작되는 버그의 원인.  이 경우엔
    # 이 figure 가 살아 있는 동안 GUI 이벤트 루프를 짧게 반복 실행하며
    # 대기한다 (Enter → ``plt.close`` / 창 X → destroy 모두 루프 종료).
    if plt.isinteractive():
        plt.show(block=False)
        while plt.fignum_exists(fig.number):
            plt.pause(0.05)
    else:
        plt.show(block=True)

    return state["t_tap"]


# ── 매뉴얼 윈도우 분할 파이프라인 ─────────────────────────────────

def process_condition_manual_window(rp, cp, c3d_path, rigid_csv_path):      # TODO: split_lifting_trial2section_manual_window.py 구현 후 이주
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
    _assert_canonical_force_keys(forces, c3d_path)
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

    print(f"    [Done] {written} sections → {cp.cond_dir}")


def process_condition_bpm_window(rp, cp, c3d_path, rigid_csv_path,
                                 t_tap_offset=0.0, interactive_tap=False):
    """BPM 기반 자동 윈도우 세그먼트 분할 → TRC/MOT 출력.

    manual_window 와 차이점은 단 하나 — cycle 시작점을 결정하는 방식.

    - manual_window: 매 cycle 마다 양손 |Fy| 합 threshold 로 contact_start 검출.
    - bpm_window:    메트로놈 첫 박자에 한쪽 로드셀(f3 또는 f4)을 친 단발성
      tap 의 onset 1점만 검출 → 0.01 s 그리드로 양자화 → 그 시점을 anchor
      삼아 모든 segment 시각을 BPM 균등 스케줄로 산정.

    윈도우 시각:
        total_idx = (cyc_i - 1) * n_phases + lift_j        (0 ≤ total_idx < n_cycles*n_phases)
        ps = t_tap + (1 + total_idx) * BPM_DURATION
        pe = ps + BPM_DURATION

    이외 단계(C3D/RigidBody 로드, 마커·ExtLoad 필터링, error_log 스킵,
    build_tree, TRC/MOT 출력) 는 manual_window 와 동일.

    Parameters
    ----------
    rp : _path.ResultPaths
    cp : _path.ConditionPaths
    c3d_path : str
    rigid_csv_path : str
    t_tap_offset : float, default 0.0
        검출된 ``t_tap`` 에 더하는 수동 보정 (초). 음수면 anchor 를 앞으로
        당김(=윈도우 전체가 일찍 시작), 양수면 뒤로 미룸. 보정값도
        ``ONSET_QUANTIZE_HZ`` 그리드(기본 100 Hz, 0.01 s)로 재양자화된다.
    interactive_tap : bool, default False
        True 면 자동 검출 직후 matplotlib GUI 창을 띄워 사용자가 직접
        ``t_tap`` 위치를 마우스 클릭으로 선택하도록 한다. 창이 열릴 때
        초기 선택값은 ``t_tap_raw + t_tap_offset`` (그리드 양자화)이며,
        창을 닫으면 그 시점에서의 선택값이 anchor 로 채택된다.
        ``t_tap_offset`` 인자는 보조 초기값 역할만 하고, 최종 effective
        offset 은 ``selected_t_tap - t_tap_raw`` 로 다시 계산된다.
    """
    seg_cfg = rp.segmentation
    if seg_cfg.get("method") != "bpm_window":
        raise ValueError(
            f"bpm_window 는 method='bpm_window' 에서 호출되어야 합니다. "
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
    tap_height = float(seg_cfg["TAP_HEIGHT_N"])
    tap_prom = float(seg_cfg["TAP_PROMINENCE_N"])
    tap_min_dist = float(seg_cfg["TAP_MIN_DISTANCE_SEC"])
    onset_thr = float(seg_cfg["ONSET_THRESHOLD_N"])
    quantize_hz = float(seg_cfg.get("ONSET_QUANTIZE_HZ", 100.0))
    error_segments = _normalize_errorlog_scetions(cp.error_log)

    print(f"    [bpm_window] BPM={bpm} window={seg_duration}s "
          f"apps={rp.apps}")

    # ── 1) 데이터 로드 (회전 없음 — Motive Y-up 가정) ──────────
    markers = _io.read_c3d_markers(c3d_path, rotations=None)
    forces = _io.read_c3d_force_platforms(c3d_path, rotations=None)
    _assert_canonical_force_keys(forces, c3d_path)
    rigid = _io.read_rigid_body_csv(
        rigid_csv_path, skiprow_num=_lcfg.RIGID_BODY_SKIPROWS,
    )

    marker_time = markers["time"]
    force_time = forces["time"]
    if len(marker_time) < 2 or len(force_time) < 2:
        print("    [SKIP] insufficient frames in C3D.")
        return
    marker_rate = 1.0 / float(np.mean(np.diff(marker_time)))    # 100 Hz
    force_rate = 1.0 / float(np.mean(np.diff(force_time)))      # 1000 Hz
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
                  f"bpm_window. Skipping ExtLoad.")
            continue
        for key in list(ext.keys()):
            if key == "time":
                continue
            ext[key] = _io.butterworth_filter(
                ext[key], fs_hz=force_rate,
                cutoff_hz=_lcfg.FORCE_FILTER_HZ, order=_lcfg.FILTER_ORDER,
            )
        ext_by_app[app] = ext

    # ── 4) tap onset 검출 (raw f3/f4, 합력 norm) ────────────────
    # NOTE: 검출은 raw(미필터링) force 채널의 ‖F‖ = √(Fx²+Fy²+Fz²) 사용.
    #       manual_window 는 양손 |Fy| 합을 쓰는 반면, bpm_window 는 한쪽 채널의
    #       3축 합력 norm 으로 더 빠른 쪽을 채택한다.
    if "f3" not in forces or "f4" not in forces:
        raise KeyError(
            "bpm_window requires hand load-cell plates 'f3', 'f4' in C3D."
        )
    norm3 = _force_plate_norm(forces, 3)
    norm4 = _force_plate_norm(forces, 4)
    tap_info = _detect_first_tap_onset(
        force_time, norm3, norm4,
        height_n=tap_height, prominence_n=tap_prom,
        min_dist_sec=tap_min_dist,
        onset_thr_n=onset_thr, quantize_hz=quantize_hz,
    )

    # ── 4-1) tap anchor 결정 (인터랙티브 선택 OR offset 보정) ───
    # interactive_tap=True 면 GUI 창에서 사용자가 직접 클릭으로 선택.
    # 그렇지 않으면 t_tap_offset 만 적용해 그리드에 재양자화.
    # 양쪽 경로 모두 동일한 tap_info dict (t_tap / t_tap_raw / t_tap_offset)
    # 형태로 통일되어 이후 plot 및 segment 분할에서 분기 없이 사용된다.
    t_tap_raw = tap_info["t_tap"]
    offset = float(t_tap_offset)

    # section 정보는 인터랙티브 창에 segment 경계를 그릴 때도 필요하므로
    # build_tree 보다 먼저 계산해둔다 (메서드 호출만으로 사이드이펙트 없음).
    section_segs = cp.section_segments()         # {"AB":[...], "BC":[...], "CA":[...]}
    section_order = list(section_segs.keys())
    n_phases = len(section_order)
    seg_labels = cp.all_sections()               # ["1AB","1BC","1CA","2AB",…]

    if interactive_tap:
        initial_idx = int(round((t_tap_raw + offset) * quantize_hz))
        initial_t_tap = initial_idx / quantize_hz
        win_title = (f"[manual tap] {os.path.basename(c3d_path)}  "
                     f"cond={cp.cond}")
        print(f"    [interactive] auto t_tap_raw={t_tap_raw:.2f}s "
              f"(initial selection={initial_t_tap:.2f}s) "
              f"— opening matplotlib window…")
        t_tap = _select_t_tap_interactive(
            force_time, norm3, norm4, tap_info,
            onset_thr_n=onset_thr,
            bpm_duration=seg_duration,
            seg_labels=seg_labels,
            quantize_hz=quantize_hz,
            initial_t_tap=initial_t_tap,
            window_title=win_title,
        )
        effective_offset = round(t_tap - t_tap_raw,
                                 int(round(np.log10(quantize_hz))))
        tap_info["t_tap_raw"] = t_tap_raw
        tap_info["t_tap"] = t_tap
        tap_info["t_tap_offset"] = effective_offset
        print(f"    [interactive] selected t_tap={t_tap:.2f}s  "
              f"(auto={t_tap_raw:.2f}s, effective offset "
              f"{effective_offset:+.2f}s)  "
              f"→ 재실행 시 동일 결과: --t-tap-offset "
              f"{effective_offset:+.2f}")
    else:
        t_tap_idx = int(round((t_tap_raw + offset) * quantize_hz))
        t_tap = t_tap_idx / quantize_hz
        tap_info["t_tap_raw"] = t_tap_raw
        tap_info["t_tap"] = t_tap
        tap_info["t_tap_offset"] = offset

        if offset != 0.0:
            print(f"    tap onset: side={tap_info['side']} "
                  f"t_tap_raw={t_tap_raw:.2f}s offset={offset:+.2f}s "
                  f"→ t_tap={t_tap:.2f}s "
                  f"peak={tap_info['peak_value']:.1f}N "
                  f"(peak_idx={tap_info['peak_idx']})")
        else:
            print(f"    tap onset: side={tap_info['side']} t_tap={t_tap:.2f}s "
                  f"peak={tap_info['peak_value']:.1f}N "
                  f"(peak_idx={tap_info['peak_idx']})")

    # ── 5) 디렉토리 트리 + 디버그 플롯 ──────────────────────────
    cp.build_tree()

    debug_png = os.path.join(cp.cond_dir, "tap_onset_check.png")
    try:
        _plot_tap_onset_check(
            debug_png, force_time, norm3, norm4,
            tap_info, onset_thr_n=onset_thr,
            bpm_duration=seg_duration, seg_labels=seg_labels,
        )
        print(f"    debug plot: {debug_png}")
    except Exception as exc:
        print(f"    [WARN] debug plot failed: {exc}")

    # ── 6) 세그먼트 분할 + 파일 출력 (tap+tempo 균등 스케줄) ────
    # 데이터 길이는 SUB_Info.cycles 만큼 모든 segment 가 들어가도록
    # 사전 검수된 trial 만 처리하므로 out-of-range 체크는 두지 않는다.
    written = 0
    for cyc_i in range(1, cp.n_cycles + 1):
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

            total_idx = (cyc_i - 1) * n_phases + lift_j
            ps = t_tap + (1 + total_idx) * seg_duration
            pe = ps + seg_duration

            mark_seg = _slice_markers_by_time(markers, ps, pe)
            if len(mark_seg["time"]) == 0:
                print(f"      [WARN] {seg_label}  empty marker slice "
                      f"({ps:.2f}~{pe:.2f}s) — 데이터 길이 / tap 검출 확인")
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

    print(f"    [Done] {written} sections → {cp.cond_dir}")


_METHOD_DISPATCH = {                                        # TODO: config 파일로 이주 필요? 아니면 그냥 두어도 괜찮을 듯
    "findpeaks":     process_condition_findpeaks,
    "manual_window": process_condition_manual_window,
    "bpm_window":    process_condition_bpm_window,
}

_IMPLEMENTED_APPS = {"MeasuredEHF", "HeavyHand", "AddBox"}  # TODO: config 파일로 이주 필요? 아니면 그냥 두어도 괜찮을 듯


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
    sections = cp.all_sections()
    section_segs = cp.section_segments()
    n_trc = len(sections)
    n_mot = n_trc * len(apps_ok)

    print(f"    Planned outputs: {n_trc} TRC + {n_mot} MOT "
          f"({len(apps_ok)}/{len(rp.apps)} APPs implemented)")
    for section, labels in section_segs.items():
        print(f"      section {section}: {labels}")

    if sections:
        ex = sections[0]
        print(f"    Example paths for section={ex!r}:")
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


def _dry_run_tap_onset_plot(rp, cp, c3d_path, t_tap_offset=0.0,
                            interactive_tap=False):
    """dry-run 전용: ``bpm_window`` 의 ``tap_onset_check.png`` 만 생성.

    실제 segment 분할 / TRC·MOT 출력은 수행하지 않는다. tap 검출 위치와
    BPM 윈도우 배치를 미리 시각적으로 검증해 ``t_tap_offset`` 을 조정할
    수 있게 돕는 용도. ``bpm_window`` 가 아닌 method 에선 아무 것도 안 함.

    ``interactive_tap=True`` 면 자동 검출 결과를 보여주는 matplotlib GUI
    창이 먼저 뜨고, 사용자가 클릭으로 선택한 ``t_tap`` 이 PNG 에 반영되어
    저장된다. (dry-run 이므로 TRC/MOT 은 여전히 작성되지 않는다.)

    Notes
    -----
    - C3D 의 force platform 만 읽으므로 RigidBody CSV 는 필요 없음.
    - ``cp.build_tree()`` 는 호출하지 않음 — PNG 가 들어갈 ``cond_dir`` 만
      ``_plot_tap_onset_check`` 내부의 ``os.makedirs`` 로 생성됨.
    - 검출/플롯이 실패해도 dry-run 자체는 중단하지 않음.
    """
    if rp.segmentation.get("method") != "bpm_window":
        return
    if not c3d_path or not os.path.isfile(c3d_path):
        return

    seg_cfg = rp.segmentation
    try:
        bpm = _extract_bpm_from_condition(cp.cond)
    except ValueError as exc:
        print(f"    [dry-run plot] BPM extract failed: {exc}")
        return

    bpm_duration_map = seg_cfg.get("BPM_DURATION", {})
    if bpm not in bpm_duration_map:
        print(f"    [dry-run plot] BPM {bpm} not in BPM_DURATION map")
        return

    seg_duration = float(bpm_duration_map[bpm])
    tap_height = float(seg_cfg["TAP_HEIGHT_N"])
    tap_prom = float(seg_cfg["TAP_PROMINENCE_N"])
    tap_min_dist = float(seg_cfg["TAP_MIN_DISTANCE_SEC"])
    onset_thr = float(seg_cfg["ONSET_THRESHOLD_N"])
    quantize_hz = float(seg_cfg.get("ONSET_QUANTIZE_HZ", 100.0))

    try:
        forces = _io.read_c3d_force_platforms(c3d_path, rotations=None)
        _assert_canonical_force_keys(forces, c3d_path)
        force_time = forces["time"]
        if len(force_time) < 2:
            print("    [dry-run plot] insufficient frames in C3D.")
            return
        if "f3" not in forces or "f4" not in forces:
            print("    [dry-run plot] hand load-cells 'f3'/'f4' missing.")
            return

        norm3 = _force_plate_norm(forces, 3)
        norm4 = _force_plate_norm(forces, 4)
        tap_info = _detect_first_tap_onset(
            force_time, norm3, norm4,
            height_n=tap_height, prominence_n=tap_prom,
            min_dist_sec=tap_min_dist,
            onset_thr_n=onset_thr, quantize_hz=quantize_hz,
        )

        # tap anchor 결정 — 실제 실행 경로(process_condition_bpm_window) 와
        # 동일한 분기 로직을 유지해 dry-run 으로 확인한 결과가 그대로 실행에
        # 재현될 수 있게 한다.
        t_tap_raw = tap_info["t_tap"]
        offset = float(t_tap_offset)
        seg_labels = cp.all_sections()

        if interactive_tap:
            initial_idx = int(round((t_tap_raw + offset) * quantize_hz))
            initial_t_tap = initial_idx / quantize_hz
            win_title = (f"[manual tap / dry-run] "
                         f"{os.path.basename(c3d_path)}  cond={cp.cond}")
            print(f"    [interactive/dry-run] auto t_tap_raw={t_tap_raw:.2f}s "
                  f"(initial={initial_t_tap:.2f}s) — opening matplotlib "
                  f"window…")
            t_tap = _select_t_tap_interactive(
                force_time, norm3, norm4, tap_info,
                onset_thr_n=onset_thr,
                bpm_duration=seg_duration,
                seg_labels=seg_labels,
                quantize_hz=quantize_hz,
                initial_t_tap=initial_t_tap,
                window_title=win_title,
            )
            effective_offset = round(t_tap - t_tap_raw,
                                     int(round(np.log10(quantize_hz))))
            tap_info["t_tap_raw"] = t_tap_raw
            tap_info["t_tap"] = t_tap
            tap_info["t_tap_offset"] = effective_offset
            print(f"    [interactive/dry-run] selected t_tap={t_tap:.2f}s  "
                  f"(auto={t_tap_raw:.2f}s, effective offset "
                  f"{effective_offset:+.2f}s)  "
                  f"→ 실제 실행: --t-tap-offset {effective_offset:+.2f}")
        else:
            t_tap_idx = int(round((t_tap_raw + offset) * quantize_hz))
            t_tap = t_tap_idx / quantize_hz
            tap_info["t_tap_raw"] = t_tap_raw
            tap_info["t_tap"] = t_tap
            tap_info["t_tap_offset"] = offset

            if offset != 0.0:
                print(f"    tap onset: side={tap_info['side']} "
                      f"t_tap_raw={t_tap_raw:.2f}s offset={offset:+.2f}s "
                      f"→ t_tap={t_tap:.2f}s "
                      f"peak={tap_info['peak_value']:.1f}N "
                      f"(peak_idx={tap_info['peak_idx']})")
            else:
                print(f"    tap onset: side={tap_info['side']} "
                      f"t_tap={t_tap:.2f}s "
                      f"peak={tap_info['peak_value']:.1f}N "
                      f"(peak_idx={tap_info['peak_idx']})")

        debug_png = os.path.join(cp.cond_dir, "tap_onset_check.png")
        _plot_tap_onset_check(
            debug_png, force_time, norm3, norm4,
            tap_info, onset_thr_n=onset_thr,
            bpm_duration=seg_duration, seg_labels=seg_labels,
        )
        print(f"    [dry-run] debug plot: {debug_png}")
    except Exception as exc:
        print(f"    [WARN] dry-run debug plot failed: {exc}")


# ── 피험자 단위 처리 ─────────────────────────────────────────────

_T_TAP_OFFSET_DEFAULT_KEY = "_default"


def _resolve_t_tap_offset(t_tap_offset, cond_key):
    """``t_tap_offset`` 인자를 condition 별 scalar 로 정규화.

    Accepted forms
    --------------
    - None                              → 0.0
    - float / int                       → 모든 condition 에 동일 적용
    - dict[str, float]                  → condition key 별 lookup
        - ``cond_key`` 가 dict 에 있으면 그 값 사용
        - 없으면 ``"_default"`` key 값 사용
        - 그것도 없으면 0.0 (정보용 print)

    Examples
    --------
    >>> _resolve_t_tap_offset(-2.3, "7kg_10bpm")
    -2.3
    >>> _resolve_t_tap_offset({"7kg_10bpm": -2.3, "7kg_16bpm": -1.5}, "7kg_10bpm")
    -2.3
    >>> _resolve_t_tap_offset({"_default": -2.0, "7kg_16bpm": -1.5}, "7kg_10bpm")
    -2.0
    """
    if t_tap_offset is None:
        return 0.0
    if isinstance(t_tap_offset, dict):
        if cond_key in t_tap_offset:
            return float(t_tap_offset[cond_key])
        if _T_TAP_OFFSET_DEFAULT_KEY in t_tap_offset:
            return float(t_tap_offset[_T_TAP_OFFSET_DEFAULT_KEY])
        print(f"    [INFO] t_tap_offset dict has no entry for "
              f"{cond_key!r} and no {_T_TAP_OFFSET_DEFAULT_KEY!r}; "
              f"using 0.0")
        return 0.0
    return float(t_tap_offset)


def _format_t_tap_offset_header(t_tap_offset):
    """``process_subject`` 헤더 출력용 문자열. dict 면 보기 좋게 정렬."""
    if isinstance(t_tap_offset, dict):
        items = ", ".join(
            f"{k}={float(v):+.2f}" for k, v in t_tap_offset.items()
        )
        return f"{{{items}}}  (per-condition)"
    return f"{float(t_tap_offset):+.2f}s  (manual)"


def process_subject(namecode, dry_run=False, t_tap_offset=0.0,
                    interactive_tap=False):
    """한 명의 피험자에 대해 전체 파이프라인 수행.

    Parameters
    ----------
    namecode : str
        피험자 namecode (예: ``"260306_KTH"``).
    dry_run : bool, default False
        True 면 파일 탐색·계획 출력만 수행하고 실제 변환은 건너뜀.
    t_tap_offset : float or dict[str, float], default 0.0
        ``bpm_window`` 전용. 자동 검출된 ``t_tap`` 에 더하는 수동 보정(초).
        음수면 윈도우를 앞으로 당김(=일찍 시작), 양수면 뒤로 미룸.

        - ``float`` 로 주면 모든 condition 에 동일 적용.
        - ``dict[cond_key, offset]`` 로 주면 condition 별로 다른 값 적용.
          dict 에 없는 cond_key 는 ``"_default"`` key 값(없으면 0.0)으로
          폴백한다.

        다른 method (manual_window/findpeaks)에서는 무시.
    interactive_tap : bool, default False
        ``bpm_window`` 전용. True 면 자동 검출 후 matplotlib GUI 창에서
        ``t_tap`` 을 마우스 클릭으로 직접 선택할 수 있게 한다.
        ``t_tap_offset`` 가 함께 주어지면 (scalar 또는 dict 모두) 해당
        condition 의 값이 창의 초기 선택 위치로 사용된다. ``dry_run``
        모드에서도 동일하게 GUI 가 뜨며, 사용자가 고른 위치로
        ``tap_onset_check.png`` 만 저장하고 TRC/MOT 은 생성하지 않는다.

    Examples
    --------
    >>> process_subject("260512_KCH", t_tap_offset=-2.3)
    >>> process_subject(
    ...     "260512_KCH",
    ...     t_tap_offset={"7kg_10bpm": -2.30, "7kg_16bpm": -1.50},
    ... )
    >>> process_subject(
    ...     "260512_KCH",
    ...     t_tap_offset={"_default": -2.0, "7kg_16bpm": -1.50},
    ... )
    """
    rp = _path.ResultPaths(namecode)

    print(f"\n{'='*60}")
    print(f"[{namecode}]  {rp.sub_label}  protocol={rp.protocol}  "
          f"method={rp.segmentation['method']}")
    print(f"  C3D dir : {rp.c3d_dir}")
    print(f"  Rigid dir: {rp.rigid_dir}")
    print(f"  Output  : {rp.sub_dir}")
    print(f"  APPs    : {rp.apps}")
    if rp.segmentation.get("method") == "bpm_window":
        # dict / scalar 양쪽 모두 동일 포맷터로 헤더 출력.
        if isinstance(t_tap_offset, dict) or t_tap_offset != 0.0:
            print(f"  t_tap_offset : {_format_t_tap_offset_header(t_tap_offset)}")

        # dict 모드: 등록된 cond_key 중 실존하지 않는 것 검출 → 사용자 경고.
        # (오타 / 사라진 condition 을 조용히 무시하지 않도록.)
        if isinstance(t_tap_offset, dict):
            available_conds = set(rp.conditions.keys())
            invalid_keys = [
                k for k in t_tap_offset.keys()
                if k != _T_TAP_OFFSET_DEFAULT_KEY and k not in available_conds
            ]
            if invalid_keys:
                print(f"  [WARN] t_tap_offset has keys not in this "
                      f"subject's conditions: {invalid_keys}")
                print(f"         available conditions: "
                      f"{sorted(available_conds)}")

        if interactive_tap:
            print(f"  interactive_tap : ON  (GUI window for t_tap selection)")
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

    static_c3d_path = _io.find_static_c3d_path(rp.c3d_dir)
    static_trc_out = rp.static_trc_path()
    static_names = ", ".join(_path.STATIC_C3D_FILENAMES)

    if dry_run:
        if static_c3d_path:
            print(f"  [static]  OK  {os.path.basename(static_c3d_path)}  →  {static_trc_out}")
        else:
            print(f"  [ERROR] Static calibration C3D missing: "
                  f"expected one of [{static_names}] under {rp.c3d_dir}")
    else:
        if static_c3d_path:
            try:
                _io.export_static_c3d_to_trc(
                    static_c3d_path,
                    static_trc_out,
                    rotations=None,
                    marker_cutoff_hz=_lcfg.MARKER_FILTER_HZ,
                    filter_order=_lcfg.FILTER_ORDER,
                )
                print(f"  [static]  Wrote {static_trc_out}")
            except Exception as exc:
                print(f"  [ERROR] Static TRC export failed ({static_c3d_path}): {exc}")
        else:
            print(f"  [ERROR] Static calibration C3D missing: "
                  f"expected one of [{static_names}] under {rp.c3d_dir}")

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

        # condition 별 offset 해석 (scalar 면 그대로, dict 면 lookup).
        cond_offset = _resolve_t_tap_offset(t_tap_offset, cond_key)
        if (rp.segmentation.get("method") == "bpm_window"
                and isinstance(t_tap_offset, dict)
                and cond_offset != 0.0):
            print(f"    [t_tap_offset] {cond_offset:+.2f}s  "
                  f"(per-condition override)")

        if dry_run:
            _report_dry_run_plan(rp, cp, cond_val, c3d_path, rigid_csv_path)
            # bpm_window 인 경우 tap_onset_check.png 도 미리 생성해
            # t_tap_offset 튜닝을 시각적으로 확인할 수 있게 한다.
            # interactive_tap=True 면 GUI 창에서 직접 선택 가능.
            if c3d_path is not None:
                _dry_run_tap_onset_plot(
                    rp, cp, c3d_path,
                    t_tap_offset=cond_offset,
                    interactive_tap=interactive_tap,
                )
            continue
        if not c3d_path:
            print(f"    [SKIP] No C3D file found for '{cond_key}'")
            continue
        if not rigid_csv_path:
            print(f"    [SKIP] No RigidBody CSV found for '{cond_key}'")
            continue

        # bpm_window 만 t_tap_offset / interactive_tap 을 사용.
        # 다른 method 시그니처는 변경 없음.
        try:
            if rp.segmentation.get("method") == "bpm_window":
                pipeline_fn(rp, cp, c3d_path, rigid_csv_path,
                            t_tap_offset=cond_offset,
                            interactive_tap=interactive_tap)
            else:
                pipeline_fn(rp, cp, c3d_path, rigid_csv_path)
        except _io.UnsupportedForceSourceCountError as exc:
            _print_force_source_warning_banner(exc, namecode, cond_key)
            sys.exit(1)


# ── CLI 엔트리포인트 ─────────────────────────────────────────────

def _parse_cli_t_tap_offset(tokens):
    """``--t-tap-offset`` CLI 토큰들을 scalar 또는 dict 으로 변환.

    Token 규칙
    ----------
    - ``=`` 가 없는 토큰: 단일 scalar (예: ``-2.3``)
    - ``cond_key=value``: condition 별 override (예: ``7kg_10bpm=-2.3``)

    Examples
    --------
    >>> _parse_cli_t_tap_offset(["-2.3"])
    -2.3
    >>> _parse_cli_t_tap_offset(["7kg_10bpm=-2.3", "7kg_16bpm=-1.5"])
    {'7kg_10bpm': -2.3, '7kg_16bpm': -1.5}
    >>> _parse_cli_t_tap_offset(["-2.0", "7kg_16bpm=-1.5"])
    {'_default': -2.0, '7kg_16bpm': -1.5}
    """
    if not tokens:
        return 0.0
    has_keyed = any("=" in t for t in tokens)
    if not has_keyed:
        if len(tokens) > 1:
            raise argparse.ArgumentTypeError(
                f"--t-tap-offset 에 scalar 토큰은 1개만 허용됩니다 "
                f"(받은 값: {tokens}). condition 별 override 는 "
                f"'cond_key=value' 형식으로 주세요."
            )
        return float(tokens[0])

    result = {}
    for t in tokens:
        if "=" in t:
            k, v = t.split("=", 1)
            k = k.strip()
            if not k:
                raise argparse.ArgumentTypeError(
                    f"--t-tap-offset: 빈 cond_key (token={t!r})"
                )
            try:
                result[k] = float(v)
            except ValueError:
                raise argparse.ArgumentTypeError(
                    f"--t-tap-offset: 잘못된 숫자 (token={t!r})"
                )
        else:
            if _T_TAP_OFFSET_DEFAULT_KEY in result:
                raise argparse.ArgumentTypeError(
                    f"--t-tap-offset 에 default scalar 가 두 번 이상 "
                    f"지정되었습니다 (token={t!r})."
                )
            result[_T_TAP_OFFSET_DEFAULT_KEY] = float(t)
    return result


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
    parser.add_argument(
        "--t-tap-offset", nargs="+", default=None, metavar="OFFSET",
        help="(bpm_window 전용) 검출된 t_tap 에 더할 수동 보정(초). "
             "음수면 윈도우를 앞으로 당김. 기본 0.\n"
             "사용 방식:\n"
             "  --t-tap-offset -2.3                              # 모든 cond\n"
             "  --t-tap-offset 7kg_10bpm=-2.3 7kg_16bpm=-1.5     # cond별\n"
             "  --t-tap-offset -2.0 7kg_16bpm=-1.5               # default + override",
    )
    parser.add_argument(
        "--interactive-tap", action="store_true",
        help="(bpm_window 전용) tap event 를 matplotlib GUI 창에서 "
             "마우스 클릭으로 직접 선택. --t-tap-offset 가 함께 주어지면 "
             "각 condition 별 값이 창의 초기 선택 위치로 사용된다. "
             "--dry-run 과도 결합 가능 (선택 결과로 tap_onset_check.png 만 저장).",
    )
    args = parser.parse_args()

    try:
        t_tap_offset = _parse_cli_t_tap_offset(args.t_tap_offset)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

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
            process_subject(namecode, dry_run=args.dry_run,
                            t_tap_offset=t_tap_offset,
                            interactive_tap=args.interactive_tap)
        except NotImplementedError as e:
            print(f"    [NOT IMPLEMENTED] {e}")
        except Exception as e:
            print(f"    [ERROR] {namecode}: {e}")
            raise

    print(f"\n{'='*60}")
    print("Done.")


if __name__ == "__main__":
    main()
