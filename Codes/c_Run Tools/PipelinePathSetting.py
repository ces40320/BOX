"""
OpenSim 파이프라인 경로/네이밍 베이스 클래스

분석 방법·피험자·과제(task) 종류에 따라 경로 및 파일명 규칙이 달라지므로,
서브클래스에서 훅 메서드를 오버라이드하여 네이밍 규칙을 지정한다.

사전 정의된 4가지 경로 클래스:
- SymmetricOneCyclePath: 대칭 리프팅 + OneCycle (디폴트, SUB1 등)
- SymmetricUpDownPath: 대칭 리프팅 + UpDown (U/D + task)
- AsymmetricOneCyclePath: 비대칭 리프팅 S버전 + OneCycle (trial_kg_bpm_S_trialnum)
- AsymmetricUpDownPath: 비대칭 리프팅 D버전 + UpDown

ExtLoad .mot variant (APP2_preRiCTO / APP2_postRiCTO):
- extload_variant "original" -> _estimated_original.mot (d_Optimization과 동일 규칙)
- extload_variant "corrected" -> _RiCTO-corrected.mot
- suffix는 d_Optimization.get_optimized_solution_and_EHF.get_extload_variant_suffixes()에서 파싱해 사용
"""
import os
import numpy as np
import pandas as pd

# ExtLoad variant suffix: d_Optimization과 동일 규칙 사용 (하드코딩 방지)
def _get_extload_variant_suffixes(app_suffix="APP2"):
    try:
        import sys
        _codes = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        if _codes not in sys.path:
            sys.path.insert(0, _codes)
        from d_Optimization.get_optimized_solution_and_EHF import get_extload_variant_suffixes
        return get_extload_variant_suffixes(app_suffix)
    except Exception:
        return "_estimated_original", "_RiCTO-corrected"


class PipelinePathBase:
    """경로·파일명 규칙을 훅으로 분리한 OpenSim 파이프라인 베이스 클래스."""

    def __init__(self, root_dir, sub_name, APP, symmetric_trial=True, extload_variant=None):
        self.root_dir = root_dir
        self.sub_name = sub_name
        self.APP = APP
        self.symmetric_trial = symmetric_trial
        # None | "original" | "corrected" (APP2_preRiCTO -> original, APP2_postRiCTO -> corrected)
        self.extload_variant = extload_variant

    # -------------------------------------------------------------------------
    # 훅 메서드: 서브클래스에서 오버라이드
    # -------------------------------------------------------------------------
    def get_trial_folder_name(self, kg_bpm, trial_num, task_num=None, **kwargs):
        """trial 폴더 이름 (예: trial15_10_S_1 또는 trial15_10_1)."""
        infix = "_" if self.symmetric_trial else "_S_"
        return f"trial{kg_bpm}{infix}{trial_num}"

    def get_trc_folder_name(self):
        """TRC 파일이 있는 상위 폴더명 (예: OneCycle_TrcMot, UpDown_TrcMot)."""
        raise NotImplementedError("서브클래스에서 get_trc_folder_name()을 구현하세요.")

    def get_trc_file_basename(self, kg_bpm, trial_num, task_num, **kwargs):
        """TRC 파일 basename (확장자 .trc 제외)."""
        raise NotImplementedError("서브클래스에서 get_trc_file_basename()을 구현하세요.")

    def get_trial_suffix(self, kg_bpm, trial_num, task_num, **kwargs):
        """IK/SO/BK/JR 설정·결과 파일명에 쓰는 접미사 (예: 15_10_trial1_12sec_1)."""
        raise NotImplementedError("서브클래스에서 get_trial_suffix()을 구현하세요.")

    def get_analysis_name(self, kg_bpm, trial_num, task_num, **kwargs):
        """분석 이름 (예: .sto 파일명에 사용되는 전체 이름)."""
        raise NotImplementedError("서브클래스에서 get_analysis_name()을 구현하세요.")

    def get_model_app_suffix(self):
        """모델 파일명에 쓰는 APP 접미사 (예: APP2 또는 APP4). 기본: APP 앞 4글자."""
        return self.APP[0:4] if len(self.APP) >= 4 else self.APP

    def get_extload_mot_basename(self, kg_bpm, trial_num, task_num, **kwargs):
        """ExtLoad .mot 파일 basename (확장자 제외)."""
        raise NotImplementedError("서브클래스에서 get_extload_mot_basename()을 구현하세요.")

    # -------------------------------------------------------------------------
    # 공통 경로 헬퍼 (훅 사용)
    # -------------------------------------------------------------------------
    def _trial_dir(self, kg_bpm, trial_num, task_num=None, app=None, **kwargs):
        """trial 폴더 기준 경로. app=None이면 self.APP 사용."""
        app = app or self.APP
        folder = self.get_trial_folder_name(kg_bpm, trial_num, task_num, **kwargs)
        return os.path.join(self.root_dir, self.sub_name, app, folder)

    def _app4_effective(self):
        """APP4일 때 IK/ExtLoad는 APP3 경로 사용."""
        return self.APP == "APP4"

    def _app_for_ik(self):
        """IK/좌표 파일 경로에 쓸 APP (APP4면 APP3)."""
        return "APP3" if self._app4_effective() else self.APP

    def _app_for_extload_dir(self):
        """ExtLoad XML 디렉에 쓸 APP (APP4면 APP3)."""
        return "APP3" if self._app4_effective() else self.APP

    def _model_addbiomech_path(self):
        """Scaled_AddBiomech 모델 경로."""
        suffix = self.get_model_app_suffix()
        return os.path.join(
            self.root_dir, self.sub_name, self.APP,
            f"{self.sub_name}_Scaled_AddBiomech_{suffix}.osim",
        )

    def _model_actuator_path(self):
        """Scaled_Actuator 모델 경로 (SO 실행 후 생성)."""
        suffix = self.get_model_app_suffix()
        return os.path.join(
            self.root_dir, self.sub_name, self.APP,
            f"{self.sub_name}_Scaled_{suffix}_Actuator.osim",
        )

    def _trc_path(self, kg_bpm, trial_num, task_num, **kwargs):
        """TRC 파일 전체 경로."""
        folder = self.get_trc_folder_name()
        basename = self.get_trc_file_basename(kg_bpm, trial_num, task_num, **kwargs)
        return os.path.join(self.root_dir, self.sub_name, folder, f"{basename}.trc")

    def _read_trc_times(self, trc_file_path):
        """TRC에서 start/end time 배열 추출."""
        df = pd.read_csv(trc_file_path, sep="\t", skiprows=4)
        trcdata = np.array(df)
        return trcdata[1, 1], trcdata[-1, 1]

    def _analysis_name(self, kg_bpm, trial_num, task_num, **kwargs):
        """분석 이름 (훅 위임) (예: SUB1_15_10_trial1_12sec_1_APP3)."""
        return self.get_analysis_name(kg_bpm, trial_num, task_num, **kwargs)

    def _trial_suffix(self, kg_bpm, trial_num, task_num, **kwargs):
        """파일명 접미사 (훅 위임) (예: 15_10_trial1_12sec_1)."""
        return self.get_trial_suffix(kg_bpm, trial_num, task_num, **kwargs)

    # ----- IK 경로 -----
    def _IK_dir(self, kg_bpm, trial_num, task_num, app=None, **kwargs):
        app = app or self.APP
        return os.path.join(self._trial_dir(kg_bpm, trial_num, task_num, app=app, **kwargs), "IK_Results")

    def _IK_mot_path(self, kg_bpm, trial_num, task_num, app=None, **kwargs):
        app = app or self.APP
        suffix = self._trial_suffix(kg_bpm, trial_num, task_num, **kwargs)
        return os.path.join(self._IK_dir(kg_bpm, trial_num, task_num, app=app, **kwargs), f"{suffix}_IK.mot")

    def _IK_setup_xml_path(self, kg_bpm, trial_num, task_num, app=None, **kwargs):
        app = app or self.APP
        suffix = self._trial_suffix(kg_bpm, trial_num, task_num, **kwargs)
        return os.path.join(self._IK_dir(kg_bpm, trial_num, task_num, app=app, **kwargs), f"SETUP_IK_{suffix}_{app}.xml")

    # ----- ExtLoad 경로 -----
    def _ExtLoad_mot_path(self, kg_bpm, trial_num, task_num, **kwargs):
        basename = self.get_extload_mot_basename(kg_bpm, trial_num, task_num, **kwargs)
        if self.extload_variant in ("original", "corrected"):
            orig_suffix, corr_suffix = _get_extload_variant_suffixes(self.get_model_app_suffix())
            basename += corr_suffix if self.extload_variant == "corrected" else orig_suffix
        folder = self.get_trc_folder_name()
        return os.path.join(self.root_dir, self.sub_name, folder, f"{basename}.mot")

    def _ExtLoad_xml_dir(self, kg_bpm, trial_num, task_num, app=None, **kwargs):
        app = app or self.APP
        return os.path.join(self._trial_dir(kg_bpm, trial_num, task_num, app=app, **kwargs), "xml_ExtLoad")

    def _ExtLoad_setup_xml_path(self, kg_bpm, trial_num, task_num, dir_app=None, file_app=None, **kwargs):
        dir_app = dir_app if dir_app is not None else self.APP
        file_app = file_app if file_app is not None else self.APP
        suffix = self._trial_suffix(kg_bpm, trial_num, task_num, **kwargs)
        base = self._ExtLoad_xml_dir(kg_bpm, trial_num, task_num, app=dir_app, **kwargs)
        return os.path.join(base, f"SETUP_ExtLoad_{suffix}_{file_app}.xml")

    # ----- SO 경로 -----
    def _SO_dir(self, kg_bpm, trial_num, task_num, **kwargs):
        return os.path.join(self._trial_dir(kg_bpm, trial_num, task_num, **kwargs), "SO_Results")

    def _SO_activation_path(self, kg_bpm, trial_num, task_num, **kwargs):
        name = self._analysis_name(kg_bpm, trial_num, task_num, **kwargs)
        return os.path.join(self._SO_dir(kg_bpm, trial_num, task_num, **kwargs), f"{name}_StaticOptimization_activation.sto")

    def _SO_force_path(self, kg_bpm, trial_num, task_num, **kwargs):
        name = self._analysis_name(kg_bpm, trial_num, task_num, **kwargs)
        return os.path.join(self._SO_dir(kg_bpm, trial_num, task_num, **kwargs), f"{name}_StaticOptimization_force.sto")

    def _SO_setup_xml_path(self, kg_bpm, trial_num, task_num, **kwargs):
        suffix = self._trial_suffix(kg_bpm, trial_num, task_num, **kwargs)
        return os.path.join(self._SO_dir(kg_bpm, trial_num, task_num, **kwargs), f"SETUP_SO_{suffix}_{self.APP}.xml")

    # ----- BK 경로 -----
    def _BK_dir(self, kg_bpm, trial_num, task_num, **kwargs):
        return os.path.join(self._trial_dir(kg_bpm, trial_num, task_num, **kwargs), "BK_Results")

    def _BK_setup_xml_path(self, kg_bpm, trial_num, task_num, **kwargs):
        suffix = self._trial_suffix(kg_bpm, trial_num, task_num, **kwargs)
        return os.path.join(self._BK_dir(kg_bpm, trial_num, task_num, **kwargs), f"SETUP_BK_{suffix}_{self.APP}.xml")

    # ----- JR 경로 -----
    def _JR_dir(self, kg_bpm, trial_num, task_num, **kwargs):
        return os.path.join(self._trial_dir(kg_bpm, trial_num, task_num, **kwargs), "JR_Results")

    def _JR_setup_xml_path(self, kg_bpm, trial_num, task_num, **kwargs):
        suffix = self._trial_suffix(kg_bpm, trial_num, task_num, **kwargs)
        return os.path.join(self._JR_dir(kg_bpm, trial_num, task_num, **kwargs), f"SETUP_JR_{suffix}_{self.APP}.xml")

    def _JR_setup_ground_xml_path(self, kg_bpm, trial_num, task_num, **kwargs):
        suffix = self._trial_suffix(kg_bpm, trial_num, task_num, **kwargs)
        return os.path.join(self._JR_dir(kg_bpm, trial_num, task_num, **kwargs), f"SETUP_JR_{suffix}_{self.APP}_ground.xml")

    def _JR_results_ground_dir(self, kg_bpm, trial_num, task_num, **kwargs):
        return os.path.join(self._trial_dir(kg_bpm, trial_num, task_num, **kwargs), "JR_Results(ground)")



    # -------------------------------------------------------------------------
    # config 기반 생성 (서브클래스에서 사용)
    # -------------------------------------------------------------------------
    @classmethod
    def from_config(cls, config):
        """config dict에서 root_dir, sub_name, APP, symmetric_trial, extload_variant를 읽어 인스턴스 생성."""
        extload_variant = config.get("extload_variant")
        if extload_variant is None and isinstance(config.get("APP"), str):
            app = config["APP"]
            if app == "APP2_preRiCTO":
                extload_variant = "original"
            elif app == "APP2_postRiCTO":
                extload_variant = "corrected"
        return cls(
            root_dir=config["root_dir"],
            sub_name=config["sub_name"],
            APP=config["APP"],
            symmetric_trial=config.get("symmetric", True),
            extload_variant=extload_variant,
        )


# =============================================================================
# 사전 정의된 4가지 경로 클래스
# =============================================================================

class SymmetricOneCyclePath(PipelinePathBase):
    """대칭 리프팅 + OneCycle (디폴트). trial{kg_bpm}_{trial_num}, 12sec, OneCycle_TrcMot."""

    def __init__(self, root_dir, sub_name, APP, **kwargs):
        super().__init__(root_dir, sub_name, APP, symmetric_trial=True)

    def get_trc_folder_name(self):
        return "OneCycle_TrcMot"

    def get_trc_file_basename(self, kg_bpm, trial_num, task_num, **kwargs):
        t, task = str(trial_num), str(task_num)
        return f"{kg_bpm}_trial{t}_12sec_{task}"

    def get_trial_suffix(self, kg_bpm, trial_num, task_num, **kwargs):
        t, task = str(trial_num), str(task_num)
        return f"{kg_bpm}_trial{t}_12sec_{task}"

    def get_analysis_name(self, kg_bpm, trial_num, task_num, **kwargs):
        t, task = str(trial_num), str(task_num)
        return f"{self.sub_name}_{kg_bpm}_{t}_12sec_{task}_{self.APP}"

    def get_extload_mot_basename(self, kg_bpm, trial_num, task_num, **kwargs):
        t, task = str(trial_num), str(task_num)
        return f"{kg_bpm}_trial{t}_12sec_{task}_ExtLoad{self.get_model_app_suffix()}"


class SymmetricUpDownPath(PipelinePathBase):
    """대칭 리프팅 + UpDown. trial{kg_bpm}_{trial_num}, UpDown_TrcMot, {updown}{task_num} (U/D)."""

    def __init__(self, root_dir, sub_name, APP, **kwargs):
        super().__init__(root_dir, sub_name, APP, symmetric_trial=True)

    def get_trc_folder_name(self):
        return "UpDown_TrcMot"

    def get_trc_file_basename(self, kg_bpm, trial_num, task_num, updown="U", **kwargs):
        t, task = str(trial_num), str(task_num)
        return f"{kg_bpm}_trial{t}_{updown}{task}"

    def get_trial_suffix(self, kg_bpm, trial_num, task_num, updown="U", **kwargs):
        t, task = str(trial_num), str(task_num)
        return f"{kg_bpm}_trial{t}_{updown}{task}"

    def get_analysis_name(self, kg_bpm, trial_num, task_num, updown="U", **kwargs):
        t, task = str(trial_num), str(task_num)
        return f"{self.sub_name}_{kg_bpm}_{t}_{updown}{task}_{self.APP}"

    def get_extload_mot_basename(self, kg_bpm, trial_num, task_num, updown="U", **kwargs):
        t, task = str(trial_num), str(task_num)
        return f"{kg_bpm}_trial{t}_{updown}{task}_ExtLoad{self.get_model_app_suffix()}"


class AsymmetricOneCyclePath(PipelinePathBase):
    """비대칭 리프팅 S버전 + OneCycle. trial{kg_bpm}_S_{trial_num}, 12sec, OneCycle_TrcMot."""

    def __init__(self, root_dir, sub_name, APP, **kwargs):
        super().__init__(root_dir, sub_name, APP, symmetric_trial=False)

    def get_trc_folder_name(self):
        return "OneCycle_TrcMot"

    def get_trc_file_basename(self, kg_bpm, trial_num, task_num, **kwargs):
        t, task = str(trial_num), str(task_num)
        return f"{kg_bpm}_S_trial{t}_12sec_{task}"

    def get_trial_suffix(self, kg_bpm, trial_num, task_num, **kwargs):
        t, task = str(trial_num), str(task_num)
        return f"{kg_bpm}_trial{t}_12sec_{task}"

    def get_analysis_name(self, kg_bpm, trial_num, task_num, **kwargs):
        t, task = str(trial_num), str(task_num)
        return f"{self.sub_name}_{kg_bpm}_{t}_12sec_{task}_{self.APP}"

    def get_extload_mot_basename(self, kg_bpm, trial_num, task_num, **kwargs):
        t, task = str(trial_num), str(task_num)
        return f"{kg_bpm}_S_trial{t}_12sec_{task}_ExtLoad{self.get_model_app_suffix()}"


class AsymmetricUpDownPath(PipelinePathBase):
    """비대칭 리프팅 D버전 + UpDown. trial{kg_bpm}_S_{trial_num}, UpDown_TrcMot, {updown}{task_num}."""

    def __init__(self, root_dir, sub_name, APP, **kwargs):
        super().__init__(root_dir, sub_name, APP, symmetric_trial=False)

    def get_trc_folder_name(self):
        return "UpDown_TrcMot"

    def get_trc_file_basename(self, kg_bpm, trial_num, task_num, updown="D", **kwargs):
        t, task = str(trial_num), str(task_num)
        return f"{kg_bpm}_trial{t}_{updown}{task}"

    def get_trial_suffix(self, kg_bpm, trial_num, task_num, updown="D", **kwargs):
        t, task = str(trial_num), str(task_num)
        return f"{kg_bpm}_trial{t}_{updown}{task}"

    def get_analysis_name(self, kg_bpm, trial_num, task_num, updown="D", **kwargs):
        t, task = str(trial_num), str(task_num)
        return f"{self.sub_name}_{kg_bpm}_{t}_{updown}{task}_{self.APP}"

    def get_extload_mot_basename(self, kg_bpm, trial_num, task_num, updown="D", **kwargs):
        t, task = str(trial_num), str(task_num)
        return f"{kg_bpm}_trial{t}_{updown}{task}_ExtLoad{self.get_model_app_suffix()}"
