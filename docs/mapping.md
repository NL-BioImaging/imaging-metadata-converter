# How the mapping works

The converter takes one metadata dict, as a reader passes it from a source
file, and returns another, laid out as the [imaging model](model.md): every
value it can place sits at its model path, every other value stays where the
source had it, and a `SourceMap` names the source of every output value.
Nothing is dropped and nothing is overwritten.

```python
from imaging_metadata_converter import convert_metadata

convert_metadata({'Make': 'Delmic B.V.', 'Model': 'Fast EM', 'Scan': {'ResolutionX': 6400}})
# {'Instrument': {'Manufacturer': 'Delmic B.V.', 'Model': 'Fast EM'},
#  'Pixels': {'SizeX': 6400},
#  'SourceMap': {'Instrument.Manufacturer': 'Make', 'Instrument.Model': 'Model',
#                'Pixels.SizeX': 'Scan.ResolutionX'}}
```

The mapping knows nothing of any file format: what it knows is in two data
files, `mappings/mappings.json` (rules) and `mappings/combinations.json`
(values built from several), plus a few steps for structures no rule can
join, each described below.

## The steps, in order

1. **Vendor wrappers** are seen through: a top-level key that only wraps a
   vendor's metadata (`FEI_TITAN.FeiImage`, `FibicsXML.Fibics`) is left out
   of the paths the rules see.
2. **Rules** place each value, from `mappings.json`, else by its **name**
   matching a model path.
3. **Implied units** - units a rule says its source implies - are written
   beside the values they qualify.
4. **Vendor steps** join what is spread over a source's structure: Leica's
   detectors, stand, cameras, sequential channels, microdissection laser and
   widefield lamps; the camera named by EXIF; and each detector's settings for
   the image.
5. **Combinations** add values built from several (a date from its date,
   time and zone).
6. **Spellings**: a value of an enumeration written otherwise (`OIL`, `um`)
   is written as the model spells it (`Oil`, `µm`).
7. The **SourceMap** is added.

## Model paths

A rule's target, and every output key, is a model path. A path starts at a
class with an identifier (`Image`, `Pixels`, `Instrument`, `Laser`,
`PhotoMultiplierTube`, ...), which the export can place on its own, and runs
through the components nested in it:

| Path | |
| --- | --- |
| `Image.ElectronBeamSettings.WorkingDistance.Value` | a component, then a `Quantity`'s value |
| `Pixels.PhysicalSizeX`, `Pixels.PhysicalSizeXUnit` | LiMi's own value and unit fields |
| `Plane.RawStage.PositionX` | an extension component of LiMi's `Plane` |
| `LightPath.GenericDetectorSettings.AnalogGain` | a slot over an abstract class (`DetectorSettings`), named by its concrete subtype, as the metaseed profile has it |

A path starting at an abstract class stands for its default subtype:
`Detector.Name` is `GenericDetector.Name`. The [model browser](model.md)
shows every path.

Three marks address list items:

- `[*]` - the item of the source's list the value comes from:
  `Pixels.Channel[*].Fluorophore.ExcitationWavelength` puts each channel's
  value in its own channel.
- `[]` - one item per child of a collapsed subtree (below).
- `[Field=Value,...]` - the item whose fields have those values, made with
  them where there is none (below).

## Rules

A `mappings.json` entry is `"source path": target`. The source path is the
path in the source dict (a wrapper left out, list items unindexed); the
target is a model path, a list of them, or an object stating more.

**Exact** - rename one field:

```json
"Beam.WD": "Image.ElectronBeamSettings.WorkingDistance.Value"
```

**Several targets** - a copy at each, where free:

```json
"MPP": ["Pixels.PhysicalSizeX", "Pixels.PhysicalSizeY"]
```

**A unit the source implies** - written beside the value, in its unit field
(`PhysicalSizeYUnit`, or the `Unit` beside a `Quantity`'s `Value`), only where
free and only once everything is mapped, so a unit the source states always
comes first:

```json
"PixelSpacing[0]": {"target": "Pixels.PhysicalSizeY", "unit": "mm"}
```

DICOM gives lengths in mm without saying so: its `PixelSpacing`
`[0.9765625, 0.9765625]` becomes `PhysicalSizeY: 0.9765625` and
`PhysicalSizeYUnit: mm`. A unit
is stated only with confidence (the vendor's convention is known and the
values agree with it). Its SourceMap entry is the list of the value it
qualifies, as a derived value's is of its parts.

**An item of a value list** - `[n]` in a source path:

```json
"PixelSpacing[0]": "Pixels.PhysicalSizeY",
"PixelSpacing[1]": "Pixels.PhysicalSizeX"
```

DICOM's `PixelSpacing` is one list, the row spacing then the column spacing.
An item whose target is taken, or that no rule names, stays in a list at the
list's own path.

**A subtree** - `Prefix.*` keeps the rest of each path below a new prefix,
field by field, so a more specific rule for a child still applies:

```json
"Vacuum.*": "Instrument.Vacuum"
```

`Vacuum.GunVacuum` becomes `Instrument.Vacuum.GunVacuum`, and a field of
the group the model does not have (`Vacuum.NewSensor`) lands in the group
too, kept beside the model's fields.

**A collapsed subtree** - `Prefix.*` to `Target[]` makes each child an item
of the list, for a vendor naming its instances by key; the key is kept as
the item's `id`, and `Prefix.*.field` rules rename fields inside the items:

```json
"Optics.Apertures.*": "Image.ElectronOpticsSettings.Aperture[]",
"Optics.Apertures.*.Diameter": {"target": "Image.ElectronOpticsSettings.Aperture[].Diameter.Value", "unit": "m"}
```

TALOS's `Optics.Apertures.Aperture-1.Diameter` `0.00015` becomes
`Aperture[1]` with `id: Aperture-1` and `Diameter: {Value: 0.00015, Unit: m}`.
A purely numeric key carries no information and is dropped instead, and an
item with an `id` or `ID` of its own keeps it. A field rule renames only
where the model's name is free in the item; `Prefix.*.id` names the field
the key becomes (Phenom's `acquisition.scan.detectors.*.id` to `Name`: the
detector `QBSD`).

**A list item named by its fields** - the item is found where it is and made
where it is not, so neither the order of the items nor their place is
assumed:

```json
"ConfocalSettingDefinition.LineAverage": "LightPath.ConfocalScannerSettings.Integration[Unit=Line,Method=Average].Number",
"ConfocalSettingDefinition.FrameAccumulation": "LightPath.ConfocalScannerSettings.Integration[Unit=Frame,Method=Sum].Number"
```

A Leica SP8's `LineAverage` 16 and `FrameAccumulation` 1 become

```yaml
Integration:
- {Unit: Line, Method: Average, Number: 16}
- {Unit: Frame, Method: Sum, Number: 1}
```

**A detector's settings, with it** - where a source describes several
detectors, a rule writes each one's settings with the detector, in its
settings class, as only later is it known which detector made the image (see
[Detectors](#detectors-and-their-settings)):

```json
"Detectors.*.LiveTime": {"target": "GenericDetector[].GenericDetectorSettings.LiveTime.Value", "unit": "s"}
```

**A `*` within a segment** - a variable stretch of one path segment (an
index, a generated UUID), discarded, the match placed as one unit:

```json
"Annotation:CustomAttributes:SVI:Image:*": "OME.Annotation[]"
```

With a `[]` target, as here, each match is appended as one item, so
`Image:0` and `Image:1` become two items rather than colliding.

### How rules are matched

- An exact rule comes before any wildcard rule, and every rule before the
  match by name. Wildcard rules are tried in file order, the first match
  winning: `"Image.BoundingBox.*"` sits above `"Image.*"` for that reason.
- Patterns are glob-matched (`fnmatch.fnmatchcase`): case-sensitive, a `*`
  matching any characters, dots included. As a `*` is unanchored, a
  whole-path rule matches only a path of as many segments, never a deeper
  one.
- Once a `Target[]` rule has made a dict a list item, a shallower wildcard
  rule no longer reaches into that item's own fields.
- A path holding `.metadata.` also tries the part after it, so TALOS's
  operations, which repeat the acquisition metadata below a generated UUID,
  reuse the rules.

### By name

A value no rule names is placed where its path's end names a model path:
an OME-derived source's `Pixels.SizeX` reaches `Pixels.SizeX` with no rule.
A name more than one model path ends in (`Name`, `ID`, `Value`) is never
guessed at. A value that matches by name but means something else needs a
rule: DICOM's `Rows` would match `Plate.Rows`, so a rule sends it to
`Pixels.SizeY`.

## Vendor wrappers

A reader keying each vendor's metadata by the tag it came from gives
`{'FEI_TITAN': {'FeiImage': {...}}}` for a Phenom image. A top-level level is
seen through when no rule and no model field names it, and strictly more of
what is below it resolves without it - a test the rules themselves answer,
so a vendor never seen before is unwrapped too. Only the rules skip the
wrapper: its unmapped fields stay under it, and the SourceMap keeps the full
source path.

## Combinations

`combinations.json` builds a value from parts, each looked up by source
path, written only where its target is free and every part is there:

```json
{"target": "Image.AcquisitionDate", "sources": ["Date", "Time", "Time Zone"],
 "format": "%m/%d/%y %H:%M:%S GMT%z"}
```

Aperio's `Date` `10/19/15`, `Time` `17:18:12` and `Time Zone` `GMT-05:00`
give `2015-10-19T17:18:12-05:00`, its SourceMap entry the list of the three.
The derived value takes its parts' place, as it holds what they did.

| Format | Gives | Example |
| --- | --- | --- |
| a `strptime` format, `unix`, `filetime` | an ISO 8601 date and time | TALOS's `1683922216`; Leica LMD's FILETIME |
| `split` (with `item`) | the n-th number of a spaced string | BigDataViewer's size `"1100 1100 1150"`, item 2: 1150 |
| `count` | last − first + 1 | time points 0 to 0: 1 |
| `duration` | a time written as text, in s | Cikteq's `"2min52s"`: 172 s |
| `quantity` | a number and the unit written after it | Cikteq's `"21.12µm"`: 21.12, µm |
| `product` | the parts multiplied | Aperio's exposure 109 × 0.000001 |
| `ratio` | the first part divided by the second | EXIF's `[41, 5000]`: 0.0082 |
| `join` (with `separator`) | the parts joined | LMD7's 8, 5, 9136: `8.5.9136` |
| `pattern` | the first group of a regular expression | `63.0` from `HCX APO L U-V-I  63.0x0.90 WATER  UV` |

A Unix time of 0 counts as unset (TALOS writes `"0"` for a time it lacks).
`duration` and `quantity` write their unit beside the value, as does an
entry stating a `"unit"` (`product`'s Aperio exposure, in s). A source path
of a part may hold `*`, for the first path it matches (Leica's
`FilterSetting.*Turret.Objective.Variant`, the turret named after its stand),
and a part may name a list item (EXIF's `"ExposureTime[0]"`); a
combination may target the key its parts are items of, so EXIF's other
rationals (`FNumber`, `FocalLength`) become their numbers in place.

A derived value may replace what a rule put at its target from its own
parts where that is no number, so a rule and a combination can share a key:
Cikteq writes `"2min52s"` under the `Scan.FrameTime` TALOS writes as a
number. A part stays where a rule put it in a model field, where a
combination naming it wrote nothing (TALOS's unset `"0"`), and for `count`,
as the number of time points does not say which they are; otherwise the
derived value replaces it, wherever a rule moved it.

A combination writes only where the field is free, after the rules and the
combinations before it, so the order of the entries is the order of
preference, and a combination is also a fallback: DICOM's
`SpacingBetweenSlices` gives `PhysicalSizeZ` before `SliceThickness` does,
each only as a positive number (a scout's spacing of -10 says nothing of a
stack), and EXIF's `DateTimeDigitized` gives the acquisition date only where
no vendor field does.

## Vendor steps

Some structures no rule can join, as what a value means depends on another
value. Each such step derives only what its source states, and lists every
source value it used in the SourceMap.

**Leica sequential channels** - channel k is the k-th detector a sequence
has on, taken sequence by sequence; its band gives the dye and a band-pass
`Filter`, the sequence's laser lines its `LightSourceSettings`, and the
detector its settings. TileScan.lof's sequences use detectors 4, 5 and 1,
so its channels are ALEXA 488, mCherry and Cerulean.

**Leica detectors** - each detector of the image's list is the class of the
type LAS X states: `PMT` a `PhotoMultiplierTube`, `HyD` a
`HybridPhotoDetector`, any other a `GenericDetector`, with an ID by its place
(`Detector:3`).

**Leica stand** - the `MicroscopeModel` (`DMI6000B-CS`) is an
`InvertedMicroscopeStand` or `UprightMicroscopeStand` as
`IsInverseMicroscopeModel` states; the system (`SystemTypeName`: TCS SP8) is
the `Instrument`'s `Model`.

**Leica cameras** - each camera (`IndividualCameraInfo`, four on a MICA) is a
`GenericDetector` of the model and serial its `FullCameraName` joins:
`DFC4400-GI-700010131528` gives `Model: DFC4400-GI`, `CatalogNumber:
700010131528`.

**Leica lamps and lasers** - a widefield channel states which shutters are
open, not what the lamps are: one with the transmitted-light (TL) shutter
open names the stand's transmitted lamp, a fluorescence channel with the
incident-light (IL) shutter open its incident lamp, each a
`GenericExcitationSource` with the role `Transmitted` or `Fluorescence`. A
laser exciting a channel with a dye has the role `Fluorescence`, an LMD
system's laser, which cuts the specimen, `Microdissection`.

**Leica LAS AF records** - older Leica files (an SP5's) list their settings
as records (`{Identifier: dblZoom, Variant: 2.5}`), which the reader keys by
their own names (`ScannerSetting.dblZoom`), so plain rules map them:
`ScannerSetting.dblZoom.Variant`.

**EXIF's recording equipment** - EXIF's `Make` and `Model` name what recorded
the image: the instrument, or, where camera software wrote the file (its own
`OlympusSIS` block beside EXIF), the camera: EMSIS's `Xarosa`.

### Detectors and their settings

LiMi keeps a detector's fixed values on the detector and how it was set for
an image in the `DetectorSettings` of the channel's `LightPath`, which name
the detector by `ID`. The step picks the detector that made the image: the
one the source names (Velox's `BinaryResult.Detector`: `HAADF`), those named
it and a number (its `DualX` image: `DualX1` and `DualX2`), or those mixed
into it (Phenom's `mixFactor` above 0). Their settings move from the
detector to the first channel:

```yaml
Pixels:
  Channel:
  - LightPath:
      GenericDetectorSettings:
      - {ID: Detector-4, AnalogGain: 18.58, Offset: -4.56,
         CollectionAngleRange: {Begin: 0.047, End: 0.2, Unit: rad}}
```

The other detectors keep theirs, as the source's. A source describing one
detector (Cikteq, a Leica camera) has rules to
`LightPath.GenericDetectorSettings`, which then name that detector.

## Never overwriting

A value is written only where it overwrites nothing; where its target is
taken, it stays at its source path. A rule therefore never loses data, even
when two sources claim one field: the first keeps it, the second stays where
it was.

## The SourceMap

Every leaf of the output has a SourceMap entry, in one of three forms:

| Form | Means | Example |
| --- | --- | --- |
| a path | the value as the source wrote it, moved | `Pixels.SizeX: Scan.ResolutionX` |
| a list of paths | a value derived from them | `Image.AcquisitionDate: [Date, Time, Time Zone]` |
| `{Source, SourceValue}` | the source's value in the model's spelling | `Objective.ImmersionType: {Source: ...Immersion, SourceValue: DRY}` (written `Air`) |

So any output value can be traced to the source, and an output with its
SourceMap holds everything the source did.

## Adding a mapping

1. Find a value that is not covered: `AcquisitionMetadataMapper.unmatched_fields(metadata)`
   lists output paths the model does not have, and the [model fit](model-fit.md)
   lists every example's values by how they were placed.
2. Prefer a rule to a field the model has; add a field only as "How new model
   fields are decided" in `notes/todo_known_issues.md` says.
3. Check every example holding the source key, not only the one at hand.
4. Run the tests. Among them, `tests/test_no_data_loss.py` checks every
   source value is kept, `tests/test_redundancy.py` that no field repeats
   another and no source name goes to two fields, and the freshness tests
   that `output/` and `export/` are regenerated
   (`python scripts/convert_examples.py`, `python scripts/dataset_exporter.py`).
