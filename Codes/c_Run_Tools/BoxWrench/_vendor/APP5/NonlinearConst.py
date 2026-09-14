import numpy as np
def NonlinearConst(x, M):
    ceq = np.zeros(3)
    ceq[0] = x[1]*x[8] - x[2]*x[7] + x[4]*x[11] - x[5]*x[10] - M[0]
    ceq[1] = x[2]*x[6] - x[0]*x[8] + x[5]*x[9] - x[3]*x[11] - M[1]
    ceq[2] = x[0]*x[7] - x[1]*x[6] + x[3]*x[10] - x[4]*x[9] - M[2]
    return(ceq)
