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

from WillisLabelLib import anatomy, core, topcow


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

        # ---- 2. Seeds
        box = ctk.ctkCollapsibleButton(); box.text = "2. Place seeds"
        self.layout.addWidget(box); f = qt.QFormLayout(box)
        info = qt.QLabel(
            "Choose an artery, press 'Place', then click on that artery in the 3D view or a slice. "
            "Placing stays on: choose the next artery and keep clicking. Skip arteries that are not visible. "
            "Several points with the same name are allowed. Press Esc or right-click to stop placing.")
        info.wordWrap = True
        f.addRow(info)
        self.arteryCombo = qt.QComboBox()
        for abbr, latin, *_ in anatomy.ARTERIES:
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

        self.topcowSelector = slicer.qMRMLNodeComboBox()
        self.topcowSelector.nodeTypes = ["vtkMRMLLabelMapVolumeNode"]
        self.topcowSelector.addEnabled = False; self.topcowSelector.noneEnabled = True
        self.topcowSelector.setMRMLScene(slicer.mrmlScene)
        self.topcowSelector.setToolTip(
            "Optional: a TopCoW multiclass circle-of-Willis segmentation (load the output .mha/.nii.gz "
            "as a label map). Its classes are used as automatic seeds; P1/P2 and A1/A2 are split at the "
            "PComA/AComA junctions. Add manual seeds only for vessels TopCoW does not label (VA, SCA, AICA, PICA).")
        f.addRow("TopCoW labels (optional):", self.topcowSelector)

        # ---- 3. Label
        box = ctk.ctkCollapsibleButton(); box.text = "3. Label arteries"
        self.layout.addWidget(box); f = qt.QFormLayout(box)
        self.fixOriginsCheck = qt.QCheckBox("Colour branches from their origin (centreline correction)")
        self.fixOriginsCheck.checked = True
        f.addRow(self.fixOriginsCheck)
        self.labelButton = qt.QPushButton("Label arteries")
        f.addRow(self.labelButton)
        self.resultText = qt.QPlainTextEdit(); self.resultText.readOnly = True
        self.resultText.setMinimumHeight(160)
        f.addRow(self.resultText)

        # ---- 4. Export
        box = ctk.ctkCollapsibleButton(); box.text = "4. Export"; box.collapsed = True
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
            seg, report = self.logic.labelArteries(vol, mask, seeds, fixOrigins=self.fixOriginsCheck.checked,
                                                   topcowNode=tc)
            self.labelSegNode = seg
            self.resultText.setPlainText(report)

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

    def labelmapOnGrid(self, labelNode, volumeNode):
        """Label map values resampled (nearest neighbour) onto the volume's voxel grid."""
        a = vtk.vtkMatrix4x4(); b = vtk.vtkMatrix4x4()
        labelNode.GetIJKToRASMatrix(a); volumeNode.GetIJKToRASMatrix(b)
        same = labelNode.GetImageData().GetDimensions() == volumeNode.GetImageData().GetDimensions() and all(
            abs(a.GetElement(r, c) - b.GetElement(r, c)) < 1e-4 for r in range(4) for c in range(4))
        if same and labelNode.GetParentTransformNode() is None:
            return slicer.util.arrayFromVolume(labelNode).astype(np.uint8)
        out = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
        try:
            params = {"inputVolume": labelNode.GetID(), "referenceVolume": volumeNode.GetID(),
                      "outputVolume": out.GetID(), "pixelType": "uchar", "interpolationMode": "NearestNeighbor"}
            slicer.cli.runSync(slicer.modules.brainsresample, None, params)
            return slicer.util.arrayFromVolume(out).astype(np.uint8).copy()
        finally:
            slicer.mrmlScene.RemoveNode(out)

    def labelArteries(self, volumeNode, maskSegNode, seedNode, fixOrigins=True, topcowNode=None):
        t0 = time.time()
        img = slicer.util.arrayFromVolume(volumeNode)
        mask = self.maskArray(maskSegNode, volumeNode)
        spacing = self._spacingKJI(volumeNode)
        raw = self.seedsKJI(seedNode, volumeNode) if seedNode is not None else {}
        tcNotes, tcVariants, tcSeeds = [], None, {}
        if topcowNode is not None:
            tc = self.labelmapOnGrid(topcowNode, volumeNode)
            mask = mask | (tc > 0)
            tcSeeds, _, tcNotes = topcow.seeds_from_topcow(tc, spacing)
            tcVariants = topcow.variant_summary(tc)
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
        lab, names, _ = core.label_from_seeds(mask, seeds, spacing)
        fixReport = {}
        if fixOrigins:
            lab, fixReport = core.fix_branch_origins(lab, mask, names, anatomy.parents(), spacing,
                                                    si_axis=self._siAxisKJI(volumeNode), other_branches=True)

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

        notPlaced = [a[0] for a in anatomy.ARTERIES if a[0] not in seeds
                     and not (a[0] in ("PCA R", "PCA L", "ACA R", "ACA L", "A2 3rd"))]
        lines.append("")
        if tcVariants is not None:
            seen = lambda k: "visualised" if tcVariants[k] else "NOT visualised"
            lines.append("Circle of Willis (from TopCoW labels):")
            for k in ("A1 R", "A1 L", "AComA", "3rd A2", "PComA R", "PComA L", "P1 R", "P1 L"):
                lines.append(f"  {k}: {seen(k)}")
            lines.extend(tcNotes)
            lines.append("")
        if lost:
            lines.append("Seeds outside the mask (ignored): " + ", ".join(sorted(set(lost))))
        if notPlaced:
            lines.append("Not seeded (not visible / not assessed): " + ", ".join(notPlaced))
        for p, r in fixReport.items():
            lines.append(f"Origin correction {p}: {r['stubs']} branch stubs, {r['moved_vox']} voxels re-assigned")
        lines.append(f"Done in {time.time() - t0:.1f} s")
        return seg, "\n".join(lines)

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
