"""Model_osim 디렉토리 내 raw AddBiomech 산출물(.osim) 이름 정규화.

Assumption
----------
AddBiomech 파이프라인이 각 피험자의 ``…/Model_osim/`` 폴더에
``match_markers_but_ignore_physics.osim`` 파일을 생성한다.

Action
------
1. 해당 파일을 ``PATH_RULE.ResultPaths.model_name()`` 규칙
   (즉 ``SUB{num}_Scaled.osim``) 으로 이름 변경한다.
2. ``add_actuators=True`` (기본) 인 경우 동일 파일에 reserve / residual /
   torque ``CoordinateActuator`` 세트를 즉시 주입한다 (파일명 변경 없음).
   이로써 downstream SO·JR 핸들러가 별도의 ``_Actuator.osim`` 없이 동일
   ``SUB{n}_Scaled.osim`` 을 그대로 사용할 수 있다.
"""

import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CODES_DIR = os.path.dirname(THIS_DIR)
if CODES_DIR not in sys.path:
    sys.path.insert(0, CODES_DIR)

import SUB_Info as _sub_info
from PATH_RULE import ResultPaths

from add_reserve_actuators import add_reserve_actuators


RAW_MODEL_NAME = "match_markers_but_ignore_physics.osim"


def rename_scaled_model(namecode: str, *,
                        overwrite: bool = False,
                        add_actuators: bool = True) -> str | None:
    """단일 피험자의 raw 모델을 ``SUB{num}_Scaled.osim`` 으로 rename.

    Parameters
    ----------
    namecode : str
        ``SUB_Info.subjects`` 의 키 (e.g. ``"260306_KTY"``).
    overwrite : bool, default False
        대상 ``*_Scaled.osim`` 이 이미 존재할 때 raw 파일로 다시 덮어쓸지 여부.
    add_actuators : bool, default True
        rename 직후 (또는 이미 존재하는 ``*_Scaled.osim`` 에도 idempotent
        하게) reserve/residual/torque ``CoordinateActuator`` 세트를 모델
        파일에 주입할지 여부.  주입은 ``add_reserve_actuators`` 가 모델 내
        sentinel 액추에이터 (``residual_pelvis_tx``) 존재 여부로 중복을
        방지한다.

    Returns
    -------
    str or None
        생성/확인된 최종 ``*_Scaled.osim`` 경로. raw 파일도 없고
        최종 파일도 존재하지 않으면 ``None``.
    """
    rp = ResultPaths(namecode)
    src = os.path.join(rp.model_dir, RAW_MODEL_NAME)
    dst = rp.model_path()

    final: str | None
    if not os.path.exists(src):
        if os.path.exists(dst):
            print(f"[SKIP] {namecode}: raw not found, target exists -> {dst}")
            final = dst
        else:
            print(f"[MISSING] {namecode}: {src}")
            return None
    else:
        if os.path.exists(dst):
            if not overwrite:
                print(f"[EXISTS] {namecode}: target already present -> {dst} "
                      f"(overwrite=True 로 호출 시 교체)")
                final = dst
            else:
                os.remove(dst)
                os.replace(src, dst)
                print(f"[RENAMED] {namecode}: {os.path.basename(src)} "
                      f"-> {os.path.basename(dst)}")
                final = dst
        else:
            os.replace(src, dst)
            print(f"[RENAMED] {namecode}: {os.path.basename(src)} "
                  f"-> {os.path.basename(dst)}")
            final = dst

    if add_actuators and final is not None:
        # Idempotent: skipped silently when sentinel actuator already present.
        # ``overwrite`` is intentionally NOT propagated — re-renaming the raw
        # file already yields a fresh osim without actuators, so the injector
        # always runs on a clean slate in that path.
        add_reserve_actuators(final)

    return final


def rename_all(namecodes: list[str] | None = None,
               *, overwrite: bool = False,
               add_actuators: bool = True) -> dict[str, str | None]:
    """여러 피험자 일괄 rename (+ 옵션 actuator 주입)."""
    if namecodes is None:
        namecodes = list(_sub_info.subjects.keys())
    return {nc: rename_scaled_model(nc, overwrite=overwrite,
                                    add_actuators=add_actuators)
            for nc in namecodes}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namecode", default=None,
                        help="단일 피험자 namecode (생략 시 전체 일괄 처리)")
    parser.add_argument("--overwrite", action="store_true",
                        help="대상 파일이 이미 있으면 덮어쓰기")
    parser.add_argument("--no-actuators", action="store_true",
                        help="reserve/residual/torque CoordinateActuator 주입 단계를 건너뜀")
    args = parser.parse_args()

    add_actuators = not args.no_actuators
    if args.namecode:
        rename_scaled_model(args.namecode, overwrite=args.overwrite,
                            add_actuators=add_actuators)
    else:
        rename_all(overwrite=args.overwrite, add_actuators=add_actuators)
