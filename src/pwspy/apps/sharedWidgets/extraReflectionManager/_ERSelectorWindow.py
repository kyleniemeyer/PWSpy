from __future__ import annotations
from datetime import datetime
from typing import List, Optional

from PyQt5 import QtCore
from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QDialog, QTableWidget, QTableWidgetItem, QMessageBox, QWidget, QCheckBox, QVBoxLayout, \
    QPushButton, QLineEdit, QComboBox, QGridLayout, QLabel, QDialogButtonBox, QHBoxLayout, QAbstractItemView, QMenu, \
    QAction, QTreeWidget, QTreeWidgetItem, QFileDialog

from pwspy import moduleConsts
from pwspy.apps.PWSAnalysisApp._sharedWidgets.tables import DatetimeTableWidgetItem
from pwspy.dataTypes import ExtraReflectanceCube
from pwspy.dataTypes.metadata import ERMetaData
import numpy as np
from .exceptions import OfflineError

import typing

from pwspy.utility.plotting import PlotNd

if typing.TYPE_CHECKING:
    from pwspy.apps.sharedWidgets.extraReflectionManager import ERManager
    from pwspy.apps.sharedWidgets.extraReflectionManager.ERIndex import ERIndexCube


class ERTreeWidgetItem(QTreeWidgetItem):
    def __init__(self, fileName: str, description: str, idTag: str, name: str, downloaded: bool):
        super().__init__()
        self.fileName = fileName
        self.description = description
        self.idTag = idTag
        self.systemName = self.idTag.split('_')[1]  # We used to categorize the calibrations by system name but this is confusing because a single system can have multiple configurations
        self.datetime = datetime.strptime(self.idTag.split('_')[2], moduleConsts.dateTimeFormat)
        self.name = name
        configurationName = name.split("-")[:-1]  # We now categorize by configurationName, however this isn't explicitly saved in the index so we extract it from the file name. Of course, this breaks if anyone puts a "-" in the configuration name. It would be better to explicitly save it from the ERCreator app
        self.configurationName = configurationName[0] if len(configurationName) == 1 else "-".join(configurationName)

        self.setText(0, datetime.strftime(self.datetime, '%B %d, %Y'))
        self.setToolTip(0, '\n'.join([f'File Name: {self.fileName}', f'ID: {self.idTag}', f'Description: {self.description}']))

        if downloaded:
            #Item can be selected. Checkbox no longer usable
            self.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            self.setCheckState(0, QtCore.Qt.PartiallyChecked)
        else:
            #Checkbox can be checked to allow downloading. Nothing else can be done.
            self.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
            self.setCheckState(0, QtCore.Qt.Unchecked)
        self._downloaded = downloaded

    @property
    def downloaded(self): return self._downloaded

    def __lt__(self, other: ERTreeWidgetItem):  # Needed for sorting by date
        return self.datetime < other.datetime

    def isChecked(self) -> bool:
        return self.checkState(0) == QtCore.Qt.Checked


class ERSelectorWindow(QDialog):
    selectionChanged = QtCore.pyqtSignal(object) #Usually an ERMetaData object, sometimes None

    def __init__(self, manager: ERManager, parent: Optional[QWidget] = None):
        self._manager = manager
        self._selectedMetadata: Optional[ERMetaData] = None
        super().__init__(parent)
        self.setModal(False)
        self.setWindowTitle("Extra Reflectance Selector")
        self.setLayout(QVBoxLayout())
        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.showContextMenu)
        self.tree.itemSelectionChanged.connect(self._setAcceptButtonEnabled)
        self.downloadButton = QPushButton("Download Checked Items")
        self.downloadButton.released.connect(self._downloadCheckedItems)
        self.selectLocalButton = QPushButton("Select From File")
        self.selectLocalButton.released.connect(self._selectLocalFile)
        self.acceptSelectionButton = QPushButton("Accept Selection")
        self.acceptSelectionButton.released.connect(self.acceptCurrentSelection)
        self.acceptSelectionButton.setEnabled(False)  # This will become enabled once a valid button is selected.
        self.layout().addWidget(self.tree)
        self.layout().addWidget(self.downloadButton)
        self.layout().addWidget(self.selectLocalButton)
        self.layout().addWidget(self.acceptSelectionButton)
        try:
            self._manager.download('index.json', parentWidget=self)
        except OfflineError:
            print('Offline Mode: Could not update `Extra Reflectance` index file. Connection to Google Drive failed.')
        self._initialize()

    def _initialize(self):
        self._items: List[ERTreeWidgetItem] = []
        self.tree.clear()
        self._manager.dataComparator.local.updateIndex()
        self.fileStatus = self._manager.dataComparator.local.getFileStatus(skipMD5=True)  # Skipping the md5 hash check should speed things up here.
        for item in self._manager.dataComparator.local.index.cubes:
            self._addItem(item)
        # Sort items by date
        for item in [self.tree.invisibleRootItem().child(i) for i in range(self.tree.invisibleRootItem().childCount())]:
            item.sortChildren(0, QtCore.Qt.AscendingOrder)
        ig = QTreeWidgetItem()
        ig.setText(0, "Ignore")
        self.tree.invisibleRootItem().addChild(ig)

    def _addItem(self, item: ERIndexCube):
        treeItem = ERTreeWidgetItem(fileName=item.fileName, description=item.description, idTag=item.idTag, name=item.name,
                                    downloaded=self.fileStatus[self.fileStatus['idTag'] == item.idTag].iloc[0]['Local Status'] == self._manager.dataComparator.local.DataStatus.found.value)
        self._items.append(treeItem)
        _ = self.tree.invisibleRootItem()
        if treeItem.configurationName not in [_.child(i).text(0) for i in range(_.childCount())]:
            sysNameItem = QTreeWidgetItem(_, [treeItem.configurationName])
            sysNameItem.setFlags(QtCore.Qt.ItemIsEnabled)  # Don't allow selecting
            _.addChild(sysNameItem)
        parent = [i for i in [_.child(i) for i in range(_.childCount())] if i.text(0) == treeItem.configurationName][0]
        parent.addChild(treeItem)

    def showContextMenu(self, pos: QPoint):
        widgetItem: ERTreeWidgetItem = self.tree.itemAt(pos)
        if not isinstance(widgetItem, ERTreeWidgetItem):
            return  # Some treeItems exist which are not our custom ERTreeWidgetItem. Not menu for these items.
        menu = QMenu()
        displayAction = QAction("Display Info")
        displayAction.triggered.connect(lambda: self.displayInfo(widgetItem))
        menu.addAction(displayAction)
        if widgetItem.downloaded:
            plotAction = QAction("Plot Data")
            plotAction.triggered.connect(lambda checked, wItem=widgetItem: self._plot3dData(wItem))
            menu.addAction(plotAction)
        menu.exec(self.mapToGlobal(pos))

    def displayInfo(self, item: ERTreeWidgetItem):
        message = QMessageBox.information(self, item.name, '\n\n'.join([f'FileName: {item.fileName}',
                                                                      f'ID Tag: {item.idTag}',
                                                                      f'Description: {item.description}']))

    def _plot3dData(self, widgetItem):
        er = ExtraReflectanceCube.fromHdfFile(self._manager._directory, widgetItem.name)
        PlotNd(er.data, extraDimIndices=[er.wavelengths])

    def _downloadCheckedItems(self):
        for item in self._items:
            if item.isChecked() and not item.downloaded:
                # If it is checked then it should be downloaded
                self._manager.download(item.fileName, parentWidget=self)
        self._initialize()

    def _selectLocalFile(self):
        import os
        filePath, filterPattern = QFileDialog.getOpenFileName(self, "Select an ExtraReflectance file.", os.path.expanduser("~"), "*.h5")
        try:
            wDir, name = ERMetaData.directory2dirName(filePath)
            md = ERMetaData.fromHdfFile(wDir, name)
            self.setSelection(md)
            self.accept()
        except Exception as e:
            msg = QMessageBox.warning(self, "Error", str(e))

    def acceptCurrentSelection(self) -> None:
        items = self.tree.selectedItems()
        if len(items) == 0:
            self.setSelection(None)
            super().accept()
        elif self.tree.selectedItems()[0].text(0) == 'Ignore':
            self.setSelection(None)
            super().accept()
        else:
            try:
                md = self._manager.getMetadataFromId(self.tree.selectedItems()[0].idTag)
                self.setSelection(md)
                super().accept()
            except IndexError:  # Nothing was selected
                msg = QMessageBox.information(self, 'Uh oh!', 'No item was selected!')

    def getSelectedMetadata(self) -> Optional[ERMetaData]:
        return self._selectedMetadata

    def setSelection(self, md: ERMetaData):
        self._selectedMetadata = md
        self.selectionChanged.emit(md)

    def _setAcceptButtonEnabled(self):
        item = None
        items = self.tree.selectedItems()
        if len(items) > 0:
            item = items[0] # There should never be more than one item selected.
        #If a selectable item was selected then we'll have it as item here. Otherwise item will be None
        self.acceptSelectionButton.setEnabled(item is not None)

