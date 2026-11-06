"""Include operation B regressions in the existing unified-schema CI job."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'modules/zqo/v2/experiments'))
from test_catalog import CatalogTest  # noqa: F401,E402
