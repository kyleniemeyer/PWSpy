from __future__ import annotations
import os
import traceback
from typing import Tuple, List
import typing
from PyQt5.QtCore import QThread

from pwspy.apps.sharedWidgets.dialogs import BusyDialog
from PyQt5 import QtCore
from PyQt5.QtWidgets import QMessageBox
from pwspy.dataTypes import ImCube, CameraCorrection, ExtraReflectanceCube, AcqDir, ICMetaData
from pwspy.analysis.pws import AnalysisSettings
from pwspy.analysis.pws import Analysis
from pwspy.analysis.warnings import AnalysisWarning
from pwspy.utility.fileIO import loadAndProcess
import threading
from multiprocessing.util import Finalize
from multiprocessing.sharedctypes import RawArray
import numpy as np
if typing.TYPE_CHECKING:
    from pwspy.apps.PWSAnalysisApp.App import PWSApp

def safeCallback(func):
    """A decorator to make a function print its traceback without crashing."""
    def newFunc(*args):
        try:
            func(*args)
        except:
            traceback.print_exc()
    return newFunc


class AnalysisManager(QtCore.QObject):
    analysisDone = QtCore.pyqtSignal(str, AnalysisSettings, list)

    def __init__(self, app: PWSApp):
        super().__init__()
        self.app = app

    def runList(self):
        """Run multiple queued analyses as specified by the user."""
        for anName, anSettings, cellMetas, refMeta, camCorrection, widgetHandle in self.app.window.analysisSettings.getListedAnalyses():
            self.runSingle(anName, anSettings, cellMetas, refMeta, camCorrection)
            [cellItem.refresh() for cellMeta in cellMetas for cellItem in self.app.window.cellSelector.tableWidget.cellItems if cellMeta == cellItem.acqDir] #Refresh our displayed cell info
            _ = widgetHandle.listWidget().takeItem(widgetHandle.listWidget().row(widgetHandle)) #remove the analysis item once it has been run
            del _

    @safeCallback
    def runSingle(self, anName: str, anSettings: AnalysisSettings, cellMetas: List[AcqDir], refMeta: AcqDir,
                  cameraCorrection: CameraCorrection) -> Tuple[str, AnalysisSettings, List[Tuple[List[AnalysisWarning], AcqDir]]]:
        """Run a single analysis batch"""
        refMeta = refMeta.pws #We are only interested in pws data here
        cellMetas = [i.pws for i in cellMetas]
        #Determine which cells already have an analysis by this name and raise a deletion dialog.
        conflictCells = []
        for cell in cellMetas:
            if anName in cell.getAnalyses():
                conflictCells.append(cell)
        if len(conflictCells) > 0:
            ret = QMessageBox.question(self.app.window, "File Conflict", f"The following cells already have an analysis named {anName}. Do you want to delete existing analyses and continue?: \n {', '.join([os.path.split(i.filePath)[-1] for i in conflictCells])}")
            if ret == QMessageBox.Yes:
                [cell.removeAnalysis(anName) for cell in conflictCells]
            else:
                return
        if cameraCorrection is None: # This means that the user has selected automatic cameraCorrection
            correctionsOk = self._checkAutoCorrectionConsistency(cellMetas + [refMeta])
        else:
            correctionsOk = True #We're using a user provided camera correction so we assume it's good to go.
        if correctionsOk:
            ref = ImCube.fromMetadata(refMeta)
            if cameraCorrection is not None:
                ref.correctCameraEffects(cameraCorrection) #Apply the user-specified correction
            else:
                print("Using automatically detected camera corrections")
                ref.correctCameraEffects()
            if anSettings.extraReflectanceId is None: #the id is None, this means we are skipping the Extra reflection correction.
                erCube = None
            else:
                erMeta = self.app.ERManager.getMetadataFromId(anSettings.extraReflectanceId)
                if refMeta.systemName != erMeta.systemName:
                    ans = QMessageBox.question(self.app.window, "Uh Oh", f"The reference was acquired on system: {refMeta.systemName} while the extra reflectance correction was acquired on system: {erMeta.systemName}. Are you sure you want to continue?")
                    if ans == QMessageBox.No:
                        return
                erCube = ExtraReflectanceCube.fromMetadata(erMeta)
            analysis = Analysis(anSettings, ref, erCube)
            useParallelProcessing = self.app.parallelProcessing
            #TODO would be good to estimate ram usage here and make a decision on whether or not to go parallel
            if (len(cellMetas) <= 3): #No reason to start 3 parallel processes for less than 3 cells.
                useParallelProcessing = False
            if useParallelProcessing:
                #Rather than have read-only arrays that are shared between processes with shared memory. saves a few gigs of ram and speeds things up.
                print("AnalysisManager: Using parallel processing. Creating shared memory.")
                refdata = RawArray('f', analysis.ref.data.size)
                refdata = np.frombuffer(refdata, dtype=np.float32).reshape(analysis.ref.data.shape)
                np.copyto(refdata, analysis.ref.data)
                analysis.ref.data = refdata
                iedata = RawArray('f', analysis.extraReflection.data.size)
                iedata = np.frombuffer(iedata, dtype=np.float32).reshape(analysis.extraReflection.data.shape)
                np.copyto(iedata, analysis.extraReflection.data)
                analysis.extraReflection.data = iedata
            #Run parallel processing
            t = self.AnalysisThread(cellMetas, analysis, anName, cameraCorrection, useParallelProcessing)
            b = BusyDialog(self.app.window, "Processing. Please Wait...")
            t.finished.connect(b.accept)
            t.errorOccurred.connect(lambda e: QMessageBox.information(self.app.window, 'Uh Oh', str(e)))
            t.start()
            b.exec()
            warnings = t.warnings
            warnings = [(warn, md) for warn, md in warnings if md is not None]
            ret = (anName, anSettings, warnings)
            self.analysisDone.emit(*ret)
            return ret

    def _checkAutoCorrectionConsistency(self, cellMetas: List[ICMetaData]) -> bool:
        """Confirm that all metadatas in cellMetas have identical camera corrections. otherwise we can't proceed"""
        camCorrections = [i.cameraCorrection for i in cellMetas]
        names = [os.path.split(i.filePath)[-1] for i in cellMetas]
        missing = []
        for name, cam in zip(names, camCorrections):
            if cam is None:
                missing.append(name)
        if len(missing) > 0:
            missingMessage = str(missing) if len(missing) <= 3 else 'Many cells are'
            QMessageBox.information(self.app.window, 'Hmm', f'{missingMessage} missing automatic camera correction')
            return False
        if len(set([hash(i) for i in camCorrections])) > 1:
            QMessageBox.information(self.app.window, 'Hmm', "Multiple camera corrections are present in the set of selected cells.")
            return False
        return True


    class AnalysisThread(QThread):
        errorOccurred = QtCore.pyqtSignal(Exception)

        def __init__(self, cellMetas, analysis, anName, cameraCorrection, parallel):
            super().__init__()
            self.cellMetas = cellMetas
            self.analysis = analysis
            self.anName = anName
            self.cameraCorrection = cameraCorrection
            self.warnings = None
            self.parallel = parallel

        def run(self):
            try:
                self.warnings = loadAndProcess(self.cellMetas, processorFunc=self._process, initArgs=[self.analysis, self.anName, self.cameraCorrection],
                                     parallel=self.parallel, initializer=self._initializer, maxProcesses=3) # Returns a list of Tuples, each tuple containing a list of warnings and the ICmetadata to go with it.
            except Exception as e:
                self.errorOccurred.emit(e)


        @staticmethod
        def _initializer(analysis: Analysis, analysisName: str, cameraCorrection: CameraCorrection):
            """This method is run once for each process that is spawned. it initialized _resources that are shared between each iteration of _process."""
            global pwspyAnalysisAppParallelGlobals
            print('initializing!')
            pwspyAnalysisAppParallelGlobals = {'analysis': analysis, 'analysisName': analysisName,
                                               'cameraCorrection': cameraCorrection}

        @staticmethod
        def _process(im: ImCube):
            """This method is run in parallel. once for each dataTypes that we want to analyze."""
            global pwspyAnalysisAppParallelGlobals
            analysis = pwspyAnalysisAppParallelGlobals['analysis']
            analysisName = pwspyAnalysisAppParallelGlobals['analysisName']
            cameraCorrection = pwspyAnalysisAppParallelGlobals['cameraCorrection']
            if cameraCorrection is not None:
                im.correctCameraEffects(cameraCorrection)
            else:
                im.correctCameraEffects()
            results, warnings = analysis.run(im)
            if len(warnings) > 0:
                md = im.metadata
            else:
                md = None
            im.metadata.saveAnalysis(results, analysisName)
            return warnings, md
