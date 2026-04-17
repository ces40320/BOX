"""Model_osim 디렉토리 내 raw AddBiomech 산출물(.osim) 이름 정규화.

Assumption
----------
AddBiomech 파이프라인이 각 피험자의 ``…/Model_osim/`` 폴더에
``match_markers_but_ignore_physics.osim`` 파일을 생성한다.

Action
------
해당 파일을 ``PATH_RULE.ResultPaths.model_name()`` 규칙
(즉 ``SUB{num}_Scaled.osim``)으로 이름 변경한다.
"""

import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CODES_DIR = os.path.dirname(THIS_DIR)
if CODES_DIR not in sys.path:
    sys.path.insert(0, CODES_DIR)

import SUB_Info as _sub_info
from PATH_RULE import ResultPaths


RAW_MODEL_NAME = "match_markers_but_ignore_physics.osim"


def rename_scaled_model(namecode: str, *, overwrite: bool = False) -> str | None:
    """단일 피험자의 raw 모델을 ``SUB{num}_Scaled.osim`` 으로 rename.

    Parameters
    ----------
    namecode : str
        ``SUB_Info.subjects`` 의 키 (e.g. ``"260306_KTY"``).
    overwrite : bool, default False
        대상 파일이 이미 존재할 때 덮어쓸지 여부.

    Returns
    -------
    str or None
        생성/확인된 최종 ``*_Scaled.osim`` 경로. raw 파일도 없고
        최종 파일도 존재하지 않으면 ``None``.
    """
    rp = ResultPaths(namecode)
    src = os.path.join(rp.model_dir, RAW_MODEL_NAME)
    dst = rp.model_path()

    if not os.path.exists(src):
        if os.path.exists(dst):
            print(f"[SKIP] {namecode}: raw not found, target exists -> {dst}")
            return dst
        print(f"[MISSING] {namecode}: {src}")
        return None

    if os.path.exists(dst):
        if not overwrite:
            print(f"[EXISTS] {namecode}: target already present -> {dst} "
                  f"(overwrite=True 로 호출 시 교체)")
            return dst
        os.remove(dst)

    os.replace(src, dst)
    print(f"[RENAMED] {namecode}: {os.path.basename(src)} -> {os.path.basename(dst)}")
    return dst


def rename_all(namecodes: list[str] | None = None,
               *, overwrite: bool = False) -> dict[str, str | None]:
    """여러 피험자 일괄 rename."""
    if namecodes is None:
        namecodes = list(_sub_info.subjects.keys())
    return {nc: rename_scaled_model(nc, overwrite=overwrite) for nc in namecodes}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namecode", default=None,
                        help="단일 피험자 namecode (생략 시 전체 일괄 처리)")
    parser.add_argument("--overwrite", action="store_true",
                        help="대상 파일이 이미 있으면 덮어쓰기")
    args = parser.parse_args()

    if args.namecode:
        rename_scaled_model(args.namecode, overwrite=args.overwrite)
    else:
        rename_all(overwrite=args.overwrite)
