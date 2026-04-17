"""``SUB{num}_Scaled.osim`` → WeldBox/SplitBox osim 모델 일괄 생성.

각 피험자 conditions 에서 수집한 박스 무게(w_kg ∈ {7, 10, 15}) 에 대해
``ADDBOX.ADDBOXtoOSIM`` 을 두 번(Constraint=True/False) 호출하여

    SUB{num}_Scaled_WeldBox_{w}kg.osim     # Constraint=True
    SUB{num}_Scaled_SplitBox_{w}kg.osim    # Constraint=False

파일을 생성한다. 박스 총 질량(``box_total_mass_kg``) 파라미터를 통해
좌/우 반 바디 질량 및 관성이 15kg 기준값에서 선형 스케일 적용된다.
"""

import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CODES_DIR = os.path.dirname(THIS_DIR)
if CODES_DIR not in sys.path:
    sys.path.insert(0, CODES_DIR)
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

import SUB_Info as _sub_info
from PATH_RULE import ResultPaths
from ADDBOX import ADDBOXtoOSIM, DEFAULT_MESH_DIR
from add_hand_mass_model import box_weights_from_conditions


BOX_VARIANTS = (
    ("WeldBox",  True),
    ("SplitBox", False),
)


def build_box_models(namecode: str,
                     *, overwrite: bool = True,
                     mesh_dir: str | None = None) -> list[str]:
    """피험자 1명에 대해 WeldBox/SplitBox × 박스 무게 조합 osim 일괄 생성."""
    info = _sub_info.subjects[namecode]
    rp = ResultPaths(namecode)
    src = rp.model_path()
    if not os.path.exists(src):
        raise FileNotFoundError(
            f"Base model not found: {src}. rename_AddBiomech_model.py 선행 필요.")

    mesh_dir = mesh_dir or DEFAULT_MESH_DIR

    outputs: list[str] = []
    for w_kg in box_weights_from_conditions(info["conditions"]):
        for variant, constraint in BOX_VARIANTS:
            dst = rp.model_path(f"{variant}_{w_kg}kg")
            if os.path.exists(dst) and not overwrite:
                print(f"[SKIP] {namecode}: {os.path.basename(dst)} already exists")
                outputs.append(dst)
                continue
            ADDBOXtoOSIM(
                model_path_input=src,
                model_path_output=dst,
                Constraint=constraint,
                box_total_mass_kg=float(w_kg),
                mesh_dir=mesh_dir,
            )
            print(f"[{variant}] {namecode}: box_total={w_kg}kg -> {os.path.basename(dst)}")
            outputs.append(dst)
    return outputs


def build_all(namecodes: list[str] | None = None,
              *, overwrite: bool = True,
              mesh_dir: str | None = None) -> dict[str, list[str]]:
    if namecodes is None:
        namecodes = list(_sub_info.subjects.keys())
    return {
        nc: build_box_models(nc, overwrite=overwrite, mesh_dir=mesh_dir)
        for nc in namecodes
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namecode", default=None)
    parser.add_argument("--no-overwrite", action="store_true",
                        help="이미 존재하면 스킵")
    parser.add_argument("--mesh-dir", default=None,
                        help=f"박스 STL 위치 (default: {DEFAULT_MESH_DIR})")
    args = parser.parse_args()

    overwrite = not args.no_overwrite
    if args.namecode:
        build_box_models(args.namecode, overwrite=overwrite, mesh_dir=args.mesh_dir)
    else:
        build_all(overwrite=overwrite, mesh_dir=args.mesh_dir)
