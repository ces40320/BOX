"""
OneCycle OpenSim 파이프라인 통합 클래스

- ExtLoad XML 설정, IK, SO 설정/실행, BK 설정/실행, JR 설정/실행 제공.
- 경로/네이밍은 PipelinePathBase 서브클래스(또는 __init__.py CONFIG)로 주입.
"""
import os
import time

os.add_dll_directory("C:/OpenSim 4.5/bin")

import numpy as np
import pandas as pd
import opensim as osim
from lxml import etree

from PipelinePathSetting import (
    PipelinePathBase,
    AsymmetricOneCyclePath,
    SymmetricOneCyclePath,
    SymmetricUpDownPath,
    AsymmetricUpDownPath,
)


class OpenSimPipeline:
    """
    OpenSim 분석 파이프라인 (실행 로직).
    경로 규칙은 path_base 인스턴스(PipelinePathBase 서브클래스)에 위임.
    """

    DEFAULT_EXLOAD_TEMPLATE = r"E:\Dropbox\SEL\BOX\OpenSim\_Main_\SETUP_ExtLoad.xml"
    DEFAULT_IK_APP12 = r"E:\Dropbox\SEL\BOX\OpenSim\_Main_\SETUP_IK_APP1,2.xml"
    DEFAULT_IK_APP34 = r"E:\Dropbox\SEL\BOX\OpenSim\_Main_\SETUP_IK_APP3,4.xml"

    def __init__(self, path_base=None, root_dir=None, sub_name=None, APP=None,
                 path_class=None, symmetric_trial=False,
                 opensim_bin=None, extload_template=None, ik_setup_app12=None, ik_setup_app34=None):
        if path_base is not None:
            self._path = path_base
        elif root_dir is not None and sub_name is not None and APP is not None:
            path_class = path_class or SymmetricOneCyclePath
            self._path = path_class(root_dir, sub_name, APP, symmetric_trial=symmetric_trial)
        else:
            raise ValueError("path_base를 넘기거나 (root_dir, sub_name, APP)를 넘기세요.")
        self.root_dir = self._path.root_dir
        self.sub_name = self._path.sub_name
        self.APP = self._path.APP
        self.opensim_bin = opensim_bin or "C:/OpenSim 4.5/bin"
        self.extload_template = extload_template or self.DEFAULT_EXLOAD_TEMPLATE
        self.ik_setup_app12 = ik_setup_app12 or self.DEFAULT_IK_APP12
        self.ik_setup_app34 = ik_setup_app34 or self.DEFAULT_IK_APP34
        if opensim_bin:
            os.add_dll_directory(opensim_bin)

    def __getattr__(self, name):
        """경로/훅 메서드는 self._path에 위임."""
        if name.startswith("_") and hasattr(self._path, name):
            return getattr(self._path, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    @classmethod
    def from_config(cls, config=None, **kwargs):
        """__init__.py CONFIG(또는 인자 config)로 path 생성 후 파이프라인 인스턴스 반환."""
        cfg = config
        if cfg is None:
            _dir = os.path.dirname(os.path.abspath(__file__))
            if _dir not in __import__("sys").path:
                __import__("sys").path.insert(0, _dir)
            try:
                import __init__ as _i
                cfg, get_path_from_config = _i.CONFIG, _i.get_path_from_config
            except (ImportError, AttributeError):
                raise ImportError("CONFIG 사용 시 c_Run Tools 폴더에 __init__.py가 있어야 합니다.")
        else:
            _dir = os.path.dirname(os.path.abspath(__file__))
            if _dir not in __import__("sys").path:
                __import__("sys").path.insert(0, _dir)
            try:
                import __init__ as _i
                get_path_from_config = _i.get_path_from_config
            except (ImportError, AttributeError):
                from PipelinePathSetting import AsymmetricOneCyclePath
                get_path_from_config = lambda c: AsymmetricOneCyclePath.from_config(c)
        path_base = get_path_from_config(cfg)
        return cls(path_base=path_base, **kwargs)

    # ----- ExtLoad XML 설정 -----
    def ext_load_xml_set(self, kg_bpm, trial_num, task_num, **path_kw):
        """외부 하중(ExtLoad) XML 설정 파일 생성."""
        tree = etree.parse(self.extload_template)
        root = tree.getroot()
        datafile_element = root.find(".//datafile")
        if datafile_element is not None:
            datafile_element.text = self._ExtLoad_mot_path(kg_bpm, trial_num, task_num, **path_kw)
        out_dir = self._ExtLoad_xml_dir(kg_bpm, trial_num, task_num, **path_kw)
        os.makedirs(out_dir, exist_ok=True)
        out_path = self._ExtLoad_setup_xml_path(kg_bpm, trial_num, task_num, **path_kw)
        tree.write(out_path, pretty_print=True, encoding="UTF-8", xml_declaration=True)

    # ----- IK 실행 -----
    def ik_run(self, kg_bpm, trial_num, task_num, **path_kw):
        """Inverse Kinematics 실행."""
        trc_dir = self._trc_path(kg_bpm, trial_num, task_num, **path_kw)
        start_time, end_time = self._read_trc_times(trc_dir)
        base_model = self._model_addbiomech_path()
        model = osim.Model(base_model)
        base_IK = self.ik_setup_app34 if self.APP == "APP3" else self.ik_setup_app12
        IK = osim.InverseKinematicsTool(base_IK)
        IK.setName(self.sub_name)
        IK.set_marker_file(trc_dir)
        IK.setModel(model)
        IK.setStartTime(start_time)
        IK.setEndTime(end_time)
        ik_dir = self._IK_dir(kg_bpm, trial_num, task_num, **path_kw)
        os.makedirs(ik_dir, exist_ok=True)
        IK.setOutputMotionFileName(self._IK_mot_path(kg_bpm, trial_num, task_num, **path_kw))
        IK.printToXML(self._IK_setup_xml_path(kg_bpm, trial_num, task_num, **path_kw))
        IK.run()

    # ----- SO 설정 -----
    def so_set(self, kg_bpm, trial_num, task_num, **path_kw):
        """Static Optimization 설정 XML 생성."""
        trc_path = self._trc_path(kg_bpm, trial_num, task_num, **path_kw)
        start_time, end_time = self._read_trc_times(trc_path)
        model_path = self._model_addbiomech_path()
        model = osim.Model(model_path)
        app_ik = self._app_for_ik()
        dir_app = self._app_for_extload_dir()
        file_app = "APP3" if self._app4_effective() else self.APP

        analyze = osim.AnalyzeTool()
        analyze.setName(self._analysis_name(kg_bpm, trial_num, task_num, **path_kw))
        analyze.setModel(model)
        analyze.setModelFilename(model_path)
        analyze.setReplaceForceSet(False)
        analyze.setCoordinatesFileName(self._IK_mot_path(kg_bpm, trial_num, task_num, app=app_ik, **path_kw))
        analyze.setLowpassCutoffFrequency(6)
        analyze.setSolveForEquilibrium(True)
        analyze.setStartTime(start_time)
        analyze.setFinalTime(end_time)
        analyze.setExternalLoadsFileName(
            self._ExtLoad_setup_xml_path(kg_bpm, trial_num, task_num, dir_app=dir_app, file_app=file_app, **path_kw)
        )
        so = osim.StaticOptimization()
        so.setModel(model)
        so.setStartTime(start_time)
        so.setEndTime(end_time)
        so.setStepInterval(1)
        so.setInDegrees(True)
        so.setUseModelForceSet(True)
        so.setActivationExponent(2)
        so.setUseMusclePhysiology(True)
        so.setConvergenceCriterion(0.0001)
        so.setMaxIterations(100)
        analyze.getAnalysisSet().adoptAndAppend(so)
        analyze.setResultsDir(self._SO_dir(kg_bpm, trial_num, task_num, **path_kw))
        analyze.printToXML(self._SO_setup_xml_path(kg_bpm, trial_num, task_num, **path_kw))

    # ----- SO 실행 (Actuator 모델 생성 후 실행) -----
    def so_run(self, kg_bpm, trial_num, task_num, **path_kw):
        """Reserve actuator 추가 후 Static Optimization 실행."""
        model_path = self._model_addbiomech_path()
        model = osim.Model(model_path)

        def add_reserve(model, coord, max_control):
            actu = osim.CoordinateActuator(coord)
            prefix = "torque_" if coord.startswith("lumbar") else ("residual_" if coord.startswith("pelvis") else "reserve_")
            actu.setName(f"{prefix}{coord}")
            actu.setMinControl(-10000)
            actu.setMaxControl(10000)
            actu.setOptimalForce(max_control)
            model.addForce(actu)

        add_reserve(model, "pelvis_tx", 100)
        add_reserve(model, "pelvis_ty", 200)
        add_reserve(model, "pelvis_tz", 100)
        add_reserve(model, "pelvis_tilt", 80)
        add_reserve(model, "pelvis_list", 80)
        add_reserve(model, "pelvis_rotation", 80)
        add_reserve(model, "L5_S1_Flex_Ext", 10)
        add_reserve(model, "L5_S1_Lat_Bending", 5)
        add_reserve(model, "L5_S1_axial_rotation", 5)
        for side in ["_l", "_r"]:
            for name in ["arm_flex", "arm_add", "arm_rot", "elbow_flex", "pro_sup", "wrist_flex", "wrist_dev",
                        "hip_rotation", "hip_flexion", "hip_adduction", "knee_angle", "ankle_angle"]:
                add_reserve(model, f"{name}{side}", 200)

        model.printToXML(self._model_actuator_path())
        so = osim.AnalyzeTool(self._SO_setup_xml_path(kg_bpm, trial_num, task_num, **path_kw))
        so.setModel(model)
        so.setModelFilename(model_path)
        so.run()

    # ----- BK 설정 -----
    def bk_set(self, kg_bpm, trial_num, task_num, **path_kw):
        """Body Kinematics 설정 XML 생성."""
        trc_path = self._trc_path(kg_bpm, trial_num, task_num, **path_kw)
        start_time, end_time = self._read_trc_times(trc_path)
        model_path = self._model_actuator_path()
        model = osim.Model(model_path)
        analyze = osim.AnalyzeTool()
        analyze.setName(self._analysis_name(kg_bpm, trial_num, task_num, **path_kw))
        analyze.setModel(model)
        analyze.setModelFilename(model_path)
        analyze.setReplaceForceSet(False)
        analyze.setControlsFileName(self._SO_activation_path(kg_bpm, trial_num, task_num, **path_kw))
        analyze.setCoordinatesFileName(self._IK_mot_path(kg_bpm, trial_num, task_num, **path_kw))
        analyze.setLowpassCutoffFrequency(6)
        analyze.setSolveForEquilibrium(True)
        analyze.setStartTime(start_time)
        analyze.setFinalTime(end_time)
        analyze.setExternalLoadsFileName(self._ExtLoad_setup_xml_path(kg_bpm, trial_num, task_num, **path_kw))
        bk = osim.BodyKinematics()
        bk.setName("BodyKinematics")
        bk.setStartTime(start_time)
        bk.setEndTime(end_time)
        bk.setStepInterval(1)
        bk.setInDegrees(True)
        analyze.getAnalysisSet().adoptAndAppend(bk)
        analyze.setResultsDir(self._BK_dir(kg_bpm, trial_num, task_num, **path_kw))
        analyze.printToXML(self._BK_setup_xml_path(kg_bpm, trial_num, task_num, **path_kw))

    # ----- BK 실행 -----
    def bk_run(self, kg_bpm, trial_num, task_num, **path_kw):
        """Body Kinematics 실행."""
        model_path = self._model_actuator_path()
        model = osim.Model(model_path)
        analyze = osim.AnalyzeTool(self._BK_setup_xml_path(kg_bpm, trial_num, task_num, **path_kw))
        analyze.setModel(model)
        analyze.setModelFilename(model_path)
        analyze.run()

    # ----- JR 설정 (ground XML 생성) -----
    def jr_set(self, kg_bpm, trial_num, task_num, **path_kw):
        """Joint Reaction 설정 XML 생성 (ground 프레임)."""
        trc_path = self._trc_path(kg_bpm, trial_num, task_num, **path_kw)
        start_time, end_time = self._read_trc_times(trc_path)
        model_path = self._model_actuator_path()
        model = osim.Model(model_path)
        app_ik = self._app_for_ik()
        dir_app = self._app_for_extload_dir()
        analyze = osim.AnalyzeTool()
        analyze.setName(self._analysis_name(kg_bpm, trial_num, task_num, **path_kw))
        analyze.setModel(model)
        analyze.setModelFilename(model_path)
        analyze.setReplaceForceSet(False)
        analyze.setControlsFileName(self._SO_activation_path(kg_bpm, trial_num, task_num, **path_kw))
        analyze.setCoordinatesFileName(self._IK_mot_path(kg_bpm, trial_num, task_num, app=app_ik, **path_kw))
        analyze.setLowpassCutoffFrequency(6)
        analyze.setSolveForEquilibrium(True)
        analyze.setStartTime(start_time)
        analyze.setFinalTime(end_time)
        analyze.setExternalLoadsFileName(
            self._ExtLoad_setup_xml_path(kg_bpm, trial_num, task_num, dir_app=dir_app, **path_kw)
        )
        jr = osim.JointReaction()
        jr.setName("JointReaction")
        jr.setStartTime(start_time)
        jr.setEndTime(end_time)
        jr.setStepInterval(1)
        jr.setInDegrees(True)
        jr.setForcesFileName(self._SO_force_path(kg_bpm, trial_num, task_num, **path_kw))
        analyze.getAnalysisSet().adoptAndAppend(jr)
        analyze.setResultsDir(self._JR_results_ground_dir(kg_bpm, trial_num, task_num, **path_kw))
        analyze.printToXML(self._JR_setup_ground_xml_path(kg_bpm, trial_num, task_num, **path_kw))

    # ----- JR XML 수정 (ground -> child) -----
    def jr_xml_set(self, kg_bpm, trial_num, task_num, **path_kw):
        """JR ground XML을 child 프레임용 XML로 복사·수정."""
        jr_ground = self._JR_setup_ground_xml_path(kg_bpm, trial_num, task_num, **path_kw)
        tree = etree.parse(jr_ground)
        root = tree.getroot()
        express_in_frame = root.find(".//express_in_frame")
        if express_in_frame is not None:
            express_in_frame.text = "child"
        results_dir = root.find(".//results_directory")
        if results_dir is not None:
            results_dir.text = self._JR_dir(kg_bpm, trial_num, task_num, **path_kw)
        tree.write(
            self._JR_setup_xml_path(kg_bpm, trial_num, task_num, **path_kw),
            pretty_print=True, encoding="UTF-8", xml_declaration=True,
        )

    # ----- JR 실행 -----
    def jr_run(self, kg_bpm, trial_num, task_num, **path_kw):
        """Joint Reaction 실행 (child 프레임)."""
        model_path = self._model_actuator_path()
        model = osim.Model(model_path)
        analyze = osim.AnalyzeTool(self._JR_setup_xml_path(kg_bpm, trial_num, task_num, **path_kw))
        analyze.setModel(model)
        analyze.setModelFilename(model_path)
        analyze.run()

    def jr_run_ground(self, kg_bpm, trial_num, task_num, **path_kw):
        """Joint Reaction 실행 (ground 프레임, APP4 등)."""
        model_path = self._model_actuator_path()
        model = osim.Model(model_path)
        analyze = osim.AnalyzeTool(self._JR_setup_ground_xml_path(kg_bpm, trial_num, task_num, **path_kw))
        analyze.setModel(model)
        analyze.setModelFilename(model_path)
        analyze.run()

    # ----- 파이프라인 배치 실행 -----
    def run_extload_set(self, kg_bpm_list, trial_range, task_range, **path_kw):
        for kg_bpm in kg_bpm_list:
            for trial_num in range(*trial_range):
                for task_num in range(*task_range):
                    self.ext_load_xml_set(kg_bpm, trial_num, task_num, **path_kw)

    def run_ik(self, kg_bpm_list, trial_range, task_range, print_time=False, **path_kw):
        for kg_bpm in kg_bpm_list:
            for trial_num in range(*trial_range):
                for task_num in range(*task_range):
                    if print_time:
                        start = time.time()
                    self.ik_run(kg_bpm, trial_num, task_num, **path_kw)
                    if print_time:
                        print(f"IK {self.APP} {kg_bpm} t{trial_num} task{task_num}: {time.time() - start:.2f}s")

    def run_so_set(self, kg_bpm_list, trial_range, task_range, **path_kw):
        for kg_bpm in kg_bpm_list:
            for trial_num in range(*trial_range):
                for task_num in range(*task_range):
                    self.so_set(kg_bpm, trial_num, task_num, **path_kw)

    def run_so(self, kg_bpm_list, trial_range, task_range, print_time=False, **path_kw):
        for kg_bpm in kg_bpm_list:
            for trial_num in range(*trial_range):
                for task_num in range(*task_range):
                    if print_time:
                        start = time.time()
                    self.so_run(kg_bpm, trial_num, task_num, **path_kw)
                    if print_time:
                        print(f"SO {self.APP} {kg_bpm} t{trial_num} task{task_num}: {time.time() - start:.2f}s")

    def run_bk_set(self, kg_bpm_list, trial_range, task_range, **path_kw):
        for kg_bpm in kg_bpm_list:
            for trial_num in range(*trial_range):
                for task_num in range(*task_range):
                    self.bk_set(kg_bpm, trial_num, task_num, **path_kw)

    def run_bk(self, kg_bpm_list, trial_range, task_range, **path_kw):
        for kg_bpm in kg_bpm_list:
            for trial_num in range(*trial_range):
                for task_num in range(*task_range):
                    self.bk_run(kg_bpm, trial_num, task_num, **path_kw)

    def run_jr_set(self, kg_bpm_list, trial_range, task_range, **path_kw):
        for kg_bpm in kg_bpm_list:
            for trial_num in range(*trial_range):
                for task_num in range(*task_range):
                    self.jr_set(kg_bpm, trial_num, task_num, **path_kw)
        for kg_bpm in kg_bpm_list:
            for trial_num in range(*trial_range):
                for task_num in range(*task_range):
                    self.jr_xml_set(kg_bpm, trial_num, task_num, **path_kw)

    def run_jr(self, kg_bpm_list, trial_range, task_range, run_ground_for_app4=False, print_time=False, **path_kw):
        for kg_bpm in kg_bpm_list:
            for trial_num in range(*trial_range):
                for task_num in range(*task_range):
                    if print_time:
                        start = time.time()
                    self.jr_run(kg_bpm, trial_num, task_num, **path_kw)
                    if run_ground_for_app4 and self.APP == "APP4":
                        self.jr_run_ground(kg_bpm, trial_num, task_num, **path_kw)
                    if print_time:
                        print(f"JR {self.APP} {kg_bpm} t{trial_num} task{task_num}: {time.time() - start:.2f}s")


def _parse_args():
    import argparse
    _dir = os.path.dirname(os.path.abspath(__file__))
    default_yaml = os.path.join(_dir, "configs", "pipeline_config.yaml")

    p = argparse.ArgumentParser(
        description="OpenSim Pipeline: YAML 설정 또는 CONFIG 기반 실행.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        metavar="YAML",
        help="설정 YAML 경로. 없으면 __init__.py CONFIG 사용.",
    )
    p.add_argument("--sub_name", type=str, default=None, help="YAML/CONFIG의 sub_name 덮어쓰기")
    p.add_argument("--APP", type=str, default=None, help="YAML/CONFIG의 APP 덮어쓰기")
    p.add_argument("--symmetric", type=lambda x: x.lower() in ("1", "true", "yes"), default=None, metavar="BOOL")
    p.add_argument("--task_type", type=str, default=None, choices=["OneCycle", "UpDown"], help="task_type 덮어쓰기")
    p.add_argument("--trial_range", type=int, nargs=2, default=None, metavar=("START", "END"), help="trial 범위 (range와 동일: end 미만)")
    p.add_argument("--task_range", type=int, nargs=2, default=None, metavar=("START", "END"), help="task 범위 (range와 동일)")
    p.add_argument(
        "--run",
        type=str,
        default=None,
        metavar="STEPS",
        help="실행할 단계 (쉼표 구분): extload_set,ik,so_set,so,bk_set,bk,jr_set,jr,jr_ground_app4",
    )
    p.add_argument("--print_time", type=lambda x: x.lower() in ("1", "true", "yes"), default=None, metavar="BOOL")
    p.add_argument("--no_run", action="store_true", help="실제 run 없이 설정만 로드 후 종료 (디버깅용)")
    return p.parse_args()


def _config_from_args(args):
    """
    CONFIG → CLI → YAML 순으로 병합. **YAML이 최우선** (YAML 값이 CLI보다 우선).
    """
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from __init__ import CONFIG, get_path_from_config as _gpf, load_config_from_yaml
    except ImportError:
        CONFIG = {"root_dir": r"E:\Dropbox\SEL\BOX\OpenSim\_Main_\c_AddBio_Continous", "sub_name": "SUB1", "APP": "APP2_postRiCTO", "symmetric": True}
        def _gpf(cfg):
            from PipelinePathSetting import SymmetricOneCyclePath
            return SymmetricOneCyclePath.from_config(cfg)
        def load_config_from_yaml(path):
            raise FileNotFoundError("--config 사용 시 c_Run Tools에 __init__.py와 load_config_from_yaml 필요")

    # 1) 베이스: CONFIG
    try:
        from __init__ import _ConfigDict
        cfg = _ConfigDict(dict(CONFIG))
    except Exception:
        cfg = dict(CONFIG) if hasattr(CONFIG, "copy") else dict(CONFIG)

    # 2) CLI 덮어쓰기 (나중에 YAML이 이걸 덮을 수 있음)
    if args.sub_name is not None:
        cfg["sub_name"] = args.sub_name
    if args.APP is not None:
        cfg["APP"] = args.APP
    if args.symmetric is not None:
        cfg["symmetric"] = args.symmetric
    if args.task_type is not None:
        cfg["task_type"] = args.task_type
    if args.trial_range is not None:
        cfg["trial_range"] = list(args.trial_range)
    if args.task_range is not None:
        cfg["task_range"] = list(args.task_range)
    if args.print_time is not None:
        cfg["print_time"] = args.print_time
    if args.run is not None:
        steps = [s.strip() for s in args.run.split(",") if s.strip()]
        run_dict = {k: False for k in ["extload_set", "ik", "so_set", "so", "bk_set", "bk", "jr_set", "jr", "jr_ground_app4"]}
        for s in steps:
            if s in run_dict:
                run_dict[s] = True
        cfg["run"] = run_dict

    # 3) YAML이 있으면 YAML 값으로 최종 덮어쓰기 (최우선)
    if args.config:
        config_path = args.config
        if not os.path.isfile(config_path):
            # 현재 디렉터리에서 못 찾으면 스크립트 위치(c_Run Tools) 기준으로 재시도
            _script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path_alt = os.path.join(_script_dir, os.path.normpath(args.config))
            if os.path.isfile(config_path_alt):
                config_path = config_path_alt
        if not os.path.isfile(config_path):
            raise FileNotFoundError(f"설정 파일 없음: {args.config}")
        yaml_cfg = load_config_from_yaml(config_path)
        for k, v in yaml_cfg.items():
            cfg[k] = v

    return cfg, _gpf


def main():
    args = _parse_args()
    cfg, get_path_from_config = _config_from_args(args)
    if args.no_run:
        print("Config loaded (--no_run):", {k: v for k, v in cfg.items() if k not in ("run",)})
        if cfg.get("run"):
            print("run:", cfg["run"])
        return

    path_base = get_path_from_config(cfg)
    pipeline = OpenSimPipeline(path_base=path_base)
    kg_bpm = cfg.get("kg_bpm", ["15_10"])
    trial_range = tuple(cfg.get("trial_range", [1, 3]))
    task_range = tuple(cfg.get("task_range", [6, 11]))
    print_time = cfg.get("print_time", False)
    run_opts = cfg.get("run") or {}

    if not run_opts:
        run_opts = {"so": True}

    if run_opts.get("extload_set"):
        pipeline.run_extload_set(kg_bpm, trial_range, task_range)
    if run_opts.get("ik"):
        pipeline.run_ik(kg_bpm, trial_range, task_range, print_time=print_time)
    if run_opts.get("so_set"):
        pipeline.run_so_set(kg_bpm, trial_range, task_range)
    if run_opts.get("so"):
        pipeline.run_so(kg_bpm, trial_range, task_range, print_time=print_time)
    if run_opts.get("bk_set"):
        pipeline.run_bk_set(kg_bpm, trial_range, task_range)
    if run_opts.get("bk"):
        pipeline.run_bk(kg_bpm, trial_range, task_range)
    if run_opts.get("jr_set"):
        pipeline.run_jr_set(kg_bpm, trial_range, task_range)
    if run_opts.get("jr"):
        pipeline.run_jr(
            kg_bpm, trial_range, task_range,
            run_ground_for_app4=run_opts.get("jr_ground_app4", False),
            print_time=print_time,
        )


def run_with_init_config():
    """
    YAML/argparse 없이 __init__.py CONFIG만으로 파이프라인 실행.
    IDE에서 직접 호출하거나, 다른 스크립트에서 from OpenSim_Pipeline import run_with_init_config; run_with_init_config()
    """
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from __init__ import CONFIG, get_path_from_config, update_config
    except ImportError:
        CONFIG = {"root_dir": r"E:\Dropbox\SEL\BOX\OpenSim\_Main_\c_AddBio_Continous", "sub_name": "SUB1", "APP": "APP2_preRiCTO", "symmetric": True}
        def get_path_from_config(cfg):
            from PipelinePathSetting import SymmetricOneCyclePath
            return SymmetricOneCyclePath.from_config(cfg)
        def update_config(**kw):
            CONFIG.update(kw)

    update_config(sub_name="SUB1", symmetric=True, task_type="OneCycle")
    path_base = get_path_from_config(CONFIG)
    pipeline = OpenSimPipeline(path_base=path_base)
    kg_bpm = CONFIG.get("kg_bpm", ["15_10"])
    trial_range = (1, 2)
    task_range = (1, 11)
    # pipeline.run_extload_set(kg_bpm, trial_range, task_range)
    # pipeline.run_bk(kg_bpm, trial_range, task_range)
    pipeline.run_jr(kg_bpm, trial_range, task_range)


if __name__ == "__main__":
    main()
