from __future__ import annotations
from typing import Tuple

import h5py
from ..metadata import ERMetaData

from ._ICBaseClass import ICBase
import numpy as np
import os
import typing
import pandas as pd
if typing.TYPE_CHECKING:
    from pwspy.dataTypes import ImCube


class ExtraReflectanceCube(ICBase):
    """This class represents a 3D data cube of the extra reflectance in a PWS system. It's values are in units of
    reflectance (between 0 and 1). It has a `metadata` attribute which is of ERMetaData. It also has a `data` attribute
    of numpy.ndarray type."""

    ERMetaData = ERMetaData

    def __init__(self, data: np.ndarray, wavelengths: Tuple[float, ...], metadata: ERMetaData):
        assert isinstance(metadata, ERMetaData)
        if data.max() > 1 or data.min() < 0:
            print("Warning!: Reflectance values must be between 0 and 1")
        self.metadata = metadata
        ICBase.__init__(self, data, wavelengths)

    @property
    def wavelengths(self) -> Tuple[float, ...]:
        """The wavelengths corresponding to each element along the 3rd axis of `self.data`."""
        return self.index

    @classmethod
    def fromHdfFile(cls, directory: str, name: str) -> ExtraReflectanceCube:
        """Load an ExtraReflectanceCube from an HDF5 file. `name` should be the file name, excluding the '_ExtraReflectance.h5' suffix."""
        filePath = ERMetaData.dirName2Directory(directory, name)
        with h5py.File(filePath, 'r') as hf:
            dset = hf[ERMetaData._DATASETTAG]
            return cls.fromHdfDataset(dset, filePath=filePath)

    def toHdfFile(self, directory: str, name: str) -> None:
        """Save an ExtraReflectanceCube to an HDF5 file. The filename will be `name` with the '_ExtraReflectance.h5' suffix."""
        savePath = ERMetaData.dirName2Directory(directory, name)
        if os.path.exists(savePath):
            raise OSError(f"The path {savePath} already exists.")
        with h5py.File(savePath, 'w') as hf:
            self.toHdfDataset(hf)

    def toHdfDataset(self, g: h5py.Group) -> h5py.Group:
        """Save the ExtraReflectanceCube to an HDF5 dataset. `g` should be an h5py Group or File."""
        g = super().toHdfDataset(g, ERMetaData._DATASETTAG)
        g = self.metadata.toHdfDataset(g)
        return g

    @classmethod
    def fromHdfDataset(cls, d: h5py.Dataset, filePath: str = None):
        """Load the ExtraReflectanceCube from `d`, an HDF5 dataset."""
        data, index = cls.decodeHdf(d)
        md = ERMetaData.fromHdfDataset(d, filePath=filePath)
        return cls(data, index, md)

    @classmethod
    def fromMetadata(cls, md: ERMetaData):
        """Load an ExtraReflectanceCube from an ERMetaData object corresponding to an HDF5 file."""
        directory, name = ERMetaData.directory2dirName(md.filePath)
        return cls.fromHdfFile(directory, name)


class ExtraReflectionCube(ICBase):
    """This class is meant to be constructed from an ExtraReflectanceCube along with additional reference measurement
    information. Rather than being in units of reflectance (between 0 and 1) it is in the same units as the reference measurement
    that is provided with, usually counts/ms or just counts."""
    def __init__(self, data: np.ndarray, wavelengths: Tuple[float, ...], metadata: ERMetaData):
        super().__init__(data, wavelengths)
        self.metadata = metadata

    @classmethod
    def create(cls, reflectance: ExtraReflectanceCube, theoryR: pd.Series, reference: ImCube):
        """Construct and ExtraReflectionCube from an ExtraReflectanceCube and a reference measurement. The resulting
        ExtraReflectionCube will be in the same units as `reference`. `theoryR` should be a spectrum describing the theoretically
        expected reflectance of the reference data cube. Both `theoryR` and `reflectance` should be in units of reflectance
        (between 0 and 1)."""
        I0 = reference.data / (theoryR[None, None, :] + reflectance.data)  # I0 is the intensity of the illumination source, reconstructed in units of `counts`. this is an inversion of our assumption that reference = I0*(referenceReflectance + extraReflectance)
        data = reflectance.data * I0  # converting extraReflectance to the extra reflection in units of counts
        return cls(data, reflectance.wavelengths, reflectance.metadata)
