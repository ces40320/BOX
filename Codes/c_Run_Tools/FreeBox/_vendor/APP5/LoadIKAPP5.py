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

# User Setup:
# Specify file paths and directories.
TrialModelFilePath='C:/Akhavanfar/Squat-7/APP5/'
os.chdir(TrialModelFilePath)

# Run Inverse Kinematics (IK) Analysis for the Box:
SampleLoadIKSetup=TrialModelFilePath+'SampleLoadIKSetup.xml'
ik=osim.InverseKinematicsTool(SampleLoadIKSetup)
# Detect the load marker file.
markerfilename=glob.glob('*.trc')[0]
markerdata=osim.MarkerData(markerfilename)
# Determine the start and end times for IK analysis.
sTime=markerdata.getStartFrameTime()
fTime=markerdata.getLastFrameTime()
ModelFileName='Load.osim'
myModel = osim.Model(ModelFileName)
myModel.initSystem()
# Configure the IK tool.
ik.setModel(myModel)
ik.setMarkerDataFileName(markerfilename)
ik.setStartTime(sTime)
ik.setEndTime(fTime)
outputfilename='IKResultsLoad.mot'
ik.setOutputMotionFileName(outputfilename)
setupFile='LoadIKSetup.xml'
ik.printToXML(TrialModelFilePath+setupFile)
# Run the IK analysis.
ik.run()
