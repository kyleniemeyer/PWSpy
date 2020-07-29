import typing

from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal, QItemSelection, QModelIndex, QItemSelectionModel
from PyQt5.QtWidgets import QTreeView, QWidget, QTreeWidget, QTreeWidgetItem, QAbstractItemView

from pwspy.apps.PWSAnalysisApp.plugins.acquisitionSequencer.model import TreeModel
from pwspy.apps.PWSAnalysisApp.plugins.acquisitionSequencer.steps import SequencerStep
from pwspy.apps.PWSAnalysisApp.plugins.acquisitionSequencer.Delegate import IterationRangeDelegate
from pwspy.apps.PWSAnalysisApp.plugins.acquisitionSequencer.sequencerCoordinate import IterationRangeCoordStep, \
    SequencerCoordinateRange


class MyTreeView(QTreeView):
    newCoordSelected = pyqtSignal(SequencerCoordinateRange)
    currentItemChanged = pyqtSignal(SequencerStep)

    def __init__(self, parent: QWidget = None):
        super().__init__(parent=parent)
        delegate = IterationRangeDelegate(self)
        self.setItemDelegate(delegate)
        delegate.editingFinished.connect(lambda: self._selectionChanged(self.selectionModel().selection())) # When we edit an item we still want to process it as a change even though the selection hasn't changed.
        self.setEditTriggers(QAbstractItemView.AllEditTriggers)  # Make editing start on a single click.
        self.setIndentation(10)  # Reduce the default indentation
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)  # Smooth scrolling
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def setRoot(self, root: SequencerStep):
        self.setModel(TreeModel(root))
        self.setSelectionModel(QItemSelectionModel(self.model(), self))
        self.selectionModel().selectionChanged.connect(self._selectionChanged)
        self.selectionModel().currentChanged.connect(self._currentChanged)

    def _selectionChanged(self, selected: QItemSelection, deselected: QItemSelection = None):
        idx = selected.indexes()[0]  # We only support a single selection anyways.
        step: SequencerStep = idx.internalPointer()
        coordSteps = []
        while step is not self.model().invisibleRootItem(): # This will break out once we reach the root item.
            coordStep = step.data(QtCore.Qt.EditRole)  # The item delegate saves an iterationRangeCoordStep in the edit role of steps.
            if coordStep is None:
                coordSteps.append(IterationRangeCoordStep(step.id, None))
            else:
                coordSteps.append(coordStep)
            step = step.parent()
        self.newCoordSelected.emit(SequencerCoordinateRange(list(reversed(coordSteps))))

    def _currentChanged(self, current: QModelIndex, previous: QModelIndex):
        self.currentItemChanged.emit(current.internalPointer())


class DictTreeView(QTreeWidget):
    def setDict(self, d: dict):
        self.clear()
        self._fillItem(self.invisibleRootItem(), d)

    @staticmethod
    def _fillItem(item: QTreeWidgetItem, value: typing.Union[dict, list]):
        """Recursively populate a tree item with children to match the contents of a `dict`"""
        item.setExpanded(True)
        if isinstance(value, dict):
            for key, val in value.items():
                child = QTreeWidgetItem()
                child.setText(0, f"{key}")
                item.addChild(child)
                if isinstance(val, (list, dict)):
                    DictTreeView._fillItem(child, val)
                else:
                    child.setText(1, f"{val}")
        elif isinstance(value, list):
            for val in value:
                child = QTreeWidgetItem()
                item.addChild(child)
                if type(val) is dict:
                    child.setText(0, '[dict]')
                    DictTreeView._fillItem(child, val)
                elif type(val) is list:
                    child.setText(0, '[list]')
                    DictTreeView._fillItem(child, val)
                else:
                    child.setText(0, val)
                    child.setExpanded(True)


