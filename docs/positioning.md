# Positioning

Where an image is in space: its pixel size, its stage position, and its rotation. Readers (biomero-converter,
napari-meta-tiff) turn their file into a metadata dict; the mapping puts these values in the model's fields, and
`spatial_metadata` returns them normalised:

```python
from imaging_metadata_converter import convert_metadata
from imaging_metadata_converter.spatial import spatial_metadata

spatial_metadata(convert_metadata(vendor_metadata), shape={'x': 1024, 'y': 768})
# {'pixel_size': {'x': ..., 'y': ...}, 'position': {...}, 'rotation': ..., 'stage_rotation': ...}
```

Every vendor's conversion is a rule (`mappings/mappings.json`) or a combination (`mappings/combinations.json`);
readers convert nothing themselves.

## Conventions

- **Units**: pixel size and position in µm, rotations in degrees, converted by the `conversion_factor` of each unit
  in `models/imaging_units.yaml` (`units.normalise`). A length without a unit is in µm, an angle in degrees; a
  vendor whose unit differs without saying so has it stated by its rule (`"unit": "m"`).
- **Frame**: positions are in the image's frame, x to the right and y down, so tiles place next to each other. A
  stage axis pointing the other way is inverted by its rule (`"factor": -1`, written −Y below).
- **Rotation**: the image's (scan) rotation turns the image against the stage axes, about its origin, before it is
  placed at its position. A viewer turns the y-x plane as napari's `rotate` does; OME-Zarr 0.6 holds it as a
  rotation between the scale and the translation. The stage rotation turns the sample instead, and places nothing.
- **No swapping**: x stays x and y stays y. An image turned against its stage is a rotation, not an exchange of x
  and y, so its positions remain the stage's own.
- **Stated first**: a value a format implies but never writes (a `constant` combination) is written only where the
  source states none.

## By source

| Source (header) | Pixel size | Position | Image rotation | Stage rotation | Conversion |
|---|---|---|---|---|---|
| Ciqtek (`FEI_HELIOS` tag) | `Beam.HFW` / pixels | `Stage.StagePosX/Y/Z` | `Beam.ElectricRotate` | `Stage.StagePosR` | mm; −Y; deg |
| FEI / TFS Helios | `Scan.PixelWidth/Height` | `Stage.StageX/Y/Z` | `Beam.ScanRotation`, `Scan.ScanRotation` | `Stage.StageR` | m; rad |
| FEI Titan / Talos (`FEI_TITAN`) | `BinaryResult.PixelSize.X/Y` | `StageSettings.StagePosition.X/Y/Z` | 90° (`constant`) | | m; −Y; 90° |
| Fibics / Zeiss Atlas | `Scan.FOV_X/Y` / pixels | `Stage.X/Y/Z` (value, units) | `Scan.ScanRot` | `Stage.Rot`, `Stage.R` | −Y |
| TFS Phenom | `pixelWidth` (value, unit) | `samplePosition.x/y` | `acquisition.scan.rotation` | | m; deg |
| OME(-TIFF) | `Pixels.PhysicalSize*` | `Plane.Position*` | | | as stated |

A pixel size given as a field of view is divided by the pixels across (`/ pixels`); a field of view for one axis
means square pixels. Readers add what only their file holds: for a TIFF without a stated pixel size, ImageJ's or
the baseline resolution.

Checked against tile grids, whose tiles must line up with their neighbours' content: Fibics (Zeiss Supra,
UMCG mito), FEI Titan (Talos) and Ciqtek (a row of SEM4000X Automap tiles). The others are checked on single files only, so their y direction is not
confirmed by a grid yet. FEI Titan's 90° is not in its header: its tiles' content is turned that way against
their stage steps, which a rotation with −Y explains without exchanging x and y.

## In the code

1. **File to metadata dict**: each reader (biomero-converter, napari-meta-tiff `metadata.py`).
2. **Mapping**: `AcquisitionMetadataMapper`: a rule's `unit` and `factor`, a combination's `constant`.
3. **Spatial values**: `spatial.py` (which model fields, in which order; the field of view over the pixels) and
   `units.py` (`normalise`).
4. **Placing**: the readers. biomero-converter's `ImageSource.get_spatial_metadata` and its OME-Zarr writer (scale,
   translation, and in 0.6 the rotation); napari-meta-tiff's reader (a layer's `scale`, `translate`, `rotate`).

To add a vendor, add its rules (and a small test in `tests/test_spatial_vendors.py`); to check a tile grid, compare
neighbouring tiles' overlap: their content must match where their positions put them.
