import os
import time

import numpy as np
import qt
import ctk
import vtk
import slicer
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleWidget,
    ScriptedLoadableModuleLogic,
    ScriptedLoadableModuleTest,
)

from WillisLabelLib import aca, anatomy, branches, core, sca, topcow


#
# WillisLabel
#
class WillisLabel(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Willis Label"
        self.parent.categories = ["Segmentation"]
        self.parent.dependencies = []
        self.parent.contributors = ["Niyazi Acer"]
        self.parent.helpText = """
Extracts intracranial arteries from a TOF-MRA volume and labels them anatomically
(vertebral, basilar, internal carotid, cerebellar arteries and the segments of the
circle of Willis: A1, AComA, A2, P1, PComA, P2, MCA) from one or more seed points per
artery. Each artery is coloured from its origin, and can be exported as a separate
STL for 3D printing.
See the <a href="https://github.com/niyaziacer/SlicerWillisLabel">project page</a>.
"""
        self.parent.acknowledgementText = """
Labelling uses geodesic (shortest-path-within-the-vessel) distances from user seeds,
followed by a centreline-based correction of branch origins.
"""


#
# Widget
#
class WillisLabelWidget(ScriptedLoadableModuleWidget):
    SEED_LIST_NAME = "WillisSeeds"

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        self.logic = WillisLabelLogic()

        # ---- 1. Vessel extraction
        box = ctk.ctkCollapsibleButton(); box.text = "1. Extract arteries"
        self.layout.addWidget(box); f = qt.QFormLayout(box)

        self.inputSelector = slicer.qMRMLNodeComboBox()
        self.inputSelector.nodeTypes = ["vtkMRMLScalarVolumeNode"]
        self.inputSelector.addEnabled = False; self.inputSelector.removeEnabled = False
        self.inputSelector.noneEnabled = False
        self.inputSelector.setMRMLScene(slicer.mrmlScene)
        self.inputSelector.setToolTip("TOF-MRA volume")
        f.addRow("TOF volume:", self.inputSelector)

        self.lowSlider = ctk.ctkSliderWidget(); self.lowSlider.decimals = 0
        self.highSlider = ctk.ctkSliderWidget(); self.highSlider.decimals = 0
        for s in (self.lowSlider, self.highSlider):
            s.minimum = 0; s.maximum = 5000; s.singleStep = 5
        self.lowSlider.setToolTip("Voxels above this value are kept if connected to a 'high' voxel")
        self.highSlider.setToolTip("Seed intensity for hysteresis thresholding")
        f.addRow("Low threshold:", self.lowSlider)
        f.addRow("High threshold:", self.highSlider)

        self.suggestButton = qt.QPushButton("Suggest thresholds")
        f.addRow(self.suggestButton)

        self.sigmaSpin = qt.QDoubleSpinBox(); self.sigmaSpin.setRange(0, 2); self.sigmaSpin.setSingleStep(0.1)
        self.sigmaSpin.value = 0.5; self.sigmaSpin.suffix = " mm"
        f.addRow("Smoothing (sigma):", self.sigmaSpin)

        self.minSizeSpin = qt.QDoubleSpinBox(); self.minSizeSpin.setRange(0, 10000)
        self.minSizeSpin.value = 30; self.minSizeSpin.suffix = " mm³"
        f.addRow("Minimum island size:", self.minSizeSpin)

        self.extractButton = qt.QPushButton("Extract arteries")
        self.extractButton.toolTip = "Creates the 'Arteries mask' segmentation. Edit it in Segment Editor if needed."
        f.addRow(self.extractButton)

        self.maskSelector = slicer.qMRMLNodeComboBox()
        self.maskSelector.nodeTypes = ["vtkMRMLSegmentationNode"]
        self.maskSelector.addEnabled = False; self.maskSelector.noneEnabled = True
        self.maskSelector.setMRMLScene(slicer.mrmlScene)
        self.maskSelector.setToolTip("All visible segments of this segmentation are used as the artery mask")
        f.addRow("Artery mask:", self.maskSelector)

        # ---- 2. Branches and names (default workflow: the anatomist names the branches)
        box = ctk.ctkCollapsibleButton(); box.text = "2. Branches and names"
        self.layout.addWidget(box); f = qt.QFormLayout(box)
        info = qt.QLabel(
            "'Split into branches' cuts the artery tree at its bifurcations; every branch gets a number and "
            "a colour. Name a branch: choose a name, press 'Name branch' and click on the branch. "
            "Branches given the same name are merged. Unnamed branches stay numbered.")
        info.wordWrap = True
        f.addRow(info)
        self.splitButton = qt.QPushButton("Split into branches")
        f.addRow(self.splitButton)
        self.nameCombo = qt.QComboBox(); self.nameCombo.editable = True
        for abbr, latin, *_ in anatomy.ARTERIES:
            self.nameCombo.addItem(f"{abbr}  –  {latin}", abbr)
        for abbr in ("ECA R", "ECA L", anatomy.NON_VASCULAR[0], branches.UNNAMED, branches.REMOVED):
            self.nameCombo.addItem(abbr, abbr)
        f.addRow("Name:", self.nameCombo)
        row = qt.QHBoxLayout()
        self.nameButton = qt.QPushButton("Name branch")
        self.nameUndoButton = qt.QPushButton("Undo")
        self.volButton = qt.QPushButton("Volume table")
        row.addWidget(self.nameButton); row.addWidget(self.nameUndoButton); row.addWidget(self.volButton)
        f.addRow(row)
        self.finishButton = qt.QPushButton("Keep named arteries only")
        self.finishButton.toolTip = (
            "Make a clean segmentation with only the branches you named, one segment per artery with its "
            "anatomical name (e.g. 'A. basilaris [BA]'). Unnamed branches are left out. The numbered "
            "branches stay hidden, so you can go back and name more, then press this again.")
        self.showAllButton = qt.QPushButton("Show all branches")
        self.showAllButton.toolTip = ("Back to the numbered branches (the named segmentation is hidden, not deleted). "
                                      "Name more branches, then press 'Keep named arteries only' again.")
        row2 = qt.QHBoxLayout(); row2.addWidget(self.finishButton); row2.addWidget(self.showAllButton)
        f.addRow(row2)
        row3 = qt.QHBoxLayout()
        self.outerButton = qt.QPushButton("Remove scalp branches")
        self.outerButton.toolTip = (
            "Remove the unnamed branches lying just under the skin (superficial temporal, occipital and other "
            "extracranial arteries): median depth below the skin smaller than the value at the right, measured "
            "slice by slice. Named branches are never removed. Undo restores them. Single pieces can also be "
            "removed by naming them '(remove)'.")
        self.outerDepth = qt.QDoubleSpinBox(); self.outerDepth.setRange(3.0, 40.0); self.outerDepth.setValue(12.0)
        self.outerDepth.setSuffix(" mm"); self.outerDepth.setToolTip("Depth below the skin (intracranial vessels are deeper than ~15 mm)")
        row3.addWidget(self.outerButton, 1); row3.addWidget(self.outerDepth)
        f.addRow(row3)
        self.topcowSelector = slicer.qMRMLNodeComboBox()
        self.topcowSelector.nodeTypes = ["vtkMRMLLabelMapVolumeNode"]
        self.topcowSelector.addEnabled = False; self.topcowSelector.noneEnabled = True
        self.topcowSelector.setMRMLScene(slicer.mrmlScene)
        self.topcowSelector.setToolTip(
            "Optional: a TopCoW multiclass circle-of-Willis segmentation (load the output .mha/.nii.gz "
            "as a label map). Its classes are used as automatic seeds; P1/P2 and A1/A2 are split at the "
            "PComA/AComA junctions. Add manual seeds only for vessels TopCoW does not label (VA, SCA, AICA, PICA).")
        tcRow = qt.QHBoxLayout()
        tcRow.addWidget(self.topcowSelector, 1)
        self.topcowLoadButton = qt.QPushButton("Load file…")
        self.topcowLoadButton.toolTip = ("Load a TopCoW output (.mha / .nii.gz) as a label map and select it here")
        tcRow.addWidget(self.topcowLoadButton)
        self.topcowRunButton = qt.QPushButton("Run TopCoW…")
        self.topcowRunButton.toolTip = ("Run the TopCoW model (Docker image topcow24_ct:latest) on the selected TOF. "
                                        "The result is saved next to the TOF as <name>_TopCoW.mha and selected here. "
                                        "Takes about 2 minutes with an NVIDIA GPU.")
        tcRow.addWidget(self.topcowRunButton)
        f.addRow("TopCoW (optional):", tcRow)
        self.suggestNamesButton = qt.QPushButton("Suggest names from TopCoW (optional)")
        self.suggestNamesButton.toolTip = ("Branches lying mostly inside a TopCoW class get that name as a suggestion "
                                           "(shown as '<name> ?'). Confirm by naming the branch yourself.")
        f.addRow(self.suggestNamesButton)
        self.branchText = qt.QPlainTextEdit(); self.branchText.readOnly = True
        self.branchText.setMinimumHeight(120)
        f.addRow(self.branchText)
        self._nameNode = None

        # ---- 2. Seeds
        box = ctk.ctkCollapsibleButton(); box.text = "A. Automatic naming – seeds (advanced)"; box.collapsed = True
        self.layout.addWidget(box); f = qt.QFormLayout(box)
        info = qt.QLabel(
            "Choose an artery, press 'Place', then click on that artery in the 3D view or a slice. "
            "Placing stays on: choose the next artery and keep clicking. Skip arteries that are not visible. "
            "Several points with the same name are allowed. Press Esc or right-click to stop placing.")
        info.wordWrap = True
        f.addRow(info)
        self.arteryCombo = qt.QComboBox()
        for abbr, latin, *_ in anatomy.ARTERIES:
            if abbr in anatomy.DERIVED:
                continue
            self.arteryCombo.addItem(f"{abbr}  –  {latin}", abbr)
        f.addRow("Artery:", self.arteryCombo)
        row = qt.QHBoxLayout()
        self.placeButton = qt.QPushButton("Place")
        self.placeButton.toolTip = "Start placing points named after the selected artery"
        self.createSeedsButton = qt.QPushButton("New seed list")
        row.addWidget(self.placeButton); row.addWidget(self.createSeedsButton)
        f.addRow(row)
        self.seedsWidget = slicer.qSlicerSimpleMarkupsWidget()
        self.seedsWidget.setMRMLScene(slicer.mrmlScene)
        self.seedsWidget.markupsSelectorComboBox().nodeTypes = ["vtkMRMLMarkupsFiducialNode"]
        f.addRow(self.seedsWidget)


        # ---- 3. Label
        box = ctk.ctkCollapsibleButton(); box.text = "B. Automatic naming – label arteries (advanced)"; box.collapsed = True
        self.layout.addWidget(box); f = qt.QFormLayout(box)
        self.fixOriginsCheck = qt.QCheckBox("Colour branches from their origin (centreline correction)")
        self.fixOriginsCheck.checked = True
        f.addRow(self.fixOriginsCheck)
        self.bridgeCheck = qt.QCheckBox("Connect faint distal branches (bridge gaps)")
        self.bridgeCheck.checked = True
        self.bridgeCheck.setToolTip("On TOF distal branches fade and break into pieces. Thin pieces are joined to "
                                    "the tree along their brightest route (max 25 mm). The report lists how many.")
        f.addRow(self.bridgeCheck)
        self.acaCheck = qt.QCheckBox("Also name distal ACA branches (pericallosal course, variations)")
        self.acaCheck.checked = False
        self.acaCheck.setToolTip("Off: only the major arteries (TopCoW classes, BA/ICA/VA) and the SCAs are named; "
                                 "other branches stay as unnamed branches of their parent. On: the A2 territory is "
                                 "also analysed (A. pericallosa, median callosal artery, variation branches).")
        f.addRow(self.acaCheck)
        self.labelButton = qt.QPushButton("Label arteries")
        f.addRow(self.labelButton)
        self.resultText = qt.QPlainTextEdit(); self.resultText.readOnly = True
        self.resultText.setMinimumHeight(160)
        f.addRow(self.resultText)

        # ---- 4. Corrections by the anatomist
        box = ctk.ctkCollapsibleButton(); box.text = "C. Correct automatic labels (advanced)"; box.collapsed = True
        self.layout.addWidget(box); f = qt.QFormLayout(box)
        info = qt.QLabel(
            "Wrong name? Choose the correct artery and press 'Pick branch'. "
            "Segment mode (default): click the start and then the end of the wrong segment; only the "
            "vessel between the two clicks is renamed (works inside the circle of Willis). "
            "Branch mode: one click near the origin renames that branch onwards. You can type a new name.")
        info.wordWrap = True
        f.addRow(info)
        self.fixCombo = qt.QComboBox(); self.fixCombo.editable = True
        for abbr, latin, *_ in anatomy.ARTERIES:
            self.fixCombo.addItem(f"{abbr}  –  {latin}", abbr)
        for abbr in ("SCA R rami", "BA rami", anatomy.NON_VASCULAR[0], anatomy.UNCONNECTED[0]):
            self.fixCombo.addItem(abbr, abbr)
        f.addRow("Correct name:", self.fixCombo)
        self.fixModeCombo = qt.QComboBox()
        self.fixModeCombo.addItem("Segment between two clicks (start and end)", "path")
        self.fixModeCombo.addItem("Branch from the click onwards", "branch")
        f.addRow("Mode:", self.fixModeCombo)
        row = qt.QHBoxLayout()
        self.pickButton = qt.QPushButton("Pick branch")
        self.undoButton = qt.QPushButton("Undo last correction")
        row.addWidget(self.pickButton); row.addWidget(self.undoButton)
        f.addRow(row)
        self._fixNode = None
        self._fixObserver = None
        self._fixFirst = None

        # ---- 5. Export
        box = ctk.ctkCollapsibleButton(); box.text = "3. Export"; box.collapsed = True
        self.layout.addWidget(box); f = qt.QFormLayout(box)
        self.exportDir = ctk.ctkDirectoryButton()
        self.exportDir.directory = os.path.expanduser("~")
        f.addRow("Folder:", self.exportDir)
        self.exportButton = qt.QPushButton("Export each artery as STL")
        f.addRow(self.exportButton)

        self.layout.addStretch(1)

        self.suggestButton.connect("clicked()", self.onSuggest)
        self.extractButton.connect("clicked()", self.onExtract)
        self.createSeedsButton.connect("clicked()", self.onCreateSeeds)
        self.placeButton.connect("clicked()", self.onPlace)
        self.arteryCombo.connect("currentIndexChanged(int)", self.onArteryChanged)
        self.labelButton.connect("clicked()", self.onLabel)
        self.exportButton.connect("clicked()", self.onExport)
        self.pickButton.connect("clicked()", self.onPickBranch)
        self.topcowLoadButton.connect("clicked()", self.onLoadTopCoW)
        self.splitButton.connect("clicked()", self.onSplit)
        self.nameButton.connect("clicked()", self.onNameBranch)
        self.nameUndoButton.connect("clicked()", self.onNameUndo)
        self.volButton.connect("clicked()", self.onVolumeTable)
        self.finishButton.connect("clicked()", self.onKeepNamed)
        self.showAllButton.connect("clicked()", self.onShowAll)
        self.outerButton.connect("clicked()", self.onRemoveOuter)
        self.suggestNamesButton.connect("clicked()", self.onSuggestNames)
        self.topcowRunButton.connect("clicked()", self.onRunTopCoW)
        self.undoButton.connect("clicked()", self.onUndoCorrection)
        self.inputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onInputChanged)
        self.onInputChanged(self.inputSelector.currentNode())

        self.labelSegNode = None

    # -------------------------------------------------------------- callbacks
    def onInputChanged(self, node):
        if node is None:
            return
        arr = slicer.util.arrayFromVolume(node)
        mx = float(arr.max())
        for s in (self.lowSlider, self.highSlider):
            s.maximum = max(mx, 1.0)
        self.onSuggest()

    def onSuggest(self):
        node = self.inputSelector.currentNode()
        if node is None:
            return
        low, high = core.suggest_thresholds(slicer.util.arrayFromVolume(node))
        self.lowSlider.value = low
        self.highSlider.value = high

    def onExtract(self):
        node = self.inputSelector.currentNode()
        if node is None:
            slicer.util.errorDisplay("Select a TOF volume first.")
            return
        with slicer.util.tryWithErrorDisplay("Artery extraction failed.", waitCursor=True):
            seg = self.logic.extractArteries(node, self.lowSlider.value, self.highSlider.value,
                                             self.sigmaSpin.value, self.minSizeSpin.value)
            self.maskSelector.setCurrentNode(seg)

    def onCreateSeeds(self):
        node = self.logic.createSeedList(self.SEED_LIST_NAME)
        self.seedsWidget.setCurrentNode(node)
        return node

    def _seedNode(self):
        node = self.seedsWidget.currentNode()
        if node is None:
            node = self.onCreateSeeds()
        return node

    def onArteryChanged(self, index):
        node = self.seedsWidget.currentNode()
        if node is not None:
            node.SetControlPointLabelFormat(self.arteryCombo.currentData)

    def onPlace(self):
        node = self._seedNode()
        node.SetControlPointLabelFormat(self.arteryCombo.currentData)
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        selectionNode.SetReferenceActivePlaceNodeClassName("vtkMRMLMarkupsFiducialNode")
        selectionNode.SetActivePlaceNodeID(node.GetID())
        interactionNode = slicer.app.applicationLogic().GetInteractionNode()
        interactionNode.SetPlaceModePersistence(1)
        interactionNode.SetCurrentInteractionMode(interactionNode.Place)

    def onLabel(self):
        vol = self.inputSelector.currentNode()
        mask = self.maskSelector.currentNode()
        seeds = self.seedsWidget.currentNode()
        tc = self.topcowSelector.currentNode()
        if vol is None or mask is None or (seeds is None and tc is None):
            slicer.util.errorDisplay("Select the TOF volume, the artery mask and a seed list and/or TopCoW labels.")
            return
        with slicer.util.tryWithErrorDisplay("Labelling failed.", waitCursor=True):
            seg, report = self.logic.labelArteries(vol, mask, seeds, fixOrigins=self.fixOriginsCheck.checked, bridge=self.bridgeCheck.checked, distalAca=self.acaCheck.checked,
                                                   topcowNode=tc)
            self.labelSegNode = seg
            self.resultText.setPlainText(report)

    def onLoadTopCoW(self):
        start = os.path.expanduser("~")
        vol = self.inputSelector.currentNode()
        sn = vol.GetStorageNode() if vol else None
        if sn and sn.GetFileName():
            start = os.path.dirname(sn.GetFileName())   # TopCoW files are kept next to the TOF
        path = qt.QFileDialog.getOpenFileName(
            slicer.util.mainWindow(), "TopCoW label map", start,
            "Label maps (*.mha *.nii.gz *.nii *.nrrd);;All files (*)")
        if not path:
            return
        with slicer.util.tryWithErrorDisplay("Could not load the TopCoW file.", waitCursor=True):
            node = slicer.util.loadLabelVolume(path)
            base = os.path.basename(path)
            for ext in (".nii.gz", ".mha", ".nii", ".nrrd"):
                if base.endswith(ext):
                    base = base[: -len(ext)]
            if base == "output":   # raw Docker output: name it after the folder it came from
                base = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(path))))) + "_TopCoW"
            node.SetName(base)
            self.topcowSelector.setCurrentNode(node)
            vol = self.inputSelector.currentNode()
            if vol is not None and vol.GetName().split("_")[0][:6] not in base:
                slicer.util.warningDisplay(
                    f"Check that the TopCoW file belongs to this image:\nTOF: {vol.GetName()}\nTopCoW: {base}")

    # ---- branches workflow
    def onSplit(self):
        vol = self.inputSelector.currentNode(); mask = self.maskSelector.currentNode()
        if vol is None or mask is None:
            slicer.util.errorDisplay("Select the TOF volume and extract the arteries first.")
            return
        with slicer.util.tryWithErrorDisplay("Splitting failed.", waitCursor=True):
            seg, n, secs = self.logic.splitBranches(vol, mask)
            self.labelSegNode = seg
            self.branchText.setPlainText(f"{n} branches in {secs:.0f} s. Name the ones you need; the rest stay numbered.")

    def _nameAbbr(self):
        i = self.nameCombo.currentIndex; txt = self.nameCombo.currentText
        if i >= 0 and self.nameCombo.itemText(i) == txt:
            return self.nameCombo.itemData(i)
        return txt.split("  –  ")[0].strip()

    def onNameBranch(self):
        if not getattr(self.logic, "bstate", None):
            slicer.util.errorDisplay("Press 'Split into branches' first.")
            return
        if self._nameNode is None or slicer.mrmlScene.GetNodeByID(self._nameNode.GetID()) is None:
            self._nameNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "WillisLabel names")
            self._nameNode.CreateDefaultDisplayNodes()
            self._nameNode.GetDisplayNode().SetSelectedColor(1.0, 1.0, 0.0)
            self._nameNode.GetDisplayNode().SetPointLabelsVisibility(False)
            self._nameNode.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self._onNamePoint)
        self._nameNode.SetControlPointLabelFormat(self._nameAbbr())
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        selectionNode.SetReferenceActivePlaceNodeClassName("vtkMRMLMarkupsFiducialNode")
        selectionNode.SetActivePlaceNodeID(self._nameNode.GetID())
        interactionNode = slicer.app.applicationLogic().GetInteractionNode()
        interactionNode.SetPlaceModePersistence(1)   # keep clicking branches; Esc / right-click to stop
        interactionNode.SetCurrentInteractionMode(interactionNode.Place)

    def _onNamePoint(self, caller, event):
        n = caller.GetNumberOfControlPoints()
        if n == 0:
            return
        ras = [0.0, 0.0, 0.0]
        caller.GetNthControlPointPositionWorld(n - 1, ras)
        caller.RemoveNthControlPoint(n - 1)   # the click is only a pointer
        with slicer.util.tryWithErrorDisplay("Naming failed.", waitCursor=True):
            self.branchText.appendPlainText(self.logic.nameBranchAt(ras, self._nameAbbr()))

    def onNameUndo(self):
        with slicer.util.tryWithErrorDisplay("Undo failed.", waitCursor=True):
            self.branchText.appendPlainText(self.logic.undoName())

    def onVolumeTable(self):
        with slicer.util.tryWithErrorDisplay("Could not compute volumes.", waitCursor=True):
            self.branchText.appendPlainText(self.logic.volumeTable())

    def onKeepNamed(self):
        if not getattr(self.logic, "bstate", None):
            slicer.util.errorDisplay("Press 'Split into branches' and name some branches first.")
            return
        with slicer.util.tryWithErrorDisplay("Could not make the named segmentation.", waitCursor=True):
            node, names = self.logic.keepNamed()
            self.labelSegNode = node   # export uses the clean segmentation
            try:   # open it in Segment Editor's selectors (visible when the user switches there)
                ed = slicer.modules.segmenteditor.widgetRepresentation().self().editor
                ed.setSegmentationNode(node)
                ed.setSourceVolumeNode(self.logic.bstate["vol"])
            except Exception:
                pass
            self.branchText.appendPlainText(
                f"'{node.GetName()}': {len(names)} arteries, unnamed branches left out:\n  " + "\n  ".join(names))

    def onRemoveOuter(self):
        if not getattr(self.logic, "bstate", None):
            slicer.util.errorDisplay("Press 'Split into branches' first.")
            return
        with slicer.util.tryWithErrorDisplay("Could not remove the scalp branches.", waitCursor=True):
            self.branchText.appendPlainText(self.logic.removeOuter(self.outerDepth.value))

    def onShowAll(self):
        if not getattr(self.logic, "bstate", None):
            return
        self.logic.showBranches()
        self.branchText.appendPlainText("All numbered branches shown again. Name more branches, then press "
                                        "'Keep named arteries only' to update the named segmentation.")

    def onSuggestNames(self):
        tc = self.topcowSelector.currentNode()
        if tc is None:
            slicer.util.errorDisplay("Load a TopCoW file (Load file…) or run TopCoW first.")
            return
        with slicer.util.tryWithErrorDisplay("Suggestion failed.", waitCursor=True):
            self.branchText.appendPlainText(self.logic.suggestNames(tc))

    def onRunTopCoW(self):
        vol = self.inputSelector.currentNode()
        if vol is None:
            slicer.util.errorDisplay("Select the TOF volume first.")
            return
        if not slicer.util.confirmOkCancelDisplay(
                f"Run TopCoW on '{vol.GetName()}'?\n\nDocker Desktop must be running. Slicer will not respond "
                "for about 2 minutes (GPU) or longer (CPU)."):
            return
        with slicer.util.tryWithErrorDisplay("TopCoW failed.", waitCursor=True):
            node, path, secs = self.logic.runTopCoW(vol)
            self.topcowSelector.setCurrentNode(node)
            self.resultText.appendPlainText(f"TopCoW finished in {secs:.0f} s, saved to {path}")

    def _fixAbbr(self):
        i = self.fixCombo.currentIndex
        txt = self.fixCombo.currentText
        if i >= 0 and self.fixCombo.itemText(i) == txt:
            return self.fixCombo.itemData(i)
        return txt.split("  –  ")[0].strip()   # typed by the user

    def onPickBranch(self):
        if not getattr(self.logic, "state", None):
            slicer.util.errorDisplay("Run 'Label arteries' first.")
            return
        if self._fixNode is None or slicer.mrmlScene.GetNodeByID(self._fixNode.GetID()) is None:
            self._fixNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "WillisLabel corrections")
            self._fixNode.CreateDefaultDisplayNodes()
            self._fixNode.GetDisplayNode().SetSelectedColor(1.0, 1.0, 0.0)
            self._fixObserver = self._fixNode.AddObserver(
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self._onFixPoint)
        self._fixNode.SetControlPointLabelFormat("fix:" + self._fixAbbr())
        self._fixFirst = None
        if self.fixModeCombo.currentData == "path":
            self.resultText.appendPlainText(f"{self._fixAbbr()}: click the START of the segment, then its END.")
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        selectionNode.SetReferenceActivePlaceNodeClassName("vtkMRMLMarkupsFiducialNode")
        selectionNode.SetActivePlaceNodeID(self._fixNode.GetID())
        interactionNode = slicer.app.applicationLogic().GetInteractionNode()
        interactionNode.SetPlaceModePersistence(1 if self.fixModeCombo.currentData == "path" else 0)
        interactionNode.SetCurrentInteractionMode(interactionNode.Place)

    def _onFixPoint(self, caller, event):
        n = caller.GetNumberOfControlPoints()
        if n == 0:
            return
        ras = [0.0, 0.0, 0.0]
        caller.GetNthControlPointPositionWorld(n - 1, ras)
        abbr = self._fixAbbr()
        if self.fixModeCombo.currentData == "path":
            if getattr(self, "_fixFirst", None) is None:
                self._fixFirst = list(ras)
                self.resultText.appendPlainText("Start set – now click the END of the segment.")
                return
            first, self._fixFirst = self._fixFirst, None
            interactionNode = slicer.app.applicationLogic().GetInteractionNode()
            interactionNode.SetCurrentInteractionMode(interactionNode.ViewTransform)
            with slicer.util.tryWithErrorDisplay("Correction failed.", waitCursor=True):
                self.resultText.appendPlainText(self.logic.applyCorrectionPath(first, ras, abbr))
            return
        with slicer.util.tryWithErrorDisplay("Correction failed.", waitCursor=True):
            line = self.logic.applyCorrection(ras, abbr)
            self.resultText.appendPlainText(line)

    def onUndoCorrection(self):
        with slicer.util.tryWithErrorDisplay("Undo failed.", waitCursor=True):
            self.resultText.appendPlainText(self.logic.undoCorrection())

    def onExport(self):
        seg = self.labelSegNode
        if seg is None:
            slicer.util.errorDisplay("Run labelling first.")
            return
        with slicer.util.tryWithErrorDisplay("Export failed.", waitCursor=True):
            n = self.logic.exportSTL(seg, self.exportDir.directory)
            slicer.util.infoDisplay(f"{n} STL files written to\n{self.exportDir.directory}")


#
# Logic
#
class WillisLabelLogic(ScriptedLoadableModuleLogic):

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _spacingKJI(volumeNode):
        return tuple(volumeNode.GetSpacing()[::-1])

    @staticmethod
    def _siAxisKJI(volumeNode):
        """Array axis (k,j,i order) that runs most closely along superior-inferior."""
        m = vtk.vtkMatrix4x4(); volumeNode.GetIJKToRASDirectionMatrix(m)
        s_comp = [abs(m.GetElement(2, c)) for c in range(3)]  # columns i, j, k
        ijk_axis = int(np.argmax(s_comp))
        return 2 - ijk_axis

    @staticmethod
    def _postSupKJI(volumeNode):
        """Unit vectors (array axes k,j,i in mm) pointing posterior, superior and left."""
        m = vtk.vtkMatrix4x4(); volumeNode.GetIJKToRASDirectionMatrix(m)
        post = np.array([-m.GetElement(1, 2 - a) for a in range(3)])
        sup = np.array([m.GetElement(2, 2 - a) for a in range(3)])
        left = np.array([-m.GetElement(0, 2 - a) for a in range(3)])
        return post, sup, left

    # ------------------------------------------------------------- extraction
    def extractArteries(self, volumeNode, low, high, sigma=0.5, minSize=30.0):
        arr = slicer.util.arrayFromVolume(volumeNode)
        t0 = time.time()
        mask = core.extract_vessels(arr, self._spacingKJI(volumeNode), low, high, sigma, minSize)
        seg = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", "Arteries mask")
        seg.SetReferenceImageGeometryParameterFromVolumeNode(volumeNode)
        seg.CreateDefaultDisplayNodes()
        sid = seg.GetSegmentation().AddEmptySegment("Arteries")
        seg.GetSegmentation().GetSegment(sid).SetColor(0.82, 0.16, 0.14)
        slicer.util.updateSegmentBinaryLabelmapFromArray(mask.astype(np.uint8), seg, sid, volumeNode)
        seg.CreateClosedSurfaceRepresentation()
        logging_msg = f"WillisLabel: {int(mask.sum())} artery voxels in {time.time() - t0:.1f} s"
        print(logging_msg)
        return seg

    # ------------------------------------------------------------------ seeds
    def createSeedList(self, name):
        node = slicer.mrmlScene.GetFirstNodeByName(name)
        if node is None or not node.IsA("vtkMRMLMarkupsFiducialNode"):
            node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", name)
            node.CreateDefaultDisplayNodes()
        dn = node.GetDisplayNode()
        dn.SetTextScale(2.5); dn.SetGlyphScale(1.5)
        return node

    def seedsKJI(self, seedNode, volumeNode):
        rasToIjk = vtk.vtkMatrix4x4(); volumeNode.GetRASToIJKMatrix(rasToIjk)
        seeds = {}
        for i in range(seedNode.GetNumberOfControlPoints()):
            if seedNode.GetNthControlPointPositionStatus(i) != slicer.vtkMRMLMarkupsNode.PositionDefined:
                continue
            ras = [0.0, 0.0, 0.0]; seedNode.GetNthControlPointPositionWorld(i, ras)
            ijk = rasToIjk.MultiplyPoint(ras + [1.0])[:3]
            kji = tuple(int(round(x)) for x in ijk[::-1])
            seeds.setdefault(seedNode.GetNthControlPointLabel(i).strip(), []).append(kji)
        return seeds

    # --------------------------------------------------------------- labelling
    def maskArray(self, segNode, volumeNode):
        lab = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
        try:
            slicer.modules.segmentations.logic().ExportVisibleSegmentsToLabelmapNode(segNode, lab, volumeNode)
            return slicer.util.arrayFromVolume(lab) > 0
        finally:
            slicer.mrmlScene.RemoveNode(lab)

    # ------------------------------------------------------- branches workflow
    def splitBranches(self, volumeNode, maskSegNode):
        t0 = time.time()
        mask = self.maskArray(maskSegNode, volumeNode)
        spacing = self._spacingKJI(volumeNode)
        lab, n = branches.split_branches(mask, spacing, si_axis=self._siAxisKJI(volumeNode))
        seg = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", "Artery branches")
        seg.SetReferenceImageGeometryParameterFromVolumeNode(volumeNode)
        seg.CreateDefaultDisplayNodes()
        self.bstate = dict(seg=seg, vol=volumeNode, lab=lab, spacing=spacing, n=n,
                           name={}, undo=[], log=[])
        # import all branches at once through a labelmap + colour table (fast, names and colours set)
        ct = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLColorTableNode", "WillisLabel branch colours")
        ct.SetTypeToUser(); ct.SetNumberOfColors(n + 1)
        ct.SetColor(0, "background", 0, 0, 0, 0)
        for b in range(1, n + 1):
            ct.SetColor(b, branches.branch_id(b), *branches.colour(b), 1.0)
        lm = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode", "WillisLabel branches tmp")
        m = vtk.vtkMatrix4x4(); volumeNode.GetIJKToRASMatrix(m); lm.SetIJKToRASMatrix(m)
        slicer.util.updateVolumeFromArray(lm, lab.astype(np.int32))
        lm.CreateDefaultDisplayNodes(); lm.GetDisplayNode().SetAndObserveColorNodeID(ct.GetID())
        try:
            slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(lm, seg)
        finally:
            slicer.mrmlScene.RemoveNode(lm); slicer.mrmlScene.RemoveNode(ct)
        seg.CreateClosedSurfaceRepresentation()
        maskSegNode.GetDisplayNode().SetVisibility(False)
        return seg, n, time.time() - t0

    def _writeBranchSegment(self, sid, mask, abbr, b=None):
        st = self.bstate
        segmentation = st["seg"].GetSegmentation()
        if abbr is None:   # branch segments were imported: their ID is found through their name
            found = segmentation.GetSegmentIdBySegmentName(sid)
            if found:
                sid = found
        if not mask.any():
            if segmentation.GetSegment(sid) is not None:
                segmentation.RemoveSegment(sid)
            return
        if segmentation.GetSegment(sid) is None:
            if abbr is None:
                name, col = sid, branches.colour(b)
            elif abbr == anatomy.NON_VASCULAR[0]:
                name, col = anatomy.segment_name(abbr), anatomy.NON_VASCULAR[2]
            elif abbr.endswith(" ?"):
                base = abbr[:-2]
                name = anatomy.segment_name(base) + " – suggestion"
                col = tuple(0.55 + 0.45 * c for c in anatomy.colour(base, 0))
            else:
                name, col = anatomy.segment_name(abbr), anatomy.colour(abbr, b or 0)
            segmentation.AddEmptySegment(sid, name)
            segmentation.GetSegment(sid).SetColor(*col)
        slicer.util.updateSegmentBinaryLabelmapFromArray(mask.astype(np.uint8), st["seg"], sid, st["vol"])

    def _segmentOf(self, b):
        abbr = self.bstate["name"].get(b)
        return (branches.branch_id(b), None) if abbr is None else (abbr, abbr)

    def _refresh(self, sids):
        st = self.bstate
        for sid, abbr in sids:
            if abbr is None:
                b = int(sid.split()[-1])
                self._writeBranchSegment(sid, (st["lab"] == b) if b not in st["name"] else np.zeros(1, bool), None, b)
            elif abbr == branches.REMOVED:
                continue   # removed branches get no segment
            else:
                bs = [b for b, a in st["name"].items() if a == abbr]
                self._writeBranchSegment(sid, np.isin(st["lab"], bs) if bs else np.zeros(1, bool), abbr)
        st["seg"].CreateClosedSurfaceRepresentation()

    def _setName(self, b, abbr):
        st = self.bstate
        old = self._segmentOf(b)
        if abbr in (None, branches.UNNAMED):
            st["name"].pop(b, None)
        else:
            st["name"][b] = abbr
        self._refresh([old, self._segmentOf(b)])
        if st.get("namedView"):   # keep the named view up to date while naming / undoing in it
            if any(not a.endswith(" ?") and a != branches.REMOVED for a in st["name"].values()):
                self.keepNamed()
            else:
                self.showBranches()

    def nameBranchAt(self, ras, abbr):
        st = getattr(self, "bstate", None)
        if not st:
            raise ValueError("Press 'Split into branches' first.")
        m = vtk.vtkMatrix4x4(); st["vol"].GetRASToIJKMatrix(m)
        ijk = m.MultiplyPoint(list(ras) + [1.0])[:3]
        kji = tuple(min(max(int(round(c)), 0), n - 1) for c, n in zip(ijk[::-1], st["lab"].shape))
        b = branches.branch_at(st["lab"], kji, st["spacing"])
        if b is None:
            return "No branch within 3 mm of the click."
        before = st["name"].get(b)
        st["undo"].append((b, before))
        self._setName(b, abbr)
        mm3 = float((st["lab"] == b).sum() * np.prod(st["spacing"]))
        line = f"Branch {b} ({mm3:.0f} mm³): {before or 'unnamed'} -> {abbr}"
        st["log"].append(line)
        st["seg"].SetAttribute("WillisLabel.names", "\n".join(st["log"]))
        return line

    def undoName(self):
        st = getattr(self, "bstate", None)
        if not st or not st["undo"]:
            return "Nothing to undo."
        entry = st["undo"].pop()
        if isinstance(entry[0], str):   # ("batch", [(branch, previous name), ...])
            items = entry[1]
            for b, before in items:
                if before is None:
                    st["name"].pop(b, None)
                else:
                    st["name"][b] = before
            self._refresh([(branches.branch_id(b), None) for b, _ in items])
            return f"Undo: {len(items)} removed branches restored"
        b, before = entry
        self._setName(b, before)
        return f"Undo: branch {b} -> {before or 'unnamed'}"

    def removeOuter(self, max_depth_mm=12.0):
        """Remove (name '(remove)') the unnamed branches lying less than max_depth_mm under the skin."""
        st = self.bstate
        if "depth" not in st:
            image = slicer.util.arrayFromVolume(st["vol"])
            st["depth"] = branches.scalp_depth(image, st["spacing"], si_axis=self._siAxisKJI(st["vol"]))
        bs = branches.outer_branches(st["lab"], st["depth"], max_depth_mm, skip=set(st["name"]))
        if not bs:
            return f"No unnamed branch lies less than {max_depth_mm:.0f} mm under the skin."
        for b in bs:
            st["name"][b] = branches.REMOVED
        st["undo"].append(("batch", [(b, None) for b in bs]))
        self._refresh([(branches.branch_id(b), None) for b in bs])
        mm3 = float(np.isin(st["lab"], bs).sum() * np.prod(st["spacing"]))
        line = (f"Removed {len(bs)} scalp branches ({mm3:.0f} mm³) less than {max_depth_mm:.0f} mm under the skin. "
                "Undo restores them.")
        st["log"].append(line)
        st["seg"].SetAttribute("WillisLabel.names", "\n".join(st["log"]))
        return line

    def volumeTable(self):
        st = self.bstate
        vox = float(np.prod(st["spacing"]))
        vols = np.bincount(st["lab"].ravel(), minlength=st["n"] + 1) * vox
        named = {}
        for b, a in st["name"].items():
            named[a] = named.get(a, 0.0) + vols[b]
        lines = ["Name\tvolume (mm³)\tbranches"]
        for a in sorted(named):
            nb = sum(1 for x in st["name"].values() if x == a)
            lines.append(f"{a}\t{named[a]:.0f}\t{nb}")
        un = [b for b in range(1, st["n"] + 1) if b not in st["name"]]
        lines.append(f"(unnamed)\t{sum(vols[b] for b in un):.0f}\t{len(un)}")
        return "\n".join(lines)

    def keepNamed(self):
        """Clean segmentation: one segment per confirmed name (suggestions '<x> ?' and unnamed left out).
        Re-pressing replaces the previous clean node. Returns (node, list of segment names)."""
        st = self.bstate
        nodeName = st["vol"].GetName() + " – named arteries"
        old = st.get("named")
        if old is not None and slicer.mrmlScene.GetNodeByID(old.GetID()) is not None:
            slicer.mrmlScene.RemoveNode(old)
        abbrs = sorted({a for a in st["name"].values() if not a.endswith(" ?") and a != branches.REMOVED})
        if not abbrs:
            raise ValueError("No branch has been named yet.")
        node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", nodeName)
        node.SetReferenceImageGeometryParameterFromVolumeNode(st["vol"])
        node.CreateDefaultDisplayNodes()
        segmentation = node.GetSegmentation()
        names = []
        for i, a in enumerate(abbrs):
            bs = [b for b, x in st["name"].items() if x == a]
            name = anatomy.segment_name(a)
            col = anatomy.NON_VASCULAR[2] if a == anatomy.NON_VASCULAR[0] else anatomy.colour(a, i)
            sid = segmentation.AddEmptySegment(a, name)
            segmentation.GetSegment(sid).SetColor(*col)
            slicer.util.updateSegmentBinaryLabelmapFromArray(
                np.isin(st["lab"], bs).astype(np.uint8), node, sid, st["vol"])
            names.append(name)
        node.SetAttribute("WillisLabel.names", "\n".join(st["log"]))
        node.CreateClosedSurfaceRepresentation()
        st["seg"].GetDisplayNode().SetVisibility(False)
        st["named"] = node
        st["namedView"] = True
        return node, names

    def showBranches(self):
        st = self.bstate
        st["namedView"] = False
        st["seg"].GetDisplayNode().SetVisibility(True)
        named = st.get("named")
        if named is not None and slicer.mrmlScene.GetNodeByID(named.GetID()) is not None:
            named.GetDisplayNode().SetVisibility(False)

    def suggestNames(self, topcowNode):
        st = self.bstate
        tc = self.labelmapOnGrid(topcowNode, st["vol"])
        _, region, _ = topcow.seeds_from_topcow(tc, st["spacing"])
        cnt = 0
        for b in range(1, st["n"] + 1):
            if b in st["name"] and not st["name"][b].endswith(" ?"):
                continue   # never overwrite the anatomist's name
            m = st["lab"] == b
            best, frac = None, 0.0
            for name, r in region.items():
                f = float((m & r).sum()) / float(m.sum())
                if f > frac:
                    best, frac = name, f
            if best is not None and frac >= 0.5:
                st["name"][b] = best + " ?"
                cnt += 1
        sids = set()
        for b in range(1, st["n"] + 1):
            sids.add((branches.branch_id(b), None))
        for a in set(st["name"].values()):
            sids.add((a, a))
        self._refresh(sorted(sids, key=lambda x: (x[1] is None, x[0])))
        return f"{cnt} branches got a suggested name ('<name> ?'). Confirm or correct them with 'Name branch'."

    def runTopCoW(self, volumeNode, image="topcow24_ct:latest", useGpu=True):
        """Run the TopCoW Docker model on a TOF volume. Returns (labelmap node, saved path, seconds)."""
        import shutil
        import subprocess
        import SimpleITK as sitk
        import sitkUtils
        if shutil.which("docker") is None:
            raise RuntimeError("Docker was not found. Install Docker Desktop and load the TopCoW image (see guide).")
        t0 = time.time()
        work = os.path.join(os.path.expanduser("~"), "WillisLabel_TopCoW", volumeNode.GetName())
        indir, outdir = os.path.join(work, "in"), os.path.join(work, "out")
        shutil.rmtree(work, ignore_errors=True)
        for sub in ("head-mr-angio", "head-ct-angio"):
            os.makedirs(os.path.join(indir, "images", sub))
        os.makedirs(outdir)
        img = sitk.DICOMOrient(sitkUtils.PullVolumeFromSlicer(volumeNode), "LPS")  # the model expects LPS
        for sub in ("head-mr-angio", "head-ct-angio"):
            sitk.WriteImage(img, os.path.join(indir, "images", sub, "tof.nii.gz"))

        def run(gpu):
            cmd = ["docker", "run", "--rm", "--network", "none", "--shm-size=8g"]
            if gpu:
                cmd += ["--gpus", "all"]
            cmd += ["-v", f"{indir}:/input:ro", "-v", f"{outdir}:/output", image]
            return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

        r = run(useGpu)
        result = os.path.join(outdir, "images", "cow-multiclass-segmentation", "output.mha")
        if not os.path.exists(result) and useGpu:
            r = run(False)  # no NVIDIA GPU: try on the CPU (slow, not validated)
        if not os.path.exists(result):
            raise RuntimeError("TopCoW produced no output.\n" + (r.stderr or r.stdout)[-1500:])
        sn = volumeNode.GetStorageNode()
        folder = os.path.dirname(sn.GetFileName()) if sn and sn.GetFileName() else work
        saved = os.path.join(folder, volumeNode.GetName() + "_TopCoW.mha")
        try:
            shutil.copyfile(result, saved)
        except OSError:
            saved = result
        node = slicer.util.loadLabelVolume(saved)
        node.SetName(volumeNode.GetName() + "_TopCoW")
        return node, saved, time.time() - t0

    def labelmapOnGrid(self, labelNode, volumeNode):
        """Label map values resampled (nearest neighbour, in physical space) onto the volume's grid.

        SimpleITK is used so that differently oriented grids (e.g. a TopCoW output written in LPS
        for a volume stored in another orientation) are matched by their physical coordinates.
        """
        import SimpleITK as sitk
        import sitkUtils
        lab = sitkUtils.PullVolumeFromSlicer(labelNode)
        ref = sitkUtils.PullVolumeFromSlicer(volumeNode)
        out = sitk.Resample(lab, ref, sitk.Transform(), sitk.sitkNearestNeighbor, 0, sitk.sitkUInt8)
        return sitk.GetArrayFromImage(out).astype(np.uint8)

    def labelArteries(self, volumeNode, maskSegNode, seedNode, fixOrigins=True, topcowNode=None, bridge=True,
                      distalAca=False):
        t0 = time.time()
        img = slicer.util.arrayFromVolume(volumeNode)
        mask = self.maskArray(maskSegNode, volumeNode)
        spacing = self._spacingKJI(volumeNode)
        raw = self.seedsKJI(seedNode, volumeNode) if seedNode is not None else {}
        tcNotes, tcVariants, tcSeeds = [], None, {}
        if topcowNode is not None:
            tc = self.labelmapOnGrid(topcowNode, volumeNode)
            # TopCoW labels must lie on this image's bright vessels; if most of them do not, the file
            # belongs to another subject or another acquisition
            inside = float(((tc > 0) & mask).sum()) / max(int((tc > 0).sum()), 1)
            if inside < 0.6:
                raise ValueError(
                    f"Only {inside:.0%} of the TopCoW labels lie on arteries of this image. "
                    "The TopCoW file probably belongs to another subject or scan "
                    f"('{topcowNode.GetName()}' for '{volumeNode.GetName()}'). Load the matching TopCoW file.")
            mask = mask | (tc > 0)
            tcSeeds, _, tcNotes = topcow.seeds_from_topcow(tc, spacing)
            tcVariants = topcow.variant_summary(tc)
            tcVol = {topcow.TOPCOW[v]: float((tc == v).sum() * np.prod(spacing)) for v in topcow.TOPCOW if (tc == v).any()}
            tcNotes.insert(0, f"TopCoW file '{topcowNode.GetName()}': {inside:.0%} of its labels lie on extracted arteries")
            tcNotes.insert(1, "TopCoW classes on this grid (mm³): " + ", ".join(f"{k} {v:.0f}" for k, v in tcVol.items()))
        if not raw and not tcSeeds:
            raise ValueError("No seed points have been placed and no TopCoW labels were given.")
        rad = tuple(max(1, int(round(2.0 / s))) for s in spacing)  # search 2 mm around each seed
        seeds, lost = {}, []
        for name, pts in raw.items():
            for p in pts:
                q = core.snap_to_mask(mask, img, p, rad)
                if q is None:
                    lost.append(name)
                else:
                    seeds.setdefault(name, []).append(q)
        for name, pts in tcSeeds.items():
            seeds.setdefault(name, []).extend(pts)
        bridgeRep = None
        if bridge:
            allPts = [p for pts in seeds.values() for p in pts]
            mask, bridgeRep = core.bridge_fragments(img, mask, allPts, spacing)
        lab, names, _ = core.label_from_seeds(mask, seeds, spacing)
        fixReport, fatMm3 = {}, 0.0
        if fixOrigins:
            lab, fixReport = core.fix_branch_origins(lab, mask, names, anatomy.parents(), spacing,
                                                    si_axis=self._siAxisKJI(volumeNode), other_branches=True,
                                                    distal=anatomy.DISTAL, seeds=seeds)
            lab, names, fatMm3 = core.flag_thick_rami(lab, names, mask, spacing)

        post, sup, left = self._postSupKJI(volumeNode)
        acaLines = []
        if distalAca:
            lab, names, acaLines = aca.classify_distal_aca(lab, names, spacing, post, sup)
        lab, names, scaLines = sca.name_sca(lab, names, spacing, post, sup, left)

        seg = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", "Labelled arteries")
        seg.SetReferenceImageGeometryParameterFromVolumeNode(volumeNode)
        seg.CreateDefaultDisplayNodes()
        voxmm3 = float(np.prod(spacing))
        lines = ["Artery\tvolume (mm³)"]
        values = [(i + 1, n) for i, n in enumerate(names)]
        if (lab == core.UNCONNECTED).any():
            values.append((core.UNCONNECTED, anatomy.UNCONNECTED[0]))
        for v, n in values:
            m = (lab == v)
            if not m.any():
                continue  # e.g. a TopCoW '3rd A2' that was renamed by the distal ACA analysis
            if n == anatomy.UNCONNECTED[0]:
                segName, col = anatomy.UNCONNECTED[0], anatomy.UNCONNECTED[2]
            else:
                segName, col = anatomy.segment_name(n), anatomy.colour(n, v - 1)
            sid = seg.GetSegmentation().AddEmptySegment(n, segName)
            seg.GetSegmentation().GetSegment(sid).SetColor(*col)
            slicer.util.updateSegmentBinaryLabelmapFromArray(m.astype(np.uint8), seg, sid, volumeNode)
            lines.append(f"{n}\t{m.sum() * voxmm3:.0f}")
        seg.CreateClosedSurfaceRepresentation()
        maskSegNode.GetDisplayNode().SetVisibility(False)

        covered = {"P1 R": "PCA R", "P2 R": "PCA R", "P1 L": "PCA L", "P2 L": "PCA L",
                   "A1 R": "ACA R", "A2 R": "ACA R", "A1 L": "ACA L", "A2 L": "ACA L"}
        notPlaced = [a[0] for a in anatomy.ARTERIES if a[0] not in seeds
                     and a[0] not in anatomy.NOT_SEEDED
                     and covered.get(a[0]) not in seeds]
        lines.append("")
        if tcVariants is not None:
            lines.append("Circle of Willis (from TopCoW labels; 'not visualised' is not proof of absence):")
            for k in ("A1 R", "A1 L", "AComA", "3rd A2", "PComA R", "PComA L", "P1 R", "P1 L"):
                lines.append(f"  {k}: {tcVariants[k]}")
            lines.extend(tcNotes)
            lines.append("")
        if fatMm3:
            lines.append(f"Thick side pieces moved to 'Non-vascular?' (probably fat): {fatMm3:.0f} mm³")
        if bridgeRep and bridgeRep["fragments"]:
            lines.append(f"Gap bridging: {bridgeRep['joined']} of {bridgeRep['fragments']} isolated fragments joined "
                         f"({bridgeRep['joined_mm3']:.0f} mm³, {bridgeRep['bridge_vox']} bridge voxels); "
                         f"{bridgeRep['rejected_thick']} thick fragments (probably fat) not joined")
        if scaLines:
            lines.extend(scaLines)
            lines.append("")
        if acaLines:
            lines.extend(acaLines)
            lines.append("")
        if lost:
            lines.append("Seeds outside the mask (ignored): " + ", ".join(sorted(set(lost))))
        if notPlaced:
            lines.append("Not seeded (not visible / not assessed): " + ", ".join(notPlaced))
        for p, r in fixReport.items():
            lines.append(f"Origin correction {p}: {r['stubs']} branch stubs, {r['moved_vox']} voxels re-assigned")
        lines.append(f"Done in {time.time() - t0:.1f} s")
        # kept for anatomist corrections (section 4)
        self.state = dict(seg=seg, vol=volumeNode, lab=lab, names=list(names), spacing=spacing, undo=[], log=[])
        return seg, "\n".join(lines)

    # ------------------------------------------------------------- correction
    def _abbrOf(self, value):
        st = self.state
        if value == core.UNCONNECTED:
            return anatomy.UNCONNECTED[0]
        return st["names"][value - 1]

    def _valueOf(self, abbr):
        st = self.state
        if abbr == anatomy.UNCONNECTED[0]:
            return core.UNCONNECTED
        if abbr not in st["names"]:
            st["names"].append(abbr)
        return st["names"].index(abbr) + 1

    def _writeSegment(self, abbr, mask):
        st = self.state
        segmentation = st["seg"].GetSegmentation()
        if segmentation.GetSegment(abbr) is None:
            if abbr == anatomy.UNCONNECTED[0]:
                name, col = anatomy.UNCONNECTED[0], anatomy.UNCONNECTED[2]
            else:
                name, col = anatomy.segment_name(abbr), anatomy.colour(abbr, len(st["names"]))
            segmentation.AddEmptySegment(abbr, name)
            segmentation.GetSegment(abbr).SetColor(*col)
        slicer.util.updateSegmentBinaryLabelmapFromArray(mask.astype(np.uint8), st["seg"], abbr, st["vol"])

    def applyCorrection(self, ras, newAbbr):
        """Rename the branch from the clicked point (RAS) onwards. Returns a report line."""
        st = getattr(self, "state", None)
        if not st:
            raise ValueError("Run 'Label arteries' first.")
        m = vtk.vtkMatrix4x4(); st["vol"].GetRASToIJKMatrix(m)
        ijk = m.MultiplyPoint(list(ras) + [1.0])[:3]
        kji = tuple(int(round(c)) for c in ijk[::-1])
        kji = tuple(min(max(c, 0), n - 1) for c, n in zip(kji, st["lab"].shape))
        new = self._valueOf(newAbbr)
        before = st["lab"].copy()
        lab, info = core.relabel_branch(st["lab"], kji, new, st["spacing"], si_axis=self._siAxisKJI(st["vol"]))
        if info is None:
            return "No vessel within 3 mm of the click – nothing changed."
        if info["old"] == new:
            return f"That branch is already {newAbbr}."
        st["undo"] = (st["undo"] + [(before, info["old"], new)])[-5:]
        oldAbbr = self._abbrOf(info["old"])
        self._writeSegment(oldAbbr, lab == info["old"])
        self._writeSegment(newAbbr, lab == new)
        st["seg"].CreateClosedSurfaceRepresentation()
        mm3 = info["n"] * float(np.prod(st["spacing"]))
        line = f"Correction: {oldAbbr} -> {newAbbr} ({mm3:.0f} mm³) at RAS ({ras[0]:.1f}, {ras[1]:.1f}, {ras[2]:.1f})"
        st["log"].append(line)
        st["seg"].SetAttribute("WillisLabel.corrections", "\n".join(st["log"]))
        return line

    def _kji(self, ras):
        st = self.state
        m = vtk.vtkMatrix4x4(); st["vol"].GetRASToIJKMatrix(m)
        ijk = m.MultiplyPoint(list(ras) + [1.0])[:3]
        kji = [int(round(c)) for c in ijk[::-1]]
        return tuple(min(max(c, 0), n - 1) for c, n in zip(kji, st["lab"].shape))

    def applyCorrectionPath(self, ras1, ras2, newAbbr):
        """Rename the vessel segment between two clicked points (RAS). Returns a report line."""
        st = getattr(self, "state", None)
        if not st:
            raise ValueError("Run 'Label arteries' first.")
        new = self._valueOf(newAbbr)
        before = st["lab"].copy()
        lab, info = core.relabel_path(st["lab"], self._kji(ras1), self._kji(ras2), new, st["spacing"])
        if info is None:
            return "No vessel path between the two clicks – nothing changed."
        olds = list(info["olds"])
        st["undo"] = (st["undo"] + [(before, olds, new)])[-5:]
        for v in olds:
            self._writeSegment(self._abbrOf(v), lab == v)
        self._writeSegment(newAbbr, lab == new)
        st["seg"].CreateClosedSurfaceRepresentation()
        vox = float(np.prod(st["spacing"]))
        frm = ", ".join(f"{self._abbrOf(v)} {c * vox:.0f} mm³" for v, c in info["olds"].items())
        line = f"Correction (segment): -> {newAbbr} ({frm or 'no change'})"
        st["log"].append(line)
        st["seg"].SetAttribute("WillisLabel.corrections", "\n".join(st["log"]))
        return line

    def undoCorrection(self):
        st = getattr(self, "state", None)
        if not st or not st["undo"]:
            return "Nothing to undo."
        before, old, new = st["undo"].pop()
        st["lab"][...] = before
        for v in (list(old) if isinstance(old, (list, tuple)) else [old]) + [new]:
            self._writeSegment(self._abbrOf(v), before == v)
        st["seg"].CreateClosedSurfaceRepresentation()
        st["log"].append("Undo: " + (st["log"][-1] if st["log"] else ""))
        st["seg"].SetAttribute("WillisLabel.corrections", "\n".join(st["log"]))
        return "Last correction undone."

    # ------------------------------------------------------------------ export
    def exportSTL(self, segNode, folder):
        ids = vtk.vtkStringArray()
        segNode.GetSegmentation().GetSegmentIDs(ids)
        slicer.vtkSlicerSegmentationsModuleLogic.ExportSegmentsClosedSurfaceRepresentationToFiles(
            folder, segNode, ids, "STL", True, 1.0, False)
        return ids.GetNumberOfValues()


#
# Test
#
class WillisLabelTest(ScriptedLoadableModuleTest):
    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.test_Y_shape()

    def test_Y_shape(self):
        """Synthetic Y: trunk 'BA' splitting into 'P1 R' and 'P1 L'."""
        self.delayDisplay("Building synthetic vessel")
        arr = np.zeros((60, 60, 60), np.float32)
        kk, jj, ii = np.mgrid[0:60, 0:60, 0:60]
        trunk = ((jj - 30) ** 2 + (ii - 30) ** 2 <= 9) & (kk < 35)
        right = (((jj - 30) ** 2 + (ii - (30 - (kk - 34))) ** 2) <= 6) & (kk >= 34) & (kk < 55)
        left = (((jj - 30) ** 2 + (ii - (30 + (kk - 34))) ** 2) <= 6) & (kk >= 34) & (kk < 55)
        arr[trunk | right | left] = 1000
        arr += np.random.RandomState(0).normal(0, 20, arr.shape).astype(np.float32)
        vol = slicer.util.addVolumeFromArray(arr, name="synthetic TOF")

        logic = WillisLabelLogic()
        seg = logic.extractArteries(vol, 500, 800, sigma=0.0, minSize=1)
        seeds = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode")
        ijkToRas = vtk.vtkMatrix4x4(); vol.GetIJKToRASMatrix(ijkToRas)
        for label, (k, j, i) in {"BA": (10, 30, 30), "P1 R": (50, 30, 14), "P1 L": (50, 30, 46)}.items():
            ras = ijkToRas.MultiplyPoint([i, j, k, 1])[:3]
            seeds.AddControlPoint(vtk.vtkVector3d(*ras), label)
        out, report = logic.labelArteries(vol, seg, seeds, fixOrigins=False)
        self.assertEqual(out.GetSegmentation().GetNumberOfSegments(), 3)
        self.delayDisplay("Test passed\n" + report)
