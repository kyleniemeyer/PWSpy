from __future__ import annotations
import abc
import enum
import json
import typing
from pwspy.apps.PWSAnalysisApp.plugins.acquisitionSequencer.item import SelfTreeItem
from pwspy.utility.micromanager import PositionList

StepTypeNames = dict(
    ACQ="Acquisition",
    POS="Multiple Positions",
    TIME="Time Series",
    CONFIG="Configuration Group",
    SUBFOLDER="Enter Subfolder",
    EVERYN="Once per `N` iterations",
    PFS="Optical Focus Lock",
    PAUSE="Pause",
    ROOT="Initialization",
    AF="Software Autofocus",
    ZSTACK="Z-Stack"
)


class SequencerStep(SelfTreeItem):
    """Implementation of a TreeItem for representing a sequencer step."""
    def __init__(self, id: int, settings: dict, stepType: str, children: typing.List[SequencerStep] = None):
        super().__init__()
        self.id = id
        self.settings = settings
        self.stepType = stepType
        # self.setData(0, f"{Names[stepType]}")
        if children is not None:
            self.addChildren(children)

    # def __repr__(self):
    #     return f"Step: {self.stepType}"

    @staticmethod
    def hook(dct: dict):
        if all([i in dct for i in ("id", 'stepType', 'settings')]):
            clazz = Types[dct['stepType']].value
            s = clazz(**dct)
            return s
        else:
            return dct

    @staticmethod
    def fromJson(j: str) -> SequencerStep:
        return json.loads(j, object_hook=SequencerStep.hook)


class CoordSequencerStep(SequencerStep):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._selectedIterations = tuple()
        # self.setData(1, f"i={self.stepIterations()}")

    def setSelectedIterations(self, iterations: typing.Sequence[int]):
        self._selectedIterations = tuple(iterations)

    def getSelectedIterations(self) -> typing.Sequence[int]:
        return self._selectedIterations

    @abc.abstractmethod
    def stepIterations(self):  # return the total number of iterations of this step.
        raise NotImplementedError()

    @abc.abstractmethod
    def getIterationName(self, iteration: int) -> str:
        raise NotImplementedError()


class PositionsStep(CoordSequencerStep):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._positionList = PositionList.fromDict(self.settings['posList'])
    def stepIterations(self):
        if not hasattr(self, '_len'):
            self._len = len(self._positionList)
        return self._len

    def getIterationName(self, iteration: int) -> str:
        return self._positionList[iteration].label

class TimeStep(CoordSequencerStep):
    def stepIterations(self):
        if not hasattr(self, '_len'):
            self._len = self.settings['numFrames']
        return self._len

    def getIterationName(self, iteration: int) -> str:
        return f"{iteration * self.settings['frameIntervalMinutes']} min."

class ZStackStep(CoordSequencerStep):
    def stepIterations(self):
        if not hasattr(self, '_len'):
            self._len = self.settings['numStacks']
        return self._len

    def getIterationName(self, iteration: int) -> str:
        return f"{iteration * self.settings['intervalUm']} μm"


class SequencerCoordinate:
    def __init__(self, treePath: typing.Sequence[int], iterations: typing.Sequence[int]):
        """treePath should be a list of the id numbers for each step in the path to this coordinate.
        iterations should be a list indicating which iteration of each step the coordinate was from."""
        assert (self.idPath) == len(self.iterations)
        self.idPath = tuple(treePath)
        self.iterations = tuple(iterations)
        self.fullPath = tuple(zip(self.idPath, self.iterations))

    @staticmethod
    def fromDict(d: dict) -> SequencerCoordinate:
        return SequencerCoordinate(treePath=d['treeIdPath'], iterations=d["stepIterations"])

    @staticmethod
    def fromJsonFile(path: str) -> SequencerCoordinate:
        with open(path) as f:
            return SequencerCoordinate.fromDict(json.load(f))

    def isSubPathOf(self, other: SequencerCoordinate):
        """Check if `self` is a parent path of the `item` coordinate """
        assert isinstance(other, SequencerCoordinate)
        if len(self.fullPath) >= len(other.fullPath):
            return False
        # return self.idPath == other.idPath[:len(self.idPath)] and self.iterations == other.iterations[:len(self.iterations)]
        return self.fullPath == other.fullPath[:len(self.fullPath)]

    def __eq__(self, other: SequencerCoordinate):
        """Check if these coordinates are identical"""
        assert isinstance(other, SequencerCoordinate)
        # return self.idPath == other.idPath and self.iterations == other.iterations
        return self.fullPath == other.fullPath


class Types(enum.Enum):
    ACQ = SequencerStep
    PFS = SequencerStep
    POS = PositionsStep
    TIME = TimeStep
    AF = SequencerStep
    CONFIG = SequencerStep
    PAUSE = SequencerStep
    EVERYN = SequencerStep
    ROOT = SequencerStep
    SUBFOLDER = SequencerStep
    ZSTACK = ZStackStep


