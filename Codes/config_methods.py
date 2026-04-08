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
            "method": "bpm_window",
            "BPM_DURATION": {10: 6.0, 16: 3.75},    # 10bpm → 6.0초, 16bpm → 3.75초
            "CONTACT_THRESHOLD_N": 5.0,             # N — 양손 |fy| 합이 이 이상이면 접촉
            "CONTACT_MIN_DUR_SEC": 0.5,             # s — 최소 접촉 지속시간
            "SKIP_FIRST_N": 1,                      # 첫 N개 리프팅은 동기화용으로 스킵
            "CYCLE_OFFSET_SEC": -1.5,               # 첫 번째 리프팅 시작점 검출용 (손 외력 threshold) 1.5초 전
        },
    },
}

_PHASE_MAP = {
    "UpDown": [("Up", "U"), ("Down", "D")],
    "ABC":    [("AB", "AB"), ("BC", "BC"), ("CA", "CA")],
}


def phase_info(style: str) -> list[tuple[str, str]]:
    """세그먼트 스타일에 따른 (디렉토리명, 라벨접두사) 튜플 목록.

    Returns
    -------
    list[tuple[str, str]]
        ``"UpDown"`` → ``[("Up", "U"), ("Down", "D")]``
        ``"ABC"``    → ``[("AB", "AB"), ("BC", "BC"), ("CA", "CA")]``
    """
    if style not in _PHASE_MAP:
        raise ValueError(f"Unknown segment_style: {style!r}")
    return list(_PHASE_MAP[style])


def segment_labels(n_cycles: int, style: str) -> list[str]:
    """모든 위상·사이클에 대한 세그먼트 레이블 (사이클 순 인터리브).

    Parameters
    ----------
    n_cycles : int
        해당 condition의 lifting cycle 수.
    style : str
        ``"UpDown"`` → ``["U1", "D1", "U2", "D2", ...]``
        ``"ABC"``    → ``["AB1", "BC1", "CA1", "AB2", "BC2", "CA2", ...]``
    """
    phases = phase_info(style)
    labels = []
    for i in range(1, n_cycles + 1):
        for _, prefix in phases:
            labels.append(f"{prefix}{i}")
    return labels


def phase_segment_labels(n_cycles: int, style: str) -> dict[str, list[str]]:
    """위상별로 그룹화된 세그먼트 레이블 딕셔너리.

    Returns
    -------
    dict[str, list[str]]
        ``"UpDown"`` → ``{"Up": ["U1","U2",...], "Down": ["D1","D2",...]}``
        ``"ABC"``    → ``{"AB": ["AB1","AB2",...], "BC": [...], "CA": [...]}``
    """
    phases = phase_info(style)
    return {
        dir_name: [f"{prefix}{i}" for i in range(1, n_cycles + 1)]
        for dir_name, prefix in phases
    }


