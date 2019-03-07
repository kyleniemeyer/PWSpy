from dataclasses import dataclass

import h5py
import numpy as np
import os.path as osp
from datetime import datetime
from .analysisSettings import AnalysisSettings


@dataclass(frozen=True)
class AnalysisResults:
    settings: AnalysisSettings
    reflectance: np.ndarray
    rms: np.ndarray
    polynomialRms: np.ndarray
    autoCorrelationSlope: np.ndarray
    rSquared: np.ndarray
    ld: np.ndarray
    opd: np.ndarray
    xvalOpd: np.ndarray
    time: str = None

    def __post_init__(self):
        self.__setattr__('time', datetime.now().strftime("%m-%d-%y %H:%M:%s"))

    def toHDF5(self, directory: str, name: str):
        fileName = osp.join(directory, f'{name}.hdf5')
        if osp.exists(fileName):
            raise OSError(f'{fileName} already exists.')
        # now save the stuff
        with h5py.File(fileName, 'w') as hf:
            for k, v in self.asdict().items():
                if k in ['settings', 'time']:
                    hf.create_dataset(k, v.toJsonString())
                else:
                    hf.create_dataset(k, data=v)

    @classmethod
    def fromHDF5(cls, directory: str, name: str):
        fileName = osp.join(directory, f'{name}.hdf5')
        # load stuff
        with h5py.File(fileName, 'r') as hf:
            d = {k: np.array(v) for k,v in hf.items()}
            return cls(**d)


class cached_property(object):
    """ A property that is only computed once per instance and then replaces
        itself with an ordinary attribute. Deleting the attribute resets the
        property.
        Source: https://github.com/bottlepy/bottle/commit/fa7733e075da0d790d809aa3d2f53071897e6f76
        """

    def __init__(self, func):
        self.__doc__ = getattr(func, '__doc__')
        self.func = func

    def __get__(self, obj, cls):
        if obj is None:
            return self
        value = obj.__dict__[self.func.__name__] = self.func(obj)
        return value


class LazyAnalysisResultsLoader:
    def __init__(self, directory: str, name: str):
        self.file = h5py.File(osp.join(directory, f'{name}.hdf5'))
        self.settings = AnalysisSettings.fromJsonString(self.file['settings'])
        self.time = self.file['time']

    def __del__(self):
        self.file.close()

    @cached_property
    def reflectance(self) -> np.ndarray:
        return np.array(self.file['reflectance'])

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
    def xvalOpd(self) -> np.ndarray:
        return np.array(self.file['xvalOpd'])
