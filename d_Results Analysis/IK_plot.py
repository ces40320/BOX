import os; import numpy as np; import pandas as pd
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt

os.chdir(r'E:\Dropbox\SEL\Python functions\OpenSim Analysis\d_Results Analysis')
from Utils import plot_MeanStd, Normalize_IK


## 조건별 데이터 입력

    # 피험자 번호 입력
# input_SUB = input("Which Number of SUB? : ")
# sub_name = 'SUB'+str(input_SUB)
sub_name = 'SUB1'

    # 데이터 로드 위치
root_dir = 'E:\\Dropbox\\SEL\\BOX\\OpenSim\\_Main_' #SUB1\\APP1\\trial10_15_1\\SO_Results\\
APP_li = ['APP1', 'APP2', 'APP4']
kg_bpm = '15_10'
UpDown_li = ['U', 'D']

    # 피규어 저장 위치
savefig_name = ("E:\\Dropbox\\SEL\\BOX\\Analysis\\IK\\"+ sub_name +"\\Figures\\"
                + sub_name +r" Lower Body Joint Angles (APP1,2,4).tif")



## Loading IK Results

for APP in APP_li:
    for UpDown in UpDown_li:
        save_name = sub_name +'_'+ APP +'_'+ UpDown +'_IK'
        locals()[save_name] = Normalize_IK(root_dir, sub_name, APP, kg_bpm, UpDown)



## IK plot (LowerBody)

# %matplotlib tk

fig = plt.figure(figsize=(20,12))
fig.subplots_adjust(left=0.1)
plt.rcParams['axes.xmargin'] = 0.0

ax1 = fig.add_subplot(231)
graph1 = plot_MeanStd(locals()[sub_name+'_APP1_U_IK']['hip_flexion_l'] + locals()[sub_name+'_APP1_U_IK']['hip_flexion_r']/2, Label='APP1', color='black')
graph2 = plot_MeanStd(locals()[sub_name+'_APP2_U_IK']['hip_flexion_l'] + locals()[sub_name+'_APP2_U_IK']['hip_flexion_r']/2, Label='APP2', color='red')
graph3 = plot_MeanStd(locals()[sub_name+'_APP4_U_IK']['hip_flexion_l'] + locals()[sub_name+'_APP4_U_IK']['hip_flexion_r']/2, Label='APP4', color='blue')
plt.title('Lifting Hip', fontsize=20)
plt.xlabel('Time(%)', fontsize=13)
plt.ylabel('Joint Angle(⁰)', fontsize=15)
plt.legend(loc='upper right')
plt.grid()

ax2 = fig.add_subplot(232)
graph4 = plot_MeanStd(locals()[sub_name+'_APP1_U_IK']['knee_angle_l'] + locals()[sub_name+'_APP1_U_IK']['knee_angle_r']/2, Label='APP1', color='black')
graph5 = plot_MeanStd(locals()[sub_name+'_APP2_U_IK']['knee_angle_l'] + locals()[sub_name+'_APP2_U_IK']['knee_angle_r']/2, Label='APP2', color='red')
graph6 = plot_MeanStd(locals()[sub_name+'_APP4_U_IK']['knee_angle_l'] + locals()[sub_name+'_APP4_U_IK']['knee_angle_r']/2, Label='APP4', color='blue')
plt.title('Lifting Knee', fontsize=20)
plt.xlabel('Time(%)', fontsize=13)
# plt.ylabel('Joint Angle(⁰)')
plt.legend(loc='lower right')
plt.grid()

ax3 = fig.add_subplot(233)
graph7 = plot_MeanStd(locals()[sub_name+'_APP1_U_IK']['ankle_angle_l'] + locals()[sub_name+'_APP1_U_IK']['ankle_angle_r']/2, Label='APP1', color='black')
graph8 = plot_MeanStd(locals()[sub_name+'_APP2_U_IK']['ankle_angle_l'] + locals()[sub_name+'_APP2_U_IK']['ankle_angle_r']/2, Label='APP2', color='red')
graph9 = plot_MeanStd(locals()[sub_name+'_APP4_U_IK']['ankle_angle_l'] + locals()[sub_name+'_APP4_U_IK']['ankle_angle_r']/2, Label='APP4', color='blue')
plt.title('Lifting Ankle', fontsize=20)
plt.xlabel('Time(%)', fontsize=13)
# plt.ylabel('Joint Angle(⁰)')
plt.legend(loc='upper right')
plt.grid()

ax4 = fig.add_subplot(234)
graph1 = plot_MeanStd(locals()[sub_name+'_APP1_D_IK']['hip_flexion_l'] + locals()[sub_name+'_APP1_D_IK']['hip_flexion_r']/2, Label='APP1', color='black')
graph2 = plot_MeanStd(locals()[sub_name+'_APP2_D_IK']['hip_flexion_l'] + locals()[sub_name+'_APP2_D_IK']['hip_flexion_r']/2, Label='APP2', color='red')
graph3 = plot_MeanStd(locals()[sub_name+'_APP4_D_IK']['hip_flexion_l'] + locals()[sub_name+'_APP4_D_IK']['hip_flexion_r']/2, Label='APP4', color='blue')
plt.title('Lowering Hip', fontsize=20)
plt.xlabel('Time(%)', fontsize=13)
plt.ylabel('Joint Angle(⁰)', fontsize=15)
plt.legend(loc='lower right')
plt.grid()

ax5 = fig.add_subplot(235)
graph4 = plot_MeanStd(locals()[sub_name+'_APP1_D_IK']['knee_angle_l'] + locals()[sub_name+'_APP1_D_IK']['knee_angle_r']/2, Label='APP1', color='black')
graph5 = plot_MeanStd(locals()[sub_name+'_APP2_D_IK']['knee_angle_l'] + locals()[sub_name+'_APP2_D_IK']['knee_angle_r']/2, Label='APP2', color='red')
graph6 = plot_MeanStd(locals()[sub_name+'_APP4_D_IK']['knee_angle_l'] + locals()[sub_name+'_APP4_D_IK']['knee_angle_r']/2, Label='APP4', color='blue')
plt.title('Lowering Knee', fontsize=20)
plt.xlabel('Time(%)', fontsize=13)
# plt.ylabel('Joint Angle(⁰)')
plt.legend(loc='upper right')
plt.grid()

ax6 = fig.add_subplot(236)
graph7 = plot_MeanStd(locals()[sub_name+'_APP1_D_IK']['ankle_angle_l'] + locals()[sub_name+'_APP1_D_IK']['ankle_angle_r']/2, Label='APP1', color='black')
graph8 = plot_MeanStd(locals()[sub_name+'_APP2_D_IK']['ankle_angle_l'] + locals()[sub_name+'_APP2_D_IK']['ankle_angle_r']/2, Label='APP2', color='red')
graph9 = plot_MeanStd(locals()[sub_name+'_APP4_D_IK']['ankle_angle_l'] + locals()[sub_name+'_APP4_D_IK']['ankle_angle_r']/2, Label='APP4', color='blue')
plt.title('Lowering Ankle', fontsize=20)
plt.xlabel('Time(%)', fontsize=13)
# plt.ylabel('Joint Angle(⁰)')
plt.legend(loc='lower right')
plt.grid()

plt.suptitle('Lower-limb Joint Angles (Sagittal Plane)', weight=1, fontsize = 25)  # suptitle -> sub ㄴㄴ sup ㅇㅇ


plt.savefig(savefig_name)







## IK plot (Wrist)
savefig_name2 = ("E:\\Dropbox\\SEL\\BOX\\Analysis\\IK\\"+ sub_name +"\\Figures\\"
                + sub_name +r" Wrist Joint Angles (APP1,2,4).tif")

# %matplotlib tk

fig = plt.figure(figsize=(20,12))
fig.subplots_adjust(left=0.1)
plt.rcParams['axes.xmargin'] = 0.0

ax1 = fig.add_subplot(231)
graph1 = plot_MeanStd(locals()[sub_name+'_APP1_U_IK']['wrist_flex_l'] + locals()[sub_name+'_APP1_U_IK']['wrist_flex_r']/2, Label='APP1', color='red')
graph2 = plot_MeanStd(locals()[sub_name+'_APP2_U_IK']['wrist_flex_l'] + locals()[sub_name+'_APP2_U_IK']['wrist_flex_r']/2, Label='APP2', color='black')
graph3 = plot_MeanStd(locals()[sub_name+'_APP4_U_IK']['wrist_flex_l'] + locals()[sub_name+'_APP4_U_IK']['wrist_flex_r']/2, Label='APP4', color='blue')
plt.title('Lifting wrist flexion', fontsize=20)
plt.xlabel('Time(%)', fontsize=13)
plt.ylabel('Joint Angle(⁰)', fontsize=15)
plt.legend(loc='upper right')
plt.grid()

ax2 = fig.add_subplot(232)
graph4 = plot_MeanStd(locals()[sub_name+'_APP1_U_IK']['wrist_dev_l'] + locals()[sub_name+'_APP1_U_IK']['wrist_dev_r']/2, Label='APP1', color='red')
graph5 = plot_MeanStd(locals()[sub_name+'_APP2_U_IK']['wrist_dev_l'] + locals()[sub_name+'_APP2_U_IK']['wrist_dev_r']/2, Label='APP2', color='black')
graph6 = plot_MeanStd(locals()[sub_name+'_APP4_U_IK']['wrist_dev_l'] + locals()[sub_name+'_APP4_U_IK']['wrist_dev_r']/2, Label='APP4', color='blue')
plt.title('Lifting wrist ulna dev.', fontsize=20)
plt.xlabel('Time(%)', fontsize=13)
# plt.ylabel('Joint Angle(⁰)')
plt.legend(loc='upper right')
plt.grid()

ax3 = fig.add_subplot(233)
graph7 = plot_MeanStd(locals()[sub_name+'_APP1_U_IK']['pro_sup_l'] + locals()[sub_name+'_APP1_U_IK']['pro_sup_r']/2, Label='APP1', color='red')
graph8 = plot_MeanStd(locals()[sub_name+'_APP2_U_IK']['pro_sup_l'] + locals()[sub_name+'_APP2_U_IK']['pro_sup_r']/2, Label='APP2', color='black')
graph9 = plot_MeanStd(locals()[sub_name+'_APP4_U_IK']['pro_sup_l'] + locals()[sub_name+'_APP4_U_IK']['pro_sup_r']/2, Label='APP4', color='blue')
plt.title('Lifting wrist pronation', fontsize=20)
plt.xlabel('Time(%)', fontsize=13)
# plt.ylabel('Joint Angle(⁰)')
plt.legend(loc='upper right')
plt.grid()

ax4 = fig.add_subplot(234)
graph1 = plot_MeanStd(locals()[sub_name+'_APP1_D_IK']['wrist_flex_l'] + locals()[sub_name+'_APP1_D_IK']['wrist_flex_r']/2, Label='APP1', color='red')
graph2 = plot_MeanStd(locals()[sub_name+'_APP2_D_IK']['wrist_flex_l'] + locals()[sub_name+'_APP2_D_IK']['wrist_flex_r']/2, Label='APP2', color='black')
graph3 = plot_MeanStd(locals()[sub_name+'_APP4_D_IK']['wrist_flex_l'] + locals()[sub_name+'_APP4_D_IK']['wrist_flex_r']/2, Label='APP4', color='blue')
plt.title('Lowering wrist flexion', fontsize=20)
plt.xlabel('Time(%)', fontsize=13)
plt.ylabel('Joint Angle(⁰)', fontsize=15)
plt.legend(loc='upper right')
plt.grid()

ax5 = fig.add_subplot(235)
graph4 = plot_MeanStd(locals()[sub_name+'_APP1_D_IK']['wrist_dev_l'] + locals()[sub_name+'_APP1_D_IK']['wrist_dev_r']/2, Label='APP1', color='red')
graph5 = plot_MeanStd(locals()[sub_name+'_APP2_D_IK']['wrist_dev_l'] + locals()[sub_name+'_APP2_D_IK']['wrist_dev_r']/2, Label='APP2', color='black')
graph6 = plot_MeanStd(locals()[sub_name+'_APP4_D_IK']['wrist_dev_l'] + locals()[sub_name+'_APP4_D_IK']['wrist_dev_r']/2, Label='APP4', color='blue')
plt.title('Lowering wrist ulna dev.', fontsize=20)
plt.xlabel('Time(%)', fontsize=13)
# plt.ylabel('Joint Angle(⁰)')
plt.legend(loc='upper right')
plt.grid()

ax6 = fig.add_subplot(236)
graph7 = plot_MeanStd(locals()[sub_name+'_APP1_D_IK']['pro_sup_l'] + locals()[sub_name+'_APP1_D_IK']['pro_sup_r']/2, Label='APP1', color='red')
graph8 = plot_MeanStd(locals()[sub_name+'_APP2_D_IK']['pro_sup_l'] + locals()[sub_name+'_APP2_D_IK']['pro_sup_r']/2, Label='APP2', color='black')
graph9 = plot_MeanStd(locals()[sub_name+'_APP4_D_IK']['pro_sup_l'] + locals()[sub_name+'_APP4_D_IK']['pro_sup_r']/2, Label='APP4', color='blue')
plt.title('Lowering wrist pronation', fontsize=20)
plt.xlabel('Time(%)', fontsize=13)
# plt.ylabel('Joint Angle(⁰)')
plt.legend(loc='upper right')
plt.grid()

plt.suptitle('Wrist Joint Angles (Sagittal-Frontal-Axial Plane)', weight=1, fontsize = 25)  # suptitle -> sub ㄴㄴ sup ㅇㅇ


plt.savefig(savefig_name2)