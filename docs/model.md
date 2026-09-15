# The metadata model

The model is the target of every conversion: each of its leaves is one field of
the output dict, named by its dotted path (`Image.Pixels.SizeX`,
`Instrument.Vacuum.GunVacuum`). The browser below reads the packaged model
files directly, so it always shows what the installed version actually maps to.

## Browse the model

<div data-model-tree
     data-base="../data/schema.json"
     data-extended="../data/schema.extended.json"
     data-mappings="../data/mappings.json">
</div>

How to use it:

- **Extended model / Base model** switches between
  `schema.extended.json` — the model used for conversion — and `schema.json`,
  the base model on its own.
- **Filter** matches anywhere in the dotted path, so `Pixels.Size` finds the
  five size fields and `Unit` finds every unit field in the model.
- **Extensions only** narrows the extended model to the fields it adds on top
  of the base model — the electron-microscopy sections and the extra fields
  scattered through the shared ones.
- **Mapped only** shows the fields some rule in `mappings.json` targets.
  Hover the badge to see which source paths reach that field.
- Clicking a field name copies its dotted path, ready to paste as the
  right-hand side of a mapping rule.
- A path in the URL fragment opens and highlights that field, so
  [`#Image.Pixels.PhysicalSizeX`](#Image.Pixels.PhysicalSizeX) is a shareable
  link to one field.

An unbadged field is one no mapping rule targets yet. That is not a gap in the
model — it is a field awaiting a source that provides it.

## Where each element comes from

The [model map](model-map.md) shows every leaf of the extended model on one
page, coloured by origin: the base model in black and what the extended model
adds in blue.

## How the two models relate

| File | Fields | Contents |
| --- | --- | --- |
| `schema.json` | 1876 | the base model, 25 top-level sections from `Instrument` to `CalibrationTools` |
| `schema.extended.json` | 2006 | the base model plus the electron-microscopy extensions: `ElectronSource`, `ElectronBeam`, `ElectronOptics`, `Scan`, `Acquisition`, `Operations`, `Features` and `CustomProperties` |

`AcquisitionMetadataMapper` loads `schema.extended.json` unless you pass
`schema_file`, and uses it twice: as the set of valid mapping targets, and as
the suffix-matched fallback for source paths no rule names.

## Reading a leaf

Every leaf is a `"FieldName": "type"` pair — there is no `properties` level and
no `$schema`. The type is one of the six JSON type names shown as a badge in
the tree:

| Badge | Meaning |
| --- | --- |
| `string` | text |
| `number` | any numeric value |
| `integer` | whole number |
| `boolean` | true / false |
| `array` | a list of records, what a `"Target[]"` mapping rule fills |
| `object` | a nested structure the model does not break down further |

The types are descriptive, not enforced: the mapper matches on paths only, and
never validates or coerces a value against its declared type.

## Keeping this page in sync

The browser fetches its copies from `docs/data/`, which
`scripts/sync_docs_data.py` mirrors from
`src/imaging_metadata_converter/data/`. After editing a model or the mappings:

```bash
python scripts/sync_docs_data.py
```

`tests/test_docs_data.py` fails when those copies are stale, so the docs cannot
drift from the packaged files unnoticed.
