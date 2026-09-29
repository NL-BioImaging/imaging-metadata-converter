# The metadata model

The model is the target of every conversion: the imaging model, a LinkML model
built from LiMi (the light-microscopy extension of OME) and extended with
electron-microscopy and other imaging metadata, shipped as
`src/imaging_metadata_converter/models/imaging.yaml`. Each of its leaves is one
field of the output dict, named by its dotted path (`Pixels.PhysicalSizeX`,
`Instrument.Vacuum.GunVacuum`). A path starts at a class with its own
identifier (`OME`, `Image`, `Pixels`, `Laser`, ...) and continues through the
components nested in it, so every value has exactly one path. The browser
below reads the packaged model directly, so it always shows what the installed
version actually maps to.

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
  `SourceMapping`).
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
block per section. Paths LiMi does not have are blue there, so the map also
shows how much of the converter's output comes from the extensions.

## The model files

| File | Contents |
| --- | --- |
| `models/imaging.yaml` | LiMi as a LinkML model, importing the three below |
| `models/imaging_extension.yaml` | metadata beyond LiMi, mostly electron microscopy |
| `models/imaging_provenance.yaml` | `Property`, `SourceFile` and `SourceMapping`, for source values the model does not model |
| `models/imaging_units.yaml` | the unit enumerations |

`AcquisitionMetadataMapper` reads `imaging.yaml` unless you pass
`schema_file`, and uses its paths twice: as the set of valid mapping targets,
and as the suffix-matched fallback for source paths no rule names.

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
drift from the packaged files unnoticed.
