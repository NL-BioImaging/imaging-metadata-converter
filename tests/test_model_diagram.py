import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

import gen_model_diagram


def test_diagram_matches_packaged_models():
    assert gen_model_diagram.main(['--check']) == 0, (
        'the model diagram in docs/model.md is stale; '
        'run python scripts/gen_model_diagram.py')
