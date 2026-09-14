import math
import numpy as np

def RotMat(x,y,z):
    x=math.radians(x)
    y=math.radians(y)
    z=math.radians(z)
    Rx=np.array([[1, 0, 0], [0, math.cos(x), -math.sin(x)],[0, math.sin(x), math.cos(x)]])
    Ry=np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0],[-math.sin(y), 0, math.cos(y)]])
    Rz=np.array([[math.cos(z), -math.sin(z), 0], [math.sin(z), math.cos(z), 0],[0, 0, 1]])
    return(np.dot(Rx, np.dot(Ry, Rz)))
