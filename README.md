# imaging-metadata-converter

Convert custom (vendor-specific) imaging acquisition metadata to common metadata.

Dict in, dict out - no file I/O, no CLI, no third-party dependencies.

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
#  'Image': {'Pixels': {'SizeX': 1024, 'SizeY': 768}}}
```

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
    schema_file='my_schema.json', mappings_file='my_mappings.json')
```

Both arguments accept a file path; omitting them uses the packaged files.

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

## How mapping works

Each field's dotted source path is resolved in two steps:

1. **`data/mappings.json`** - explicit rules (see below).
2. **`data/schema.extended.json`** - the model itself, matched by path suffix
   as a fallback, since OME-derived sources already use model field names
   (`Pixels.SizeX` resolves to `Image.Pixels.SizeX`). A suffix that would be
   ambiguous - shared by several model leaves, like the many `Name`/`ID`
   fields - is never guessed at.

Fields matching neither step are kept at their original path, so no data is
lost.

### Vendor tag wrappers

A reader that takes its metadata straight from a file's tags commonly keys
each vendor's blob by the tag it came from, so a Phenom file arrives as
`{'FEI_TITAN': {...}}` and a Zeiss one as `{'FibicsXML': {...}}`. That extra
level is not part of any rule, and it would stop every rule below it from
matching, so a top-level key is dropped when both hold:

- **no rule and no model field names it**, so it is not a namespace this
  model has an opinion about. A key that *is* part of the mapped paths
  (`Beam` in `Beam.WD`), or a vendor namespace a rule names (TALOS
  `CustomProperties`), is never stripped - however well its fields would
  resolve without it.
- **dropping it lets strictly more of the subtree resolve**, so an
  unrecognised key whose contents gain nothing stays where it is.

Both tests are answered by the rules themselves rather than by a list of
vendor tag names here, so a vendor this file has never seen is unwrapped
too. Several vendor tags in one file are each unwrapped in turn, and a plain
tag value beside them (`Make`, `Model`, `Software`) is kept as it is. A field
already present at the top level wins over one lifted out of a wrapper.

### Mapping rules

A `mappings.json` entry is `"source path": "target path"`. There are four
forms.

**Exact** - rename one field:

```json
"Beam.WD": "ElectronBeam.WorkingDistance.Value"
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
"Detectors.*": "Detector.Configuration[]",
"Optics.Apertures.*": "ElectronOptics.Apertures[]"
```

Use this where the vendor names instances by key (`Detectors.QBSD`,
`Detectors.SED`) instead of using a JSON array. Each child dict is mapped in
full and appended, so the key naming stays out of the output - but because
that key is often meaningful, it is preserved as an `id` on the item
(`Detector.Configuration[0].id = "QBSD"`). A purely numeric key carries no
information and is dropped instead, and an item that already has an `id` or
`ID` of its own is left alone.

**A `*` that is not a trailing `.*`** - match the whole path and discard the
part the `*` covered:

```json
"Annotation:CustomAttributes:SVI:Image:*": "Annotation[]"
```

This is for a variable stretch *within* one path segment - an instance index
or a generated UUID. Nothing of it is worth keeping, so the match is placed at
the target as one unit, or, with a `[]` target as here, appended as one list
item. `Image:0` and `Image:1` become two items rather than colliding.

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

## Flattening

`flatten_dict` reduces a nested metadata dict to one entry per leaf, keyed
by dotted path, which is the form the resolution steps above work in:

```python
from imaging_metadata_converter import flatten_dict

flatten_dict({'Scan': {'Resolution': {'X': 1024}}})
# {'Scan.Resolution.X': 1024}

flatten_dict({'Detectors': [{'Name': 'QBSD'}, {'Name': 'SED'}]})
# {'Detectors.0.Name': 'QBSD', 'Detectors.1.Name': 'SED'}
```

List and tuple items are keyed by their index. Keys are joined with dots and
are otherwise left exactly as they are - a source key that itself contains
colons stays a single path segment, since the OME
`Annotation:CustomAttributes:SVI:Image:0` annotations are real keys of that
shape rather than paths:

```python
flatten_dict({'Annotation:CustomAttributes:SVI:Image:0': {'RefrIndexMedium': 1.515}})
# {'Annotation:CustomAttributes:SVI:Image:0.RefrIndexMedium': 1.515}
```

## The model format

The model files are plain nested JSON. Every leaf is a `"FieldName": "type"`
pair, and the nesting is the model structure itself - there is no wrapper,
no `properties` level, no `$schema`:

```json
{
  "Instrument": {
    "Manufacturer": "string",
    "Model": "string",
    "Vacuum": {
      "GunVacuum": "number",
      "VacuumMode": "string"
    }
  },
  "Image": {
    "Pixels": {
      "SizeX": "integer",
      "PhysicalSizeX": "number",
      "PhysicalSizeXUnit": "string",
      "BigEndian": "boolean"
    },
    "BinaryResult": "object"
  }
}
```

A leaf's dotted path is its field name in the converted output, so the model
above defines `Instrument.Manufacturer`, `Instrument.Vacuum.GunVacuum`,
`Image.Pixels.SizeX` and so on. These are exactly the paths `mappings.json`
targets on the right-hand side, and the paths the schema fallback matches
against by suffix.

The type is one of the six JSON type names:

| Type | Meaning |
| --- | --- |
| `string` | text |
| `number` | any numeric value |
| `integer` | whole number |
| `boolean` | true / false |
| `array` | a list of records, e.g. `OpticsHolder.OpticsTurret.Lens` |
| `object` | a nested structure the model does not break down further, e.g. `Image.BinaryResult` |

The types are **descriptive, not enforced**. The mapper matches on paths only
- it never validates a value against its declared type and never coerces one,
so whatever the source held is written through unchanged. Use the types to
decide what a field is meant to hold when writing a mapping, not as a
guarantee about what a converted dict contains.

`array` and `object` leaves mark the places where the model expects a whole
substructure rather than a single value. An `array` leaf is what a `"Target[]"`
mapping entry fills, one item per matched source instance.

## Data files

- `src/imaging_metadata_converter/data/schema.extended.json` - the model used
  for conversion: the base model plus the extensions (2006 fields, adding the
  electron-microscopy sections `ElectronSource`, `ElectronBeam`,
  `ElectronOptics`, `Scan`, `Acquisition`, `Operations`, `Features` and
  `CustomProperties`).
- `src/imaging_metadata_converter/data/schema.json` - the base model on its
  own (1876 fields, 25 top-level sections from `Instrument` to
  `CalibrationTools`).
- `src/imaging_metadata_converter/data/mappings.json` - source field to model
  field mappings.
