from pwspy.dataTypes import DynCube
import os
from glob import glob

wDir = r''
refPath = r''

ref = DynCube.loadAny(refPath)
ref.correctCameraEffects()
ref.normalizeByExposure()

files = glob(os.path.join(wDir, 'Cell*'))
for f in files:
    dyn = DynCube.loadAny(f)
    dyn.correctCameraEffects()
    dyn.normalizeByExposure()
    dyn.normalizeByReference(ref)

    #TODO the original matlab script optionally uses 3 frame frame-averaging here as a lowpass

    #This is equivalent to subtracting the mean from each spectra and taking the RMS
    rms = dyn.data.std(axis=2)

    #TODO save the RMS