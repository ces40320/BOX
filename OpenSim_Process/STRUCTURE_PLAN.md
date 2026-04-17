# OpenSim_Process Structure Plan

아래는 `OpenSim/_Main_/c_AddBio_Continous/STRUCTURE_GUIDE.md`의 `0) New structure plan` 구간(5-147줄)을 기준으로 정리한 `OpenSim_Process` 구조 계획안입니다.

> 아래 구조는 `PATH_RULE.py`의 `ResultPaths` 클래스 메서드들이 자동 생성하는 디렉토리/파일명 규칙과 일치함.

> **Model variant ↔ condition kg 매칭 규칙 (b_Build_Model 산출물 기준)**
>
> `Codes/b_Build_Model/` 의 `add_hand_mass_model.py`, `add_box_weldjoint_model.py` 는
> 피험자 `conditions` 키 prefix (`7kg`, `10kg`, `15kg`) 에서 박스 무게 후보 `w_kg` 를
> 자동 추출하여 다음 osim 파일들을 **kg 별로 각각** 생성한다.
>
> - `SUB{n}_Scaled.osim`                          ← 베이스 (kg 무관)
> - `SUB{n}_Scaled_HeavyHand_{w}kg.osim`          ← 각 손에 `w/2 kg` 추가
> - `SUB{n}_Scaled_WeldBox_{w}kg.osim`            ← `ADDBOXtoOSIM(Constraint=True)`
> - `SUB{n}_Scaled_SplitBox_{w}kg.osim`           ← `ADDBOXtoOSIM(Constraint=False)`
>
> 따라서 `<Condition>` (예: `7kg_10bpm`) 의 kg prefix 와 사용할 모델의 kg suffix 는
> **반드시 일치**해야 한다. 즉 `7kg_10bpm` 하위 분석은 `..._HeavyHand_7kg.osim` /
> `..._WeldBox_7kg.osim` / `..._SplitBox_7kg.osim` 만을 사용한다.

## Planned structure

```Mermaid
OpenSim_Process
└─ _Main_/
  ├─ Symmetric/
  │  └─ SUB1/
  │    ├─ Model_osim/                              # SUB1 conditions = {7kg_*, 15kg_*}  ⇒ w_kg ∈ {7, 15}
  │    │  ├─ SUB1_Scaled.osim
  │    │  ├─ SUB1_Scaled_HeavyHand_7kg.osim
  │    │  ├─ SUB1_Scaled_HeavyHand_15kg.osim
  │    │  ├─ SUB1_Scaled_WeldBox_7kg.osim
  │    │  ├─ SUB1_Scaled_WeldBox_15kg.osim
  │    │  ├─ SUB1_Scaled_SplitBox_7kg.osim
  │    │  └─ SUB1_Scaled_SplitBox_15kg.osim
  │    ├─ 7kg_10bpm_trial1/
  │    │  ├─ Up/
  │    │  │  ├─ Markers/
  │    │  │  │  └─ SUB1_7kg_10bpm_trial1_1U.trc
  │    │  │  ├─ ExtLoad/
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_1U_ExtLoad_MeasuredEHF.mot
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_1U_ExtLoad_HeavyHand.mot
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_1U_ExtLoad_AddBox.mot
  │    │  │  │  ├─ SETUP_ExtLoad_7kg_10bpm_trial1_1U_MeasuredEHF.xml
  │    │  │  │  ├─ SETUP_ExtLoad_7kg_10bpm_trial1_1U_HeavyHand.xml
  │    │  │  │  └─ SETUP_ExtLoad_7kg_10bpm_trial1_1U_AddBox.xml
  │    │  │  ├─ IK/
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_1U_IK.mot
  │    │  │  │  └─ SETUP_IK_7kg_10bpm_trial1_1U.xml
  │    │  │  ├─ IK_AddBox/
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_1U_AddBox_IK.mot
  │    │  │  │  └─ SETUP_IK_7kg_10bpm_trial1_1U_AddBox.xml
  │    │  │  ├─ BK/
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_1U_BodyKinematics_pos_global.sto
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_1U_BodyKinematics_vel_global.sto
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_1U_BodyKinematics_acc_global.sto
  │    │  │  │  └─ SETUP_BK_7kg_10bpm_trial1_1U.xml
  │    │  │  ├─ SO_MeasuredEHF/
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_1U_MeasuredEHF_StaticOptimization_activation.sto
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_1U_MeasuredEHF_StaticOptimization_force.sto
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_1U_MeasuredEHF_StaticOptimization_control.xml
  │    │  │  │  └─ SETUP_SO_7kg_10bpm_trial1_1U_MeasuredEHF.xml
  │    │  │  ├─ SO_HeavyHand/
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_1U_HeavyHand_StaticOptimization_activation.sto
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_1U_HeavyHand_StaticOptimization_force.sto
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_1U_HeavyHand_StaticOptimization_control.xml
  │    │  │  │  └─ SETUP_SO_7kg_10bpm_trial1_1U_HeavyHand.xml
  │    │  │  ├─ SO_AddBox/
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_1U_AddBox_StaticOptimization_activation.sto
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_1U_AddBox_StaticOptimization_force.sto
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_1U_AddBox_StaticOptimization_control.xml
  │    │  │  │  └─ SETUP_SO_7kg_10bpm_trial1_1U_AddBox.xml
  │    │  │  ├─ JR_MeasuredEHF/
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_1U_MeasuredEHF_JointReaction_ReactionLoads.sto
  │    │  │  │  └─ SETUP_JR_7kg_10bpm_trial1_1U_MeasuredEHF.xml
  │    │  │  ├─ JR_HeavyHand/
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_1U_HeavyHand_JointReaction_ReactionLoads.sto
  │    │  │  │  └─ SETUP_JR_7kg_10bpm_trial1_1U_HeavyHand.xml
  │    │  │  └─ JR_AddBox/
  │    │  │     ├─ SUB1_7kg_10bpm_trial1_1U_AddBox_JointReaction_ReactionLoads.sto
  │    │  │     ├─ SUB1_7kg_10bpm_trial1_1U_AddBox_JointReaction_ReactionLoads_ground.sto
  │    │  │     └─ SETUP_JR_7kg_10bpm_trial1_1U_AddBox_ground.xml
  │    │  │     └─ SETUP_JR_7kg_10bpm_trial1_1U_AddBox.xml
  │    │  └─ Down/ (하위 생략)
  │    ├─ 7kg_10bpm_trial2/ (하위 생략)
  │    ├─ 15kg_10bpm_trial1/ (하위 생략)
  │    ├─ 15kg_10bpm_trial2/ (하위 생략)
  │    ├─ 7kg_16bpm_trial1/ (하위 생략)
  │    ├─ 7kg_16bpm_trial2/ (하위 생략)
  │    ├─ 15kg_16bpm_trial1/ (하위 생략)
  │    └─ 15kg_16bpm_trial2/ (하위 생략)
  └─ Asymmetric
    ├─ SUB2/
    │  ├─ Model_osim/                              # SUB2 conditions = {7kg_*, 15kg_*}  ⇒ w_kg ∈ {7, 15}
    │  │  ├─ SUB2_Scaled.osim
    │  │  ├─ SUB2_Scaled_HeavyHand_7kg.osim
    │  │  ├─ SUB2_Scaled_HeavyHand_15kg.osim
    │  │  ├─ SUB2_Scaled_WeldBox_7kg.osim
    │  │  ├─ SUB2_Scaled_WeldBox_15kg.osim
    │  │  ├─ SUB2_Scaled_SplitBox_7kg.osim
    │  │  └─ SUB2_Scaled_SplitBox_15kg.osim
    │  ├─ 7kg_10bpm/
    │  │  ├─ AB/
    │  │  │  ├─ Markers/
    │  │  │  │  └─ SUB2_7kg_10bpm_1AB.trc
    │  │  │  ├─ ExtLoad/
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_ExtLoad_MeasuredEHF.mot
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_ExtLoad_HeavyHand.mot
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_ExtLoad_AddBox.mot      (미정)
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_ExtLoad_PreRiCTO.mot
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_ExtLoad_PostRiCTO.mot
    │  │  │  │  ├─ SETUP_ExtLoad_7kg_10bpm_1AB_MeasuredEHF.xml
    │  │  │  │  ├─ SETUP_ExtLoad_7kg_10bpm_1AB_HeavyHand.xml
    │  │  │  │  ├─ SETUP_ExtLoad_7kg_10bpm_1AB_AddBox.xml     (미정)
    │  │  │  │  ├─ SETUP_ExtLoad_7kg_10bpm_1AB_PreRiCTO.xml
    │  │  │  │  └─ SETUP_ExtLoad_7kg_10bpm_1AB_PostRiCTO.xml
    │  │  │  ├─ IK/
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_IK.mot
    │  │  │  │  └─ SETUP_IK_7kg_10bpm_1AB.xml
    │  │  │  ├─ BK/
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_BodyKinematics_pos_global.sto
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_BodyKinematics_vel_global.sto
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_BodyKinematics_acc_global.sto
    │  │  │  │  └─ SETUP_BK_7kg_10bpm_1AB.xml
    │  │  │  ├─ SO_MeasuredEHF/
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_MeasuredEHF_StaticOptimization_activation.sto
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_MeasuredEHF_StaticOptimization_force.sto
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_MeasuredEHF_StaticOptimization_control.xml
    │  │  │  │  └─ SETUP_SO_7kg_10bpm_1AB_MeasuredEHF.xml
    │  │  │  ├─ SO_HeavyHand/
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_HeavyHand_StaticOptimization_activation.sto
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_HeavyHand_StaticOptimization_force.sto
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_HeavyHand_StaticOptimization_control.xml
    │  │  │  │  └─ SETUP_SO_7kg_10bpm_1AB_HeavyHand.xml
    │  │  │  ├─ SO_PreRiCTO/
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_PreRiCTO_StaticOptimization_activation.sto
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_PreRiCTO_StaticOptimization_force.sto
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_PreRiCTO_StaticOptimization_control.xml
    │  │  │  │  └─ SETUP_SO_7kg_10bpm_1AB_PreRiCTO.xml
    │  │  │  ├─ SO_PostRiCTO/
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_PostRiCTO_StaticOptimization_activation.sto
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_PostRiCTO_StaticOptimization_force.sto
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_PostRiCTO_StaticOptimization_control.xml
    │  │  │  │  └─ SETUP_SO_7kg_10bpm_1AB_PostRiCTO.xml
    │  │  │  ├─ JR_MeasuredEHF/
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_MeasuredEHF_JointReaction_ReactionLoads.sto
    │  │  │  │  └─ SETUP_JR_7kg_10bpm_1AB_MeasuredEHF.xml
    │  │  │  ├─ JR_HeavyHand/
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_HeavyHand_JointReaction_ReactionLoads.sto
    │  │  │  │  └─ SETUP_JR_7kg_10bpm_1AB_HeavyHand.xml
    │  │  │  ├─ JR_PreRiCTO/
    │  │  │  │  ├─ SUB2_7kg_10bpm_1AB_PreRiCTO_JointReaction_ReactionLoads.sto
    │  │  │  │  └─ SETUP_JR_7kg_10bpm_1AB_PreRiCTO.xml
    │  │  │  └─ JR_PostRiCTO/
    │  │  │     ├─ SUB2_7kg_10bpm_1AB_PostRiCTO_JointReaction_ReactionLoads.sto
    │  │  │     └─ SETUP_JR_7kg_10bpm_1AB_PostRiCTO.xml
    │  │  ├─ BC/ (하위 생략)
    │  │  └─ CA/ (하위 생략)
    │  ├─ 15kg_10bpm/ (하위 생략)
    │  ├─ 7kg_16bpm/ (하위 생략)
    │  └─ 15kg_16bpm/ (하위 생략)
    └─ SUB3/                                       # SUB3 conditions = {7kg_*, 10kg_*}  ⇒ w_kg ∈ {7, 10}
      ├─ Model_osim/
      │  ├─ SUB3_Scaled.osim
      │  ├─ SUB3_Scaled_HeavyHand_7kg.osim
      │  ├─ SUB3_Scaled_HeavyHand_10kg.osim
      │  ├─ SUB3_Scaled_WeldBox_7kg.osim
      │  ├─ SUB3_Scaled_WeldBox_10kg.osim
      │  ├─ SUB3_Scaled_SplitBox_7kg.osim
      │  └─ SUB3_Scaled_SplitBox_10kg.osim
      ├─ 7kg_10bpm/   (하위 생략, HeavyHand_7kg / WeldBox_7kg / SplitBox_7kg 모델 사용)
      ├─ 10kg_10bpm/  (하위 생략, HeavyHand_10kg / WeldBox_10kg / SplitBox_10kg 모델 사용)
      ├─ 7kg_16bpm/   (하위 생략)
      └─ 10kg_16bpm/  (하위 생략)
```

## Notes on kg-aware model resolution

1. **Condition prefix → model variant**
   `<Condition>` 의 첫 토큰이 `{w}kg` 형식이면, 해당 condition 의 모든 분석은
   `Model_osim/SUB{n}_Scaled_<Variant>_{w}kg.osim` (Variant ∈ {HeavyHand, WeldBox, SplitBox})
   에서 골라 사용한다. 베이스 모델(`SUB{n}_Scaled.osim`) 은 IK 등 박스/손 질량 보정이
   불필요한 분석에만 사용한다.

2. **App ↔ model variant 매핑 (현 시점 합의안)**

   | App (folder suffix)  | 사용 모델 (`{w}` = condition kg)        | 비고                     |
   |----------------------|-----------------------------------------|--------------------------|
   | `MeasuredEHF`        | `SUB{n}_Scaled.osim`                    | EHF 외력만, 부가질량 없음 |
   | `HeavyHand`          | `SUB{n}_Scaled_HeavyHand_{w}kg.osim`    | 손 추가질량              |
   | `AddBox` *(미정)*    | `SUB{n}_Scaled_WeldBox_{w}kg.osim`  *or* `..._SplitBox_{w}kg.osim` | (ASSUMPTION) 단일 `AddBox` 앱이 두 variant 중 어느 것을 쓰는지, 또는 두 variant 를 별도 app 으로 분리할지 정책 필요 |
   | `preRiCTO/postRiCTO` | `SUB{n}_Scaled.osim`                    | 베이스 모델 사용 — RiCTO 분기는 모델이 아니라 외력/세팅 단에서 처리 (상세 근거는 추후 보강) |

3. **(ASSUMPTION)** 위 (2) 의 `AddBox` 항목은 `config_methods.PROTOCOL_Candidates` 의
   `APPs` 목록과 모델 variant 의 1:1 매핑이 아직 명시되지 않았기 때문에 미정이다.
   해소 옵션:
    - (a) `APPs` 를 `WeldBox`, `SplitBox` 두 항목으로 분리 → 폴더가
      `SO_WeldBox/`, `JR_WeldBox/`, `SO_SplitBox/`, `JR_SplitBox/` 로 분기됨.
    - (b) `AddBox` 단일 앱 유지하되 정책 모듈에서 한 variant 만 선택.
   결정 시 본 문서와 `Codes/c_Run_Tools/REFAC_RUN_TOOLS_PLAN.md` 양측 동시 갱신.
