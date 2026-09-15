import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

import gen_model_map


def test_map_matches_packaged_data():
    assert gen_model_map.main(['--check']) == 0, (
        'the model map in docs/model-map.md is stale; '
        'run python scripts/gen_model_map.py')
