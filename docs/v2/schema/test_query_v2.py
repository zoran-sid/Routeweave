"""CI entry for ZC query/result/cache tests against the shared schema."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'modules/zc/v2/experiments'))
from test_query import QueryTablesTest, CacheAcrossReleasesTest  # noqa: F401,E402
