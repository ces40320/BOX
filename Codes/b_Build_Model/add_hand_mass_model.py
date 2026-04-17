"""``SUB{num}_Scaled.osim`` → ``SUB{num}_Scaled_HeavyHand_{w}kg.osim`` 생성.

각 피험자의 conditions (``7kg_*``, ``10kg_*``, ``15kg_*``) 로부터 박스 총 무게
후보(w_kg ∈ {7, 10, 15}) 를 수집하고, 각 무게의 절반(w/2)을
``hand_l`` / ``hand_r`` 바디의 질량(mass)에 더해 새 모델 파일로 저장한다.

Note
----
- .osim 은 XML 형식이지만 OpenSim API(``osim.Body.setMass``)로 수정하는 편이
  안전하여 그대로 사용한다.
- conditions 키의 prefix(`7kg`, `10kg`, `15kg`)를 그대로 무게 후보로 사용.
  → 남성(15kg)·여성(10kg) 구분은 SUB_Info 의 conditions 구성에 이미 반영됨.
"""

import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CODES_DIR = os.path.dirname(THIS_DIR)
if CODES_DIR not in sys.path:
    sys.path.insert(0, CODES_DIR)

_OSIM_DLL_DIR = "C:/OpenSim 4.5/bin"
if hasattr(os, "add_dll_directory") and os.path.isdir(_OSIM_DLL_DIR):
    os.add_dll_directory(_OSIM_DLL_DIR)

import opensim as osim

import SUB_Info as _sub_info
from PATH_RULE import ResultPaths


def box_weights_from_conditions(conditions: dict) -> list[int]:
    """condition 키 prefix(``"7kg"``, ``"10kg"``, ``"15kg"``) 에서 유니크 무게(kg) 추출."""
    weights = set()
    for key in conditions:
        prefix = key.split("_", 1)[0]
        if prefix.endswith("kg") and prefix[:-2].isdigit():
            weights.add(int(prefix[:-2]))
    return sorted(weights)


def add_hand_mass(model_path_in: str, model_path_out: str,
                  mass_per_hand_kg: float) -> str:
    """hand_l / hand_r 바디 각각에 ``mass_per_hand_kg`` 을 더해 저장."""
    if not os.path.isfile(model_path_in):
        raise FileNotFoundError(model_path_in)
    os.makedirs(os.path.dirname(model_path_out), exist_ok=True)

    model = osim.Model(model_path_in)
    for body_name in ("hand_l", "hand_r"):
        body = model.getBodySet().get(body_name)
        body.setMass(body.getMass() + float(mass_per_hand_kg))
    model.finalizeConnections()
    model.printToXML(model_path_out)
    return model_path_out


def build_heavyhand_models(namecode: str,
                           *, overwrite: bool = True) -> list[str]:
    """피험자 1명에 대해 조건별 HeavyHand osim 모델 일괄 생성.

    Returns
    -------
    list[str]
        생성(또는 스킵)된 osim 경로 리스트.
    """
    info = _sub_info.subjects[namecode]
    rp = ResultPaths(namecode)
    src = rp.model_path()
    if not os.path.exists(src):
        raise FileNotFoundError(
            f"Base model not found: {src}. rename_AddBiomech_model.py 선행 필요.")

    outputs: list[str] = []
    for w_kg in box_weights_from_conditions(info["conditions"]):
        per_hand = w_kg / 2.0
        dst = rp.model_path(f"HeavyHand_{w_kg}kg")
        if os.path.exists(dst) and not overwrite:
            print(f"[SKIP] {namecode}: {os.path.basename(dst)} already exists")
            outputs.append(dst)
            continue
        add_hand_mass(src, dst, per_hand)
        print(f"[HeavyHand] {namecode}: +{per_hand}kg/hand -> {os.path.basename(dst)}")
        outputs.append(dst)
    return outputs


def build_all(namecodes: list[str] | None = None,
              *, overwrite: bool = True) -> dict[str, list[str]]:
    if namecodes is None:
        namecodes = list(_sub_info.subjects.keys())
    return {nc: build_heavyhand_models(nc, overwrite=overwrite) for nc in namecodes}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namecode", default=None)
    parser.add_argument("--no-overwrite", action="store_true",
                        help="이미 존재하면 스킵")
    args = parser.parse_args()

    overwrite = not args.no_overwrite
    if args.namecode:
        build_heavyhand_models(args.namecode, overwrite=overwrite)
    else:
        build_all(overwrite=overwrite)
