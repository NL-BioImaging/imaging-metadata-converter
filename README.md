# imaging-metadata-converter

Convert custom (vendor-specific) imaging acquisition metadata to common metadata.

Dict in, dict out - no file I/O, no CLI. The target is the imaging model, a
LinkML model built from LiMi and extended with electron-microscopy and other
imaging metadata; the one dependency is `linkml-runtime`, for reading it.

The model, and the metaseed profile made from it, are maintained here (see
Maintaining the model); they were developed in
[imaging-metadata-consolidator](https://github.com/NL-BioImaging/imaging-metadata-consolidator),
which this repository replaces.

Documentation, with a browser for the whole model and a map of what the
converter produces: <https://nl-bioimaging.github.io/imaging-metadata-converter/>

## Installation

```bash
pip install .
```

Or, for development (editable install plus the tests):

```bash
pip install -e .
python -m pytest tests
```

## Quick start

### 1. Convert a metadata dict

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

A value the model spells otherwise, listed as an alias of one of its
enumeration values, is written in the model's spelling: Leica's immersion
`"OIL"` as `Oil`, BigDataViewer's unit `"micron"` as `µm`. Its `SourceMap`
entry then records the source's spelling too:
`{"Source": "...Immersion", "SourceValue": "OIL"}`.

The input is whatever metadata dict you already extracted from your file or
acquisition software; the output is the same information placed on the common
model. Nested dicts and lists of dicts are walked recursively.

### 2. Reuse the mapper for many files

The model and mappings are parsed once per mapper instance, so create one
mapper and convert repeatedly rather than calling `convert_metadata` in a
tight loop:

```python
import json
from pathlib import Path

from imaging_metadata_converter import AcquisitionMetadataMapper

mapper = AcquisitionMetadataMapper()

for path in Path('examples').glob('*.json'):
    custom = json.loads(path.read_text(encoding='utf-8'))
    common = mapper.convert_metadata(custom)
    print(path.name, sorted(common))
```

### 3. Use your own model or mappings

```python
mapper = AcquisitionMetadataMapper(
    schema_file='my_model.yaml', mappings_file='my_mappings.json',
    combinations_file='my_combinations.json')
```

Each argument accepts a file path; omitting one uses the packaged file. The
model is a LinkML model like `models/imaging.yaml`.

## Examples

`examples/` holds real acquisition metadata from a range of instruments, used
by `tests/test_examples.py` and handy as input while extending the mappings:

| Example | Source |
| --- | --- |
| `Cikteq SEM4000x Automap.json` | Cikteq SEM4000x (Automap) |
| `Cikteq SEM4000x Normal.json` | Cikteq SEM4000x (Normal) |
| `Delmic FAST-EM.json` | Delmic FAST-EM |
| `EMSIS Xarosa.json` | EMSIS Xarosa |
| `TFS Phenom Pharos.json` | Thermo Fisher Phenom Pharos |
| `TFS TALOSF.json`, `TFS TALOSF 2.json` | Thermo Fisher Talos F |
| `Zeiss Supra55 Fibics ATLAS.json` | Zeiss Supra55 (Fibics ATLAS) |
| `ome-tiff.json` | OME-TIFF derived metadata |
| `dicom.json` | DICOM (dummy patient data) |
| `lif_metadata.json`, `lif_tilescan_metadata.json` | Leica LIF (LAS X) |
| `lif_sp5_metadata.json` | Leica LIF (LAS AF, a TCS SP5) |
| `lif_lmd7_metadata.json` | Leica LIF (LMD7 laser microdissection) |
| `platy_tomography.json` | BigDataViewer (SpimData) tomography |
| `svs_metadata.json` | Aperio SVS |

`output/` holds what the converter makes of each, as YAML, written by
`scripts/convert_examples.py`.

## How mapping works

Each source value is placed by a rule in `mappings/mappings.json`, else where
its path's end names a model path (an OME-derived source's `Pixels.SizeX`);
`mappings/combinations.json` builds values from several (a date from its
date, time and zone), and a few vendor steps join what a source spreads over
its structure (Leica's sequential channels, a detector's settings for the
image). A value is never written over another: where its target is taken, it
stays at its source path, as does every value no rule or model path names,
and the output's `SourceMap` names the source of every value, so nothing is
lost and every value can be traced.

```json
"Beam.WD": "Image.ElectronBeamSettings.WorkingDistance.Value",
"PixelSpacing[0]": {"target": "Pixels.PhysicalSizeY", "unit": "mm"},
"Vacuum.*": "Instrument.Vacuum"
```

[How the mapping works](https://nl-bioimaging.github.io/imaging-metadata-converter/mapping/)
(`docs/mapping.md`) describes it in full, with examples: model paths, every
form of rule, matching by name, vendor wrappers, combinations, the vendor
steps and the SourceMap.

## The model

`models/imaging.yaml` is LiMi as a LinkML model, importing
`imaging_extension.yaml` (metadata beyond LiMi, mostly electron microscopy),
`imaging_provenance.yaml` (`Property`, `SourceFile`, `SourceMapping`) and
`imaging_units.yaml` (the unit enumerations). `ModelPaths` reads it into the
dotted paths the mapper uses:

```python
from imaging_metadata_converter import ModelPaths

tree = ModelPaths().tree()
tree['Pixels']['PhysicalSizeX']
# 'PositiveFloat'
```

Every leaf's value is its range: a type (`string`, `float`, `datetime`, ...),
an enumeration (`UnitsLength`, ...) or, for a reference, the class it refers
to. The ranges are **descriptive, not enforced**: the mapper matches on paths
only, never validates a value against its range and never coerces one, so
whatever the source held is written through unchanged (combinations aside).

The [model page](https://nl-bioimaging.github.io/imaging-metadata-converter/model/)
of the documentation browses every path, flags the ones the extensions add
and the ones a mapping rule targets, and describes where the model comes from;
[how the mapping works](https://nl-bioimaging.github.io/imaging-metadata-converter/mapping/)
describes, with examples, how a source's values reach them.

## Data files

- `src/imaging_metadata_converter/models/imaging.yaml` and its imports - the
  imaging model (see The model).
- `src/imaging_metadata_converter/mappings/mappings.json` - source field to
  model field mappings.
- `src/imaging_metadata_converter/mappings/combinations.json` - values built
  from others (see Combinations).

## Maintaining the model

Outside the package, `scripts/` holds the tools the model is maintained with;
[Maintaining the model](https://nl-bioimaging.github.io/imaging-metadata-converter/maintaining/)
in the documentation describes them in full.

- `scripts/linkml_converter.py` - converted the LiMi XSD (`reference/`) into
  the model, once; the model is edited by hand since, so it refuses to
  overwrite it without `--force`. Kept for comparing a future LiMi XSD.
- `scripts/metaseed_generator.py` - generates the metaseed profile
  `profile/imaging.metaseed.yaml` (`imaging` 2.0; 1.1 is published on the
  metaseed Hub) from the model; rerun it after a change to the model.
- `scripts/dataset_exporter.py` - exports each example as a metaseed dataset
  of the profile into `export/`, with every value the model has no field for
  kept as a `Property` record.
- `scripts/model_fit.py` - how well each example can be expressed in the
  model, from its dataset in `export/`: whether the output keeps and traces
  every input value (100% each), the source keys covered by a rule or
  automatically, and the ones not covered, with why. `analyse()` returns
  these statistics for any conversion, `analyse_metadata()` for a source dict
  (also the docs' Model fit page).

The tests check that `profile/` and `export/` are up to date and lose no
data; the tests of the XSD conversion need `linkml` and those validating
`export/` with metaseed need `metaseed`, and are skipped without them.

## Documentation

The documentation site is built with MkDocs from `docs/` and published to
GitHub Pages on every push to `main`. To build it locally:

```bash
pip install -e ".[docs]"
mkdocs serve
```

Nothing on the model pages is stored in the repository. The MkDocs hook
`scripts/docs_data.py` reads the packaged model and mappings as the site is
built: it writes the JSON the model browser fetches (`data/model.json`,
`added.json`, `mappings.json`, `details.json`) into the site, fills in the model's counts on
`model.md`, and the examples' fit on `model-fit.md`. A new version of the model files or an edited
`mappings.json` shows up on the next build, with nothing to regenerate.
