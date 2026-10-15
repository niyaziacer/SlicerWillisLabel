import sys
from pathlib import Path

# The core algorithms do not depend on Slicer, so they can be tested with plain pytest.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "WillisLabel"))
