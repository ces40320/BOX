# OpenSim_Process Structure Plan

아래는 `OpenSim/_Main_/c_AddBio_Continous/STRUCTURE_GUIDE.md`의 `0) New structure plan` 구간(5-147줄)을 기준으로 정리한 `OpenSim_Process` 구조 계획안입니다.

> 아래 구조는 `PATH_RULE.py`의 `ResultPaths` 클래스 메서드들이 자동 생성하는 디렉토리/파일명 규칙과 일치함.

## Planned structure

```Mermaid
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
    │  ├─ Model_osim/
    │  │  ├─ SUB2_Scaled.osim
    │  │  ├─ SUB2_Scaled_HeavyHand.osim
    │  │  ├─ SUB2_Scaled_WeldBox.osim  (미정)
    │  │  └─ SUB2_Scaled_SplitBox.osim (미정)
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
    └─ SUB3/ (하위 생략)
      ├─ Model_osim/ (하위 생략)
      ├─ 7kg_10bpm/ (하위 생략)
      ├─ 10kg_10bpm/ (하위 생략)
      ├─ 7kg_16bpm/ (하위 생략)
      └─ 10kg_16bpm/ (하위 생략)
```
