import sys
from pathlib import Path

# scripts/ isn't a package (this repo's scripts are run standalone via
# `python scripts/foo.py`, not imported) -- add it to sys.path so tests can
# import script modules directly, e.g. `from build_powiat_suitability import ...`.
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
