"""Generate the static model map embedded in docs/model-map.md.

The map draws the part of the model the converter actually produces: the
137 paths some rule in mappings.json targets, with the groups above them,
as one Mermaid flowchart. A path the base model does not have is blue, so
the map also shows how much of what the converter fills in comes from the
electron-microscopy extensions rather than from the base model.

It is deliberately not the whole model. All 2006 fields cannot carry a
legible name in one static picture - that is what the interactive browser
on model.md is for - and a field no rule targets is not something the
converter can currently produce.

Each section is a subgraph laid out left to right, and the subgraphs are
packed into rows joined by invisible links so the map stays roughly
landscape; Mermaid has no aspect-ratio control, so the shape is
approached rather than set.

Run after editing the mappings or either model:

    python scripts/gen_model_map.py

Use --check to fail instead of writing, which is what
tests/test_model_map.py does so a stale map cannot be committed
unnoticed.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'src' / 'imaging_metadata_converter' / 'data'
PAGE = ROOT / 'docs' / 'model-map.md'

BEGIN = '<!-- begin generated map: scripts/gen_model_map.py -->'
END = '<!-- end generated map -->'

BLUE = '#4a7fb5'
# Four styles, so both distinctions carry colour as well as shape: base
# against extension, and a group against a field inside it. Stroke and
# fill only, never the label colour, so a name keeps whatever the
# Material palette uses and both schemes stay readable. These are the
# baseline; docs/stylesheets/model-map.css sharpens them per scheme.
STYLES = {
    'gbase': 'fill:#8a8a8a26,stroke:#5f6368,stroke-width:2px',
    'fbase': 'fill:none,stroke:#8a8a8a,stroke-width:1.5px',
    'gext': f'fill:{BLUE}88,stroke:#2f6fa8,stroke-width:2.5px',
    'fext': f'fill:{BLUE}3a,stroke:{BLUE},stroke-width:2px',
}

# Rough rendered size of a node, used only to pick how many section blocks
# go in a row. Being a little off shifts the shape, never the content.
NODE_WIDTH = 34.0            # per character of the label
NODE_HEIGHT = 42.0
LEVEL_GAP = 40.0
BLOCK_GAP = 30.0
TARGET_RATIO = 16 / 9


def load(name):
    """Return one packaged data file as a dict."""
    return json.loads((DATA / name).read_text(encoding='utf-8'))


def is_leaf(node):
    """A model leaf is a ``"FieldName": "type"`` pair, so a string value."""
    return isinstance(node, str)


def all_paths(model):
    """Every path in `model`, groups as well as leaves."""
    found = set()
    stack = list(model.items())
    while stack:
        path, node = stack.pop()
        found.add(path)
        if not is_leaf(node):
            stack.extend((f'{path}.{name}', child)
                         for name, child in node.items())
    return found


def targets(mappings, model_paths):
    """The model paths the rules target, in the order the rules name them.

    A rule's target may be omitted, in which case the source path is also
    the target, and a "Target[]" rule fills a list at that path.
    """
    found = []
    for source, target in mappings.items():
        path = (target or source).rstrip('[]')
        if path in model_paths and path not in found:
            found.append(path)
    return found


class Node:
    """One drawn box: a targeted field, or a group on the way to one."""

    def __init__(self, name, path, new):
        self.name = name
        self.path = path
        self.new = new
        self.children = []
        self.targeted = False

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def leaves(self):
        if not self.children:
            return 1
        return sum(child.leaves() for child in self.children)

    def depth(self):
        if not self.children:
            return 1
        return 1 + max(child.depth() for child in self.children)


def build(paths, base_paths):
    """Build one tree per top-level section covering every path in `paths`."""
    sections = {}
    for path in paths:
        parts = path.split('.')
        node = sections.get(parts[0])
        if node is None:
            node = Node(parts[0], parts[0], parts[0] not in base_paths)
            sections[parts[0]] = node
        for index in range(1, len(parts)):
            prefix = '.'.join(parts[:index + 1])
            child = next((c for c in node.children if c.path == prefix), None)
            if child is None:
                child = Node(parts[index], prefix, prefix not in base_paths)
                node.children.append(child)
            node = child
        node.targeted = True
    return list(sections.values())


def block_size(section):
    """Estimate a section subgraph's size, laid out left to right."""
    width = 0.0
    for node in section.walk():
        if not node.children:
            width = max(width, 0)
    longest = max(len(n.name) for n in section.walk())
    width = section.depth() * (longest * NODE_WIDTH / 3 + LEVEL_GAP)
    return width, section.leaves() * NODE_HEIGHT + NODE_HEIGHT


def pack(sizes, row_width):
    """Split blocks into rows no wider than `row_width`, keeping model order."""
    rows, row, used = [], [], 0.0
    for index, (width, _height) in enumerate(sizes):
        if row and used + BLOCK_GAP + width > row_width:
            rows.append(row)
            row, used = [], 0.0
        used += width + (BLOCK_GAP if row else 0)
        row.append(index)
    if row:
        rows.append(row)
    width = max(sum(sizes[i][0] for i in r) + BLOCK_GAP * (len(r) - 1)
                for r in rows)
    height = (sum(max(sizes[i][1] for i in r) for r in rows)
              + BLOCK_GAP * (len(rows) - 1))
    return rows, width, height


def best_packing(sizes):
    """Pick the row width whose estimated shape is closest to 16:9."""
    widest = max(width for width, _ in sizes)
    total = sum(width + BLOCK_GAP for width, _ in sizes)
    best = None
    step = max(int(widest / 8), 1)
    for row_width in range(int(widest), int(total) + step, step):
        rows, width, height = pack(sizes, row_width)
        score = abs((width / height) - TARGET_RATIO)
        if best is None or score < best[0]:
            best = (score, rows, width, height)
    return best[1:]


def diagram(sections):
    """Render the targeted part of the model as one Mermaid flowchart."""
    sizes = [block_size(section) for section in sections]
    rows, width, height = best_packing(sizes)

    lines = ['```mermaid', 'flowchart LR']
    lines.extend(f'classDef {name} {style}' for name, style in STYLES.items())

    ids = {}
    classed = {name: [] for name in STYLES}
    counter = 0
    for index, section in enumerate(sections):
        lines.append(f'subgraph s{index} [" "]')
        lines.append('direction LR')
        for node in section.walk():
            ids[node.path] = f'n{counter}'
            counter += 1
            group = 'g' if node.children else 'f'
            kind = group + ('ext' if node.new else 'base')
            classed[kind].append(ids[node.path])
            shape = f'["{node.name}"]' if node.children else f'("{node.name}")'
            lines.append(f'{ids[node.path]}{shape}')
        for node in section.walk():
            for child in node.children:
                lines.append(f'{ids[node.path]}-->{ids[child.path]}')
        lines.append('end')

    for row in rows:
        if len(row) > 1:
            lines.append('~~~'.join(f's{i}' for i in row))

    for style, members in classed.items():
        if members:
            lines.append(f'class {",".join(members)} {style}')
    lines.append('```')
    return '\n'.join(lines), width / height


def rendered_block():
    """The full generated block, markers included, that the page should hold."""
    base = load('schema.json')
    ext = load('schema.extended.json')
    mappings = load('mappings.json')

    base_paths = all_paths(base)
    paths = targets(mappings, all_paths(ext))
    sections = build(paths, base_paths)

    body, ratio = diagram(sections)
    boxes = sum(1 for s in sections for _ in s.walk())
    new = sum(1 for p in paths if p not in base_paths)
    legend = (
        f'The **{len(paths)} fields** some rule in `mappings.json` targets —'
        ' what the converter can actually fill in — with the groups above'
        f' them, {boxes} boxes over {len(sections)} sections. Rounded boxes'
        ' are the targeted fields themselves; square boxes are the groups'
        f' holding them. <span class="map-key">Blue</span> is a path'
        f' `schema.json` does not have: {new} of the {len(paths)} targets'
        ' come from the electron-microscopy extensions.\n\n'
        'The other fields of the model are not drawn — all 2006 cannot be'
        ' named in one static picture, and a field no rule targets is not'
        ' something the converter can produce yet. Use the'
        ' [model browser](model.md) to see the model in full.')
    return f'{BEGIN}\n\n{body}\n\n{legend}\n\n{END}'


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
