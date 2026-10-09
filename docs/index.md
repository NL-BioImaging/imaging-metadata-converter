# imaging-metadata-converter

Convert custom (vendor-specific) imaging acquisition metadata to common
metadata. Dict in, dict out — no file I/O, no CLI; the one dependency is
`linkml-runtime`, for reading the model.

```python
from imaging_metadata_converter import convert_metadata

custom = {
    'Make': 'Acme',
    'Model': 'Widget-1000',
    'Scan': {'ResolutionX': 1024, 'ResolutionY': 768},
}

common = convert_metadata(custom)
# {'Instrument': {'Manufacturer': 'Acme', 'Model': 'Widget-1000'},
#  'Pixels': {'SizeX': 1024, 'SizeY': 768},
#  'SourceMap': {'Instrument.Manufacturer': 'Make', 'Instrument.Model': 'Model',
#                'Pixels.SizeX': 'Scan.ResolutionX', 'Pixels.SizeY': 'Scan.ResolutionY'}}
```

`SourceMap` records the source path of every output field, so renamed and
collapsed keys stay recoverable from the output alone.

The input is whatever metadata dict you already extracted from your file or
acquisition software; the output places the same information on the common
model.

## Where to go next

- **[The model](model.md)** — browse the model interactively: every field, its
  range, whether it extends LiMi, and which source paths map to it.
- **[How the mapping works](mapping.md)** — the rule forms, matching by name,
  vendor wrappers, combinations, the vendor steps and the SourceMap, with
  examples.
- **[API reference](reference.md)** — `AcquisitionMetadataMapper`,
  `convert_metadata` and `ModelPaths`.

## Installation

```bash
pip install .
```

For development, plus the tests:

```bash
pip install -e .
python -m pytest tests
```

## Building these docs

```bash
pip install -e ".[docs]"
mkdocs serve
```
