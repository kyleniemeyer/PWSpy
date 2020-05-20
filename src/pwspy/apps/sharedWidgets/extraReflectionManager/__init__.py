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

import logging
import os
import typing
from io import IOBase
from typing import Optional, Dict, List

import httplib2
from PyQt5 import QtCore
from PyQt5.QtCore import QObject, QThread
from PyQt5.QtWidgets import QMessageBox, QWidget, QApplication, QPushButton
from googleapiclient.http import MediaIoBaseDownload

from pwspy.apps.sharedWidgets.dialogs import BusyDialog
from pwspy.apps.sharedWidgets.extraReflectionManager.ERDataComparator import ERDataComparator
from pwspy.apps.sharedWidgets.extraReflectionManager._ERDataDirectory import ERDataDirectory, EROnlineDirectory
from ._ERSelectorWindow import ERSelectorWindow
from ._ERUploaderWindow import ERUploaderWindow
from pwspy.dataTypes import ERMetaData
from pwspy.utility import GoogleDriveDownloader
from .exceptions import OfflineError
from pwspy.apps.PWSAnalysisApp import applicationVars
from google.auth.exceptions import TransportError


def _offlineDecorator(func):
    """Functions decorated with this will raise an OfflineError if they are attempted to be called while the ERManager
    is in offline mode. Only works on instance methods."""
    def wrappedFunc(self, *args, **kwargs):
        if self.offlineMode:
            logging.getLogger(__name__).warning("Attempting to download when ERManager is in offline mode.")
            raise OfflineError("Is Offline")
        func(self, *args, **kwargs)
    return wrappedFunc


class ERManager:
    """This class expects that the google drive application will already have access to a folder named
    `PWSAnalysisAppHostedFiles` which contains a folder `ExtraReflectanceCubes`, you will
    have to create these manually if starting on a new Drive account.

    Args:
        filePath: The file path to the local folder where Extra Reflection calibration files are stored.
        parentWidget: An optional reference to a QT widget that will act as the parent to any dialog windows that are opened.
    """
    def __init__(self, filePath: str, parentWidget: QWidget = None):
        self._directory = filePath
        self.offlineMode, self._downloader = self._logIn(parentWidget)

        indexPath = os.path.join(self._directory, 'index.json')
        if not os.path.exists(indexPath) and not self.offlineMode:
            self.download('index.json')
        self.dataComparator = ERDataComparator(self._downloader, self._directory)

    def _logIn(self, parentWidget: QWidget) -> typing.Tuple[bool, ERDownloader]:
        creds = ERDownloader.getCredentials(applicationVars.googleDriveAuthPath)
        if creds is None:  # Check if the google drive credentials exists and if they don't then give the user a message.
            msg = QMessageBox(parentWidget)
            msg.setIcon(QMessageBox.Information)
            msg.setText("Please log in to the google drive account containing the PWS Calibration Database. This is currently backman.lab@gmail.com")
            msg.setWindowTitle("Time to log in!")
            msg.setWindowModality(QtCore.Qt.WindowModal)
            okButton = msg.addButton("Ok", QMessageBox.YesRole)
            skipButton = msg.addButton("Skip (offline mode)", QMessageBox.NoRole)
            msg.exec()
            if msg.clickedButton() is skipButton:
                return True, None
        try:
            downloader = ERDownloader(applicationVars.googleDriveAuthPath)
            return False, downloader
        except (TransportError, httplib2.ServerNotFoundError):
            msg = QMessageBox.information(parentWidget, "Internet?", "Google Drive connection failed. Proceeding in offline mode.")
            return True, None

    def createSelectorWindow(self, parent: QWidget):
        return ERSelectorWindow(self, parent)

    def createManagerWindow(self, parent: QWidget):
        return ERUploaderWindow(self, parent)

    @_offlineDecorator
    def download(self, fileName: str, parentWidget: Optional[QWidget] = None):
        """Begin downloading `fileName` in a separate thread. Use the main thread to update a progress bar.
        If directory is left blank then file will be downloaded to the ERManager main directory"""
        self._downloader.download(fileName, self._directory, parentWidget)

    @_offlineDecorator
    def upload(self, fileName: str):
        """Uploads the file at `fileName` to the `ExtraReflectanceCubes` folder of the google drive account"""
        filePath = os.path.join(self._directory, fileName)
        self._downloader.upload(filePath)

    def getMetadataFromId(self, idTag: str) -> ERMetaData:
        """Given the unique idTag string for an ExtraReflectanceCube this will search the index.json and return the
        ERMetaData file. If it cannot be found then an `IndexError will be raised."""
        try:
            match = [item for item in self.dataComparator.local.index.cubes if item.idTag == idTag][0]
        except IndexError:
            raise IndexError(f"An ExtraReflectanceCube with idTag {idTag} was not found in the index.json file at {self._directory}.")
        return ERMetaData.fromHdfFile(self._directory, match.name)


class ERDownloader:
    """Implements downloading functionality specific to the structure that we have calibration files stored on our google drive account."""
    def __init__(self, authPath: str):
        self._downloader = self._QtGoogleDriveDownloader(authPath)

    def download(self, fileName: str, directory: str, parentWidget: Optional[QWidget] = None):
        """Begin downloading `fileName` in a separate thread. Use the main thread to update a progress bar.
        If directory is left blank then file will be downloaded to the ERManager main directory"""
        t = self._DownloadThread(self._downloader, fileName, directory)
        b = BusyDialog(parentWidget, f"Downloading {fileName}. Please Wait...", progressBar=True)  # This dialog blocks the screen until the download thread is completed.
        t.finished.connect(b.accept)  # When the thread finishes, close the busy dialog.
        self._downloader.progress.connect(b.setProgress)  # Progress from the downloader updates a progress bar on the busy dialog.
        t.errorOccurred.connect(lambda e: QMessageBox.information(parentWidget, 'Error in Drive Downloader Thread', str(e)))
        t.start()
        b.exec()

    def downloadToRam(self, fileName: str, stream: IOBase) -> IOBase:
        """Download a file directly to a stream in ram rather than saving to file, best for small temporary files.
        Args:
            fileName (str): The name of the file stored on google drive, must be in the Extra reflectance directory.
            stream (IOBase): An empty stream that the file contents will be loaded into.
        Returns:
            IOBase: The same stream that was passed in as `stream`."""
        files = self._downloader.getFolderIdContents(
            self._downloader.getIdByName('PWSAnalysisAppHostedFiles'))
        files = self._downloader.getFolderIdContents(
            self._downloader.getIdByName('ExtraReflectanceCubes', fileList=files))
        fileId = self._downloader.getIdByName(fileName, fileList=files)  
        self._downloader.downloadFile(fileId, stream)
        return stream

    def upload(self, filePath: str):
        parentId = self._downloader.getIdByName("ExtraReflectanceCubes")
        self._downloader.uploadFile(filePath, parentId)

    def getFileMetadata(self) -> List[Dict]:
        """Return GoogleDrive metadata about the files in the extra reflectance drive folder"""
        files = self._downloader.getFolderIdContents(
            self._downloader.getIdByName('PWSAnalysisAppHostedFiles'))
        files = self._downloader.getFolderIdContents(
            self._downloader.getIdByName('ExtraReflectanceCubes', fileList=files))
        return files

    @staticmethod
    def getCredentials(authPath: str):
        return ERDownloader._QtGoogleDriveDownloader.getCredentials(authPath)

    class _DownloadThread(QThread):
        """A QThread to download from google drive"""
        errorOccurred = QtCore.pyqtSignal(Exception)  # If an exception occurs it can be passed to another thread with this signal

        def __init__(self, downloader: GoogleDriveDownloader, fileName: str, directory: str):
            super().__init__()
            self.downloader = downloader
            self.fileName = fileName
            self.directory = directory

        def run(self):
            try:
                files = self.downloader.getFolderIdContents(
                    self.downloader.getIdByName('PWSAnalysisAppHostedFiles'))
                files = self.downloader.getFolderIdContents(
                    self.downloader.getIdByName('ExtraReflectanceCubes', fileList=files))
                fileId = self.downloader.getIdByName(self.fileName, fileList=files)
                with open(os.path.join(self.directory, self.fileName), 'wb') as f:
                    self.downloader.downloadFile(fileId, f)
            except Exception as e:
                self.errorOccurred.emit(e)

    class _QtGoogleDriveDownloader(GoogleDriveDownloader, QObject):
        """Same as the standard google drive downloader except it emits a progress signal after each chunk downloaded. This can be used to update a progress bar."""
        progress = QtCore.pyqtSignal(int)  # gives an estimate of download progress percentage

        def __init__(self, authPath: str):
            GoogleDriveDownloader.__init__(self, authPath)
            QObject.__init__(self)

        def downloadFile(self, Id: str, file: IOBase):
            """Save the file with googledrive file identifier `Id` to `savePath` while emitting the `progress` signal
            which can be connected to a progress bar or whatever."""
            fileRequest = self.api.files().get_media(fileId=Id)
            downloader = MediaIoBaseDownload(file, fileRequest, chunksize=1024*1024*5) # Downloading in 5mb chunks instead of the default 100mb chunk just so that the progress bar looks smoother
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                self.progress.emit(int(status.progress() * 100))


