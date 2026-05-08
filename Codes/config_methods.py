import os
import sys

import SUB_Info as _sub_info

NAMECODE_li = list(_sub_info.subjects.keys())
PROTOCOL_li = [
    _sub_info.subjects[namecode]["protocol"]
    for namecode in NAMECODE_li
]

PROTOCOL_Candidates = {
    "Symmetric": {
        "APPs": ["MeasuredEHF", "HeavyHand", "AddBox"],
        "segment_style": "UpDown",
        "segmentation": {
            "method": "findpeaks",
            "pair_threshold": 0.5, # 대칭 프로토콜 세그먼트 분할 임계값 (meter)
        },
    },
    "Asymmetric_Pilot": {
        "APPs": ["MeasuredEHF", "HeavyHand"],
        "segment_style": "UpDown",
        "segmentation": {
            "method": "findpeaks",
            "pair_threshold": 0.005, # 비대칭 프로토콜 세그먼트 분할 임계값 (meter)
        },
    },
    "Asymmetric": {
        "APPs": ["MeasuredEHF", "HeavyHand", "preRiCTO", "postRiCTO"],
        "result_root": "Asymmetric",
        "segment_style": "ABC",
        "segmentation": {
            "method": "bpm_window",                 # bpm_window: 메트로놈 첫 박자 tap onset 1회 검출 → BPM 균등 스케줄링
            "BPM_DURATION": {10: 6.0, 16: 3.75},    # 10bpm → 6.0초, 16bpm → 3.75초

            # ── manual_window 전용 (백업/디버그용으로 유지) ─────────
            # detect_signal: 양손 |Fy| 합 (f3·f4 Y축)
            "CONTACT_THRESHOLD_N": 5.0,             # N — 양손 |fy| 합이 이 이상이면 접촉
            "CONTACT_MIN_DUR_SEC": 0.5,             # s — 최소 접촉 지속시간
            "SKIP_FIRST_N": 1,                      # 첫 N개 리프팅은 동기화용으로 스킵
            "CYCLE_OFFSET_SEC": -1.5,               # 첫 번째 리프팅 시작점 검출용 (손 외력 threshold) 1.5초 전

            # ── bpm_window 전용 (현 디폴트) ────────────────────────
            # detect_signal: 한쪽 로드셀(f3 또는 f4)의 합력 norm ‖F‖ = √(Fx²+Fy²+Fz²)
            "TAP_PROMINENCE_N": 20.0,               # N — find_peaks prominence (잡음 대비 두드러짐)
            "TAP_HEIGHT_N": 30.0,                   # N — find_peaks height (tap 강도 하한)
            "TAP_MIN_DISTANCE_SEC": 0.2,            # s — 같은 채널 내 인접 피크 최소 간격
            "ONSET_THRESHOLD_N": 5.0,               # N — peak→onset 역추적 임계 (CONTACT_THRESHOLD_N 과 통일; 단 적용 신호는 ‖F‖)
            "ONSET_QUANTIZE_HZ": 100.0,             # Hz — onset 시간 양자화 그리드 (정수 인덱스 경유)
        },
    },
}

_SECTION_MAP = {
    "UpDown": [("Up", "U"), ("Down", "D")],
    "ABC":    [("AB", "AB"), ("BC", "BC"), ("CA", "CA")],
}


def section_info(style: str) -> list[tuple[str, str]]:
    """세그먼트 스타일에 따른 (디렉토리명, 라벨접두사) 튜플 목록.

    Returns
    -------
    list[tuple[str, str]]
        ``"UpDown"`` → ``[("Up", "U"), ("Down", "D")]``
        ``"ABC"``    → ``[("AB", "AB"), ("BC", "BC"), ("CA", "CA")]``
    """
    if style not in _SECTION_MAP:
        raise ValueError(f"Unknown segment_style: {style!r}")
    return list(_SECTION_MAP[style])


def section_labels(n_cycles: int, style: str) -> list[str]:
    """모든 섹션·사이클에 대한 세그먼트 레이블 (사이클 순 인터리브).

    Parameters
    ----------
    n_cycles : int
        해당 condition의 lifting cycle 수.
    style : str
        ``"UpDown"`` → ``["1U", "1D", "2U", "2D", ...]``
        ``"ABC"``    → ``["1AB", "1BC", "1CA", "2AB", "2BC", "2CA", ...]``
    """
    sections = section_info(style)
    labels = []
    for i in range(1, n_cycles + 1):
        for _, prefix in sections:
            labels.append(f"{i}{prefix}")
    return labels


def section_segment_labels(n_cycles: int, style: str) -> dict[str, list[str]]:
    """섹션별로 그룹화된 세그먼트 레이블 딕셔너리.

    Returns
    -------
    dict[str, list[str]]
        ``"UpDown"`` → ``{"Up": ["1U","2U",...], "Down": ["1D","2D",...]}``
        ``"ABC"``    → ``{"AB": ["1AB","2AB",...], "BC": [...], "CA": [...]}``
    """
    sections = section_info(style)
    return {
        dir_name: [f"{i}{prefix}" for i in range(1, n_cycles + 1)]
        for dir_name, prefix in sections
    }


