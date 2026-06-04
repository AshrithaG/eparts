"""Make the package importable for the test runner without `pip install -e .`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
