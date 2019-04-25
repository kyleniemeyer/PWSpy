from __future__ import annotations
import dataclasses
from typing import Optional

import h5py
import numpy as np
import os.path as osp
from datetime import datetime
import typing
if typing.TYPE_CHECKING:
    from pwspy import KCube
from .analysisSettings import AnalysisSettings
from abc import ABC, abstractmethod
from pwspy.moduleConsts import dateTimeFormat
from pwspy.utility.misc import cached_property


class AbstractAnalysisResults(ABC):
    """Enforce that derived classes will have the following properties."""
    @property
    @abstractmethod
    def settings(self) -> AnalysisSettings:
        pass

    @property
    @abstractmethod
    def reflectance(self) -> KCube:
        pass

    @property
    @abstractmethod
    def meanReflectance(self) -> np.ndarray:
        pass

    @property
    @abstractmethod
    def rms(self) -> np.ndarray:
        pass

    @property
    @abstractmethod
    def polynomialRms(self) -> np.ndarray:
        pass

    @property
    @abstractmethod
    def autoCorrelationSlope(self) -> np.ndarray:
        pass

    @property
    @abstractmethod
    def rSquared(self) -> np.ndarray:
        pass

    @property
    @abstractmethod
    def ld(self) -> np.ndarray:
        pass

    @property
    @abstractmethod
    def opd(self) -> np.ndarray:
        pass

    @property
    @abstractmethod
    def opdIndex(self) -> np.ndarray:
        pass

    @property
    @abstractmethod
    def time(self) -> str:
        pass

    @property
    @abstractmethod
    def imCubeIdTag(self) -> str:
        pass

    @property
    @abstractmethod
    def referenceIdTag(self) -> str:
        pass

    @property
    @abstractmethod
    def extraReflectionTag(self) -> str:
        pass

    @staticmethod
    def name2FileName(name: str) -> str:
        return f'analysisResults_{name}.h5'

    @staticmethod
    def fileName2Name(fileName: str) -> str:
        return fileName.split('analysisResults_')[1][:-3]


@dataclasses.dataclass
class AnalysisResults: #TODO this should inherit from abstract class but it doesn't work easily
    """A saveable object to hold the results of an analysis. Also stored the creation time of the analysis."""
    settings: AnalysisSettings
    reflectance: KCube
    meanReflectance: np.ndarray
    rms: np.ndarray
    polynomialRms: np.ndarray
    autoCorrelationSlope: np.ndarray
    rSquared: np.ndarray
    ld: np.ndarray
    opd: np.ndarray
    opdIndex: np.ndarray
    imCubeIdTag: str
    referenceIdTag: str
    extraReflectionTag: Optional[str]
    time: str = None

    def __post_init__(self):
        self.__setattr__('time', datetime.now().strftime(dateTimeFormat))

    def toHDF5(self, directory: str, name: str):
        from pwspy.imCube import KCube #Need this for instance checking
        fileName = osp.join(directory, AbstractAnalysisResults.name2FileName(name))
        if osp.exists(fileName):
            raise OSError(f'{fileName} already exists.')
        # now save the stuff
        with h5py.File(fileName, 'w') as hf:
            for k, v in self.__dict__.items():
                if k == 'settings':
                    v = v.toJsonString()
                if isinstance(v, str):
                    hf.create_dataset(k, data=np.string_(v)) #h5py recommends encoding strings this way for compatability.
                elif isinstance(v, KCube):
                    hf = v.toHdfDataset(hf, k)
                elif isinstance(v, np.ndarray):
                    hf.create_dataset(k, data=v)
                elif v is None:
                    pass #Don't bother writing values that were skipped.
                else:
                    raise TypeError(f"Analysis results type {k}, {type(v)} not supported or expected")




class AnalysisResultsLoader(AbstractAnalysisResults):
    """A read-only loader for analysis results that will only load them from hard disk as needed."""
    def __init__(self, directory: str, name: str):
        self.file = h5py.File(osp.join(directory, self.name2FileName(name)))

    def __del__(self):
        self.file.close()

    @cached_property
    def settings(self) -> AnalysisSettings:
        return AnalysisSettings.fromJsonString(self.file['settings'])

    @cached_property
    def imCubeIdTag(self) -> str:
        return self.file['imCubeIdTag'].encode()

    @cached_property
    def referenceIdTag(self) -> str:
        return self.file['referenceIdTag'].encode()

    @cached_property
    def time(self) -> str:
        return self.file['time']

    @cached_property
    def reflectance(self):
        grp = self.file['reflectance']
        return KCube(grp['data'], grp['wavenumbers'])

    @cached_property
    def meanReflectance(self):
        return np.ndarray(self.file['reflectance'])

    @cached_property
    def rms(self) -> np.ndarray:
        return np.array(self.file['rms'])

    @cached_property
    def polynomialRms(self) -> np.ndarray:
        return np.array(self.file['polynomialRms'])

    @cached_property
    def autoCorrelationSlope(self) -> np.ndarray:
        return np.array(self.file['autoCorrelationSlope'])

    @cached_property
    def rSquared(self) -> np.ndarray:
        return np.array(self.file['rSquared'])

    @cached_property
    def ld(self) -> np.ndarray:
        return np.array(self.file['ld'])

    @cached_property
    def opd(self) -> np.ndarray:
        return np.array(self.file['opd'])

    @cached_property
    def opdIndex(self) -> np.ndarray:
        return np.array(self.file['xvalOpd'])

    @cached_property
    def extraReflectionTag(self) -> str:
        return self.file['extraReflectionTag'].encode()

    def loadAllFromDisk(self) -> None:
        """Access all cached properties in order to load them from disk"""
        for i in [self.opdIndex, self.opd, self.ld, self.rSquared,
                  self.autoCorrelationSlope, self.polynomialRms,
                  self.rms, self.reflectance, self.time, self.referenceIdTag,
                  self.imCubeIdTag, self.settings, self.extraReflectionTag]:
            _ = i

