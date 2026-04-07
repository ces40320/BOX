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
        "APPs": ["APP1", "APP2", "APP3", "APP4"],
        "segment_style": "UpDown",
        "segment": {
            "method": "findpeaks",
            "pair_threshold": 0.5, # 대칭 프로토콜 세그먼트 분할 임계값 (meter)
        },
    },
    "Asymmetric_Pilot": {
        "APPs": ["APP1", "APP2"],
        "segment_style": "UpDown",
        "segment": {
            "method": "findpeaks",
            "pair_threshold": 0.005, # 비대칭 프로토콜 세그먼트 분할 임계값 (meter)
        },
    },
    "Asymmetric_Triangle": {
        "APPs": ["APP1", "APP2", "APP2_preRiCTO", "APP2_postRiCTO"],
        "segment_style": "ABC",
        "segment": {
            "method": "bpm_window",
            "BPM_DURATION": {10: 6.0, 16: 3.75},    # 10bpm → 6.0초, 16bpm → 3.75초
            "CONTACT_THRESHOLD_N": 5.0,             # N — 양손 |fy| 합이 이 이상이면 접촉
            "CONTACT_MIN_DUR_SEC": 0.5,             # s — 최소 접촉 지속시간
            "SKIP_FIRST_N": 1,                      # 첫 N개 리프팅은 동기화용으로 스킵
            "CYCLE_OFFSET_SEC": -1.5,               # 첫 번째 리프팅 시작점 검출용 (손 외력 threshold) 1.5초 전
        },
    },
}

_TRIANGLE_PHASES = ["AB", "BC", "CA"]


def segment_labels(n_cycles:int, style:str) -> list[str]:
    """프로토콜 세그먼트 스타일에 맞는 레이블 목록 생성.

    Parameters
    ----------
    n_cycles : int
        해당 condition의 lifting cycle 수.
    style : str
        ``"UpDown"``  → ``["1U", "1D", "2U", "2D", ...]``
        ``"ABC"`` → ``["1AB", "1BC", "1CA", "2AB", "2BC", "2CA", ...]``
    """
    if style == "UpDown":
        labels = []
        for i in range(1, n_cycles + 1):
            labels.append(f"{i}U")
            labels.append(f"{i}D")
        return labels
    if style == "ABC":
        labels = []
        for i in range(1, n_cycles + 1):
            for phase in _TRIANGLE_PHASES:
                labels.append(f"{i}{phase}")
        return labels
    raise ValueError(f"Unknown segment_style: {style!r}")


