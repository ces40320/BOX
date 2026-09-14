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
import os
import glob
import numpy as np
from numpy import linalg as LA
from statistics import mean
import math

# User Setup:
# Please modify to locate the Squat-7 folder on your computer.
MainDir='C:/Akhavanfar/Squat-7/'
os.chdir(MainDir)

# Creating the Box Model with Markers in Ground Reference Frame:
# Use '7kgBox_MrkGND_Sample.osim' as the basis for creating a box model for the
# specific trial (Squat-7).
SampleModelFileName='7kgBox_MrkGND_Sample.osim'

# Read marker data from the box with respect to the ground reference frame.
MeasuredMarkerFileName=glob.glob('*.trc')[0]
MeasuredMarker=osim.MarkerData(MeasuredMarkerFileName)

# Identify marker indices in the trc file.
TFR_index=MeasuredMarker.getMarkerIndex('TFR')
TFL_index=MeasuredMarker.getMarkerIndex('TFL')
TBR_index=MeasuredMarker.getMarkerIndex('TBR')
TBL_index=MeasuredMarker.getMarkerIndex('TBL')
FHR_index=MeasuredMarker.getMarkerIndex('FHR')
FHL_index=MeasuredMarker.getMarkerIndex('FHL')
BHR_index=MeasuredMarker.getMarkerIndex('BHR')
BHL_index=MeasuredMarker.getMarkerIndex('BHL')

# Extract marker positions and convert from mm to m.
A=osim.Storage()
MeasuredMarker.makeRdStorage(A)
B=A.getStateVector(0)
C=B.getData()
Mrk1=np.zeros((1, 3))
Mrk2=np.zeros((1, 3))
Mrk3=np.zeros((1, 3))
Mrk4=np.zeros((1, 3))
Mrk5=np.zeros((1, 3))
Mrk6=np.zeros((1, 3))
Mrk7=np.zeros((1, 3))
Mrk8=np.zeros((1, 3))
Mrk1[0,0]=C.get(TFR_index*3)/1000.0
Mrk1[0,1]=C.get(TFR_index*3+1)/1000.0
Mrk1[0,2]=C.get(TFR_index*3+2)/1000.0
Mrk2[0,0]=C.get(TFL_index*3)/1000.0
Mrk2[0,1]=C.get(TFL_index*3+1)/1000.0
Mrk2[0,2]=C.get(TFL_index*3+2)/1000.0
Mrk3[0,0]=C.get(TBL_index*3)/1000.0
Mrk3[0,1]=C.get(TBL_index*3+1)/1000.0
Mrk3[0,2]=C.get(TBL_index*3+2)/1000.0
Mrk4[0,0]=C.get(TBR_index*3)/1000.0
Mrk4[0,1]=C.get(TBR_index*3+1)/1000.0
Mrk4[0,2]=C.get(TBR_index*3+2)/1000.0
Mrk5[0,0]=C.get(FHL_index*3)/1000.0
Mrk5[0,1]=C.get(FHL_index*3+1)/1000.0
Mrk5[0,2]=C.get(FHL_index*3+2)/1000.0
Mrk6[0,0]=C.get(BHL_index*3)/1000.0
Mrk6[0,1]=C.get(BHL_index*3+1)/1000.0
Mrk6[0,2]=C.get(BHL_index*3+2)/1000.0
Mrk7[0,0]=C.get(FHR_index*3)/1000.0
Mrk7[0,1]=C.get(FHR_index*3+1)/1000.0
Mrk7[0,2]=C.get(FHR_index*3+2)/1000.0
Mrk8[0,0]=C.get(BHR_index*3)/1000.0
Mrk8[0,1]=C.get(BHR_index*3+1)/1000.0
Mrk8[0,2]=C.get(BHR_index*3+2)/1000.0
Mrk=np.concatenate((Mrk1,Mrk2,Mrk3,Mrk4,Mrk5,Mrk6,Mrk7,Mrk8), axis=0)

# Calculate the center of the load (box).
x=mean(Mrk[:,0])
y=Mrk1[0][1]-0.135
z=mean(Mrk[:,2])
LoadCenter=[x,y,z]

# Define a coordinate system for the box.
e1=(Mrk4-Mrk1)/LA.norm(Mrk4-Mrk1)
e3=(Mrk2-Mrk1)/LA.norm(Mrk2-Mrk1)
e2=np.cross(e3,e1)
eRotMat=np.c_[np.transpose(e1),np.transpose(e2),np.transpose(e3)]

if eRotMat[0,2]<1:
    if eRotMat[0,2]>-1:
        thetay=math.asin(eRotMat[0,2])
        thetax=math.atan2(-eRotMat[1,2],eRotMat[2,2])
        thetaz=math.atan2(-eRotMat[0,1],eRotMat[0,0])
    elif eRotMat[0,2]==-1:
        thetay=-math.pi/2
        thetax=-math.atan2(eRotMat[1,0],eRotMat[1,1])
        thetaz=0
    else:
        thetay=math.pi/2
        thetax=math.atan2(eRotMat[1,0],eRotMat[1,1])
        thetaz=0
theta=[thetax,thetay,thetaz]

# Create the load model representing the box with 8 markers in the ground (GND)
# reference frame.
myModel = osim.Model(SampleModelFileName)
joint = myModel.getJointSet().get('BoxGround')
frame=joint.get_frames(0)
A=osim.Vec3(LoadCenter[0],LoadCenter[1],LoadCenter[2])
frame.set_translation(A)
B=osim.Vec3(thetax,thetay,thetaz)
frame.set_orientation(B)
markers=myModel.getMarkerSet()
nummarkers=markers.getSize()

# Iterate through markers and set their offsets relative to the load.
for ii in range(1,nummarkers+1):
    marker=markers.get(ii-1)
    C=osim.Vec3(Mrk[ii-1][0],Mrk[ii-1][1],Mrk[ii-1][2])
    marker.set_location(C)
    
# Initialize the model system and save it as 'Load_MrkGND.osim'.
myModel.initSystem()
setupFile='Load_MrkGND.osim'
myModel.printToXML(setupFile)
