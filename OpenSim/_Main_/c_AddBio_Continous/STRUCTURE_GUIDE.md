# c_AddBio_Continous Folder/File Structure Guide

이 문서는 `OpenSim/_Main_/c_AddBio_Continous` 내부의 폴더 구조와 파일명 규칙을 정리한 가이드입니다.

## 0) New structure plan
```text
OpenSim_Process
└─ _Main_/
  ├─ Symmetric/
  │  └─ SUB1/
  │    ├─ Model_osim/
  │    │  ├─ SUB1_Scaled.osim
  │    │  ├─ SUB1_Scaled_HeavyHand.osim
  │    │  ├─ SUB1_Scaled_WeldBox.osim
  │    │  └─ SUB1_Scaled_SplitBox.osim
  │    ├─ 7kg_10bpm_trial1/
  │    │  ├─ Up/
  │    │  │  ├─ Markers/
  │    │  │  │  └─ SUB1_7kg_10bpm_trial1_U1.trc
  │    │  │  ├─ ExtLoad/
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_U1_ExtLoad_MeasuredEHF.mot
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_U1_ExtLoad_HeavyHand.mot
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_U1_ExtLoad_AddBox.mot
  │    │  │  │  ├─ SETUP_ExtLoad_7kg_10bpm_trial1_U1_MeasuredEHF.xml
  │    │  │  │  ├─ SETUP_ExtLoad_7kg_10bpm_trial1_U1_HeavyHand.xml
  │    │  │  │  └─ SETUP_ExtLoad_7kg_10bpm_trial1_U1_AddBox.xml
  │    │  │  ├─ IK/
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_U1_IK.mot
  │    │  │  │  └─ SETUP_IK_7kg_10bpm_trial1_U1.xml
  │    │  │  ├─ IK_AddBox/
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_U1_AddBox_IK.mot
  │    │  │  │  └─ SETUP_IK_7kg_10bpm_trial1_U1_AddBox.xml
  │    │  │  ├─ BK/
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_U1_BodyKinematics_pos_global.sto
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_U1_BodyKinematics_vel_global.sto
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_U1_BodyKinematics_acc_global.sto
  │    │  │  │  └─ SETUP_BK_7kg_10bpm_trial1_U1.xml
  │    │  │  ├─ SO_MeasuredEHF/
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_U1_MeasuredEHF_StaticOptimization_activation.sto
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_U1_MeasuredEHF_StaticOptimization_force.sto
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_U1_MeasuredEHF_StaticOptimization_control.xml
  │    │  │  │  └─ SETUP_SO_7kg_10bpm_trial1_U1_MeasuredEHF.xml
  │    │  │  ├─ SO_HeavyHand/
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_U1_HeavyHand_StaticOptimization_activation.sto
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_U1_HeavyHand_StaticOptimization_force.sto
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_U1_HeavyHand_StaticOptimization_control.xml
  │    │  │  │  └─ SETUP_SO_7kg_10bpm_trial1_U1_HeavyHand.xml
  │    │  │  ├─ SO_AddBox/
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_U1_AddBox_StaticOptimization_activation.sto
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_U1_AddBox_StaticOptimization_force.sto
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_U1_AddBox_StaticOptimization_control.xml
  │    │  │  │  └─ SETUP_SO_7kg_10bpm_trial1_U1_AddBox.xml
  │    │  │  ├─ JR_MeasuredEHF/
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_U1_MeasuredEHF_JointReaction_ReactionLoads.sto
  │    │  │  │  └─ SETUP_JR_7kg_10bpm_trial1_U1_MeasuredEHF.xml
  │    │  │  ├─ JR_HeavyHand/
  │    │  │  │  ├─ SUB1_7kg_10bpm_trial1_U1_HeavyHand_JointReaction_ReactionLoads.sto
  │    │  │  │  └─ SETUP_JR_7kg_10bpm_trial1_U1_HeavyHand.xml
  │    │  │  └─ JR_AddBox/
  │    │  │     ├─ SUB1_7kg_10bpm_trial1_U1_AddBox_JointReaction_ReactionLoads.sto
  │    │  │     ├─ SUB1_7kg_10bpm_trial1_U1_AddBox_JointReaction_ReactionLoads_ground.sto
  │    │  │     └─ SETUP_JR_7kg_10bpm_trial1_U1_AddBox_ground.xml
  │    │  │     └─ SETUP_JR_7kg_10bpm_trial1_U1_AddBox.xml
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
    │  ├─ Model_osim/
    │  │  ├─ SUB2_Scaled.osim
    │  │  ├─ SUB2_Scaled_HeavyHand.osim
    │  │  ├─ SUB2_Scaled_WeldBox.osim  (미정)
    │  │  └─ SUB2_Scaled_SplitBox.osim (미정)
    │  ├─ 7kg_10bpm/
    │  │  ├─ AB/
    │  │  │  ├─ Markers/
    │  │  │  │  └─ SUB2_7kg_10bpm_AB1.trc
    │  │  │  ├─ ExtLoad/
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_ExtLoad_MeasuredEHF.mot
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_ExtLoad_HeavyHand.mot
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_ExtLoad_AddBox.mot      (미정)
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_ExtLoad_PreRiCTO.mot
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_ExtLoad_PostRiCTO.mot
    │  │  │  │  ├─ SETUP_ExtLoad_7kg_10bpm_AB1_MeasuredEHF.xml
    │  │  │  │  ├─ SETUP_ExtLoad_7kg_10bpm_AB1_HeavyHand.xml
    │  │  │  │  ├─ SETUP_ExtLoad_7kg_10bpm_AB1_AddBox.xml     (미정)
    │  │  │  │  ├─ SETUP_ExtLoad_7kg_10bpm_AB1_PreRiCTO.xml
    │  │  │  │  └─ SETUP_ExtLoad_7kg_10bpm_AB1_PostRiCTO.xml
    │  │  │  ├─ IK/
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_IK.mot
    │  │  │  │  └─ SETUP_IK_7kg_10bpm_AB1.xml
    │  │  │  ├─ BK/
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_BodyKinematics_pos_global.sto
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_BodyKinematics_vel_global.sto
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_BodyKinematics_acc_global.sto
    │  │  │  │  └─ SETUP_BK_7kg_10bpm_AB1.xml
    │  │  │  ├─ SO_MeasuredEHF/
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_MeasuredEHF_StaticOptimization_activation.sto
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_MeasuredEHF_StaticOptimization_force.sto
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_MeasuredEHF_StaticOptimization_control.xml
    │  │  │  │  └─ SETUP_SO_7kg_10bpm_AB1_MeasuredEHF.xml
    │  │  │  ├─ SO_HeavyHand/
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_HeavyHand_StaticOptimization_activation.sto
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_HeavyHand_StaticOptimization_force.sto
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_HeavyHand_StaticOptimization_control.xml
    │  │  │  │  └─ SETUP_SO_7kg_10bpm_AB1_HeavyHand.xml
    │  │  │  ├─ SO_PreRiCTO/
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_PreRiCTO_StaticOptimization_activation.sto
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_PreRiCTO_StaticOptimization_force.sto
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_PreRiCTO_StaticOptimization_control.xml
    │  │  │  │  └─ SETUP_SO_7kg_10bpm_AB1_PreRiCTO.xml
    │  │  │  ├─ SO_PostRiCTO/
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_PostRiCTO_StaticOptimization_activation.sto
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_PostRiCTO_StaticOptimization_force.sto
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_PostRiCTO_StaticOptimization_control.xml
    │  │  │  │  └─ SETUP_SO_7kg_10bpm_AB1_PostRiCTO.xml
    │  │  │  ├─ JR_MeasuredEHF/
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_MeasuredEHF_JointReaction_ReactionLoads.sto
    │  │  │  │  └─ SETUP_JR_7kg_10bpm_AB1_MeasuredEHF.xml
    │  │  │  ├─ JR_HeavyHand/
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_HeavyHand_JointReaction_ReactionLoads.sto
    │  │  │  │  └─ SETUP_JR_7kg_10bpm_AB1_HeavyHand.xml
    │  │  │  ├─ JR_PreRiCTO/
    │  │  │  │  ├─ SUB2_7kg_10bpm_AB1_PreRiCTO_JointReaction_ReactionLoads.sto
    │  │  │  │  └─ SETUP_JR_7kg_10bpm_AB1_PreRiCTO.xml
    │  │  │  └─ JR_PostRiCTO/
    │  │  │     ├─ SUB2_7kg_10bpm_AB1_PostRiCTO_JointReaction_ReactionLoads.sto
    │  │  │     └─ SETUP_JR_7kg_10bpm_AB1_PostRiCTO.xml
    │  │  ├─ BC/ (하위 생략)
    │  │  └─ CA/ (하위 생략)
    │  ├─ 15kg_10bpm/ (하위 생략)
    │  ├─ 7kg_16bpm/ (하위 생략)
    │  └─ 15kg_16bpm/ (하위 생략)
    └─ SUB3/ (하위 생략)
      ├─ Model_osim/ (하위 생략)
      ├─ 7kg_10bpm/ (하위 생략)
      ├─ 10kg_10bpm/ (하위 생략)
      ├─ 7kg_16bpm/ (하위 생략)
      └─ 10kg_16bpm/ (하위 생략)

```

## 1) Top-level structure

현재 확인된 최상위 구조는 아래와 같습니다.

```text
c_AddBio_Continous/
└─ SUB1/
   ├─ UpDown_TrcMot/
   ├─ OneCycle_TrcMot/
   ├─ APP1/
   ├─ APP1_OneCycle/
   ├─ APP2/
   └─ APP3/
```

- 현재 기준으로 `SUB1`만 존재합니다.
- 이후 `SUB2`, `SUB3` 등도 같은 패턴으로 확장될 가능성이 높습니다.

## 2) Subject-level folders (`SUB#`)

- 형식: `SUB{subject_id}`
- 예시: `SUB1`

각 subject 폴더 안에는 크게 2가지 영역이 있습니다.

1. 입력/전처리 모션 데이터  
   - `UpDown_TrcMot`
   - `OneCycle_TrcMot`
2. OpenSim 처리 결과(APP별)  
   - `APP1`, `APP1_OneCycle`, `APP2`, `APP3`

## 3) Motion input folders

### 3.1 `UpDown_TrcMot`

- 예시 파일:
  - `Static.trc`
  - `15_10_trial1_U1.trc`
  - `15_10_trial1_D1.trc`
  - `15_10_trial1_U1_ExtLoadAPP1.mot`
  - `15_10_trial1_U1_ExtLoadAPP2.mot`
  - `15_10_trial1_U1_ExtLoadAPP3.mot`

규칙:

- `trc`: marker trajectory
- `ExtLoadAPP*.mot`: external load data (APP별 분기)
- `U1`/`D1`: Up/Down phase 표시

### 3.2 `OneCycle_TrcMot`

- 예시 파일:
  - `15_10_trial1_12sec_1.trc`
  - `15_10_trial1_12sec_1_ExtLoadAPP1.mot`

규칙:

- one-cycle 구간 기반 입력
- phase 표기 대신 `12sec_{index}` 형태 사용

## 4) APP folders

공통적으로 APP 폴더 안에는 모델 파일(`.osim`)과 trial 폴더가 있습니다.

- 모델 파일 예시:
  - `SUB1_Scaled_AddBiomech_APP1.osim`
  - `SUB1_Scaled_APP1_Actuator.osim`

trial 폴더 형식:

- `trial{condition}_trial{n}`
- 예시: `trial15_10_1`, `trial15_10_2`

trial 폴더 하위 공통 결과 디렉토리:

- `xml_ExtLoad`
- `IK_Results`
- `SO_Results`
- `JR_Results`
- (APP2 전용) `BK_Results`
- (일부) `JR_Results(ground)`

## 5) Result folder naming rules

### 5.1 Setup XML naming

- 일반 형식:
  - `SETUP_{STEP}_{condition}_trial{n}_{phase_or_cycle}_{APP}.xml`

예시:

- `SETUP_ExtLoad_15_10_trial2_U3_APP2.xml`
- `SETUP_IK_15_10_trial1_D8_APP1.xml`
- `SETUP_SO_15_10_trial1_U5_APP4.xml`
- `SETUP_JR_15_10_trial2_U6_APP1_ground.xml`

`STEP` 의미:

- `ExtLoad`: external loads
- `IK`: inverse kinematics
- `SO`: static optimization
- `JR`: joint reaction
- `BK`: body kinematics

### 5.2 Analysis output naming

- 일반 형식:
  - `SUB{sid}_{condition}_{trial}_{phase_or_cycle}_{APP}_{AnalysisType}.{ext}`

예시:

- `SUB1_15_10_2_U1_APP2_StaticOptimization_force.sto`
- `SUB1_15_10_2_U1_APP2_StaticOptimization_controls.xml`
- `SUB1_15_10_2_U1_APP2_JointReaction_ReactionLoads.sto`
- `SUB1_15_10_2_U1_APP2_BodyKinematics_acc_global.sto`
- `SUB1_15_10_2_U1_APP2_BodyKinematics_acc.csv`

추가 표기:

- `_Crop_`가 포함된 파일은 crop된 결과
- `_ground`는 JR ground 기준 setup 파일

## 6) Phase / cycle token conventions

- Up/Down 기반:
  - `U1..U10`, `D1..D10`
- OneCycle 기반:
  - `12sec_1..12sec_10` (구간 index)

## 7) APP-specific notes

- `APP1`, `APP2`:
  - 파일명 APP 번호와 결과 폴더 APP 번호가 대체로 일치
- `APP3`:
  - 모델/ExtLoad/IK는 `APP3` 표기
  - JR/SO 출력은 `APP4` 표기 사용
  - 예: `SETUP_SO_..._APP4.xml`, `..._APP4_StaticOptimization_force.sto`
- `APP1_OneCycle`:
  - 파일명에 `_OneCycle` suffix가 포함됨
  - 예: `SETUP_SO_15_10_trial2_12sec_3_APP1_OneCycle.xml`

## 8) Quick glossary

- `trc`: marker trajectory data
- `mot`: motion/external load input
- `sto`: OpenSim storage output
- `osim`: OpenSim model
- `xml`: OpenSim tool setup file
- `csv`: postprocessed tabular output (예: BK acceleration)

## 9) Summary

핵심적으로 이 구조는 `SUB → APP → trial → step_results`의 계층을 따르며,  
파일명은 `조건(condition) + trial + phase/cycle + APP + 분석타입` 토큰 조합으로 일관되게 구성되어 있습니다.
