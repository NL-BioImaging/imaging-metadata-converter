# Maintaining the model

How the imaging model was made from the LiMi XSD, how a metaseed profile and
metaseed datasets are made from it, and how all three are validated. None of
this is part of the package: it is done with the scripts in `scripts/`, which
need nothing beyond the package's own dependencies (some of their tests need
`linkml` and `metaseed`).

## The files

| File | What it is |
|---|---|
| `src/imaging_metadata_converter/models/imaging.yaml` | The master model, edited by hand, and its three imports (see [The model](model.md)) |
| `src/imaging_metadata_converter/mappings/mappings.json`, `combinations.json` | The mapping rules |
| `profile/imaging.metaseed.yaml` | The metaseed profile, generated (`scripts/metaseed_generator.py`), published on the metaseed Hub as `imaging` 1.0 |
| `export/` | One metaseed dataset per example, generated (`scripts/dataset_exporter.py`) |
| `reference/LiMi_XMLSchema.xsd` | The LiMi XSD the model was converted from (unchanged) |
| `reference/ome-2016-06.xsd` | The OME 2016-06 schema, source of descriptions LiMi leaves out |
| `reference/fullSchema.json` | LiMi's JSON schemas (unchanged) |
| `reference/LiMi_Model.json` | LiMi's model as JSON (unchanged) |

## From the LiMi XSD to the model

`python scripts/linkml_converter.py` converted the whole XSD once, with the
rules described on [The model](model.md). The model has been edited by hand
since, so the script refuses to overwrite it without `--force`; it is kept for
comparing a future LiMi XSD, and a test checks that everything it yields is
still in the master.

Descriptions the XSD leaves out were filled where a source exists, each marked
with `description_source`: 28 from the OME 2016-06 schema (CC BY 3.0,
attributed in the model), and 265 derived from the model itself (an
enumeration from the slot that uses it, `XUnit` as "The unit of X"). The rest
(mostly enumeration values) stay empty rather than invented.

Slips in the XSD were worked around, keeping the original names as
annotations:

- `OpticalAperture` uses `LensID` as its ID type; `FilterCubeRef` extends
  `FilterCubeRef` with a generic LSID; `StageInsertRef` and `LightSensorRef`
  name their ID attribute `StageInsertID` and `LightSensorID`.
- `BeamSplitter` has both an attribute and an element
  `TransmittanceProfileFile` (the element's slot is
  `TransmittanceProfileFileElement`); `MaskingPlate` has an attribute named
  `ApertureNr.` (slot `ApertureNr`, with an `xsd_name` annotation), since a
  dot would split the slot's path.
- The typo `lluminationPowerSettingsUnit` (`LightSourceSettings`) is kept.
- `LightSensor` is referenced but no element contains it: the one class the
  profile cannot reach, so its references stay plain strings.
- `LightPath` has no tier in the XSD; tier 1 is taken from `fullSchema.json`.

## From the model to a metaseed profile

`python scripts/metaseed_generator.py` writes the profile. metaseed has no
inheritance, so:

- every concrete class reachable from `OME` is an entity with its inherited
  fields written out (228 entities, 3667 fields);
- a slot over an abstract class becomes one field per subtype
  (`Instrument.Laser`, `Instrument.Arc`, ...); none of them can be required,
  since metaseed has no "one of";
- references are ID strings; enumerations, patterns and bounds become
  constraints;
- LiMi's tiers become metaseed tiers: the higher tier of the field and its
  class, tier 1 as `required`, 2 as `recommended`, 3 (and
  `MechanicalCalibration`'s 4) as `optional`. LiMi documents at these levels,
  so a field the XSD requires stays required only at tier 1;
- metaseed keys an entity by its `is_identifier` field, else by its first
  field that is not a reference. Where that field is optional free text,
  metaseed would warn, so the generator adds an optional `ID`; where it was
  required in the model and is optional only through its tier (StageLabel's
  `Name`), it is declared the identifier instead, so that a new version does
  not re-key existing datasets;
- a `uri` field with a pattern is written as a string with the pattern (the
  UUIDs), since metaseed applies the pattern to the parsed URL and fails on
  every value;
- entities are written in metaseed's containment order, each after every
  entity nesting it.

### Publishing a new version

After a change to the model: regenerate the profile, compare it with the last
published version using metaseed's own compatibility check
(`metaseed.specs.compare.compare_specs(old, new)`, the check behind the Hub's
"Breaking changes"), bump the version it asks for, and publish.

- 0.1 to 0.2: no breaking change. 0.2 added the LiMi tiers (458 fields no
  longer required through them).
- 0.2 to 1.0: 16 breaking changes, all intended: the EM groups moved from
  `OME` into `Instrument` and `Image`, `ObjectiveSettings.Medium` and
  `RefractiveIndex` removed (they are `ImmersionLiquid`'s), the UUID fields
  strings with a pattern, and `ElectronSource.ID` required, as every LiMi
  hardware ID is.

## From examples to metaseed datasets

`python scripts/dataset_exporter.py` converts each file in `examples/` and
builds one metaseed dataset of the profile from it, in `export/`. A value goes
into a field only if it fits exactly (type, enumeration, format, free slot),
with a `SourceMapping` naming its source key; anything else becomes a
`Property` with its source path and JSON-encoded value, under the
`CustomProperties` of the nearest `Image`, `Instrument` or `OME`. A record that
fits no declared field (a vendor object where the model has a string) is taken
apart into one Property per leaf. Nothing is dropped.

A unit spelled otherwise than the model spells it (`um`, `micrometre`) is
stored as the model's unit (`µm`) when the units schema lists the spelling as
an alias; the mapping keeps the source's spelling as `SourceValue`. Record IDs
follow OME's `Type:N` convention (`Property:2653`, `SourceMapping:12`).

A dataset for the metaseed Hub needs metaseed's tree serialisation, not this
nested form: `MetaseedClient(...)._facade.load_nested(document)`, then
`serialize(format='tree')`.

## Validation

**The model**

- Valid against the LinkML metamodel; `linkml lint` reports only naming style
  (LiMi's PascalCase names are kept on purpose) and missing descriptions.
- Instance tests with the LinkML validator: an Instrument with a Laser and a
  Filament in one light-source list validates; a Laser with role Transmitted
  and a Filament with a laser field are rejected.
- Nothing lost from the sources: everything a fresh conversion of the XSD
  yields is still in the master, with the same range (or the XSD's kept as
  `xsd_range` where a range was changed on purpose), and every property of
  `fullSchema.json` has a slot in the model.

**The profile**

- metaseed `spec validate`: valid, no problems, no warnings, locally and on
  the Hub.
- Every concrete class is reachable from `OME` (except `LightSensor`), the
  entities are in containment order, and the committed profile is what the
  model generates.

**The datasets**

- Every dataset in `export/` validates with metaseed's own validator against
  the profile, but for required fields the examples do not state: LiMi's tier-1
  requirements (identifiers, names, pixel dimensions, objective and detector
  specifications, the Image's references to Instrument, Experiment, Sample and
  AcquisitionSoftware). No type, format, constraint or unknown-field error.
- metaseed makes a new profile loader, with an empty cache, for every nested
  entity it validates, and re-parses the whole profile each time (hours for a
  TALOS file). The test shares one cache between them, which gives the same
  result in seconds.
- No data lost: every value of every example is found again, with its type,
  in the exported dataset as a typed field or a Property, both in memory and
  after writing.

## Reproducing

```bash
pip install -e . pytest
python scripts/metaseed_generator.py    # model -> profile/imaging.metaseed.yaml
python scripts/convert_examples.py      # examples -> output/
python scripts/dataset_exporter.py      # examples -> export/, metaseed datasets
python -m pytest tests                  # all of the checks above
```

The tests of the XSD conversion need `linkml`, and the dataset validation
`metaseed`; without them those tests are skipped.

With the metaseed CLI: `metaseed spec import <draft> profile/imaging.metaseed.yaml`,
`metaseed spec validate <draft>`, `metaseed spec save <draft>`, then
`metaseed validate export/<name>.yaml -p imaging -v 1.0 -e OME`.
