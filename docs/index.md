# imaging-metadata-converter

Convert custom (vendor-specific) imaging acquisition metadata to common
metadata. Dict in, dict out — no file I/O, no CLI, no third-party
dependencies.

```python
from imaging_metadata_converter import convert_metadata

custom = {
    'Make': 'Acme',
    'Model': 'Widget-1000',
    'Scan': {'ResolutionX': 1024, 'ResolutionY': 768},
}

common = convert_metadata(custom)
# {'Instrument': {'Manufacturer': 'Acme', 'Model': 'Widget-1000'},
#  'Image': {'Pixels': {'SizeX': 1024, 'SizeY': 768}}}
```

The input is whatever metadata dict you already extracted from your file or
acquisition software; the output places the same information on the common
model.

## Where to go next

- **[The model](model.md)** — browse the model interactively: every field, its
  type, whether it is a base or extended field, and which source paths map to
  it.
- **[API reference](reference.md)** — `AcquisitionMetadataMapper`,
  `convert_metadata` and `flatten_dict`.
- The [README](https://github.com/NL-BioImaging/imaging-metadata-converter#readme)
  covers the mapping rule forms, vendor tag unwrapping and matching details in
  full.

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
