"""
리프팅 연구용 OpenSim Run Tools 패키지

기본 변수를 CONFIG로 미리 설정하고, PipelinePathBase / OneCycle_Pipeline에서
이 설정을 반영해 사용할 수 있다.

사용 예:
    from c_Run_Tools import CONFIG, get_path_class, get_path_from_config
    CONFIG["sub_name"] = "SUB2"
    path_class = get_path_class(CONFIG)
    path_instance = get_path_from_config(CONFIG)
"""
import os


def _build_kg_bpm(kg, bpm):
    """kg, bpm을 받아 'kg_bpm' 문자열 리스트로 조합. 스칼라는 리스트처럼 확장."""
    kg_list = [kg] if not hasattr(kg, "__iter__") or isinstance(kg, str) else list(kg)
    bpm_list = [bpm] if not hasattr(bpm, "__iter__") or isinstance(bpm, str) else list(bpm)
    if len(kg_list) == 1 and len(bpm_list) > 1:
        kg_list = kg_list * len(bpm_list)
    elif len(bpm_list) == 1 and len(kg_list) > 1:
        bpm_list = bpm_list * len(kg_list)
    return [f"{k}_{b}" for k, b in zip(kg_list, bpm_list)]


class _ConfigDict(dict):
    """CONFIG['kg_bpm'] 접근 시 CONFIG['kg'], CONFIG['bpm']으로 자동 조합해 반환."""

    def __getitem__(self, key):
        if key == "kg_bpm":
            if super().get("_kg_bpm_explicit"):
                return super().__getitem__("kg_bpm")
            kg = super().get("kg", 15)
            bpm = super().get("bpm", 10)
            return _build_kg_bpm(kg, bpm)
        return super().__getitem__(key)

    def __setitem__(self, key, value):
        if key == "kg_bpm":
            super().__setitem__("_kg_bpm_explicit", True)
        super().__setitem__(key, value)

    def get(self, key, default=None):
        if key == "kg_bpm":
            if super().get("_kg_bpm_explicit"):
                return super().get("kg_bpm", default)
            kg = super().get("kg", 15)
            bpm = super().get("bpm", 10)
            return _build_kg_bpm(kg, bpm)
        return super().get(key, default)


# -----------------------------------------------------------------------------
# 기본 CONFIG: 리프팅 연구 디렉터리 세팅에서 공통으로 쓰는 변수
# -----------------------------------------------------------------------------
CONFIG = _ConfigDict({
    "root_dir": r"E:\Dropbox\SEL\BOX\OpenSim\_Main_\c_AddBio_Continous",
    # SUB
    "sub_name": "SUB1",
    
    # Symmetric or Asymmetric
    "symmetric": True,          # True: 대칭 리프팅(SUB1 스타일)
                                # False: 비대칭(SUB2 스타일, trial_kg_bpm_S_trialnum)
    # 조건: kg_bpm은 CONFIG["kg"], CONFIG["bpm"]으로 자동 조합됨 (아래 개별 지정)
    "kg": 15,                   # 단일 값 또는 리스트 (예: 15 또는 [7, 15])
    "bpm": [10, 16],            # 단일 값 또는 리스트 (예: 10 또는 [10, 16]) → kg_bpm: ["15_10", "15_16"]
    
    # GripEventDetect
    "task_type": "OneCycle",    # "OneCycle" | "UpDown"
    # UpDown 전용: 'U' or 'D'
    "updown": "U",
    
    # EHF Approach
    "APP": "APP2_OneCycle",     # APP1_OneCycle, APP2_OneCycle, APP3, APP4 등
                                # APP2_preRiCTO / APP2_postRiCTO 시 ExtLoad .mot variant 자동 적용
    # ExtLoad .mot variant (optional): "original" | "corrected" | None
    # None이면 APP에 따라 자동: APP2_preRiCTO -> original (_estimated_original.mot),
    #                           APP2_postRiCTO -> corrected (_RiCTO-corrected.mot)
    # suffix 규칙은 d_Optimization.get_optimized_solution_and_EHF에서 파싱해 사용
    "extload_variant": None,

})


def get_path_class(config=None):
    """
    config의 symmetric, task_type에 따라 사용할 Path 클래스를 반환.

    Returns
    -------
    SymmetricOneCyclePath | SymmetricUpDownPath | AsymmetricOneCyclePath | AsymmetricUpDownPath
    """
    try:
        from .PipelinePathSetting import (
            SymmetricOneCyclePath,
            SymmetricUpDownPath,
            AsymmetricOneCyclePath,
            AsymmetricUpDownPath,
        )
    except ImportError:
        from PipelinePathSetting import (
            SymmetricOneCyclePath,
            SymmetricUpDownPath,
            AsymmetricOneCyclePath,
            AsymmetricUpDownPath,
        )
    cfg = config or CONFIG
    symmetric = cfg.get("symmetric", True)
    task_type = (cfg.get("task_type") or "OneCycle").strip().lower()
    if "onecycle" in task_type or task_type == "one":
        return SymmetricOneCyclePath if symmetric else AsymmetricOneCyclePath
    if "updown" in task_type or task_type == "up" or task_type == "ud":
        return SymmetricUpDownPath if symmetric else AsymmetricUpDownPath
    return SymmetricOneCyclePath


def get_path_from_config(config=None):
    """config에서 Path 인스턴스 생성 (get_path_class(config).from_config(config))."""
    cfg = config or CONFIG
    path_class = get_path_class(cfg)
    return path_class.from_config(cfg)


def update_config(**kwargs):
    """CONFIG에 키워드 인자로 값 반영."""
    CONFIG.update(kwargs)


# 패키지에서 사용할 때 경로 기준 디렉터리 (c_Run Tools)
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))

__all__ = [
    "CONFIG",
    "PACKAGE_DIR",
    "get_path_class",
    "get_path_from_config",
    "update_config",
]
