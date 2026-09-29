import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import docs_data
import model_map


def test_map_draws_every_targeted_path():
    data = docs_data.ModelData()
    rendered = model_map.render(data)
    assert rendered.startswith('```mermaid\nflowchart LR\n')
    for path in model_map.targets(data.mappings, data.tree):
        name = path.split('.')[-1]
        assert f'("{name}")' in rendered or f'["{name}"]' in rendered


def test_map_page_fills_in():
    page = (ROOT / 'docs' / 'model-map.md').read_text(encoding='utf-8')
    assert '{{ model.map }}' in page
    filled = docs_data.fill(page, {'map': model_map.render(docs_data.ModelData())})
    assert '{{' not in filled
