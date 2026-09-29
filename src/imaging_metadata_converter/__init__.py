"""Convert custom (vendor-specific) acquisition metadata to common metadata.

Dict in, dict out:

    from imaging_metadata_converter import convert_metadata

    common = convert_metadata({'Make': 'Acme', 'Model': 'Widget-1000'})
"""

from .AcquisitionMetadataMapper import (
    DEFAULT_MAPPINGS_FILE,
    DEFAULT_SCHEMA_FILE,
    AcquisitionMetadataMapper,
    flatten_dict,
)

__all__ = [
    'AcquisitionMetadataMapper',
    'DEFAULT_MAPPINGS_FILE',
    'DEFAULT_SCHEMA_FILE',
    'convert_metadata',
    'flatten_dict',
]

__version__ = '0.1.0'

_default_mapper = None


def _get_default_mapper():
    """Return the shared mapper using the packaged schema and mappings."""
    global _default_mapper
    if _default_mapper is None:
        _default_mapper = AcquisitionMetadataMapper()
    return _default_mapper


def convert_metadata(metadata):
    """Map a custom metadata dict onto the common schema and return the result."""
    return _get_default_mapper().convert_metadata(metadata)
