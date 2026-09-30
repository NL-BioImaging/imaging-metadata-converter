# Known issues and TODO

Carried over from imaging-metadata-consolidator (2026-09-29), which this repository replaces.

## Known issues

### Hub state

Published on the Hub (account j.j.m.defolter@amsterdamumc.nl): profile `imaging` 0.1, 0.2 and 1.0 (1.0 =
`profile/imaging.metaseed.yaml`, model 1.0.0, 2026-09-28; valid, no problems, no warnings); the account holds
no datasets. After a change to the model: regenerate (`python scripts/metaseed_generator.py`), run
metaseed's compatibility check against the last published version (see "Profile versions"), bump the
version, and push and publish again.

Unpublished since 1.0 (2026-09-30): `Instrument.CatalogNumber`, the detector extension fields
(DetectorExtension: Inserted, Enabled, ExposureTime, Binning, angles, CollectionAngleRange, EDS times,
rates and energies) and the class `QuantityRange`; metaseed's check finds all 155 changes compatible
(optional fields, one entity): publish as 1.1, with the model's version.

The model's `id` and `imaging:` prefix still name the consolidator's URL
(https://github.com/NL-BioImaging/imaging-metadata-consolidator/models/imaging), kept for now (user,
2026-09-29); move them to this repository with the next model version, since it changes the profile.

### Profile versions

metaseed's compatibility check is `metaseed.specs.compare.compare_specs(old, new)`, the check behind the
Hub's "Breaking changes"; run it before publishing a new version.
- 0.1 -> 0.2: no breaking change (required bump minor). 0.2 adds the LiMi tiers: every field gets the higher
  LiMi tier of the field and its class (1 required, 2 recommended, 3 and MechanicalCalibration's 4
  optional), and the XSD's `required` holds only at tier 1; untiered fields (extension, provenance) keep
  theirs. A first 0.2 re-keyed StageLabel and MicroscopeTableSettings; the generator now keeps metaseed's
  inferred identifier (see "Generated metaseed profile").
- 0.2 -> 1.0: 16 breaking changes, all intended (required bump major): the EM groups moved from OME into
  Instrument and Image, ObjectiveSettings.Medium/RefractiveIndex removed (they are ImmersionLiquid's), the
  UUID fields strings with a pattern, and ElectronSource.ID required (an identifier, as all LiMi hardware
  IDs).

### Validation of the exports

All 14 export/ datasets validate with metaseed 0.54.0 against `imaging` 1.0, in full (2026-09-29): Delmic 12,
EMSIS 35, SVS 32, platy 32, DICOM 30, Zeiss 31, Cikteq Automap 40, Cikteq Normal 40, Phenom 54, ome-tiff 57,
Leica 29, Leica tilescan 97, TALOS 56, TALOS 2 56 errors - all "Field 'X' is required", no type, format,
constraint or unknown-field error. They are LiMi's own tier-1 requirements the sources do not state
(identifiers, names, pixel dimensions, objective and detector specifications, the Image's references to
Instrument, Experiment, Sample, AcquisitionSoftware). tests/test_metaseed_validation.py runs this (~15 s,
skipped without metaseed): metaseed's API against a temporary copy of the profile
(LOCALAPPDATA/XDG_DATA_HOME pointed at it), failing on any error but a missing required field. SVS's one
Property without a Name is its source key "", kept as it is.

The Hub validates the same way: a Delmic test dataset gave the same 12 issues there (deleted again, soft; the
user chose local validation only). Hub datasets need metaseed's tree serialization, not the nested export
(save_dataset silently stored an empty dataset): `MetaseedClient(...)._facade.load_nested(document)` then
`serialize(format='tree')`.

### metaseed workarounds (reported upstream, 2026-09-28)

Both reported to https://github.com/sorenwacker/metaseed/issues by the user; the workarounds stay until fixed.
- Slow validation: metaseed makes a new SpecLoader, with an empty `_profile_cache`, for every nested entity it
  validates, and re-parses the 1.2 MB profile YAML each time (~4 s; hours for TALOS). Sharing one cache
  across loaders (patch `metaseed.specs.loader.SpecLoader.__init__` to set `self._profile_cache` to one
  dict) gives identical results in seconds; the metaseed test does this.
- A `uri` field with a pattern fails on every value (metaseed applies the pattern to the parsed URL): the
  generator writes such fields (the UUIDs) as strings with the pattern.

### Generated metaseed profile

metaseed has no inheritance and no "one of": a slot over an abstract class is one field per concrete
subtype (Instrument.Laser, Instrument.Arc, ...), none required, so "an instrument has a light source" is
not enforced there. metaseed keys an entity by its `is_identifier` field, else by its first field that is
no reference; where that field is optional free text, an optional ID identifier is added (MapEntry,
BinData, Rights, ...), unless it is required in the model and optional only through its tier
(StageLabel.Name): then it is declared the identifier, so the entity keeps its key. Entities are written in
metaseed's containment order (each after every entity nesting it).

### LiMi XSD slips (worked around in the converter, original names kept)

- OpticalAperture uses `LensID` as its ID type; FilterCubeRef extends FilterCubeRef with a generic LSID;
  StageInsertRef/LightSensorRef name their ID attribute StageInsertID/LightSensorID.
- BeamSplitter has both an attribute and an element `TransmittanceProfileFile` (element slot ->
  `TransmittanceProfileFileElement`); MaskingPlate has an attribute named `ApertureNr.` (slot `ApertureNr`,
  `xsd_name` annotation) - a dot would split the slot's path.
- Typo `lluminationPowerSettingsUnit` (LightSourceSettings) kept; 7 unit slots have no value slot of their
  name (ReadNoiseUnit, XYZResolutionUnit, WavelengthUnit, MinTemperatureUnit, DevianceAngleUnit,
  ObservedIlluminationPowerAtBackObjectiveUnit, lluminationPowerSettingsUnit).
- LightSensor is referenced (LightSensorRef) but no element contains it: the only class the generated
  profile cannot reach; its references stay plain strings.
- LightPath has no Tier in the XSD; Tier 1 taken from reference/fullSchema.json (hand edit, `Tier_source`).

### Dates and IDs are taken gracefully (user, 2026-09-28)

- Image.AcquisitionDate is a datetime (OME's xsd:dateTime; LiMi's xsd:date kept as `xsd_range`). ISO 8601
  variations are taken as they come, without conversion (T or space, with or without a zone, `Z`); a value
  that is no datetime stays a Property. Other formats could be converted by a rule, as combinations.json
  does. metaseed accepts "2025-05-28 10:54:00".
- IDs and references accept any string: the 29 LSID-based ID types keep the XSD's pattern as an advisory
  `xsd_pattern` annotation only, so vendor IDs (`SS1735`, `9953543`) fit Instrument.ID. The UUID type keeps
  its pattern (a file link, no object ID).

### Values that stay Properties by design

- TALOS: AcquisitionDatetime and AcquisitionStartDatetime are Unix timestamps; combinations.json converts them
  (format "unix", seconds since 1970, UTC) into Image.AcquisitionDate, AcquisitionDatetime first. A "0" is an
  unset time, not converted, so TALOS's date comes from AcquisitionStartDatetime (2023-05-12T20:10:16+00:00,
  2022-03-09T17:43:42+00:00); the raw timestamps stay Properties, as every combination's parts do.
- ome-tiff: OME's ObjectiveSettings Medium "Oil" fits no LiMi ImmersionLiquidType (Mineral Oil, Silicone
  Oil, ...), and is not guessed.
- Where a source states a value twice (ome-tiff's Huygens annotation and its own OME fields: pixel sizes,
  wavelengths, immersion refractive index), the second copy meets a filled field and stays a Property; a
  test checks the two agree. `RefrIndexMedium` is per channel: channel 0's value goes to
  MountingMedium.RefractiveIndex, channel 1's collides and stays in its channel item.

### DICOM example holds dummy patient details

`examples/dicom.json` has patient fields (PatientName, PatientID, PatientBirthDate, InstitutionName,
...), which reach `output/` and, as Property records, `export/`. They are dummy values, not real
identifiers (user, 2026-09-25), so they can be committed and shared. A real DICOM source would need
de-identifying before it is added.

### Environment

The package needs only linkml-runtime; `.venv` (uv) has that and pytest, so the linkml and metaseed tests
skip there, as in the docs CI. biomero-converter-env (conda) has linkml 1.11.1 and metaseed 0.54.0 and runs
every test. chardet kept at 5.2.0 there (linkml's ShEx generator pyshexc wants >=7.4.1 but is unused;
requests warns on 7.x). The metaseed CLI writes to `%LOCALAPPDATA%/metaseed`, whatever `HOME` is set to:
point `LOCALAPPDATA` and `APPDATA` at a scratch folder when trying profiles locally.

`.gitattributes` keeps `examples/*.json` byte for byte (`-text`): export/ records each file's SHA-256, and
with `core.autocrlf` Windows checked six of them out with CRLF, so the committed checksums differed from CI's
(Linux, LF) and the export freshness test failed there (2026-09-29).

## In progress

Model fit analytics (user, 2026-09-30): how well each example can be expressed in the model, from
export/. A source value (and a distinct source key, list indices removed; the headline) counts in its
best category: covered by a rule (mappings.json or combinations.json), covered automatically (the
mapper's own match of a source path to a model path as is, counted as covered: 1:1 values need no rule,
by design), or not covered - does not fit its field (Property whose SchemaPath is a model field), no
such field (SchemaPath not a model field) or no model location (no SchemaPath). Also LiMi vs extension
among the fields filled, and per example the automatic matches (to review: DICOM Rows/Columns land in
Plate, not Pixels.SizeY/SizeX), the groups lacking fields and the source prefixes with no location.
Output: scripts/model_fit.py (prints the tables) and docs/model-fit.md, filled by the MkDocs hook.
Then (user): raise coverage of platy, LIF and DICOM - prefer extending the mapping over the model,
though both are valid; propose per key with stated assumptions, confirm, add. Their coverage was low
from when they were added (consolidator 46a960a, 2026-09-25), not from the OME root or the LinkML move.
Analytics done and pushed (171254d). DICOM (user, 2026-09-30): plain rules agreed - Manufacturer,
ManufacturerModelName, StationName -> Instrument.Name, Modality -> Instrument.Type, SoftwareVersions,
Rows/Columns -> Pixels.SizeY/SizeX (fixing the automatic Plate match), BitsStored -> SignificantBits,
SOPInstanceUID -> Image.ID, StudyInstanceUID -> Experiment.ID, StudyDescription, SeriesDescription ->
Image.Name, ImageComments -> Image.Description, InstitutionName -> Experimenter.Institution; the rest
(patient/admin, CT physics, display) stays Property. Open: a list-element split with an implied unit
(PixelSpacing, SliceThickness in mm) is no existing rule form - the "split" of c2cb391 copies one value
to several targets, the merge (combinations) builds datetimes only; Instrument.SerialNumber (model
extension) for DeviceSerialNumber; a combination cannot replace the automatic AcquisitionDate (date
only) since combinations write only where free, after the rules.
DICOM rules pushed (8247f53). Now (user): C and D.
C done: a rule may be an object {"target": ..., "unit": ...}, the unit written to the target's unit
field where free once everything is mapped, recorded as derived from its value (DerivedFrom in the
export); a rule may name one item of a plain value list ("PixelSpacing[0]"), the other items staying in
a list at its place. DICOM PixelSpacing and SliceThickness map with unit mm. D done, as
Instrument.CatalogNumber (user): LiMi's ManufacturerSpec has no SerialNumber, its CatalogNumber is
"Catalog, Part or Serial Number"; DeviceSerialNumber maps to it. DICOM: 21% of keys (17 of 94).
C and D pushed (ff5ac6a). LIF (user, 2026-09-30): round 1 agreed - summary keys (manufacturer, model,
lens_na, immersion), SystemTypeName -> Instrument.Name, SystemSerialNumber -> Instrument.CatalogNumber,
ObjectiveName/-Number -> Objective.Model/CatalogNumber, StagePosX/Y + ZPosition -> Plane.Position* (m),
MountingMediumRefractionIndex, UserManagementUserName, camera/scan format -> Pixels.SizeX/Y,
Resolution/BitSize -> SignificantBits, CameraName -> GenericDetector.Model, camera ExposureTime (s),
PixelDwellTime (s), Zoom, Pinhole (m), ScanDirectionXName -> ConfocalScannerSettings; the shared
magnification rule -> Objective.Magnification (nominal; EMSIS too); EMSIS pixelsizex/y unit m (were read
as um). Round 2 (user): LaserName/Wavelength (nm) -> Laser[*], LineAverage -> IntegrationNumber; not the
channel names/dyes (Spectro.MultiBand band i = image channel i unconfirmed). An implied unit now also
follows a [*] target. Not placed: Leica's integer order/serial numbers (CatalogNumber is a string, the
exporter keeps types exact), immersion "Oil" (not in LiMi's list), the HardwareSetting copies of the
summary keys (field taken), values needing translation (laser type, TL-BF contrast), ScanSpeed. WLL's
Wavelength 0 is placed as 0 nm, as the file says. Keys: widefield 1 -> 5%, tilescan 3 -> 10%.
LIF pushed (eb75b15). Platy (user, 2026-09-30): a combination format "split" (item n of a
whitespace-separated value, as a number) for ViewSetup.size -> Pixels.SizeX/Y/Z and voxelSize.size ->
PhysicalSizeX/Y/Z (BDV order x y z); voxelSize.unit -> the three units, "micron"/"microns" as aliases
of um; ViewSetup.name -> Channel.Name; ImageLoader.n5.value -> Image.Name.
Done: platy 0 -> 22% of keys (5 of 23; the rest is BDV's loader, time points and registration).
Coverage of the three now: DICOM 21%, LIF widefield 5%, LIF confocal 10%, platy 22% (pushed 50ebcb5).
TALOS (user, 2026-09-30): A - the exporter reads a number written as a string into a numeric field
(and a number into a string field), SourceValue keeping the source's (TALOS 22 core values; measured: 8
examples up, none down); B - one GenericDetector per TALOS detector, extension fields for what LiMi
lacks; C - apertures, optics modes, CustomProperties values, instrument/scan/binary-result keys; all
proposed per key first. Not D: Operations/Features (Velox processing history) stay Properties.
A done (numbers as text and back, SourceValue keeping the source's; 128 tests pass), not committed.
B (user): B1 a rule "Detectors.*.DetectorName": "GenericDetector[].Name" renames a field inside each
record a Target[] rule collapses (TALOS Detectors.*, Phenom acquisition.scan.detectors.* ->
GenericDetector[]); B2 DetectorExtension gains Inserted, Enabled, ExposureTime (s), Binning (Vector2D),
Collection/Elevation/AzimuthAngle (rad), CollectionAngleRange {Begin, End}, Live/Real/PulseProcessTime
(s), Input/OutputCountRate, Dispersion/OffsetEnergy/BeginEnergy/ElectronicsNoise (eV); B3 "true"/"false"
read into boolean fields. Configuration stays in the model, unused by these.
B done: item-field rules (and the label, as "Prefix.*.id"; an implied unit too), the extension fields,
text booleans. TALOS keys 3 -> 15% (TALOS 2 2 -> 11%), Phenom 44 -> 53%. DetectorMetadata now has
no location (GenericDetector is a list, so ActiveConfiguration cannot take it): part of C.
Status: A and B done, not committed; next C (apertures, optics, CustomProperties, DetectorMetadata,
instrument/scan/binary-result keys), proposed per key.

## The model and the pipeline

See docs/model.md and docs/maintaining.md for the full account.
- Model: `src/imaging_metadata_converter/models/imaging.yaml` (LinkML, style of the OME LinkML schema
  https://github.com/gouttegd/yamf-playground/blob/main/linkml/ome/ome.yaml, LiMi's PascalCase names),
  importing `imaging_units.yaml` (units enums, with aliases: LiMi's unit names and an ASCII form such as
  "um"), `imaging_provenance.yaml` (Property, SourceFile, SourceMapping) and `imaging_extension.yaml` (what
  the source files hold beyond LiMi, mostly EM; mixins OMEExtension, InstrumentExtension, ... used by the
  model's classes; shared Quantity {Value, Unit}, Vector2D, StagePosition). Edited by hand; version 1.0.0.
- Created once from the whole LiMi XSD by `python scripts/linkml_converter.py` (refuses to overwrite
  without --force). Rules: extension base -> `is_a`; an abstract `*Group` -> a slot over its (abstract)
  type with a type designator; `*Ref` -> a reference slot without `Ref` (`inlined: false`); Settings' ID
  refers to the component; the XSD's `Split` -> a `Role` field on LightSource, limited per class;
  descriptions the XSD lacks from OME 2016-06 ome.xsd (`reference/ome-2016-06.xsd`, CC BY 3.0, attributed)
  or derived, each with `description_source`. The script stays for comparing a future LiMi XSD; a test
  checks everything it yields is still in the model.
- Hand edits: the three imports and their mixins/CustomProperties/SourceFile slots; OME.ID/Name (metaseed
  datasets identify their root); LightPath Tier; MaskingPlate.ApertureNr; Image.AcquisitionDate as datetime;
  ID patterns advisory; `default_subtype` annotations on abstract classes (LiMi's Generic* subtypes;
  Stage -> MechanicalStage and Software -> AcquisitionSoftware chosen by the user) - where values for an
  abstract class go; exact_mappings/close_mappings with prefix ome: to the OME LinkML schema (21 classes, 55
  fields; a name match with another meaning is only close).
- EM groups follow LiMi's hardware/settings split: ElectronSource under Instrument; ElectronBeamSettings
  (referring to its ElectronSource), ElectronOpticsSettings and ScanSettings under Image; the operator is
  Experimenter.UserName, the start of acquisition Image.AcquisitionDate. Immersion medium and refractive
  index go to ObjectiveSettings.ImmersionLiquid, as in LiMi.
- Model paths (ModelPaths): start at a class with an identifier (OME, Image, Pixels, Laser, ...) and run
  through components without one: `Image.ElectronBeamSettings.WorkingDistance.Value`,
  `MechanicalStage.Position.X.Value`, `Pixels.PhysicalSizeX`. mappings.json targets are these paths (tested);
  a target may hold `[*]`, the index of the list item the value comes from
  (`Pixels.Channel[*].Fluorophore.ExcitationWavelength`). The mapper's name matching indexes the paths, plus
  aliases for abstract classes (`Detector.Name` -> `GenericDetector.Name`). A vendor wrapper
  (`FEI_TITAN.FeiImage`, `FibicsXML.Fibics`) or the root of an OME document is left out of the paths the
  rules see.
- metaseed profile: `python scripts/metaseed_generator.py` -> `profile/imaging.metaseed.yaml` (profile
  `imaging` 1.0, 228 entities, 3667 fields), inherited fields written out, references as ID strings,
  constraints from enums, patterns and bounds, LiMi tiers as metaseed tiers. The exporter
  (`scripts/dataset_exporter.py` -> `export/`) places a record by name only at a class a model path starts
  at (or an abstract class, into its default subtype), never at a component; a unit alias is stored as the
  unit, with `SourceMapping.SourceValue` keeping the source's spelling.
- Kept as references, read only by the XSD conversion and its tests: reference/LiMi_XMLSchema.xsd,
  reference/ome-2016-06.xsd, reference/fullSchema.json (a test checks every property is in the model),
  reference/LiMi_Model.json.
- Retired (in the consolidator's git history): mappings/schema.json, schema.extended.json, ProfileConverter,
  the `consolidate` command (Consolidator) and the image readers (TiffSource, ImageSource, ome_tiff_util).

## How new, unmapped metadata is kept

Nothing a source holds is dropped; unmapped metadata stays reachable at its source path.

In `output/` (`scripts/convert_examples.py`), for example with a source
`{Make: Acme, NewVendorKey: 42, Beam: {WD: 0.005, NewBeamSetting: 'on'}, Odd: {Deep: {Value: 1.5}},
ACME_TAG: {Model: X1-rev2, Serial: S123}}`:
- `NewVendorKey` (no rule, no model name match) stays at `NewVendorKey`.
- `Beam.NewBeamSetting` lands at `Image.ElectronBeamSettings.NewBeamSetting`: a subtree rule (`Beam.*` ->
  `Image.ElectronBeamSettings`) carries new fields of that group along.
- `Odd.Deep.Value` (unknown group) stays as it is.
- `ACME_TAG` is a vendor wrapper: its unmapped `Serial` stays at `ACME_TAG.Serial`; its `Model` has a
  rule and goes to `Instrument.Model`, as if the wrapper were absent (had a top-level `Model` taken
  `Instrument.Model` first, it would stay at `ACME_TAG.Model` instead of overwriting).
- Every leaf gets a SourceMap entry (output path -> source path), e.g.
  `Image.ElectronBeamSettings.NewBeamSetting: Beam.NewBeamSetting`.

In `export/` (metaseed dataset, `scripts/dataset_exporter.py`): metaseed rejects undeclared keys, so each
such value is a `Property` record under `CustomProperties` of the nearest anchor (Image, Instrument, else
OME): `Name` = source path, `Value` = JSON-encoded value, `SchemaPath` = where a rule moved it. A record that
fits no declared field (a vendor object where the model has a string) is taken apart into one Property per
leaf. Values that fit a declared field are typed, with a `SourceMapping` record (e.g. `Make` ->
`Instrument[0].Manufacturer`). Record IDs follow OME's `Type:N` convention (`Property:2653`,
`SourceMapping:12`, `SourceFile:0`); what a record is about is in `Name`/`SchemaPath`/`Field` - IDs made
of paths were considered and not taken (user, 2026-09-28).

What follows from a new example or new metadata:
- The output/ and export/ freshness tests (tests/test_examples.py, tests/test_dataset_exporter.py) fail
  until `scripts/convert_examples.py` and `scripts/dataset_exporter.py` are rerun; the no-data-loss tests
  (tests/test_no_data_loss.py) confirm every new value is kept, and tests/test_metaseed_validation.py that
  the exports validate.
- `AcquisitionMetadataMapper.unmatched_fields()` lists output paths the model does not have - the
  candidates for new rules.
- To make a value typed: add a rule to mappings.json (its target a model path - a test checks it is in
  the model; add the field to imaging_extension.yaml if missing). A change to the model makes the
  committed profile out of date (a test fails until `python scripts/metaseed_generator.py` is rerun); then
  rerun both example scripts, and the value moves from a Property to a typed field. To publish the changed
  profile, see "Hub state".

## TODO

- [ ] Light-source role, when a source holds light sources (none does yet, so rules setting it would have
      nothing to act on or be tested with; user, 2026-09-28): rules for Transmitted/Fluorescence light
      sources should set `LightSource.Role`.
