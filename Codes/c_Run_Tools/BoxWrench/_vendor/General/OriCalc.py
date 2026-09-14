import math

def OriCalc(eRotMat):
    if eRotMat[0][2]<1:
        if eRotMat[0][2]>-1:
            thetay=math.asin(eRotMat[0][2])
            thetax=math.atan2(-eRotMat[1][2],eRotMat[2][2])
            thetaz=math.atan2(-eRotMat[0][1],eRotMat[0][0])
        elif eRotMat[0][2]==-1:
            thetay=-math.pi/2
            thetax=-math.atan2(eRotMat[1][0],eRotMat[1][1])
            thetaz=0
        else:
            thetay=math.pi/2
            thetax=math.atan2(eRotMat[1][0],eRotMat[1][1])
            thetaz=0
    return([thetax,thetay,thetaz])
