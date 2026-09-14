'''
Script Information:
Please read README.pdf for more info about the script.
For a comprehensive understanding of our model and methodology, please refer to
our papers:

1) Akhavanfar, M., Uchida, T. K., Clouthier, A. L., & Graham, R. B. (2022).
   Sharing the load: Modeling loads in OpenSim to simulate two-handed lifting.
   Multibody System Dynamics 54(2): 213-234. https://doi.org/10.1007/s11044-021-09808-7

2) Akhavanfar, M., Mir-Orefice, A., Uchida, T. K., & Graham, R. B. (2023).
   An enhanced spine model validated for simulating dynamic lifting tasks in OpenSim.
   Annals of Biomedical Engineering. https://doi.org/10.1007/s10439-023-03368-x
'''

import opensim as osim
import math
import os
import pandas as pd
import numpy as np
from scipy.interpolate import CubicSpline
import sys
# Please modify to locate the General folder on your computer.
sys.path.append(r"E:\Dropbox\SEL\Python functions\OpenSim Analysis\Python Codes\General")
from RotMat import RotMat
from normalize import normalize
from io import StringIO
from NonlinearConst import NonlinearConst
from scipy.optimize import minimize

# User Setup:
# Specify file paths and directories.
TrialModelFilePath='E:/Dropbox/SEL/BOX/OpenSim/_Main_/SUB1(ASB)/APP5/'
os.chdir(TrialModelFilePath)

# External Force File Headings:
# Define the number of columns in the external force file.
s=37
ss=str(s)
# Create cell array to store the external force file headings.
textdata = np.empty((7, s), dtype=object)
textdata[:,1:]=''
textdata[0,0]='externalforce.mot'
textdata[1,0]='version=1'
textdata[3,0]='nColumns='+ss
textdata[4,0]='inDegrees=yes'
textdata[5,0]='endheader'
textdata[6,0]='time'
textdata[6,1]='ground_force1_vx'
textdata[6,2]='ground_force1_vy'
textdata[6,3]='ground_force1_vz'
textdata[6,4]='ground_force1_px'
textdata[6,5]='ground_force1_py'
textdata[6,6]='ground_force1_pz'
textdata[6,7]='ground_torque1_x'
textdata[6,8]='ground_torque1_y'
textdata[6,9]='ground_torque1_z'
textdata[6,10]='ground_force2_vx'
textdata[6,11]='ground_force2_vy'
textdata[6,12]='ground_force2_vz'
textdata[6,13]='ground_force2_px'
textdata[6,14]='ground_force2_py'
textdata[6,15]='ground_force2_pz'
textdata[6,16]='ground_torque2_x'
textdata[6,17]='ground_torque2_y'
textdata[6,18]='ground_torque2_z'
textdata[6,19]='Rhand_vx'
textdata[6,20]='Rhand_vy'
textdata[6,21]='Rhand_vz'
textdata[6,22]='Rhand_px'
textdata[6,23]='Rhand_py'
textdata[6,24]='Rhand_pz'
textdata[6,25]='Rhand_torque_x'
textdata[6,26]='Rhand_torque_y'
textdata[6,27]='Rhand_torque_z'
textdata[6,28]='Lhand_vx'
textdata[6,29]='Lhand_vy'
textdata[6,30]='Lhand_vz'
textdata[6,31]='Lhand_px'
textdata[6,32]='Lhand_py'
textdata[6,33]='Lhand_pz'
textdata[6,34]='Lhand_torque_x'
textdata[6,35]='Lhand_torque_y'
textdata[6,36]='Lhand_torque_z'

# Reading Force Plate Data:
# Load external force data from 'ExtForceAPP1.mot'.
with open('ExtForceAPP1.mot') as file:
    csv_data = file.read().replace('\t', ',')
ExtForceAPP1 = pd.read_csv(StringIO(csv_data), skiprows=6)
ExtForceAPP1Data = ExtForceAPP1.to_numpy()
MeasuredExtForceData=ExtForceAPP1Data[:,0:19]
ForcePlateFrames=MeasuredExtForceData.shape[0]
tt=str(ForcePlateFrames)
# Update the number of rows in the external force file header.
textdata[2,0]='nRows='+tt
# Reading Motion Cycle times
tcyl=[1.9067,2.9233,3.6983,5.0567]

# Calculaing Hand External Forces:
# Load the box model.
ModelFileName='Load.osim'
myModel=osim.Model(ModelFileName)
# Extract the inertial properties of the box.
load=myModel.getBodySet().get("Load")
m=load.getMass()
I = load.get_inertia()
Ixx=I.get(0)
Iyy=I.get(1)
Izz=I.get(2)
g=-9.8066

# Import Body Kinematics and States Reporter results for the box:
# Fit curves to box velocities and differentiate to calculate accelerations.
# Calculate forces (Fx, Fy, Fz) and moments (Mx, My, Mz).
LoadAnalysisDir=TrialModelFilePath+'LoadAnalysis/'
BKFileName='Load_BodyKinematics_vel_global.sto'
SRFileName='Load_StatesReporter_states.sto'
with open(LoadAnalysisDir+BKFileName, 'r') as file:
    csv_data = file.read().replace('\t', ',')
A = pd.read_csv(StringIO(csv_data), skiprows=18)
B = A.to_numpy()
t=np.array(B[:,0])
VGlob=B[:,1:4]
# Vx fitting
f1 = CubicSpline(t, VGlob[:,0])
Vxdot = f1(t, 1)
Fx=m*Vxdot
# Vy fitting
f2 = CubicSpline(t, VGlob[:,1])
Vydot = f2(t, 1)
Fy=m*(Vydot-g)
# Vz fitting
f3 = CubicSpline(t, VGlob[:,2])
Vzdot = f3(t, 1)
Fz=m*Vzdot
# Ext Force Vector
F=np.array([Fx,Fy,Fz]).T

with open(LoadAnalysisDir+SRFileName, 'r') as file:
    csv_data = file.read().replace('\t', ',')
A = pd.read_csv(StringIO(csv_data), skiprows=12)
B = A.to_numpy()
t=B[:,0]
W=B[:,[2,4,6]]
# Wx fitting
f4 = CubicSpline(t, W[:,0])
Wxdot = f4(t, 1)
Mx=Ixx*Wxdot
# Wy fitting
f5 = CubicSpline(t, W[:,1])
Wydot = f5(t, 1)
My=Iyy*Wydot
# Wz fitting
f6 = CubicSpline(t, W[:,2])
Wzdot = f6(t, 1)
Mz=Izz*Wzdot
# Ext Moment Vector
Wdot=np.array([Wxdot,Wydot,Wzdot])
M=np.array([Mx,My,Mz]).T

# Transform forces and moments to box coordinate system.
BKPosFileName='Load_BodyKinematics_pos_global.sto'
with open(LoadAnalysisDir+BKPosFileName, 'r') as file:
    csv_data = file.read().replace('\t', ',')
A = pd.read_csv(StringIO(csv_data), skiprows=18)
B = A.to_numpy()
OriMat=B[:,4:7]
FBoxCoord=np.zeros((821, 3))
for x in range(len(t)):
    R=RotMat(OriMat[x,0],OriMat[x,1],OriMat[x,2])
    FBoxCoord[x,:]=np.transpose(np.dot(np.linalg.inv(R),np.transpose(F[x,:])))

# Use optimization to find forces applied to right and left handles (FRBoxCoord
# and FLBoxCoord) and their corresponding points of application (RCOPr and
# RCOPl). Based on Newton's third law, calculate hand external forces as
# -FRBoxCoord and -FLBoxCoord.
t1=tcyl[0]
t2=tcyl[3]
t1round=math.floor(t1*100)/100
t2round=math.floor(t2*100)/100
n1 = np.argmax(t > t1round)
n2 = np.argmax(t > t2round)
FRBoxCoord=np.zeros((len(t),3))
FLBoxCoord=np.zeros((len(t),3))
RCOPr = np.column_stack((np.zeros(len(t)), np.zeros(len(t)), -0.17 * np.ones(len(t))))
RCOPl = np.column_stack((np.zeros(len(t)), np.zeros(len(t)), 0.17 * np.ones(len(t))))

for kk in range(n1,n2+1):
    fun = lambda x: x[6]**2 + x[7]**2 + x[8]**2 + x[9]**2 + x[10]**2 + x[11]**2
    x0 = [0.01,0.01,-0.17,0.01,0.01,0.17,0.01,0.01,0.01,0.01,0.01,0.01]
    lb = np.array([-0.05, -0.05, -0.22, -0.05, -0.05, 0.12, -100, -100, -100, -100, -100, -100])
    ub = np.array([0.05, 0.05, -0.12, 0.05, 0.05, 0.22, 100, 100, 100, 100, 100, 100])
    Aeq = np.zeros((3,12))
    Aeq[0,6]=1.0
    Aeq[0,9]=1.0
    Aeq[1,7]=1.0
    Aeq[1,10]=1.0
    Aeq[2,8]=1.0
    Aeq[2,11]=1.0
    beq = FBoxCoord[kk,:].T
    lcon = lambda x: np.dot(Aeq,x)-beq
    nonlcon = lambda x: NonlinearConst(x,M[kk,:])
    constraints = (
        {'type': 'eq', 'fun': lcon},
        {'type': 'eq', 'fun': nonlcon}
                )
    bounds = list(zip(lb, ub))
    result = minimize(fun, x0, constraints=constraints, bounds=bounds, tol=1.0e-6)
    x=result.x
    RCOPr[kk,:]=np.array([x[0],x[1],x[2]])
    RCOPl[kk,:]=np.array([x[3],x[4],x[5]])
    FRBoxCoord[kk,:]=np.array([x[6],x[7],x[8]])
    FLBoxCoord[kk,:]=np.array([x[9],x[10],x[11]])

# Based on Newton's third law, hand external forces are -FRBoxCoord and -FLBoxCoord.
HandExtForceApp5 = np.hstack([-FRBoxCoord, RCOPr, np.zeros((len(t), 3)), -FLBoxCoord, RCOPl, np.zeros((len(t), 3))])

# Writing External Forces File:
# Normalize hand forces to have the same vector length as force plate data.
HandExtForceApp5Norm=normalize(HandExtForceApp5,ForcePlateFrames)
# Combine measured external forces and normalized hand forces.
Data = np.hstack((MeasuredExtForceData, HandExtForceApp5Norm))
# Write data to 'ExtForceAPP5.mot' file.
with open('ExtForceAPP5.mot', 'w') as fid:
    for nn in range(7):
        fid.write('\t'.join(map(str,textdata[nn, :])) + '\n')
    for oo in range(ForcePlateFrames):
        fid.write('\t'.join(map(str, Data[oo, :])) + '\n')
