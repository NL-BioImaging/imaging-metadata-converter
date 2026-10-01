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
"PixelSpacing[0]": {"target": "Pixels.PhysicalSizeY", "unit": "mm"}
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
writes `"0"` for a time it lacks). The combined value's `SourceMap` entry is
the list of its parts, and it takes their place: it holds the same
information, so the parts are left out of the output rather than kept twice
(see below for which stay).

The format `split` instead takes one item, counted from 0, of a value's
whitespace-separated words, as a number, for a source that writes several
numbers in one string:

```json
{"target": "Pixels.SizeZ", "sources": ["SpimData.SequenceDescription.ViewSetups.ViewSetup.size"],
 "format": "split", "item": 2}
```

BigDataViewer's size `"1100 1100 1150"` gives `SizeZ` 1150. An item that is
not there, or is no number, adds nothing.

Eight more formats derive a value a source writes in another form:

- `count` gives last − first + 1 of two parts: BigDataViewer's time points
  `first` 0 and `last` 0 give `Pixels.SizeT` 1.
- `duration` reads a time written as text in seconds, and writes the unit `s`
  beside it: Cikteq's frame time `"2min52s"` gives 172 s.
- `quantity` splits a number from the unit written after it: Cikteq's
  horizontal field width `"21.12µm"` gives 21.12 with the unit `µm`.
- `product` multiplies its parts: Aperio's `Exposure Time` 109 and
  `Exposure Scale` 0.000001 give 0.000109. An entry may state the unit the
  result is in, written beside it where free (`"unit": "s"` here, as the
  model would read an exposure without one in ms).
- `ratio` divides the first part by the second: Exif's `ExposureTime`, the
  fraction `[41, 5000]`, gives 0.0082 s. A part may name a list item
  (`"ExposureTime[0]"`). Every other Exif rational (`FNumber`,
  `FocalLength`, `ExposureBiasValue`, ...), which the model has no field
  for, becomes its number at its own key: a combination may target the key
  its parts are items of.
- `join` joins its parts with the entry's `"separator"`: LMD7's version
  numbers 8, 5 and 9136 give `"8.5.9136"`.
- `filetime` reads a Windows FILETIME (100 ns steps since 1601), as Leica's
  LMD software writes its acquisition time: `133966300315161733` gives
  `2025-07-10T14:07:11.516173`, without a zone, as the file states none.
- `pattern` takes the first group of the entry's regular expression
  `"pattern"`, as a number where it is one: Leica's objective name
  `"HCX APO L U-V-I  63.0x0.90 WATER  UV"` gives the magnification 63.0
  (`(\d+(?:\.\d+)?)\s*x`) and the immersion `WATER`, the model's `Water`.
  A source path may hold `*`, for the first path it matches
  (`HardwareSettingList.FilterSetting.*Turret.Objective.Variant`, the turret
  being named after the stand).

A derived value may replace what a rule put at its target from its own
parts, when that is no number, so the rule and the combination can share a
key: Cikteq writes `"2min52s"` under the `Scan.FrameTime` TALOS writes as a
number, and TALOS's number stays; Exif's exposure fraction, which the model's
own `ExposureTime` takes as a list, gives way to its ratio.

A part stays where it sits in a model field (a rule mapped it), where a
combination naming it with all its parts there wrote nothing (Exif's date
below, or TALOS's unset `"0"`), and for `count`: the number of time points
does not say which they are, and BigDataViewer's registrations name their
time point by index. Otherwise it goes, wherever a rule moved it: Cikteq's
`User.TimeStamp`, which `"User.*"` moves to `Experimenter`, is the
acquisition date.

A combination writes only where the field is free, after the rules and the
combinations before it, so it also serves as a fallback, and the order of the
entries sets which source wins: DICOM's `SpacingBetweenSlices` gives
`PhysicalSizeZ` before `SliceThickness` does, as Bio-Formats takes it (a
Philips MR states 6 mm slices 7.5 mm apart), each only as a positive number
(a scout's spacing of -10 says nothing about a stack). Likewise Exif's
`DateTimeDigitized` (`"2025:05:28 10:54:29"`) gives the acquisition date only
where no vendor field does, as EMSIS's Olympus `datetime` does.

### Leica sequential confocal scans

One structure no rule can join: a Leica (LAS X) sequential scan, as
biomero-converter's `LeicaSource` passes it, describes each channel across
three places. Channel k is the k-th active detector, taken sequence by
sequence (`LDM_Block_Sequential_List`); that detector's spectral band
(`Spectro.MultiBand`, numbered by detector and stated once) gives its dye and
detection window; the sequence's laser lines on give its excitation. The
mapper joins them into `Pixels.Channel[k]`: the dye as written as `Name` and
`Fluorophore.Name`, the window as a band-pass `Filter` its `LightPath` names
as `EmissionFilter`, a `LightSourceSettings` per laser line on, naming the
laser (whose `Role` is `Fluorescence`, as it excites a dye; a laser
microdissection system's laser, which cuts the specimen, has the role
`Microdissection`, a value the model adds to LiMi's), and
`Fluorophore.ExcitationWavelength` where only one line is on. The
filters and lasers get IDs by their place (`Filter:0`, `Laser:3`), as the
source has none. The order is the sequences', not the bands': TileScan.lof's
sequences use detectors 4, 5 and 1, so its channels are ALEXA 488, mCherry
and Cerulean, which their LUTs (green, red, blue) and their pixels (two HyD
detectors and a PMT) confirm.

A Leica widefield image states per channel (`WideFieldChannelInfo`) which
shutters are open, not what the lamps are: a channel with the transmitted-light
(TL) shutter open names the stand's transmitted lamp, a fluorescence channel
with the incident-light (IL) shutter open its incident lamp, each a
`GenericExcitationSource` (a light source of no stated type) with the `Role`
`Transmitted` or `Fluorescence`, named by the channel's `LightSourceSettings`.

Older Leica files (LAS AF, as from an SP5) list their settings as records
instead (`{Identifier: dblZoom, Variant: 2.5}`); `LeicaSource` keys each
record by its own name (`ScannerSetting.dblZoom`, `FilterSetting.<object>.
<attribute>`), so plain rules map them: `ScannerSetting.dblZoom.Variant`,
and the objective's `FilterSetting.*Turret.NumericalAperture.Variant`, the
turret being named after the stand.

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
  1.1) from the model; rerun it after a change to the model.
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
`model.md`, and draws the model map on `model-map.md` (with
`scripts/model_map.py`). A new version of the model files or an edited
`mappings.json` shows up on the next build, with nothing to regenerate.
