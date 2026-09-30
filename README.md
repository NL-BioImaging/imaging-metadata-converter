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
| `lif_metadata.json`, `lif_tilescan_metadata.json` | Leica LIF |
| `platy_tomography.json` | BigDataViewer (SpimData) tomography |
| `svs_metadata.json` | Aperio SVS |

`output/` holds what the converter makes of each, written by
`scripts/convert_examples.py`.

## How mapping works

Each field's dotted source path is resolved in two steps:

1. **`mappings/mappings.json`** - explicit rules (see below).
2. **the model itself** (`models/imaging.yaml`), matched by path suffix as a
   fallback, since OME-derived sources already use model field names
   (`Pixels.SizeX`). A suffix that would be ambiguous - shared by several
   model leaves, like the many `Name`/`ID` fields - is never guessed at.

A model path starts at a class with an identifier (`OME`, `Image`, `Pixels`,
`Laser`, ...) and continues through the components nested in it:
`Image.ElectronBeamSettings.WorkingDistance.Value`, `Pixels.PhysicalSizeX`,
`MechanicalStage.Position.X.Value`. Every value in the model has one such
path.

Fields matching neither step are kept at their original path, and a value is
never written over another: when its target is taken, it stays at its source
path instead. The output's `SourceMap` records the source path of every output
field, so no data is lost and every value's origin can be traced.

### Vendor tag wrappers

A reader that takes its metadata straight from a file's tags commonly keys
each vendor's blob by the tag it came from, so a Phenom file arrives as
`{'FEI_TITAN': {'FeiImage': {...}}}` and a Zeiss one as
`{'FibicsXML': {'Fibics': {...}}}`. Those levels are not part of any rule,
and they would stop every rule below them from matching, so the rules see
the contents of a top-level key, one level or more deep, when both hold:

- **no rule and no model field names it**, so it is not a namespace this
  model has an opinion about. A key that *is* part of the mapped paths
  (`Beam` in `Beam.WD`), or a vendor namespace a rule names (TALOS
  `CustomProperties`), is never treated as a wrapper. The model's root
  (`OME`, wrapping a whole OME document) is the exception.
- **strictly more of the subtree resolves below it**, so an unrecognised key
  whose contents gain nothing is taken as it is.

Both tests are answered by the rules themselves rather than by a list of
vendor tag names, so a vendor never seen before is unwrapped too. Only the
rules skip the wrapper: its unmapped fields stay under it, and every source
path in the `SourceMap` keeps it.

### Mapping rules

A `mappings.json` entry is `"source path": "target path"`. There are nine
forms.

**Exact** - rename one field:

```json
"Beam.WD": "Image.ElectronBeamSettings.WorkingDistance.Value"
```

**Several targets** - copy one value to each, where free:

```json
"MPP": ["Pixels.PhysicalSizeX", "Pixels.PhysicalSizeY"]
```

**`Prefix.*` -> `Target`** - rename a whole subtree, keeping the remainder of
each path below it:

```json
"Vacuum.*": "Instrument.Vacuum",
"ImageCorrections.*": "Image.Corrections"
```

`Vacuum.GunVacuum` becomes `Instrument.Vacuum.GunVacuum`. The subtree is
expanded field by field rather than moved as one lump, so a more specific rule
for a child still gets its chance to apply.

**`Prefix.*` -> `Target[]`** - collapse each immediate child of the subtree
into its own item of a list at `Target`:

```json
"Detectors.*": "GenericDetector.Configuration[]",
"Optics.Apertures.*": "Image.ElectronOpticsSettings.Apertures[]"
```

Use this where the vendor names instances by key (`Detectors.QBSD`,
`Detectors.SED`) instead of using a JSON array. Each child dict is mapped in
full and appended, so the key naming stays out of the output - but because
that key is often meaningful, it is preserved as an `id` on the item
(`GenericDetector.Configuration[0].id = "QBSD"`). A purely numeric key carries
no information and is dropped instead, and an item that already has an `id`
or `ID` of its own is left alone.

A rule for `Prefix.*.field` whose target is `Target[].Field` renames a field
inside each of those items, where the model name is free, rather than writing
it at the root; the label counts as the item's field `id`:

```json
"Detectors.*": "GenericDetector[]",
"Detectors.*.DetectorName": "GenericDetector[].Name",
"Detectors.*.ExposureTime": {"target": "GenericDetector[].ExposureTime.Value", "unit": "s"},
"acquisition.scan.detectors.*.id": "GenericDetector[].Name"
```

**A `*` that is not a trailing `.*`** - match the whole path and discard the
part the `*` covered:

```json
"Annotation:CustomAttributes:SVI:Image:*": "OME.Annotation[]"
```

This is for a variable stretch *within* one path segment - an instance index
or a generated UUID. Nothing of it is worth keeping, so the match is placed at
the target as one unit, or, with a `[]` target as here, appended as one list
item. `Image:0` and `Image:1` become two items rather than colliding.

**`[*]` in a target** - send a value from a list item to the same item of a
model list:

```json
"StructuredAnnotations.XMLAnnotation.Value.ChannelData.LambdaEx": "Pixels.Channel[*].Fluorophore.ExcitationWavelength"
```

`[*]` stands for the index of the list item the value comes from, so each
channel's value goes to its own channel.

**`[n]` in a source path** - send one item of a list of values to its own
field:

```json
"PixelSpacing[0]": "Pixels.PhysicalSizeY",
"PixelSpacing[1]": "Pixels.PhysicalSizeX"
```

DICOM's `PixelSpacing` is one list, the row spacing then the column spacing.
An item whose target is taken, or that no rule names, stays in a list at the
list's own path, so nothing is lost.

**A unit the source implies** - a rule may be an object, whose `unit` is
written beside the value where the source states none:

```json
"SliceThickness": {"target": "Pixels.PhysicalSizeZ", "unit": "mm"}
```

DICOM gives every length in mm without saying so; left out, the model would
read them in its default µm. The unit goes to the target's unit field
(`PhysicalSizeZUnit`, or the `Unit` beside a `Quantity`'s `Value`), only where
free, and only once everything is mapped, so a unit the source does state
always comes first. Its `SourceMap` entry is the list of the value it
qualifies, as a combined value's is of its parts.

### Combinations

`mappings/combinations.json` adds a value built from others, as an ISO 8601
datetime: the parts, looked up by source path, are joined with spaces and
parsed with a `strptime` format, or with the format `unix` for seconds since
1970 (UTC):

```json
{"target": "Image.AcquisitionDate", "sources": ["Date", "Time", "Time Zone"],
 "format": "%m/%d/%y %H:%M:%S GMT%z"},
{"target": "Image.AcquisitionDate", "sources": ["Acquisition.AcquisitionStartDatetime.DateTime"],
 "format": "unix"}
```

The SVS `Date`, `Time` and `Time Zone` become `2015-10-19T17:18:12-05:00`,
and the TALOS start time `1683922216` becomes `2023-05-12T20:10:16+00:00`. A
combined value is written only where its target is free and every part is
there and parses; a Unix time of 0 counts as unset, not as 1970-01-01 (TALOS
writes `"0"` for a time it lacks). The parts stay where the mapping put them,
and the combined value's `SourceMap` entry is the list of its parts.

The format `split` instead takes one item, counted from 0, of a value's
whitespace-separated words, as a number, for a source that writes several
numbers in one string:

```json
{"target": "Pixels.SizeZ", "sources": ["SpimData.SequenceDescription.ViewSetups.ViewSetup.size"],
 "format": "split", "item": 2}
```

BigDataViewer's size `"1100 1100 1150"` gives `SizeZ` 1150. An item that is
not there, or is no number, adds nothing.

### Matching details

- Patterns are glob-matched with `fnmatch.fnmatchcase`, so matching is
  **case-sensitive** and `*` matches any characters, dots included.
- Because `*` is unanchored, segment counts are checked too: a whole-path rule
  matches only a path with the same number of dotted segments, never a deeper
  descendant.
- Wildcard rules are tried **in file order, first match wins**. A specific
  rule must therefore be placed above a more general one that would also
  match - `"Image.BoundingBox.*"` sits above `"Image.*"` in the current file
  for exactly this reason.
- Exact rules are always tried before any wildcard rule, and every
  `mappings.json` rule before the model fallback.
- Once a `Target[]` rule has claimed a dict as a list item, a *shallower*
  wildcard rule can no longer reach into that item's own fields, even though
  their absolute paths still start with its prefix.
- A path containing `.metadata.` also retries the part after it against the
  exact rules, so a Talos-style operation that embeds a second copy of the
  acquisition metadata below a generated UUID reuses the normal mappings.

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
the [model map](https://nl-bioimaging.github.io/imaging-metadata-converter/model-map/)
draws the fields the converter can fill in.

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
  `profile/imaging.metaseed.yaml` (published on the metaseed Hub as `imaging`
  1.0) from the model; rerun it after a change to the model.
- `scripts/dataset_exporter.py` - exports each example as a metaseed dataset
  of the profile into `export/`, with every value the model has no field for
  kept as a `Property` record.
- `scripts/model_fit.py` - prints how well each example can be expressed in
  the model, from its dataset in `export/`: the source keys covered by a rule
  or automatically, and the ones not covered, with why (also the docs' Model
  fit page).

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
`model.md`, and draws the model map on `model-map.md` (with
`scripts/model_map.py`). A new version of the model files or an edited
`mappings.json` shows up on the next build, with nothing to regenerate.
