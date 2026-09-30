# Model fit

How well each example in `examples/` can be expressed in the model. Every
source value ends up in the example's dataset in `export/`, either in a model
field or, where it has none, in a `Property` record, so nothing is lost; this
page counts which. It measures the model and the mapping rules together: a
value the model has a field for still counts as not covered until a rule, or
the mapper's own matching, takes it there.

A value is counted in one of five categories:

| Category | Covered | The value |
| --- | --- | --- |
| **By rule** | yes | is placed in a model field by a rule of `mappings.json` or `combinations.json` |
| **Automatic** | yes | is placed without a rule: its source path matches the end of one model path, as it is (`Pixels.SizeX` is `Image.Pixels.SizeX`); a source using the model's own names needs no rules |
| **Does not fit** | no | was taken to a model field, but its type, format or enumeration does not fit the field, or the field was taken |
| **No such field** | no | was taken into a model group that has no field of its name (`Image.ScanSettings.scanHW`) |
| **No location** | no | has no rule, and matches no model path |

The table counts **keys**: source paths with their list indices removed, so
`Laser[0].Name` and `Laser[1].Name` are one key, and a long list of repeated
records does not swamp an example. A key whose values differ, one channel's
fitting and another's not, counts in the best of its values' categories.
*Covered, values* gives the same share of the example's **values**; the
counts after it are of keys.

{{ model.fit }}

## Improving the fit

Each category not covered points to its own remedy:

- **No location**, the source groups listed per example: a value the
  model has a field for needs a rule taking it there; a common value the
  model has no place for needs a field, added to the extension where the
  model's structure has one for it. The rules come first.
- **No such field**, the model paths listed per example: the group is there,
  so the field is what is missing - a new field in the extension, or a rule
  sending the value to the field the group has under another name.
- **Does not fit**: the rule is right, the value's form is not, such as a unit
  the units schema does not list, or a date the field cannot parse.

An **automatic** match is taken on the path alone, so each is listed per
example to be checked: a source's `Rows` matches `Plate.Rows`, the rows of a
well plate, where a DICOM file means the image's height in pixels. A rule for
the source key overrides the match.

The **fields filled** are counted as LiMi's or the extension's, a field
counting as extension as soon as its path runs through a class or slot LiMi
does not have, as on the [model browser](model.md).

## Keeping this page in sync

The tables are computed when the site is built, by the MkDocs hook
`scripts/docs_data.py` (with `scripts/model_fit.py`), from the datasets in
`export/`; the tests keep those up to date with the examples, the rules and
the model. `python scripts/model_fit.py` prints the same tables.
