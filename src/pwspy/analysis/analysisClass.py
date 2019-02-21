# -*- coding: utf-8 -*-
"""
Created on Tue Feb 12 23:10:35 2019

@author: Nick
"""

from pwspy import ImCube, CameraCorrection, KCube
from typing import NamedTuple
import json
import numpy as np
import scipy.signal as sps


class AnalysisSettings(NamedTuple):
    filterOrder:int
    filterCutoff:float
    polynomialOrder:int
    rInternalSubtractionPath:str
    referenceMaterial:str
    wavelengthStart:int
    wavelengthStop:int
    useHannWindow:bool
    autoCorrStopIndex:int
    hardwareCorrection:CameraCorrection
              
    @classmethod
    def fromJson(cls, filePath):
        with open(filePath,'r') as f:
            return cls(**json.load(f))
        
    def toJson(self,filePath):
        with open(filePath,'w') as f:
            json.dump(dict(self),f)
                    
class AnalysisResults(NamedTuple):
            reflectance: np.ndarray
            rms: np.ndarray
            polynomialRms: np.ndarray
            autoCorrelationSlope: np.ndarray
            rSquared: np.ndarray
            ld: np.ndarray
            opd: np.ndarray
            xvalOpd: np.ndarray

class Analysis:
    indexOpdStop = 100   
    def __init__(self, settings:AnalysisSettings, verbose:bool, advanced:bool):
        self.settings = settings
        self.verbose = verbose
        self.advanced = advanced
    
    def run(self, cube:ImCube, ref:ImCube):
        cube = self._normalizeImCube(cube, ref)
        cube = self._filterSignal(cube)
        #The rest of the analysis will be performed only on the selected wavelength range.
        cube = cube.wvIndex(
                self.settings.wavelengthStart, 
                self.settings.wavelengthStop)
        # Determine the mean-reflectance for each pixel in the cell.
        reflectance = cube.data.mean(axis=2)
        cube = KCube(cube)     ## -- Convert to K-Space
        cubePoly = self._fitPolynomial()
        # Remove the polynomial fit from filtered cubeCell.
        cube.data = cube.data - cubePoly  
    
        ## -- RMS
        # Obtain the RMS of each signal in the cube.
        rms = cube.data.std(axis=2)
        
        if self.advanced:
            ## RMS - POLYFIT
            # The RMS should be calculated on the mean-subtracted polyfit. This may
            # also be accomplished by calculating the standard-deviation.
            rmsPoly = cubePoly.std(axis=2)
            
            slope, rSquared = cube.getAutoCorrelation(isAutocorrMinSub, self.settings.autoCorrStopIndex)
            opd, xvalOpd = cube.getOpd(self.settings.useHannWindow, self.indexOpdStop)  
            ld = self._calculateLd(rms, slope)
        else:
            rmsPoly = slope = rSquared = opd = xvalOpd = ld = None
        
        self.results = AnalysisResults(
                reflectance = reflectance,
                rms = rms,
                rmsPoly = rmsPoly,
                slope = slope,
                rSquared = rSquared,
                opd = opd,
                xvalOpd = xvalOpd,
                ld = ld)
        
        return self.results
        
    
    def _normalizeImCube(self, cube:ImCube, ref:ImCube):
        cube.correctCameraEffects(self.settings.hardwareCorrection)
        cube.normalizeByExposure()    
        ref.correctCameraEffects(self.settings.hardwareCorrection)
        ref.normalizeByExposure()
        cube.normalizeByReference(ref)
        return cube
     
    def _filterSignal(self, cube:ImCube):
        b,a = sps.butter(self.settings.filterOrder, self.settings.filterCutoff) #The cutoff totally ignores what the `sample rate` is. so a 2nm interval image cube will be filtered differently than a 1nm interval cube. This is how it is in matlab.
        cube.data = sps.filtfilt(b,a,cube.data,axis=2)

    ## -- Polynomial Fit
    def _fitPolynomial(self, cube:KCube):
        order = self.settings.polynomialOrder
        flattenedData = cube.data.reshape((cube.data.shape[0]*cube.data.shape[1], cube.data.shape[2]))
        flattenedData = np.rollaxis(flattenedData,1) #Flatten the array to 2d and put the wavenumber axis first.
        cubePoly = np.zeros(flattenedData.shape)#make an empty array to hold the fit values.
        polydata = np.polyfit(cube.wavenumbers,flattenedData,order) #At this point polydata goes from holding the cube data to holding the polynomial values for each pixel. still 2d.
        for i in range(order + 1):
            cubePoly += (np.array(cube.wavenumbers)[:,np.newaxis]**i) * polydata[i,:] #Populate cubePoly with the fit values.
        cubePoly = np.moveaxis(cubePoly, 0, 1)
        cubePoly = cubePoly.reshape(cube.data.shape) #reshape back to a cube.
        return cubePoly

    ## Ld Calculation
    def _calculateLd(self, rms:np.ndarray, slope:np.ndarray):
        k = 2 * np.pi / 0.55
        fact = 1.38 * 1.38 / 2 / k / k;
        A1 = 0.008
        A2 = 4
        ld = ((A2 / A1) * fact) * (rms / (-1 * slope.reshape(rms.shape)))
        return ld

