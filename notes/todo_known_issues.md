# Known issues and TODO

Carried over from imaging-metadata-consolidator (2026-09-29), which this repository replaces.

## Known issues

### Hub state

Published on the Hub (account j.j.m.defolter@amsterdamumc.nl): profile `imaging` 0.1, 0.2 and 1.0 (1.0 =
`profile/imaging.metaseed.yaml`, model 1.0.0, 2026-09-28; valid, no problems, no warnings); the account holds
no datasets. After a change to the model: regenerate (`python scripts/metaseed_generator.py`), run
metaseed's compatibility check against the last published version (see "Profile versions"), bump the
version, and push and publish again.

Generated, not yet published (2026-09-30): profile `imaging` 1.1 = `profile/imaging.metaseed.yaml`, model
1.1.0. It adds, compatibly with 1.0: `Instrument.CatalogNumber`, the detector extension fields
(DetectorExtension: Inserted, Enabled, ExposureTime, Binning, angles, CollectionAngleRange, EDS times,
rates and energies), ElectronOpticsSettings.Aperture (class ElectronAperture), Condenser1/2,
ScanSettings.LineInterlacing, the class QuantityRange, and "Oil" in the immersion enumeration. The
model's `id` and `imaging:` prefix moved with it from the consolidator's URL to this repository's
(https://github.com/NL-BioImaging/imaging-metadata-converter/models/imaging), as planned (user,
2026-09-29); in the profile that is only its description. To publish: import the profile on the Hub
(`metaseed spec import`), validate, save and publish it as 1.1.

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
- 1.0 -> 1.1: 162 changes, all compatible (required bump minor): 158 optional fields and 2 entities added
  (QuantityRange, ElectronAperture), the immersion enumeration widened by "Oil", and the description
  (model 1.1.0, the model's URL in this repository).

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
  Oil, ...), and is not guessed. The objective's own ImmersionType takes "Oil" since 2026-09-30: OME's value,
  added to ImmersionTypeList, not a guess at the kind of oil.
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
A and B pushed (d455b0f). C (user): C1 rules - Optics.Focus -> ElectronBeamSettings.Focus,
LastMeasuredScreenCurrent -> ElectronBeamSettings.Current (A), BinaryResult.Detector and
DetectorMetadata.DetectorName -> ScanSettings.Detector (the DetectorMetadata -> ActiveConfiguration rule
dropped), CustomProperties.StemMagnification.value -> Objective.Magnification, Sample.SampleId ->
Sample.ID, Detectors.*.id -> GenericDetector[].ID; C2 an ElectronAperture class (Name, Number, Type,
MechanismType, Diameter m, Enabled, PositionOffset Vector2D) as ElectronOpticsSettings.Aperture, the
text field Apertures kept (a range change would break 1.0). Not C3 (optics modes, lens intensities,
extractor voltage) nor C4 (scan interlacing, mains lock). "0"/"1" read into boolean fields too.
C done: the rule "Sample": "Sample" is gone (it moved TALOS's Sample record whole, so Sample.SampleId
could not reach Sample.ID; the "Sample.*" rule covers the record); "CustomProperties" became
"CustomProperties.*", the same paths, so a rule for one of its values applies. TALOS keys 15 -> 21%
(TALOS 2 11 -> 16%); the rest is mostly Velox's Operations/Features.
Of C3/C4, only what other examples share too (user): ScanSettings.LineInterlacing (TALOS, Phenom;
Cikteq's "0/1"/"Disable" do not fit an integer) and ElectronOpticsSettings.Condenser1/2 (TALOS C1/C2
lens intensity, Cikteq Condenser/Condenser2, each on the vendor's scale). The rest is TALOS only.
C pushed (11cf170). Cross-dataset round (user, 2026-09-30): TALOS's 15 core values get their SI units
(V, rad, m, s; all its own exact rules); LIF camera Gain/Brightness and Zeiss Image.Brightness/Contrast,
Scan.ShiftX/Y to the fields other vendors fill. Found: an implied unit was written for a value that is
no number (Cikteq's Scan.FrameTime "2min52s" shares TALOS's rule): units now qualify numbers only.
Analytics gain Kept (input values in the output) and Traced (output records naming input values),
100% for every example, tested. Not done, open for the user: Cikteq units (mm, deg; current and point
time unknown), SVS Left/Top in mm, immersion "Oil" in the enumeration.
Next (user): units where reasonably confident (Cikteq WD and stage mm, rotation/tilt deg; SVS Left/Top
mm; not Cikteq's current or point time), "Oil" in the immersion list, and the analysis as a reused
Python function returning the stats (coverage, kept, traced, ...), used by the script, page and tests.
Done: units Cikteq WD/stage mm, rotation/tilt deg, SVS Left/Top mm (Cikteq's current and point time
left without); "Oil" in ImmersionTypeList (from OME 2016-06; LIF confocal and ome-tiff now fit; the
profile's enum widened, compatible); model_fit.analyse(dataset, metadata) returns the stats as a dict,
analyse_metadata(metadata) for a source dict (converted and exported in memory), analyse_examples()
for all; render, the script and the tests use them.
1.1.0 released in the repository (f115688), not yet published on the Hub.
Coverage beyond this (user, 2026-09-30), in order: (1) in-scope coverage - a reviewed list of source
groups out of scope (processing history, file bookkeeping, software/UI state, patient/administrative),
the analytics adding coverage of in-scope values; (2) derived values - small combination extensions
(SizeT from BDV time points, durations such as Cikteq's "2min52s"); (3) rules implied by Bio-Formats'
readers (LIF, DICOM, SVS, FEI/TFS, Zeiss), proposed per format. Not: vendor values as MapAnnotation.
(1) done, list to be reviewed by the user: scripts/out_of_scope.json (processing, file, display, software
state, patient and administrative; fnmatch patterns over source keys; a covered key always counts; a
test fails on a pattern matching no key). In-scope key coverage: TALOS 61/66%, DICOM 47%, ome-tiff 49%,
LIF 7/13% (LIF's remaining settings are real gaps).
(2) done: combination formats count (platy SizeT), duration (Cikteq FrameTime "2min52s" -> 172 s) and
quantity (Cikteq HFW "21.12µm" -> 21.12 um); a one-part combination replaces its part's non-numeric text
a rule placed (the text back at its path). Cikteq also gets its acquisition date from User.TimeStamp
(unix) - so User.* is no longer all display, only BottomInfoShowEnable, DateTimeFmt, RulerText.
Cikteq 57 -> 60% keys (in scope 64%), platy 22 -> 30% (41%).
(3) Bio-Formats (develop, read 2026-09-30): no reader for Velox/EMD or Zeiss/Fibics; FEITiffReader maps
fewer FEI fields than ours; SVSReader/DicomReader/LIFReader imply three rules, taken (user): DICOM
ImagePositionPatient[0/1/2] -> Plane.PositionX/Y/Z (mm), SVS Exposure Time x Exposure Scale ->
Plane.ExposureTime (s; a new "product" combination, without Bio-Formats' x1000, which looks like a bug
there), LIF DetectorList.Detector[].IsActive -> GenericDetector.Enabled. Kept (user): SliceThickness ->
PhysicalSizeZ (Bio-Formats uses SpacingBetweenSlices, which no example has), Leica stage positions raw
(Bio-Formats applies FlipX/FlipY/SwapXY). Not taken: the stand model (LiMi types the stand by
IsInverseMicroscopeModel, no rule picks a class by value), channel names/dyes (Bio-Formats joins
active detectors to the last SizeC, which the metadata lacks), AOTF lines (Bio-Formats skips them at
this level).
Done: the three rules; the exporter reads an integer flag 0/1 into a boolean field (Leica's IsActive),
and keeps a source value whose type the stored one changes (0 -> False compare equal) in SourceValue -
the no-data-loss test caught it. DICOM 21 -> 22% (in scope 49%), SVS 42 -> 50% (68%), LIF confocal 11%
(14%). A SpacingBetweenSlices rule waits for an example stating it.
Status: (1)+(2)+(3) done, not committed.

## The model and the pipeline

See docs/model.md and docs/maintaining.md for the full account.
- Model: `src/imaging_metadata_converter/models/imaging.yaml` (LinkML, style of the OME LinkML schema
  https://github.com/gouttegd/yamf-playground/blob/main/linkml/ome/ome.yaml, LiMi's PascalCase names),
  importing `imaging_units.yaml` (units enums, with aliases: LiMi's unit names and an ASCII form such as
  "um"), `imaging_provenance.yaml` (Property, SourceFile, SourceMapping) and `imaging_extension.yaml` (what
  the source files hold beyond LiMi, mostly EM; mixins OMEExtension, InstrumentExtension, ... used by the
  model's classes; shared Quantity {Value, Unit}, QuantityRange, Vector2D, StagePosition). Edited by hand;
  version 1.1.0.
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

## How new model fields are decided

The criteria the extension (imaging_extension.yaml) grew by, 2026-09-30, while raising the examples'
coverage (user: "match values from source formats to the extended model, extending the model following its
structure, for common fields in the source data"). A value is only a candidate if the analytics
(scripts/model_fit.py) list it as not covered; each step is tried in order, and the first that applies wins.

1. A rule to a field the model has, before any new field. The model is LiMi (itself OME 2016-06) plus the
   extension; a vendor name that means an existing field gets a rule, whatever it is called: DICOM
   ManufacturerModelName -> Instrument.Model, Leica ObjectiveNumber -> Objective.CatalogNumber, TALOS
   LastMeasuredScreenCurrent -> ElectronBeamSettings.Current. A value that already reaches its field by the
   mapper's automatic match needs no rule (the analytics list those to check: DICOM Rows matched Plate.Rows
   automatically, so a rule sends it to Pixels.SizeY). A mapper feature comes before a model field when only
   the source's form is in the way (a list item, PixelSpacing[0]; a spaced string, BDV "1100 1100 1150"; a
   renamed field in a collapsed record, Detectors.*.DetectorName; a unit left unstated).
2. Only acquisition metadata: what the instrument is (hardware: Instrument and its components) or how it was
   set for this image (settings: Image and its settings classes). Not processing history (Velox's
   Operations/Features), file bookkeeping (Core.MetadataSchemaVersion, GUIDs), UI or software state (LIF
   triggers, autofocus, filter-wheel positions), or patient and administrative data (DICOM). Those stay
   Properties, kept and traced.
3. Common to the data: a new field is added when more than one source (vendor or file) states it, or when it
   is a core parameter of its modality that LiMi has no place for (the EM detector's collection angles, live
   and real time, spectrum energies). A value only one vendor writes, and specific to that vendor's design,
   stays a Property: TALOS's lens intensities, probe and illumination modes, EFTEM and mains lock were left
   out, while its C1/C2 intensities became Condenser1/2 because Cikteq writes Condenser/Condenser2 too, and
   LineInterlacing was added because TALOS and Phenom both write it.
4. Clear meaning: the source's meaning has to be certain enough to state in the field's description. Where
   it is not, the value stays a Property rather than a guess: LIF's spectral bands as the image's channels
   (band i = channel i unconfirmed), ScanSpeed (LiMi's ScanningFrequency is a percentage), a white-light
   laser's wavelength 0 is placed only because the file says 0. Values that would need translating (Argon
   -> laser type Gas, TL-BF -> Brightfield) are not translated.
5. The model's structure, not the vendor's:
   - on the class that owns the concept, following LiMi's split of hardware and settings (as Objective and
     ObjectiveSettings): an aperture's diameter and position as set for the image are ElectronOpticsSettings.
     Aperture, a detector's own values are the GenericDetector's (one per detector, not a Configuration
     record);
   - on LiMi's classes through the extension's mixins (InstrumentExtension, DetectorExtension, ...), new
     groups as classes of their own (ElectronAperture);
   - LiMi's names and terms first, then OME's: Instrument.CatalogNumber, LiMi's "Catalog, Part or Serial
     Number", not a SerialNumber LiMi does not have; "Oil" from OME's immersion list, not a new term;
   - the shared classes for values with a unit or several parts: Quantity {Value, Unit} with the unit as
     free text, QuantityRange {Begin, End, Unit}, Vector2D {X, Y}; typed ranges (float, integer, boolean)
     wherever the values are numbers or flags.
6. Additive only: new optional fields, classes and enumeration values, never a removal or a changed range,
   so the profile stays compatible with the published version (metaseed's compare_specs finds every change
   since 1.0 compatible). ElectronOpticsSettings.Apertures (text) stays beside the new Aperture records, and
   Detector.Configuration stays although no example uses it now.
7. A unit the source leaves out is stated only with reasonable confidence: the vendor's convention is known
   and the values agree with it and with each other (TALOS's SI units: 4 nm pixels x 2048 = the 8.19 um
   field of view, 2048 lines x 0.207 s = the frame time; Cikteq's working distance in mm; Aperio's slide
   position in mm, within a 75 x 25 mm slide). Cikteq's beam current and point time have no unit, as pA/nA and
   us/ns cannot be told apart. An implied unit qualifies numbers only.
8. Checked as a whole: a synthetic test for every new mapper or exporter code path before real data; then
   the profile, output/ and export/ regenerated, the no-data-loss and metaseed validation tests passing, and
   the analytics showing the keys moving to covered with Kept and Traced still at 100%. Before a rule for a
   shared or short key, every example holding that key is checked, not only the ones where it is placed
   (Cikteq's "2min52s" under TALOS's Scan.FrameTime rule showed why).

## TODO

- [ ] Light-source role, when a source holds light sources (none does yet, so rules setting it would have
      nothing to act on or be tested with; user, 2026-09-28): rules for Transmitted/Fluorescence light
      sources should set `LightSource.Role`.
