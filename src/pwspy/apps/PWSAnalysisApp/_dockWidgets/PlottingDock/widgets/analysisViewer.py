# Copyright 2018-2020 Nick Anthony, Backman Biophotonics Lab, Northwestern University
#
# This file is part of PWSpy.
#
# PWSpy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PWSpy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PWSpy.  If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations
from PyQt5 import QtCore
from PyQt5.QtWidgets import QWidget, QGridLayout, QComboBox
from typing import Optional

from pwspy.apps.PWSAnalysisApp._utilities.conglomeratedAnalysis import ConglomerateAnalysisResults

from pwspy.apps.PWSAnalysisApp._dockWidgets.PlottingDock.widgets.widgets import AnalysisPlotter
from pwspy.apps.PWSAnalysisApp._dockWidgets.PlottingDock.widgets.roiPlot import RoiPlot


class AnalysisViewer(AnalysisPlotter, RoiPlot):
    """This class is a window that provides convenient viewing of a pws acquisition, analysis, and related images.
    It expands upon the functionality of `BigPlot` which handles ROIs but not analysis images."""
    def __init__(self, metadata: AcqDir, analysisLoader: ConglomerateAnalysisResults, title: str, parent=None,
                 initialField=AnalysisPlotter.PlotFields.Thumbnail, flags=None):
        RoiPlot.__init__(self, metadata, metadata.getThumbnail(), parent=parent, flags=flags)
        AnalysisPlotter.__init__(self, metadata, analysisLoader)
        self.setWindowTitle(title)
        self.analysisCombo = QComboBox(self)
        self._populateFields()
        self.layout().itemAt(0).insertWidget(0, self.analysisCombo)
        self.changeData(initialField)

    def _populateFields(self):
        currField = self.analysisCombo.currentText()
        try:
            self.analysisCombo.disconnect()
        except:
            pass #Sometimes there is nothing to disconnect
        self.analysisCombo.clear()
        _ = self.PlotFields  # Just doing this to make for less typing later.
        items = [_.Thumbnail]
        for i in [_.MeanReflectance, _.RMS, _.AutoCorrelationSlope, _.RSquared, _.Ld]:
            try:
                if hasattr(self.analysis.pws, i.value[1]):  # This will raise a key error if the analysis object exists but the requested item is not found
                    items.append(i)
            except KeyError:
                pass
        for i in [_.RMS_t_squared, _.Diffusion, _.DynamicsReflectance]:
            try:
                if hasattr(self.analysis.dyn, i.value[1]):  # This will raise a key error if the analysis object exists but the requested item is not found
                    items.append(i)
            except KeyError:
                pass
        if self.analysis.pws is not None:
            if 'reflectance' in self.analysis.pws.file.keys(): #This is the normalized 3d data cube. needed to generate the opd.
                items.append(_.OpdPeak)
        if self.acq.fluorescence is not None:
            items.append(_.Fluorescence)
        self.analysisCombo.addItems([i.name for i in items])
        if currField in [i.name for i in items]:
            self.analysisCombo.setCurrentText(currField) #Maintain the same field if possible.
        self.analysisCombo.currentTextChanged.connect(self.changeDataByName)  # If this line comes before the analysisCombo.addItems line then it will get triggered when adding items.


    def changeDataByName(self, field: str):
        field = [enumField for enumField in self.PlotFields if enumField.name == field][0] #This function recieves the name of the Enum item. we want to get the enum item itself.
        self.changeData(field)

    def changeData(self, field: AnalysisPlotter.PlotFields):
        """Change which image associated with the PWS acquisition we want to view."""
        super().changeData(field)
        if self.analysisCombo.currentText() != field.name:
            self.analysisCombo.setCurrentText(field.name)
        self.setImageData(self.data)

    def setMetadata(self, md: AcqDir, analysis: Optional[ConglomerateAnalysisResults] = None):
        """Change this widget to display data for a different acquisition and optionally an analysis."""
        try:
            super().setMetadata(md, analysis)
        except ValueError:  # Trying to set new metadata may result in an error if the new analysis/metadata can't plot the currently set analysisField
            self.changeData(self.PlotFields.Thumbnail)  # revert back to thumbnail which should always be possible
            super().setMetadata(md, analysis)
        self.setRoiPlotMetadata(md)
        self._populateFields()

if __name__ == '__main__':
    fPath = r'G:\Aya_NAstudy\matchedNAi_largeNAc\cells\Cell2'
    from pwspy.dataTypes import AcqDir
    from PyQt5.QtWidgets import QApplication
    acq = AcqDir(fPath)
    import sys
    app = QApplication(sys.argv)
    b = AnalysisViewer(acq, ConglomerateAnalysisResults(None, None), "Test")
    b.show()
    sys.exit(app.exec())