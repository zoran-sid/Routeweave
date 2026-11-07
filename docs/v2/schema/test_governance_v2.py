"""CI entry for LQ governance tests against the shared schema."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'modules/lq/v2/experiments'))
from test_governance import GovernanceTest  # noqa: F401,E402
