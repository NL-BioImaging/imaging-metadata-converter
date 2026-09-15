"""Generate the Mermaid model map embedded in docs/model-map.md.

The map shows every leaf of the extended model - one box per group of
leaves, listing the leaf names themselves rather than a count - coloured
by where each leaf comes from: the base model (schema.json) in the
theme's own text colour, and what schema.extended.json adds in blue.

Mermaid has no aspect-ratio control: a flowchart is laid out by dagre,
and 156 unconnected boxes would be stacked into one very tall column.
The boxes are therefore packed into rows joined by invisible links
(``~~~``), each row a disconnected chain so the rows stack. `pack`
searches the row width whose estimated shape comes closest to 16:9;
the estimate is arithmetic, since rendering to measure would need a
browser.

Run after editing either model:

    python scripts/gen_model_map.py

Use --check to fail instead of writing, which is what
tests/test_model_map.py does so a stale map cannot be committed
unnoticed.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'src' / 'imaging_metadata_converter' / 'data'
PAGE = ROOT / 'docs' / 'model-map.md'

BEGIN = '<!-- begin generated map: scripts/gen_model_map.py -->'
END = '<!-- end generated map -->'

BLUE = '#4a7fb5'
# Only stroke and fill are set on a box, never the label colour, so base
# leaf names keep whatever the Material palette uses and stay readable in
# both the light and the dark scheme. Blue is applied per leaf instead.
BASE_STYLE = 'fill:none,stroke:#6b6b6b,stroke-width:1px'
EXT_STYLE = f'fill:{BLUE}22,stroke:{BLUE},stroke-width:2px'

# Rough glyph box of the rendered label text, used only to choose how many
# boxes go in a row. Being a little off shifts the shape, never the content.
CHAR_WIDTH = 7.2
LINE_HEIGHT = 21.0
BOX_PADDING_X = 26.0
BOX_PADDING_Y = 18.0
BOX_GAP_X = 18.0
BOX_GAP_Y = 18.0
TARGET_RATIO = 16 / 9


def load(name):
    """Return one packaged model file as a dict."""
    return json.loads((DATA / name).read_text(encoding='utf-8'))


def leaf_paths(node, prefix=''):
    """Yield every ``(dotted path, type)`` leaf below `node`, in file order."""
    if isinstance(node, str):
        yield prefix, node
        return
    for name, child in node.items():
        yield from leaf_paths(child, f'{prefix}.{name}' if prefix else name)


def grouped_leaves(model):
    """Group the model's leaves by their parent path, keeping file order.

    A leaf directly under a top-level section has that section as its
    group, so every leaf lands in exactly one box.
    """
    groups = {}
    for path, _type in leaf_paths(model):
        parent, _, name = path.rpartition('.')
        groups.setdefault(parent or path, []).append((name, path))
    return groups


def node_id(path):
    """A Mermaid-safe node id for a dotted model path."""
    return 'g_' + re.sub(r'[^0-9A-Za-z]', '_', path)


def box(group, leaves, base_paths):
    """Render one group as a Mermaid node, and say whether it is all new.

    Leaf names the base model does not have are wrapped in a blue span,
    so a group the extended model only adds fields to shows exactly which
    of its fields those are.
    """
    lines = [f'<b>{group}</b>']
    new = 0
    for name, path in leaves:
        if path in base_paths:
            lines.append(name)
        else:
            new += 1
            lines.append(f'<span style="color:{BLUE}">{name}</span>')
    return '<br/>'.join(lines), new == len(leaves)


def box_size(group, leaves):
    """Estimate the rendered size of a box, for row packing only."""
    widest = max([len(group) + 2] + [len(name) for name, _ in leaves])
    return (widest * CHAR_WIDTH + BOX_PADDING_X,
            (len(leaves) + 1) * LINE_HEIGHT + BOX_PADDING_Y)


def pack(sizes, row_width):
    """Split boxes into rows no wider than `row_width`, keeping model order.

    Returns the rows and the estimated overall width and height, a row
    being as tall as its tallest box.
    """
    rows, row, used = [], [], 0.0
    for index, (width, _height) in enumerate(sizes):
        if row and used + BOX_GAP_X + width > row_width:
            rows.append(row)
            row, used = [], 0.0
        used += width + (BOX_GAP_X if row else 0)
        row.append(index)
    if row:
        rows.append(row)

    width = max(
        sum(sizes[i][0] for i in r) + BOX_GAP_X * (len(r) - 1) for r in rows)
    height = (sum(max(sizes[i][1] for i in r) for r in rows)
              + BOX_GAP_Y * (len(rows) - 1))
    return rows, width, height


def best_packing(sizes):
    """Pick the row width whose estimated shape is closest to 16:9."""
    widest = max(width for width, _ in sizes)
    total = sum(width + BOX_GAP_X for width, _ in sizes)
    best = None
    # One box per row up to every box on one row, in coarse steps - the
    # shape changes slowly, so a fine search would not pick a better one.
    step = max(int(widest / 4), 1)
    for row_width in range(int(widest), int(total) + step, step):
        rows, width, height = pack(sizes, row_width)
        score = abs((width / height) - TARGET_RATIO)
        if best is None or score < best[0]:
            best = (score, rows, width, height)
    return best[1:]


def diagram(base, ext):
    """Render every leaf of the extended model as one Mermaid flowchart."""
    base_paths = {path for path, _type in leaf_paths(base)}
    groups = grouped_leaves(ext)

    names = list(groups)
    sizes = [box_size(name, groups[name]) for name in names]
    rows, width, height = best_packing(sizes)

    lines = [
        '```mermaid',
        'flowchart LR',
        f'  classDef base {BASE_STYLE}',
        f'  classDef ext {EXT_STYLE}',
        '',
    ]
    for row in rows:
        # A row is one chain of invisible links, so its boxes sit side by
        # side; rows share no link, so dagre stacks them.
        rendered = []
        for index in row:
            name = names[index]
            label, all_new = box(name, groups[name], base_paths)
            style = 'ext' if all_new else 'base'
            rendered.append(f'{node_id(name)}["{label}"]:::{style}')
        lines.append('  ' + ' ~~~ '.join(rendered))
    lines.append('```')

    total = sum(len(v) for v in groups.values())
    new = total - len(base_paths & {p for v in groups.values() for _, p in v})
    lines.append('')
    lines.append(
        f'All {total} leaves of the extended model, in {len(groups)} groups.'
        ' **Unstyled names** come from `schema.json`;'
        f' <span style="color:{BLUE}"><strong>blue names</strong></span> are'
        f' the {new} that `schema.extended.json` adds, and a fully blue box is'
        ' a group the base model does not have at all.'
        f' (Estimated shape {width / height:.2f}:1 against 1.78:1 for 16:9 -'
        ' Mermaid lays the boxes out itself, so the ratio is approached, not'
        ' set.)')
    return '\n'.join(lines)


def rendered_block():
    """The full generated block, markers included, that the page should hold."""
    body = diagram(load('schema.json'), load('schema.extended.json'))
    return f'{BEGIN}\n\n{body}\n\n{END}'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='report a stale map without writing')
    args = parser.parse_args(argv)

    text = PAGE.read_text(encoding='utf-8')
    if BEGIN not in text or END not in text:
        print(f'{PAGE.name} has no generated-map markers', file=sys.stderr)
        return 1

    start, end = text.index(BEGIN), text.index(END) + len(END)
    updated = text[:start] + rendered_block() + text[end:]
    if updated == text:
        return 0
    if args.check:
        print(f'out of date: {PAGE.name}', file=sys.stderr)
        print('run: python scripts/gen_model_map.py', file=sys.stderr)
        return 1
    PAGE.write_text(updated, encoding='utf-8')
    print(f'updated: {PAGE.name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
