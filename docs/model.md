# The metadata model

The model is the target of every conversion: the **imaging model** (version
1.0.0), a [LinkML](https://linkml.io) schema shipped as
`src/imaging_metadata_converter/models/imaging.yaml`. It is LiMi — the
4DN-BINA-OME light-microscopy model, itself an extension of the OME 2016-06
data model — converted from LiMi's XSD (version 02.00), and extended with the
metadata real source files hold beyond it, mostly electron microscopy, and with
provenance, so that no source value is lost. It is maintained in
[imaging-metadata-consolidator](https://github.com/NL-BioImaging/imaging-metadata-consolidator),
and this package ships an unchanged copy.

Each leaf of the model is one field of the output dict, named by its dotted
path (`Pixels.PhysicalSizeX`, `Instrument.Vacuum.GunVacuum`). A path starts at
a class with its own identifier (`OME`, `Image`, `Pixels`, `Laser`, ...) and
continues through the components nested in it, so every value has exactly one
path. The browser below reads the packaged model directly, so it always shows
what the installed version actually maps to.

## Browse the model

<div data-model-tree
     data-model="../data/model.json"
     data-added="../data/added.json"
     data-mappings="../data/mappings.json">
</div>

How to use it:

- **Filter** matches anywhere in the dotted path, so `Pixels.Size` finds the
  size fields and `Unit` finds every unit field in the model.
- **Extensions only** narrows the model to the fields it adds to LiMi — the
  electron-microscopy classes, the extra fields scattered through the shared
  ones, and the provenance classes (`Property`, `SourceFile`,
  `SourceMapping`). These carry an orange *extension* flag.
- **Mapped only** shows the fields some rule in `mappings.json` targets.
  Hover the badge to see which source paths reach that field.
- Clicking a field name copies its dotted path, ready to paste as the
  right-hand side of a mapping rule.
- A path in the URL fragment opens and highlights that field, so
  [`#Pixels.PhysicalSizeX`](#Pixels.PhysicalSizeX) is a shareable link to one
  field.

An unbadged field is one no mapping rule targets yet. That is not a gap in the
model — it is a field awaiting a source that provides it.

## What the converter produces

The [model map](model-map.md) is the other side of that: one picture of the
fields some rule *does* target, drawn under the groups that hold them, with a
block per section. Paths LiMi does not have are orange there, against grey for
LiMi's own, so the map also shows how much of the converter's output comes
from the extensions.

## The model files

| File | Contents |
| --- | --- |
| `models/imaging.yaml` | LiMi as a LinkML model: 248 classes (37 abstract), 136 enumerations, 71 types; imports the three below |
| `models/imaging_extension.yaml` | metadata beyond LiMi, mostly electron microscopy: 21 classes, the ones for existing classes as mixins |
| `models/imaging_provenance.yaml` | `Property`, `SourceFile` and `SourceMapping`: where values came from, and the ones the model does not model |
| `models/imaging_units.yaml` | the 16 unit enumerations, each unit with the other spellings it is known by |

Together they give 4039 paths, 3713 of them fields; 252 of those fields are
added by the extension and provenance schemas.

`AcquisitionMetadataMapper` reads `imaging.yaml` unless you pass
`schema_file`, and uses its paths twice: as the set of valid mapping targets,
and as the suffix-matched fallback for source paths no rule names.

## From LiMi to LinkML

LiMi's XSD, rather than its JSON schemas, is the source: it defines each part
once, and has the inheritance, the abstract groups, the references and the
enumerations the JSON copies out. The conversion follows the style of the
[OME LinkML schema](https://github.com/gouttegd/yamf-playground/blob/main/linkml/ome/ome.yaml):

- A global element or named type is a class, and its `extension base` its
  `is_a`, so every field is defined once, on the class that owns it, and
  inherited by its subtypes.
- An abstract group is one slot over its abstract type:
  `Instrument.LightSource` holds Lasers, Arcs, Filaments, ... in one list.
- A `*Ref` is a reference to the target's `ID`, named without `Ref`
  (`ElectronBeamSettings.ElectronSource`).
- LiMi's `Split`, the roles a light source can play, is a `Role` field on
  `LightSource` instead of a copy of the class per role.
- The XSD's documentation gives the descriptions and annotations (`Tier`,
  `Category`, ...). Missing descriptions come from the OME 2016-06 schema where
  it has one, marked with `description_source`.
- Classes and fields that match the OME LinkML schema carry `exact_mappings`
  or `close_mappings` to it (prefix `ome:`), such as `Laser` to
  `ome:LaserLightSource`.

A few choices are made for real data rather than taken from the XSD:

- `Image.AcquisitionDate` is a `datetime`, as in OME, where LiMi has a date.
- IDs and references accept any string; the XSD's LSID patterns are kept only
  as advisory annotations, so vendor IDs such as `SS1735` fit.

## The extensions

The fields LiMi has no place for, formerly this package's
`schema.extended.json`. Fields for LiMi's own classes are LinkML mixins those
classes use (`InstrumentExtension`, `ImageExtension`, ...), so they appear in
the tree next to LiMi's fields; new groups are classes of their own.

| Where | What |
| --- | --- |
| `Image` | `ElectronBeamSettings` (type, mode, focus, spot size, working distance, acceleration voltage, currents, convergence angle, defocus, shift, source tilt, stigmator, high-voltage readings, and the electron source it applies to), `ElectronOpticsSettings` (camera length, operating and projector modes, gun lens, apertures), `ScanSettings` (field of view, rotation, frame and line time, line integration, detector) |
| `Image` | `Type`, `CropHint`, `Corrections` (contrast, brightness, gamma, black and white level) |
| `Instrument` | `Manufacturer`, `Model`, `Type`, `ComputerName`, `Vacuum` (buffer, gun, sample and system vacuum, mode), `ElectronSource` |
| `Detector` | `Type`, `Gain`, `Offset`, `Brightness`, `Contrast`, `Channel`, configuration |
| `Stage` | `Position`, `RawPosition`, `Tilt`, `Rotation`, `Bias`, `MultiStage` (sample height and radius) |
| `Software` | `ApplicationID` |
| `OME` | `Operations`, `Features`, `Annotation`, kept as source text |

The electron-microscopy groups follow LiMi's split between hardware and
settings, as `Objective` and `ObjectiveSettings` do: the electron source is
part of the `Instrument`, with its own `ID`, and how the beam, optics and scan
were set for one image are that `Image`'s `ElectronBeamSettings` (which refers
to its electron source), `ElectronOpticsSettings` and `ScanSettings`. The
operator is LiMi's `Experimenter.UserName`, the start of acquisition
`Image.AcquisitionDate`.

A value with a unit (`WorkingDistance`, `FieldOfView.X`, ...) is one shared
class, `Quantity` with `Value` and `Unit`, the unit as the source writes it; a
pair along X and Y (`Shift`, `Stigmator`) is a `Vector2D`.

## Provenance

`imaging_provenance.yaml` records where the output came from:

| Class | Holds |
| --- | --- |
| `SourceFile` | a file the metadata was read from: its name, SHA-256 checksum and format, and a `Mapping` list |
| `SourceMapping` | for a value placed in a model field, the source key it came from, the value as the source wrote it, and the source paths it was derived from when several were combined |
| `Property` | a source value the model does not model: its source path, JSON-encoded value and unit |

The `SourceMap` in the converter's output is the same idea at conversion time: every
output value knows its source path.

## Units

The unit enumerations (`UnitsLength`, `UnitsTime`, `UnitsPressure`, ...) come
from LiMi. Each unit lists the other spellings it is known by as aliases —
`µm` is also `um`, `micrometer` and `micrometre` — so a vendor's spelling can
be recognised as the model's unit.

## Reading a leaf

Every leaf is shown with its range as a badge:

| Badge | Meaning |
| --- | --- |
| a type (`string`, `float`, `integer`, `boolean`, `datetime`, ...) | a plain value |
| an enumeration (`UnitsLength`, `UnitsTime`, ...) | one of a fixed set of values, such as a unit |
| a class (`Annotation`, `FileAnnotation`, ...) | a reference to an object with its own place at the top of the tree |

The ranges are descriptive, not enforced: the mapper matches on paths only,
and never validates or coerces a value against its range.

## Keeping this page in sync

The browser fetches `docs/data/model.json`, `added.json` and `mappings.json`,
which `scripts/sync_docs_data.py` writes from the packaged model and mappings.
After editing the model or the mappings:

```bash
python scripts/sync_docs_data.py
```

`tests/test_docs_data.py` fails when those copies are stale, so the docs cannot
drift from the packaged files unnoticed. The counts on this page are written by
hand; update them when a new version of the model comes over from the
consolidator.
