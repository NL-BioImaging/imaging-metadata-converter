"""Convert every example in examples/ and write the results to output/, as YAML.

The output files show what the converter currently makes of each
instrument's metadata, which is handy for checking the effect of a
mapping change by diffing output/ before and after. Run from anywhere:

    python scripts/convert_examples.py

Use --check to fail instead of writing when an output file is missing or
differs from what the converter now produces.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from imaging_metadata_converter import AcquisitionMetadataMapper

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'examples'
TARGET = ROOT / 'output'


class _Dumper(yaml.SafeDumper):
    """Quotes text that a YAML 1.2 reader would take for a number ("042959", a DICOM time), which PyYAML, reading
    YAML 1.1, leaves bare."""


def _text(dumper, value):
    looks_numeric = re.fullmatch(r'[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?', value) is not None
    return dumper.represent_scalar('tag:yaml.org,2002:str', value, style="'" if looks_numeric else None)


_Dumper.add_representer(str, _text)


def rendered(mapper, path):
    """The text the output copy of the example at ``path`` should hold."""
    custom = json.loads(path.read_text(encoding='utf-8'))
    common = mapper.convert_metadata(custom)
    return yaml.dump(common, Dumper=_Dumper, sort_keys=False, allow_unicode=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='report stale outputs without writing')
    args = parser.parse_args(argv)

    mapper = AcquisitionMetadataMapper()
    TARGET.mkdir(parents=True, exist_ok=True)
    stale = []
    for source in sorted(SOURCE.glob('*.json')):
        text = rendered(mapper, source)
        path = TARGET / f'{source.stem}.yaml'
        is_current = path.exists() and path.read_text(encoding='utf-8') == text
        if not is_current:
            stale.append(path.name)
        if not is_current and not args.check:
            with path.open('w', encoding='utf-8', newline='\n') as file:
                file.write(text)

    if args.check and stale:
        print('out of date: ' + ', '.join(stale), file=sys.stderr)
        print('run: python scripts/convert_examples.py', file=sys.stderr)
        return 1
    if stale and not args.check:
        print('updated: ' + ', '.join(stale))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
