import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

import sync_docs_data


def test_docs_copies_match_packaged_data():
    assert sync_docs_data.main(['--check']) == 0, (
        'docs/data is stale; run python scripts/sync_docs_data.py')
