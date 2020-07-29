import typing

from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QApplication, QTableWidgetItem, QDialog, QPushButton, QGridLayout

from pwspy.apps.PWSAnalysisApp.componentInterfaces import CellSelector
from pwspy.apps.PWSAnalysisApp.pluginInterfaces import CellSelectorPlugin
import pwspy.dataTypes as pwsdt
import os

from pwspy.apps.PWSAnalysisApp.plugins.acquisitionSequencer.TreeView import DictTreeView, MyTreeView
from pwspy.apps.PWSAnalysisApp.plugins.acquisitionSequencer.sequencerCoordinate import SequencerCoordinateRange, \
    SeqAcqDir
from pwspy.apps.PWSAnalysisApp.plugins.acquisitionSequencer.steps import SequencerStep, CoordSequencerStep, \
    SequencerStepTypes
from pwspy.dataTypes import AcqDir


def requirePluginActive(method):
    def newMethod(self, *args, **kwargs):
        if self._ui.isVisible():  # If the ui isn't visible then we consider the plugin to be off.
            method(self, *args, **kwargs)
    return newMethod


class AcquisitionSequencerPlugin(CellSelectorPlugin): #TODO switch to a qdialog or dock widget, make sure widget has a parent. Provide new columns to the cell selector and results selector with coordinate?
    def __init__(self):
        self._selector: CellSelector = None
        self._sequence: SequencerStep = None
        self._cells: typing.List[SeqAcqDir] = None
        self._ui = SequenceViewer()
        self._ui.newCoordSelected.connect(self._updateSelectorSelection)

    def setContext(self, selector: CellSelector, parent: QWidget):
        """set the CellSelector that this plugin is associated to."""
        self._selector = selector
        self._ui.setParent(parent)
        self._ui.setWindowFlags(QtCore.Qt.Window) # Without this is just gets added to the main window in a weird way.

    @requirePluginActive
    def onCellsSelected(self, cells: typing.List[pwsdt.AcqDir]):
        """This method will be called when the CellSelector indicates that it has had new cells selected."""
        pass

    @requirePluginActive
    def onReferenceSelected(self, cell: pwsdt.AcqDir):
        """This method will be called when the CellSelector indicates that it has had a new reference selected."""
        pass

    # @requirePluginActive
    def onNewCellsLoaded(self, cells: typing.List[pwsdt.AcqDir]):
        """This method will be called when the CellSelector indicates that new cells have been loaded to the selector."""
        if len(cells) == 0: # This causes a crash
            return
        #Search the parent directory for a `sequence.pwsseq` file containing the sequence information.
        paths = [i.filePath for i in cells]
        commonPath = os.path.commonpath(paths)
        # We will search up to 3 parent directories for a sequence file
        for i in range(3):
            if os.path.exists(os.path.join(commonPath, 'sequence.pwsseq')):
                with open(os.path.join(commonPath, 'sequence.pwsseq')) as f:
                    try:
                        self._sequence = SequencerStep.fromJson(f.read())
                    except:  # if the file format is messed up this will fail, dont' let it crash the whole plugin though.
                        commonPath = os.path.split(commonPath)[0]  # Go up one directory
                        continue
                    self._cells = []
                    for i in cells:
                        try:
                            self._cells.append(SeqAcqDir(i)) # TODO should probably verify that the coords match up with the sequence we loaded.
                        except:  # Coordinates weren't found
                            pass
                    self._ui.setSequenceStepRoot(self._sequence)
                return
            commonPath = os.path.split(commonPath)[0]  # Go up one directory
        # We only get this far if the sequence search fails.
        self._sequence = None
        self._cells = None

    def getName(self) -> str:
        """The name to refer to this plugin by."""
        return "Acquisition Sequence Selector"

    def onPluginSelected(self):
        """This method will be called when the plugin is activated."""
        self._ui.show()  # We use ui visibility to determine if the plugin is active or not.
        self.onNewCellsLoaded(self._selector.getAllCellMetas())  # Make sure we're all up to date

    def additionalColumnNames(self) -> typing.Sequence[str]:
        """The header names for each column."""
        return tuple() #return "Coord. Type", "Coord. Value" # We used to add new columns, but it was confusing, better not to.

    def getTableWidgets(self, acq: pwsdt.AcqDir) -> typing.Sequence[QWidget]:  #TODO this gets called before the sequence has been loaded. Make it so this isn't required for constructor of cell table widgets.
        """provide a widget for each additional column to represent `acq`"""
        return tuple()
        # typeNames = {SequencerStepTypes.POS.name: "Position", SequencerStepTypes.TIME.name: "Time", SequencerStepTypes.ZSTACK.name: "Z Stack"}
        # try:
        #     acq = SeqAcqDir(acq)
        # except:
        #     return tuple((QTableWidgetItem(), QTableWidgetItem()))
        # coord = acq.sequencerCoordinate
        # idx, iteration = [(i, iteration) for i, iteration in enumerate(coord.iterations) if iteration is not None][-1]
        # for step in self._sequence.iterateChildren():
        #     if step.id == coord.ids[idx]:
        #         step: CoordSequencerStep
        #         val = QTableWidgetItem(step.getIterationName(iteration))
        #         t = QTableWidgetItem(typeNames[step.stepType])
        #         return tuple((t, val))
        # return tuple((QTableWidgetItem(), QTableWidgetItem()))  # This will happen if the acquisition has a coords file but the coord isn't actually found in the sequence file.
        #

    def _updateSelectorSelection(self, coordRange: SequencerCoordinateRange):
        select: typing.List[AcqDir] = []
        for cell in self._cells:
            if cell.sequencerCoordinate in coordRange:
                select.append(cell.acquisitionDirectory)
        self._selector.setSelectedCells(select)


class SequenceViewer(QWidget):
    newCoordSelected = pyqtSignal(SequencerCoordinateRange)

    def __init__(self, parent: QWidget = None):
        super().__init__(parent, QtCore.Qt.Window)
        self.setWindowTitle("Acquisition Sequence Viewer")

        l = QGridLayout()
        self.setLayout(l)

        self._sequenceTree = MyTreeView(self)

        self._showSettingsButton = QPushButton("Show Settings")
        self._showSettingsButton.released.connect(self._showHideSettings)

        self._selectButton = QPushButton("Update Selection")
        def func():
            self.newCoordSelected.emit(self._sequenceTree.getCurrentSelectedCoordinateRange())
            self._selectButton.setEnabled(False)
        self._selectButton.released.connect(func)

        self._settingsTree = DictTreeView()
        self._settingsTree.setColumnCount(2)
        self._settingsTree.setIndentation(10)
        self._sequenceTree.currentItemChanged.connect(lambda item: self._settingsTree.setDict(item.settings))

        self._sequenceTree.newCoordSelected.connect(lambda coordRange: self._selectButton.setEnabled(True))

        l.addWidget(self._sequenceTree, 0, 0)
        l.addWidget(self._selectButton, 1, 0)
        l.addWidget(self._showSettingsButton, 2, 0)
        l.addWidget(self._settingsTree, 0, 1, 1, 3)
        self._settingsTree.hide()

    def setSequenceStepRoot(self, root: SequencerStep):
        self._sequenceTree.setRoot(root)
        self._sequenceTree.expandAll()

    def _showHideSettings(self):
        w = self.width()
        if self._showSettingsButton.text() == "Show Settings":
            self._showSettingsButton.setText("Hide Settings")
            self.setFixedWidth(w*2)
            self._settingsTree.show()
        else:
            self._showSettingsButton.setText("Show Settings")
            self._settingsTree.hide()
            self.setFixedWidth(int(w / 2))


if __name__ == '__main__':
    with open(r'C:\Users\nicke\Desktop\data\toast2\sequence.pwsseq') as f:
        s = SequencerStep.fromJson(f.read())
    import sys
    from pwspy import dataTypes as pwsdt
    from glob import glob

    acqs = [pwsdt.AcqDir(i) for i in glob(r"C:\Users\nicke\Desktop\data\toast2\Cell*")]
    sacqs = [SeqAcqDir(acq) for acq in acqs]

    import sys

    app = QApplication(sys.argv)


    view = MyTreeView()
    view.setRoot(s)

    view.setWindowTitle("Simple Tree Model")
    view.show()
    sys.exit(app.exec_())


    app = QApplication(sys.argv)

    W = QWidget()
    W.setLayout(QHBoxLayout())

    w = QTreeWidget()
    w.setColumnCount(2)
    w.addTopLevelItem(s)
    w.setIndentation(10)

    w2 = DictTreeView()
    w2.setColumnCount(2)
    w2.setIndentation(10)


    w.itemClicked.connect(lambda item, column: w2.setDict(item.settings))

    W.layout().addWidget(w)
    W.layout().addWidget(w2)


    W.show()
    app.exec()
    a = 1
