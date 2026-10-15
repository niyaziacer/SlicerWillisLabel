"""Artery catalogue: names (Terminologia Anatomica, Latin), abbreviations, colours.

Each entry: (abbreviation, Latin name, RGB colour 0-1, is_parent_trunk)
Parent trunks are the vessels from which side branches are re-assigned by the
branch-origin correction (see core.fix_branch_origins).
"""

ARTERIES = [
    ("VA R",    "A. vertebralis dextra",                          (0.85, 0.20, 0.20), True),
    ("VA L",    "A. vertebralis sinistra",                        (0.95, 0.55, 0.55), True),
    ("BA",      "A. basilaris",                                   (0.90, 0.45, 0.10), True),
    ("ICA R",   "A. carotis interna dextra",                      (0.80, 0.10, 0.45), True),
    ("ICA L",   "A. carotis interna sinistra",                    (0.95, 0.50, 0.75), True),
    ("PICA R",  "A. inferior posterior cerebelli dextra",         (0.60, 0.40, 0.15), False),
    ("PICA L",  "A. inferior posterior cerebelli sinistra",       (0.80, 0.60, 0.35), False),
    ("AICA R",  "A. inferior anterior cerebelli dextra",          (0.55, 0.75, 0.20), False),
    ("AICA L",  "A. inferior anterior cerebelli sinistra",        (0.75, 0.90, 0.45), False),
    ("SCA R",   "A. superior cerebelli dextra",                   (0.95, 0.85, 0.15), False),
    ("SCA L",   "A. superior cerebelli sinistra",                 (1.00, 0.95, 0.55), False),
    ("P1 R",    "A. cerebri posterior dextra, pars precommunicalis (P1)",  (0.10, 0.45, 0.80), False),
    ("P1 L",    "A. cerebri posterior sinistra, pars precommunicalis (P1)", (0.45, 0.70, 0.95), False),
    ("P2 R",    "A. cerebri posterior dextra, pars postcommunicalis (P2+)", (0.15, 0.25, 0.60), False),
    ("P2 L",    "A. cerebri posterior sinistra, pars postcommunicalis (P2+)", (0.35, 0.45, 0.85), False),
    ("PComA R", "A. communicans posterior dextra",                (0.85, 0.15, 0.15), False),
    ("PComA L", "A. communicans posterior sinistra",              (0.10, 0.65, 0.30), False),
    ("AChA R",  "A. choroidea anterior dextra",                   (0.55, 0.85, 0.75), False),
    ("AChA L",  "A. choroidea anterior sinistra",                 (0.35, 0.65, 0.55), False),
    ("MCA R",   "A. cerebri media dextra",                        (0.20, 0.70, 0.85), False),
    ("MCA L",   "A. cerebri media sinistra",                      (0.50, 0.85, 0.95), False),
    ("A1 R",    "A. cerebri anterior dextra, pars precommunicalis (A1)",  (0.55, 0.20, 0.70), False),
    ("A1 L",    "A. cerebri anterior sinistra, pars precommunicalis (A1)", (0.75, 0.50, 0.90), False),
    ("AComA",   "A. communicans anterior",                        (1.00, 0.40, 0.00), False),
    ("A2 R",    "A. cerebri anterior dextra, pars postcommunicalis (A2+)", (0.40, 0.10, 0.50), False),
    ("A2 L",    "A. cerebri anterior sinistra, pars postcommunicalis (A2+)", (0.60, 0.35, 0.75), False),
    # used when TopCoW labels cannot be split into P1/P2 or A1/A2
    ("PCA R",   "A. cerebri posterior dextra",                    (0.15, 0.35, 0.70), False),
    ("PCA L",   "A. cerebri posterior sinistra",                  (0.40, 0.55, 0.90), False),
    ("ACA R",   "A. cerebri anterior dextra",                     (0.45, 0.15, 0.60), False),
    ("ACA L",   "A. cerebri anterior sinistra",                   (0.65, 0.45, 0.85), False),
    ("A2 3rd",  "A. cerebri anterior mediana (third A2)",         (0.90, 0.60, 0.20), False),
    # distal ACA, named by course and origin (see aca.py); not seeded directly
    ("Pericall R", "A. pericallosa dextra",                        (0.90, 0.72, 0.00), False),
    ("Pericall L", "A. pericallosa sinistra",                      (1.00, 0.85, 0.35), False),
    ("A2 R var", "A. cerebri anterior dextra – perikallozal varyasyon dalı (VARYASYON)", (0.95, 0.30, 0.55), False),
    ("A2 L var", "A. cerebri anterior sinistra – perikallozal varyasyon dalı (VARYASYON)", (1.00, 0.55, 0.70), False),
    ("CallMed", "A. callosa mediana (VARYASYON)",                  (0.00, 0.75, 0.55), False),
    ("ACA var", "A. cerebri anterior – perikallozal varyasyon dalı, köken belirsiz (VARYASYON)", (0.85, 0.20, 0.20), False),
]

# entries that are derived, never placed as seeds (not listed as "not seeded")
DERIVED = ("Pericall R", "Pericall L", "A2 R var", "A2 L var", "CallMed", "ACA var")
NOT_SEEDED = ("PCA R", "PCA L", "ACA R", "ACA L", "A2 3rd") + DERIVED

NON_VASCULAR = ("Non-vascular?", "Probably not an artery (thick piece, e.g. fat)", (0.75, 0.65, 0.50))

UNCONNECTED = ("Unconnected", "Not connected to any seed", (0.6, 0.6, 0.6))

BY_ABBR = {a[0]: a for a in ARTERIES}


RAMI = " rami"


def segment_name(abbr):
    if abbr == NON_VASCULAR[0]:
        return f"{NON_VASCULAR[1]} [{abbr}]"
    if abbr.endswith(RAMI):
        base = BY_ABBR.get(abbr[: -len(RAMI)])
        return f"{base[1]} – rami alii [{abbr}]" if base else abbr
    a = BY_ABBR.get(abbr)
    return f"{a[1]} [{abbr}]" if a else abbr


_FALLBACK = [
    (0.90, 0.10, 0.10), (0.10, 0.50, 0.90), (0.95, 0.75, 0.10), (0.20, 0.70, 0.30),
    (0.60, 0.25, 0.75), (0.95, 0.50, 0.10), (0.10, 0.75, 0.75), (0.90, 0.40, 0.70),
    (0.55, 0.35, 0.15), (0.50, 0.80, 0.10), (0.25, 0.25, 0.70), (0.80, 0.80, 0.80),
]


def colour(abbr, index=0):
    """Catalogue colour, or a distinct fallback colour for names not in the catalogue."""
    if abbr == NON_VASCULAR[0]:
        return NON_VASCULAR[2]
    if abbr.endswith(RAMI):
        base = BY_ABBR.get(abbr[: -len(RAMI)])
        if base:  # washed-out version of the parent colour
            return tuple(0.55 + 0.35 * c for c in base[2])
    a = BY_ABBR.get(abbr)
    return a[2] if a else _FALLBACK[index % len(_FALLBACK)]


# named distal continuation of each parent trunk (used to find the distal end of its centreline)
DISTAL = {
    "VA R": ("BA",), "VA L": ("BA",),
    "BA": ("P1 R", "P1 L", "PCA R", "PCA L"),
    "ICA R": ("A1 R", "ACA R", "MCA R"), "ICA L": ("A1 L", "ACA L", "MCA L"),
}


def parents():
    return [a[0] for a in ARTERIES if a[3]]
