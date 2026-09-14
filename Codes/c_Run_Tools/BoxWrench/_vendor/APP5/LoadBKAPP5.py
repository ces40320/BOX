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

# User Setup:
# Specify file paths and directories.
TrialModelFilePath='C:/Akhavanfar/Squat-7/APP5/'
os.chdir(TrialModelFilePath)

# Running Body Kinematics Analysis (BK) for the Box:
ModelFileName='Load.osim'
thisModel = osim.Model(ModelFileName)
# Cut-off frequency for low-pass filter.
cutoff=3
# Define prefixes and file paths.
Prefix='Load'
BK_setup_file_name='LoadBKSetup.xml'
ikloadname='IKResultsLoad.mot'
ikloadfile=TrialModelFilePath+ikloadname
# Load the IK results as a storage.
ikloadresults=osim.Storage(ikloadfile)
sTime=ikloadresults.getFirstTime()
fTime=ikloadresults.getLastTime()
# Create a BK analysis.
bk = osim.BodyKinematics()
bk.setOn(True)
bk.setStartTime(sTime)
bk.setEndTime(fTime)
bk.setName('BodyKinematics')
# Set up the Analyze Tool and configure it for BK analysis.
at = osim.AnalyzeTool()
at.setModel(thisModel)
at.setModelFilename(ModelFileName)
BKResultsDir='LoadAnalysis'
at.setResultsDir(BKResultsDir)
at.setInitialTime(sTime)
at.setFinalTime(fTime)
at.setSolveForEquilibrium(False)
at.setCoordinatesFileName(ikloadname)
at.setName(Prefix)
at.setLowpassCutoffFrequency(cutoff)
# Add BK to the Analyze Tool.
at.getAnalysisSet().cloneAndAppend(bk)
# Print the BK setup file and run the analysis.
at.printToXML(BK_setup_file_name)
at = osim.AnalyzeTool(BK_setup_file_name)
at.run()
# Remove the BK analysis set from the model.
at.removeAnalysisSetFromModel()
