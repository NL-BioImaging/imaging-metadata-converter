# The metadata model

<div class="github-only" markdown>

**Reading this on GitHub?** The interactive model browser below, and the
numbers on this page, only show on the documentation site:
[nl-bioimaging.github.io/imaging-metadata-converter/model](https://nl-bioimaging.github.io/imaging-metadata-converter/model/).

</div>

The model is the target of every conversion: the **imaging model** (version
{{ model.version }}), a [LinkML](https://linkml.io) schema shipped as
`src/imaging_metadata_converter/models/imaging.yaml`. It is LiMi — the
4DN-BINA-OME light-microscopy model, itself an extension of the OME 2016-06
data model — converted from LiMi's XSD (version 02.00), and extended with the
metadata real source files hold beyond it, mostly electron microscopy, and with
provenance, so that no source value is lost. How it was made, and the metaseed
profile made from it, are on [Maintaining the model](maintaining.md).

Each leaf of the model is one field of the output dict, named by its dotted
path (`Pixels.PhysicalSizeX`, `Instrument.Vacuum.GunVacuum`). A path starts at
a class with its own identifier (`OME`, `Image`, `Pixels`, `Laser`, ...) and
continues through the components nested in it, so every value has exactly one
path. The browser below reads the packaged model directly, so it always shows
what the installed version actually maps to.

The browser starts at the model's root, `OME`. Opening a group shows what it
holds, and a field holding a class opens that class in place: `OME` holds
`Image`, which holds `Pixels`, which holds `Channel`. A field holding an
abstract class, such as `Instrument.LightSource`, opens onto the classes that
can stand for it (`Laser`, `Arc`, ...). Paths still start at the nearest class
with its own identifier, so `Pixels.PhysicalSizeX` sits under `OME > Image >
Pixels`. A class held in several places, such as `MapAnnotation`, shows the
same fields in each. The only class `OME` cannot reach, `LightSensor`, is
listed beside it.

## Browse the model

<div data-model-tree
     data-model="../data/model.json"
     data-added="../data/added.json"
     data-mappings="../data/mappings.json"
     data-details="../data/details.json">
</div>

How to use it:

- **Filter** matches anywhere in the dotted path, so `Pixels.Size` finds the
  size fields and `Unit` finds every unit field in the model. With **Search
  descriptions** it also matches the fields' descriptions, so `wavelength`
  finds the fields that describe one whatever they are called.
- **Tier** narrows the model to LiMi's tiers: *Tier 1* keeps the fields LiMi
  requires, *Tiers 1-2* adds the recommended ones.
- **Extensions only** narrows the model to the fields it adds to LiMi — the
  electron-microscopy classes, the extra fields scattered through the shared
  ones, and the provenance classes (`Property`, `SourceFile`,
  `SourceMapping`). These carry an orange *extension* flag.
- **Mapped only** shows the fields some rule in `mappings.json` targets.
  Hover the badge to see which source paths reach that field.
- Clicking a field or group name opens what the model says of it (see
  [Reading a field](#reading-a-field)); its *copy* button copies its dotted
  path, ready to paste as the right-hand side of a mapping rule.
- The badge of a reference, or of a class already open above it, links to
  where that class is opened.
- A path in the URL fragment opens, highlights and describes that field, so
  [`#Pixels.PhysicalSizeX`](#Pixels.PhysicalSizeX) is a shareable link to one
  field, and [`#Laser`](#Laser) to one class. A class held in several places
  opens where it is nested least deep.

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
| `models/imaging.yaml` | LiMi as a LinkML model: {{ model.classes }} classes ({{ model.abstract_classes }} abstract), {{ model.enums }} enumerations, {{ model.types }} types; imports the three below |
| `models/imaging_extension.yaml` | metadata beyond LiMi, mostly electron microscopy: {{ model.extension_classes }} classes, the ones for existing classes as mixins |
| `models/imaging_provenance.yaml` | `Property`, `SourceFile` and `SourceMapping`: where values came from, and the ones the model does not model |
| `models/imaging_units.yaml` | the {{ model.unit_enums }} unit enumerations, each unit with the other spellings it is known by |

Together they give {{ model.paths }} paths, {{ model.fields }} of them fields; {{ model.added_fields }} of those
fields are added by the extension and provenance schemas.

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
| `Image` | `ElectronBeamSettings` (type, mode, focus, spot size, working distance, acceleration voltage, currents, convergence angle, defocus, shift, source tilt, stigmator, high-voltage readings, and the electron source it applies to), `ElectronOpticsSettings` (camera length, operating and projector modes, gun lens, the two condenser lenses' settings, apertures, and each `Aperture` with its name, number, shape, mechanism, diameter, whether it is in the beam and its position offset), `ScanSettings` (field of view, rotation, frame and line time, line integration and interlacing, detector) |
| `Image` | `Type`, `CropHint`, `Corrections` (contrast, brightness, gamma, black and white level) |
| `Instrument` | `Manufacturer`, `Model`, `CatalogNumber`, `Type`, `ComputerName`, `Vacuum` (buffer, gun, sample and system vacuum, mode), `ElectronSource` |
| `Detector` | `Type`, `Gain`, `Offset`, `Brightness`, `Contrast`, `Channel`, configuration; `Inserted`, `Enabled`, `ExposureTime`, `Binning`, and for electron-microscopy detectors the collection, elevation and azimuth angles, `CollectionAngleRange`, live, real and pulse-processing times, input and output count rates, and the spectrum's `Dispersion`, `OffsetEnergy`, `BeginEnergy` and `ElectronicsNoise` |
| `Pixels` | `TimePoints`: the source's own indices of the first and last time point (BigDataViewer's `Timepoints` range), whose count is `SizeT` and by which its registrations name them |
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
range (`CollectionAngleRange`, `Pixels.TimePoints`) is a `QuantityRange` with
`Begin`, `End` and `Unit`; a pair along X and Y (`Shift`, `Stigmator`,
`Binning`) is a `Vector2D`.

The model adds values to two of LiMi's enumerations too: `Oil` to the
objective's immersions (OME's, for an oil of a kind the source does not state),
and `Microdissection` to the lasers' roles (a laser that cuts the specimen, as a
Leica LMD7's, rather than lighting the image). LiMi shares the latter list with
arc lamps and multi-laser engines, so they accept it too.

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
be recognised as the model's unit. Other enumerations do the same where a
vendor spells a value its own way: Leica's immersions `DRY`, `OIL` and `WATER`
are `Air`, `Oil` and `Water`.

## Reading a field

Every field is shown with its range as a badge:

| Badge | Meaning |
| --- | --- |
| a type (`string`, `float`, `integer`, `boolean`, `datetime`, ...) | a plain value |
| an enumeration (`UnitsLength`, `UnitsTime`, ...) | one of a fixed set of values, such as a unit |
| a class (`Annotation`, `Channel`, ...) | an object nested in this one, opened in place, or referred to by its `ID` if the field is marked *ref* |

and with what the model constrains it to, from its LinkML slot:

| Badge | LinkML | Meaning |
| --- | --- | --- |
| *list* | `multivalued` | the field holds a list of values |
| *ref* | a class `range` that is not `inlined` | the value is the `ID` of an object held elsewhere, as LiMi's `*Ref` elements are |
| *ID* | `identifier` | the field identifies its object, and references name it |
| *T1* ... *T4* | the `Tier` annotation | LiMi's tier: 1 required, 2 recommended, 3 and 4 optional |
| *required* | `required` | the field is required in the model |

A field's tier is the larger number of its own tier and its class's, as the
metaseed profile gives it, so a field of a tier-2 class is tier 2 or beyond.
In the profile a field is required only if it is `required` here *and* of
tier 1: `Image.StageLabel.Name`, for one, is `required` but tier 2, so the
profile does not require it.

Clicking a name opens the rest:

| Line | LinkML | |
| --- | --- | --- |
| the text | `description` | the field's or class's description, from LiMi's XSD; the ones LiMi leaves out come from the OME 2016-06 schema, and say so (`description_source`) |
| *Class*, *Range*, *Refers to* | `range` | the class of a group, or the range of a field, linked to its place in the tree |
| *Is a* | `is_a` | for a class, the class it extends |
| *Declared by* | the class owning the slot | for an inherited field, the class it is declared on: `Laser.Manufacturer` is `ManufacturerSpec`'s, shared by every piece of hardware; an extension field names its mixin (`InstrumentExtension`) |
| *Category*, *Domain* | LiMi's annotations | where LiMi files the field or class, such as `LightSource` in `MicroscopeHardwareSpecifications` |
| *Same as* / *Close to in OME* | `exact_mappings`, `close_mappings` | the matching term of the [OME LinkML schema](https://github.com/gouttegd/yamf-playground/blob/main/linkml/ome/ome.yaml) |
| *Mapped from* | `mappings.json` | the source paths a rule sends to the field |

The ranges and constraints describe the model; the converter does not
enforce them: the mapper matches on paths only, and never validates or
coerces a value against its range. Validating a converted dataset against
them is what the metaseed profile is for (see
[Maintaining the model](maintaining.md)).

## Keeping this page in sync

Nothing on this page is copied from the model by hand. When the site is
built, the MkDocs hook `scripts/docs_data.py` reads the packaged model and
mappings and writes the four files the browser fetches — `data/model.json`,
`data/added.json`, `data/mappings.json` and `data/details.json`, the last
holding each path's description, constraints and mappings — into the site, and fills in the
counts above. A new version of the model files, or an edited `mappings.json`,
shows up on the next build with nothing to regenerate.
