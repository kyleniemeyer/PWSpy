# -*- coding: utf-8 -*-
"""
Created on Wed Aug 22 11:05:40 2018

@author: Nick Anthony
"""

import pandas as pd
import numpy as np
import os
from pwspy.moduleConsts import Material


class ReflectanceHelper:
    materialFiles = {
        Material.Glass: 'N-BK7.csv',
        Material.Water: 'Daimon-21.5C.csv',
        Material.Air: 'Ciddor.csv',
        Material.Silicon: 'Silicon.csv',
        Material.Oil_1_7: 'CargilleOil1_7.csv',
        Material.Oil_1_4: "CargilleOil1_4.csv",
        Material.Ipa: 'Sani-DellOro-IPA.csv',
        Material.Ethanol: 'Rheims.csv',
        Material.ITO: 'Konig.csv'}

    _instance = None

    @staticmethod
    def getInstance():
        """ Static access method. """
        if ReflectanceHelper._instance is None:
            ReflectanceHelper()
        return ReflectanceHelper._instance

    def __init__(self):
        """ Virtually private constructor. """
        if ReflectanceHelper._instance is not None:
            raise Exception("This class is a singleton!")
        else:
            ReflectanceHelper._instance = self
        fileLocation = os.path.join(os.path.split(__file__)[0], 'refractiveIndexFiles')
        ser = {}  # a dictionary of the series by name
        for name, file in self.materialFiles.items():
            # create a series for each csv file
            arr = np.genfromtxt(os.path.join(fileLocation, file), skip_header=1, delimiter=',')
            _ = pd.DataFrame({'n': arr[:, 1], 'k': arr[:, 2]}, index=arr[:, 0].astype(np.float) * 1e3)
            ser[name] = _

        # Find the first and last indices that won't require us to do any extrapolation
        first = []
        last = []
        for k, v in ser.items():
            first += [v.first_valid_index()]
            last += [v.last_valid_index()]
        first = max(first)
        last = min(last)
        # Interpolate so we don't have any nan values.
        #    df = pd.DataFrame(ser)
        df = pd.concat(ser, axis='columns', keys=self.materialFiles.keys())
        df = df.interpolate('index')
        self.n = df.loc[first:last]


    def getReflectance(self, mat1: Material, mat2: Material, wavelengths=None) -> pd.Series:
        """Given the names of two interfaces this provides the reflectance in units of percent.
        If given a series as index the data will be interpolated and reindexed to match the index."""

        # nc1 = np.array([np.complex(i[0], i[1]) for idx, i in n[mat1].iterrows()])  # complex index for material 1
        # nc2 = np.array([np.complex(i[0], i[1]) for idx, i in n[mat2].iterrows()])
        nc1 = self.getRefractiveIndex(mat1)
        nc2 = self.getRefractiveIndex(mat2)
        result = np.abs(((nc1 - nc2) / (nc1 + nc2)) ** 2)
        result = pd.Series(result, index=self.n.index)
        if wavelengths is not None:
            wavelengths = pd.Index(wavelengths)
            combinedIdx = result.index.append(
                wavelengths)  # An index that contains all the original index points and all of the new. That way we can interpolate without first throwing away old data.
            result = result.reindex(combinedIdx)
            result = result.sort_index()
            result = result.interpolate(method='index')  #Use the values of the index rather than assuming it is linearly spaced.
            result = result[~result.index.duplicated()]  # remove duplicate indices to avoid error
            result = result.reindex(wavelengths)  # reindex again to get rid of unwanted index points.
        return result


    def getRefractiveIndex(self, mat: Material, wavelengths=None) -> pd.Series:
        refractiveIndex = np.array([np.complex(i[0], i[1]) for idx, i in self.n[mat].iterrows()])
        refractiveIndex = pd.Series(refractiveIndex, self.n.index)
        if wavelengths is not None: #Need to do interpolation
            wavelengths = pd.Index(wavelengths)
            combinedIdx = refractiveIndex.index.append(
                wavelengths)  # An index that contains all the original index points and all of the new. That way we can interpolate without first throwing away old data.
            from scipy.interpolate import griddata
            out = griddata(refractiveIndex.index, refractiveIndex.values, wavelengths)  #This works with complex numbers
            refractiveIndex = pd.Series(out, index=wavelengths)
        return refractiveIndex


reflectanceHelper = ReflectanceHelper.getInstance() #Instantiate singleton instance.



