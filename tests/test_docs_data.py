import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import docs_data


def test_model_page_counts_are_all_known():
    data = docs_data.ModelData()
    page = (ROOT / 'docs' / 'model.md').read_text(encoding='utf-8')
    filled = docs_data.fill(page, data.counts())
    assert '{{' not in filled


def test_site_data_is_the_packaged_model():
    data = docs_data.ModelData()
    files = data.files()
    assert set(files) == {'model.json', 'added.json', 'mappings.json'}
    assert json.loads(files['model.json']) == data.model.tree()
    assert set(json.loads(files['added.json'])) <= set(docs_data.all_paths(data.tree))
