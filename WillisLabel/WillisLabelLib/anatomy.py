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
]

UNCONNECTED = ("Unconnected", "Not connected to any seed", (0.6, 0.6, 0.6))

BY_ABBR = {a[0]: a for a in ARTERIES}


def segment_name(abbr):
    a = BY_ABBR.get(abbr)
    return f"{a[1]} [{abbr}]" if a else abbr


_FALLBACK = [
    (0.90, 0.10, 0.10), (0.10, 0.50, 0.90), (0.95, 0.75, 0.10), (0.20, 0.70, 0.30),
    (0.60, 0.25, 0.75), (0.95, 0.50, 0.10), (0.10, 0.75, 0.75), (0.90, 0.40, 0.70),
    (0.55, 0.35, 0.15), (0.50, 0.80, 0.10), (0.25, 0.25, 0.70), (0.80, 0.80, 0.80),
]


def colour(abbr, index=0):
    """Catalogue colour, or a distinct fallback colour for names not in the catalogue."""
    a = BY_ABBR.get(abbr)
    return a[2] if a else _FALLBACK[index % len(_FALLBACK)]


def parents():
    return [a[0] for a in ARTERIES if a[3]]
