"""The model map on docs/model-map.md, drawn when the site is built.

The map draws the part of the imaging model the converter actually
produces: the paths some rule in mappings.json targets, with the groups
above them, as one Mermaid flowchart. A path LiMi does not have - one of the
model's extension (mostly electron-microscopy) or provenance classes and
slots - is orange, so the map also shows how much of what the converter fills
in comes from the extensions rather than from LiMi.

It is deliberately not the whole model. All its fields cannot carry a
legible name in one static picture - that is what the interactive browser
on model.md is for - and a field no rule targets is not something the
converter can currently produce.

Each section is a subgraph laid out left to right, and the subgraphs are
packed into rows joined by invisible links so the map stays roughly
landscape; Mermaid has no aspect-ratio control, so the shape is
approached rather than set.

The MkDocs hook scripts/docs_data.py puts render() in place of the page's
{{ model.map }}, so the map is never stored and cannot go stale.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from imaging_metadata_converter.AcquisitionMetadataMapper import rule_targets  # noqa: E402
from docs_data import all_paths, leaf_paths  # noqa: E402

ORANGE = '#e8710a'
# Four styles, so both distinctions carry colour as well as shape: base
# against extension, and a group against a field inside it. The extensions
# are a saturated orange - the colour the model browser flags them with -
# against a recessive grey for LiMi, so what the imaging model adds stands
# out at a glance. Stroke and fill only, never the label colour, so a name
# keeps whatever the Material palette uses and both schemes stay readable.
# These are the baseline; docs/stylesheets/model-map.css sharpens them per
# scheme.
STYLES = {
    'gbase': 'fill:#8a8a8a1f,stroke:#80868b,stroke-width:1.5px',
    'fbase': 'fill:none,stroke:#9aa0a6,stroke-width:1px',
    'gext': f'fill:{ORANGE},stroke:#a04a00,stroke-width:3px',
    'fext': f'fill:{ORANGE}40,stroke:{ORANGE},stroke-width:2.5px',
}

# Rough rendered size of a node, used only to pick how many section blocks
# go in a row. Being a little off shifts the shape, never the content.
NODE_WIDTH = 34.0            # per character of the label
NODE_HEIGHT = 42.0
LEVEL_GAP = 40.0
BLOCK_GAP = 30.0
TARGET_RATIO = 16 / 9


def targets(mappings, tree):
    """The model paths the rules target, in the order the rules name them.

    A rule can name several targets, and a "Target[]" rule fills a list at
    that path. A per-item target (Pixels.Channel[*].Fluorophore.Emission
    Wavelength) runs through classes with their own place in the tree, the
    top-level keys, so it is drawn from the last one it passes.
    """
    model_paths = set(all_paths(tree))
    found = []
    for rule in mappings.values():
        for target in rule_targets(rule):
            # "GenericDetector[].Name" names a field of each item a "Target[]" rule collapses
            parts = target.removesuffix('[]').replace('[].', '.').replace('[*]', '').split('.')
            starts = [index for index, part in enumerate(parts) if index > 0 and part in tree]
            start = starts[-1] if '[*]' in target and starts else 0
            path = '.'.join(parts[start:])
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


def build(paths, added):
    """Build one tree per top-level section covering every path in `paths`."""
    sections = {}
    for path in paths:
        parts = path.split('.')
        node = sections.get(parts[0])
        if node is None:
            node = Node(parts[0], parts[0], parts[0] in added)
            sections[parts[0]] = node
        for index in range(1, len(parts)):
            prefix = '.'.join(parts[:index + 1])
            child = next((c for c in node.children if c.path == prefix), None)
            if child is None:
                child = Node(parts[index], prefix, prefix in added)
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


def render(data):
    """The map and its legend, as Markdown, for a docs_data.ModelData."""
    added = set(data.added)
    paths = targets(data.mappings, data.tree)
    sections = build(paths, added)

    body, _ratio = diagram(sections)
    boxes = sum(1 for s in sections for _ in s.walk())
    new = sum(1 for p in paths if p in added)
    fields = sum(1 for _ in leaf_paths(data.tree))
    legend = (
        f'The **{len(paths)} fields** some rule in `mappings.json` targets —'
        ' what the converter can actually fill in — with the groups above'
        f' them, {boxes} boxes over {len(sections)} sections. Rounded boxes'
        ' are the targeted fields themselves; square boxes are the groups'
        f' holding them. <span class="map-key">Orange</span> is a path'
        f' LiMi does not have: {new} of the {len(paths)} targets come from'
        ' the extensions, mostly electron microscopy.\n\n'
        f'The other fields of the model are not drawn — all {fields} cannot be'
        ' named in one static picture, and a field no rule targets is not'
        ' something the converter can produce yet. Use the'
        ' [model browser](model.md) to see the model in full.')
    return f'{body}\n\n{legend}'
