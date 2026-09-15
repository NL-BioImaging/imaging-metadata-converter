"""Generate the Mermaid origin diagram embedded in docs/model.md.

The diagram is one view of the model's top level, coloured by where each
element comes from: the base model (schema.json) in black, and what
schema.extended.json adds on top of it in blue - both the sections that
exist only in the extended model and the groups it adds inside sections
the base model already has.

It is generated rather than hand-drawn so it cannot disagree with the
packaged model files. Run after editing either model:

    python scripts/gen_model_diagram.py

Use --check to fail instead of writing, which is what
tests/test_model_diagram.py does so a stale diagram cannot be committed
unnoticed.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'src' / 'imaging_metadata_converter' / 'data'
PAGE = ROOT / 'docs' / 'model.md'

BEGIN = '<!-- begin generated diagram: scripts/gen_model_diagram.py -->'
END = '<!-- end generated diagram -->'

# Only stroke and fill are set, never the label colour, so the text keeps
# whatever the Material palette uses and both light and dark stay readable.
BASE_STYLE = 'fill:none,stroke:#6b6b6b,stroke-width:1px'
EXT_STYLE = 'fill:#4a7fb522,stroke:#4a7fb5,stroke-width:2px'


def load(name):
    """Return one packaged model file as a dict."""
    return json.loads((DATA / name).read_text(encoding='utf-8'))


def is_leaf(node):
    """A model leaf is a ``"FieldName": "type"`` pair, so a string value."""
    return isinstance(node, str)


def count_fields(node):
    """Count the leaves below `node`, which is the field count of a section."""
    if is_leaf(node):
        return 1
    return sum(count_fields(child) for child in node.values())


def node_id(*parts):
    """A Mermaid-safe node id for a dotted model path."""
    return re.sub(r'[^0-9A-Za-z]', '_', '_'.join(parts))


def summary(name, node):
    """The label for `node`: its name over its size, or its type if a leaf."""
    if is_leaf(node):
        return f'{name}<br/>{node}'
    fields = count_fields(node)
    return f'{name}<br/>{fields} field{"" if fields == 1 else "s"}'


def added_children(base_section, ext_section):
    """The groups `ext_section` adds to a section the base model also has."""
    if is_leaf(ext_section) or is_leaf(base_section):
        return []
    return [(name, child) for name, child in ext_section.items()
            if name not in base_section]


def diagram(base, ext):
    """Render the whole model top level as one Mermaid flowchart."""
    base_total = sum(count_fields(node) for node in base.values())
    ext_total = sum(count_fields(node) for node in ext.values())

    lines = [
        '```mermaid',
        'flowchart LR',
        f'  classDef base {BASE_STYLE}',
        f'  classDef ext {EXT_STYLE}',
        '',
        '  model["metadata model"]:::base',
        '',
    ]

    for name, node in ext.items():
        section = node_id(name)
        in_base = name in base
        style = 'base' if in_base else 'ext'
        # A shared section is counted as the base model has it, since the
        # groups the extended model adds to it are drawn as their own nodes.
        label = summary(name, base[name] if in_base else node)
        lines.append(f'  model --> {section}["{label}"]:::{style}')
        for child_name, child in added_children(base.get(name, {}), node):
            child_id = node_id(name, child_name)
            label = summary(child_name, child)
            lines.append(f'  {section} --> {child_id}["{label}"]:::ext')
        lines.append('')

    lines.append('```')
    lines.append('')
    # The legend colours are inline rather than a stylesheet class so they
    # cannot drift from the classDef colours a few lines above. "Black" is
    # left unstyled so it stays the theme's own text colour in dark mode.
    lines.append(
        f'**Black** &mdash; `schema.json`, the base model:'
        f' {len(base)} sections, {base_total} fields.'
        f' <span style="color:#4a7fb5"><strong>Blue</strong></span> &mdash;'
        f' what `schema.extended.json` adds: {len(ext) - len(base)}'
        f' electron-microscopy sections and {ext_total - base_total} fields,'
        ' including the groups it adds inside sections the base model'
        ' already has.')
    return '\n'.join(lines)


def rendered():
    """The full generated block, markers included, that model.md should hold."""
    body = diagram(load('schema.json'), load('schema.extended.json'))
    return f'{BEGIN}\n\n{body}\n\n{END}'


def replaced(text, block):
    """Return `text` with its generated block swapped for `block`."""
    start, end = text.index(BEGIN), text.index(END) + len(END)
    return text[:start] + block + text[end:]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='report a stale diagram without writing')
    args = parser.parse_args(argv)

    text = PAGE.read_text(encoding='utf-8')
    if BEGIN not in text or END not in text:
        print(f'{PAGE.name} has no generated-diagram markers', file=sys.stderr)
        return 1

    updated = replaced(text, rendered())
    if updated == text:
        return 0
    if args.check:
        print(f'out of date: {PAGE.name}', file=sys.stderr)
        print('run: python scripts/gen_model_diagram.py', file=sys.stderr)
        return 1
    PAGE.write_text(updated, encoding='utf-8')
    print(f'updated: {PAGE.name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
