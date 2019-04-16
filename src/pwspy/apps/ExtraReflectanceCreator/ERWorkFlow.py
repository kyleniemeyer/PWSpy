import os
from glob import glob
from typing import List, Any, Dict
import json
from pwspy import ImCube, CameraCorrection, ExtraReflectanceCube
from pwspy.apps.ExtraReflectanceCreator.widgets.dialog import IndexInfoForm
from pwspy.imCube import ICMetaData
from pwspy.utility import loadAndProcess
from pwspy.utility.reflectanceHelper import Material
import pwspy.apps.ExtraReflectanceCreator.extraReflectance  as er
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
import pandas as pd

def _splitPath(path: str) -> List[str]:
    folders = []
    while 1:
        path, folder = os.path.split(path)
        if folder != "":
            folders.append(folder)
        else:
            if path != "":
                folders.append(path)
            break
    return folders

def scanDirectory(directory: str) -> Dict[str, Any]:
    try:
        cam = CameraCorrection.fromJsonFile(os.path.join(directory, 'cameraCorrection.json'))
    except Exception as e:
        print(e)
        raise Exception(f"Could not load a camera correction at {directory}")
    files = glob(os.path.join(directory, '*', '*', 'Cell*'))
    rows = []
    matMap = {'air': Material.Air, 'water': Material.Water, 'ipa': Material.Ipa, 'ethanol': Material.Ethanol}
    for file in files:
        filelist = _splitPath(file)
        s = filelist[2]
        m = matMap[filelist[1]]
        rows.append({'setting': s, 'material': m, 'cube': file})
    df = pd.DataFrame(rows)
    return {'dataFrame': df, 'camCorrection': cam}

def _processIm(im: ImCube, camCorrection: CameraCorrection, binning: int) -> ImCube:
    im.correctCameraEffects(camCorrection, binning=binning)
    im.normalizeByExposure()
    im.filterDust(6)  # TODO change units
    return im

class ERWorkFlow:
    def __init__(self, workingDir: str, homeDir: str):
        self.cubes = self.fileStruct = self.df = self.cameraCorrection = self.currDir = self.plotnds = None
        self.figs = []
        self.homeDir = homeDir
        # generateFileStruct:
        folders = [i for i in glob(os.path.join(workingDir, '*')) if os.path.isdir(i)]
        settings = [os.path.split(i)[-1] for i in folders]
        fileStruct = {}
        for f, s in zip(folders, settings):
            fileStruct[s] = scanDirectory(f)
        self.fileStruct = fileStruct

    def invalidateCubes(self):
        self.cubes = None

    def deleteFigures(self):
        for fig in self.figs:
            plt.close(fig)
        self.figs = []

    def loadCubes(self, includeSettings: List[str], binning: int):
        if binning is None:
            md = ICMetaData.loadAny(self.df['cube'].loc[0])
            if 'binning' not in md.metadata:
                raise Exception("No binning metadata found. Please specify a binning setting.")
        df = self.df[self.df['setting'].isin(includeSettings)]
        self.cubes = loadAndProcess(df, _processIm, parallel=True, procArgs=[self.cameraCorrection, binning])

    def plot(self, saveToPdf: bool = False, saveDir: str = None):
        cubes = self.cubes
        settings = set(cubes['setting'])  # Unique setting values
        materials = set(cubes['material'])
        theoryR = er.getTheoreticalReflectances(materials, cubes['cube'].iloc[0].wavelengths)  # Theoretical reflectances
        matCombos = er.generateMaterialCombos(materials)

        print("Select an ROI")
        mask = cubes['cube'].sample(n=1).iloc[0].selectLassoROI()  # Select an ROI to analyze
        self.figs.extend(er.plotExtraReflection(cubes, theoryR, matCombos, mask, plotReflectionImages=True))
        if saveToPdf:
            with PdfPages(os.path.join(saveDir, "figs.pdf")) as pp:
                for i in plt.get_fignums():
                    f = plt.figure(i)
                    f.set_size_inches(9, 9)
                    pp.savefig(f)

    def save(self):
        settings = set(self.cubes['setting'])
        for setting in settings:
            cubes = self.cubes[self.cubes['setting'] == setting]
            materials = set(cubes['material'])
            theoryR = er.getTheoreticalReflectances(materials, cubes['cube'].iloc[0].wavelengths)  # Theoretical reflectances
            matCombos = er.generateMaterialCombos(materials)
            combos = er.getAllCubeCombos(matCombos, cubes)
            erCube, rExtraDict, self.plotnds = er.generateRExtraCubes(combos, theoryR)
            saveName = f'{self.currDir}-{setting}'
            dialog = IndexInfoForm(f'{self.currDir}-{setting}', erCube.idTag)
            dialog.exec()
            erCube.metadata['description'] = dialog.description
            erCube.toHdfFile(self.homeDir, saveName)
            self.updateIndex(saveName, erCube.idTag, dialog.description, f'{saveName}{erCube.FILESUFFIX}')

    def updateIndex(self, saveName: str, idTag: str, description: str, filePath: str):
        with open(os.path.join(self.homeDir, 'index.json'), 'r') as f:
            index = json.load(f)
        cubes = index['reflectanceCubes']
        newEntry = {'fileName': filePath,
                    'description': description,
                    'idTag': idTag,
                    'name': saveName}
        cubes.append(newEntry)
        index['reflectanceCubes'] = cubes
        with open(os.path.join(self.homeDir, 'index.json'), 'w') as f:
            json.dump(index, f, indent=4)

    def compareDates(self):
        self.anims = er.compareDates(self.cubes) #The animation objects must not be deleted for the animations to keep working

    def directoryChanged(self, directory: str):
        self.currDir = directory
        _ = self.fileStruct[directory]
        self.df = _['dataFrame']
        self.cameraCorrection = _['camCorrection']
        self.invalidateCubes()
