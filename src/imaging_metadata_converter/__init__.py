"""Convert custom (vendor-specific) acquisition metadata to common metadata.

Dict in, dict out:

    from imaging_metadata_converter import convert_metadata

    common = convert_metadata({'Make': 'Acme', 'Model': 'Widget-1000'})
"""

from .AcquisitionMetadataMapper import (
    DEFAULT_COMBINATIONS_FILE,
    DEFAULT_MAPPINGS_FILE,
    DEFAULT_SCHEMA_FILE,
    SOURCE_MAP_KEY,
    AcquisitionMetadataMapper,
)
from .model_files import DEFAULT_MODEL_FILE, DEFAULT_MODEL_INDEX_FILE

try:
    from .ModelPaths import ModelPaths
except ImportError as error:
    # ModelPaths reads the LinkML model itself (the [model] extra); mapping works without it
    if not (error.name or '').startswith('linkml'):
        raise

__all__ = [
    'AcquisitionMetadataMapper',
    'DEFAULT_COMBINATIONS_FILE',
    'DEFAULT_MAPPINGS_FILE',
    'DEFAULT_MODEL_FILE',
    'DEFAULT_MODEL_INDEX_FILE',
    'DEFAULT_SCHEMA_FILE',
    'SOURCE_MAP_KEY',
    'convert_metadata',
] + (['ModelPaths'] if 'ModelPaths' in globals() else [])

__version__ = '2.1.0'

_default_mapper = None


def __getattr__(name):
    if name == 'ModelPaths':
        raise ImportError('ModelPaths reads the LinkML model: install imaging-metadata-converter[model]')
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


def _get_default_mapper():
    """Return the shared mapper using the packaged model and mappings."""
    global _default_mapper
    if _default_mapper is None:
        _default_mapper = AcquisitionMetadataMapper()
    return _default_mapper


def convert_metadata(metadata):
    """Map a custom metadata dict onto the common model and return the result."""
    return _get_default_mapper().convert_metadata(metadata)
