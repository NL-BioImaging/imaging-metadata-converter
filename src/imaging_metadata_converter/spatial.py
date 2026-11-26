"""Where an image is in space, from metadata mapped onto the model: its pixel size and position in µm, and its
rotation and the stage's in degrees.

    from imaging_metadata_converter import convert_metadata
    from imaging_metadata_converter.spatial import spatial_metadata

    spatial = spatial_metadata(convert_metadata(vendor_metadata))
    # {'pixel_size': {'x': 0.01, 'y': 0.01}, 'position': {'x': 1000.0, 'y': 2000.0},
    #  'rotation': 28.64788975654116, 'stage_rotation': 57.29577951308232}

The rotation is the image's, as written (only converted to degrees): the scan's turn against the stage axes, which
places the image beside others by their stage positions. The stage rotation turns the sample instead, and leaves
the stage positions of one acquisition alone. A value without a unit is taken in µm or degrees; a source whose
unit differs, without saying so, has it stated by its mapping rule ({"target": ..., "unit": "rad"}).
"""

from .units import normalise

AXES = ('x', 'y', 'z')
# where each value is in the model, in order of preference: (class path, field name pattern)
PIXEL_SIZE_FIELDS = (('Pixels', 'PhysicalSize{axis}'),)
POSITION_FIELDS = (('Plane', 'Position{axis}'), ('Image.StageLabel', '{axis}'))
ROTATION_FIELDS = (('Image.BeamScanSettings', 'Rotation'), ('Image.SlideScanSettings', 'Rotation'))
STAGE_ROTATION_FIELDS = (('Plane', 'Rotation'), ('Plane.RawStage', 'Rotation'))


def spatial_metadata(mapped):
    """{'pixel_size': {axis: µm}, 'position': {axis: µm}, 'rotation': degrees or None,
    'stage_rotation': degrees or None} from metadata mapped onto the model (convert_metadata's result)."""
    return {
        'pixel_size': _axes(mapped, PIXEL_SIZE_FIELDS, 'µm'),
        'position': _axes(mapped, POSITION_FIELDS, 'µm'),
        'rotation': _first_quantity(mapped, ROTATION_FIELDS, None, 'deg'),
        'stage_rotation': _first_quantity(mapped, STAGE_ROTATION_FIELDS, None, 'deg'),
    }


def _axes(mapped, fields, unit):
    values = {axis: _first_quantity(mapped, fields, axis.upper(), unit) for axis in AXES}
    return {axis: value for axis, value in values.items() if value is not None}


def _first_quantity(mapped, fields, axis, unit):
    """The first of these fields with a value, in `unit`; a value without a unit is taken in `unit`."""
    for class_path, pattern in fields:
        holder = _at(mapped, class_path)
        name = pattern.format(axis=axis)
        value = normalise(holder[name], holder.get(f'{name}Unit', unit), unit) if name in holder else None
        if value is not None:
            return value
    return None


def _at(mapped, class_path):
    """The dict at a dotted path, the first item where the model holds a list (Plane, per plane); {} if none."""
    holder = mapped
    for name in class_path.split('.'):
        holder = holder.get(name, {}) if isinstance(holder, dict) else {}
        if isinstance(holder, list):
            holder = holder[0] if holder else {}
    return holder if isinstance(holder, dict) else {}
