# SlicerWillisLabel

> **Status: work in progress.** Validated on one TOF-MRA case so far; multi-case validation on the public IXI dataset is under way. Not yet submitted to the Slicer Extensions Index.

A 3D Slicer extension that extracts the intracranial arteries from a **TOF-MRA** volume and labels them anatomically:

- vertebral, basilar and internal carotid arteries
- PICA, AICA, SCA, anterior choroidal artery
- the segments of the circle of Willis: **A1, AComA, A2, P1, PComA, P2**, and the MCA

Every branch is coloured **from its origin** (not only from where it leaves the parent's silhouette), and each artery can be exported as a separate STL for 3D printing.

Intended uses: anatomy teaching, 3D printing, and research on **anatomical variations** of the intracranial arteries (circle of Willis configuration, fetal PCA, A1 hypoplasia, PICA/AICA origin, etc.).

## Workflow

1. **Extract arteries**: hysteresis thresholding (thresholds are suggested automatically from the intensity histogram), light Gaussian smoothing, removal of small islands and flat sheets (bright subcutaneous fat on TOF). The result is an ordinary segmentation, so you can refine it in Segment Editor.
2. **Place seeds**: choose an artery from the list (`VA R`, `BA`, `ICA L`, `A1 R`, `AComA`, `P1 L`, `PComA R`, …), press *Place* and click on it in the 3D view or a slice. Placing stays on, so choose the next artery and keep clicking. Skip arteries that are not visible. Several points with the same name are allowed for long or tortuous arteries.
3. **Label arteries**: every artery voxel is assigned to the artery whose seeds are closest **along the vessel** (geodesic distance on the 26-connected voxel graph). A centreline-based correction then re-assigns the first millimetres of each side branch from the parent trunk (VA, BA, ICA) to the branch itself. Voxels not connected to any seed go to an `Unconnected` segment.
4. **Export**: one STL per artery (LPS, mm).

Segment names use Terminologia Anatomica (Latin) with the usual abbreviation, e.g. `A. cerebri anterior dextra, pars precommunicalis (A1) [A1 R]`.

## Notes and limitations

- **"Not visualised" is not "absent".** Slow-flow or sub-millimetre vessels (often AComA or a hypoplastic PComA) may not appear on TOF. Arteries left without a seed are listed as *not seeded*, not as missing.
- The slab may not cover the origins of the VA, PICA or ICA, and variations there cannot be assessed.
- Only `numpy` and `scipy` are used; no extra Python packages need to be installed.

## Roadmap

- [ ] Variation report per case: circle of Willis completeness, fetal / partial-fetal PCA, A1 hypoplasia or aplasia (left/right ratios), AComA/PComA visualisation, VA dominance, PICA origin
- [ ] Validation on IXI TOF-MRA cases (CC BY-SA 3.0) and sample data
- [ ] Screenshot and tutorial

## Development

The algorithms in `WillisLabel/WillisLabelLib/core.py` do not depend on Slicer and are tested with plain pytest:

```
pip install -r requirements-dev.txt
pytest tests
```

## License

MIT (see `LICENSE.txt`).
