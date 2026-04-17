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
            "method": "manual_window",              # TODO: split_lifting_trial2section_bpm_window.py 구현 후 "bpm_window" 로 변경 필요
            "BPM_DURATION": {10: 6.0, 16: 3.75},    # 10bpm → 6.0초, 16bpm → 3.75초
            "CONTACT_THRESHOLD_N": 5.0,             # N — 양손 |fy| 합이 이 이상이면 접촉
            "CONTACT_MIN_DUR_SEC": 0.5,             # s — 최소 접촉 지속시간
            "SKIP_FIRST_N": 1,                      # 첫 N개 리프팅은 동기화용으로 스킵
            "CYCLE_OFFSET_SEC": -1.5,               # 첫 번째 리프팅 시작점 검출용 (손 외력 threshold) 1.5초 전
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


