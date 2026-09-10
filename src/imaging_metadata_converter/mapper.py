"""Map per-source acquisition metadata onto the consolidated schema.

Uses the field mappings in data/mappings.json to translate vendor-specific
metadata trees into the consolidated model defined by
data/schema.extended.json. This module works purely with in-memory dicts:
custom metadata dict in, common metadata dict out.

Fields with no entry in mappings.json are matched against the schema itself
as a fallback, since some sources (e.g. OME-derived metadata) already use
field names that match the schema, just without a vendor-specific prefix.
"""

import json
from fnmatch import fnmatchcase
from importlib.resources import files


DEFAULT_SCHEMA_FILE = files(__package__).joinpath('data/schema.extended.json')
DEFAULT_MAPPINGS_FILE = files(__package__).joinpath('data/mappings.json')


class AcquisitionMetadataMapper:
    """Maps vendor-specific acquisition metadata onto the consolidated schema.

    Loads the packaged schema.extended.json and mappings.json once (or the
    files given as `schema_file`/`mappings_file`), then converts one or
    more metadata dicts using `convert_metadata`. Resolution for each field
    happens in two steps: first the explicit mappings.json rules (exact or
    "Prefix.*" wildcard), then, for anything left unmapped, a fallback match
    against the schema's own field names (e.g. standard OME metadata, which
    the schema is based on, already lines up with it directly). Fields that
    match neither step are kept at their original path so no data is lost.
    """

    def __init__(self, schema_file=DEFAULT_SCHEMA_FILE, mappings_file=DEFAULT_MAPPINGS_FILE):
        self.schema = self._load_json(schema_file)
        self.mappings = self._load_json(mappings_file)
        self._schema_index = self._build_schema_index(self.schema)

    @staticmethod
    def _load_json(file_path):
        """Load JSON from a path, or from a packaged resource (Traversable)."""
        if hasattr(file_path, 'read_text'):
            return json.loads(file_path.read_text(encoding='utf-8'))
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)

    @classmethod
    def _schema_leaf_paths(cls, schema, path=''):
        """Yield the dotted path of every leaf (non-dict) field in `schema`."""
        for key, value in schema.items():
            current = f'{path}.{key}' if path else key
            if isinstance(value, dict):
                yield from cls._schema_leaf_paths(value, current)
            else:
                yield current

    @classmethod
    def _build_schema_index(cls, schema):
        """Index every schema leaf path by each of its lowercase dotted suffixes.

        This lets an unmapped source path like "Pixels.SizeX" find the schema
        leaf "Image.Pixels.SizeX" without a vendor prefix. A suffix shared by
        more than one leaf (e.g. the many "Name"/"ID"/"Value" fields) is
        ambiguous and dropped, so it is never guessed at.
        """
        index = {}
        ambiguous = set()
        for full_path in cls._schema_leaf_paths(schema):
            components = full_path.split('.')
            for start in range(len(components)):
                suffix = tuple(part.lower() for part in components[start:])
                if suffix in index and index[suffix] != full_path:
                    ambiguous.add(suffix)
                else:
                    index[suffix] = full_path
        for suffix in ambiguous:
            del index[suffix]
        return index

    def _resolve_schema_path(self, source_path):
        """Resolve a dotted source path via the schema fallback, or None."""
        components = tuple(part.lower() for part in source_path.split('.'))
        return self._schema_index.get(components)

    def _resolve_wildcard_path(self, source_path, min_rule_segments=0):
        """Resolve a dotted source path via a "*"-containing mapping entry, or None.

        A pattern ending in ".*" remaps a whole subtree: the matched prefix
        is replaced by the target namespace and the remainder of the path is
        kept, so nested fields under the subtree keep their relative
        structure (e.g. "Beam.*" -> "ElectronBeam" turns "Beam.Focus" into
        "ElectronBeam.Focus").

        Any other "*"-containing pattern (e.g. one wildcarding a single,
        variable path segment such as "Annotation:...:Image:*") is treated
        as a whole-path match instead: on a match the target is the bare
        namespace with no remainder appended, since the varying segment
        (an index, a generated ID, ...) carries no information worth
        preserving in the consolidated schema. A "Target[]" namespace is
        never valid here - it only has meaning for a dict, never a plain
        leaf value (see `_resolve_whole_segment_wildcard_path`).

        `min_rule_segments` (see `_apply_mappings`) excludes any pattern
        shorter than it: once a "Target[]" match has claimed a dict as its
        own list item, a *shallower* pre-existing subtree rule must not
        keep reaching into that item's own fields just because their full
        absolute path still happens to start with the shallower rule's
        prefix. A whole-path match additionally requires exactly as many
        segments as `source_path` itself - `fnmatchcase` alone would also
        match any *deeper* descendant path, since "*" is unanchored and
        happily eats further dots too.
        """
        source_segments = source_path.split('.')
        for pattern, namespace in self.mappings.items():
            has_wildcard = '*' in pattern
            pattern_segments = pattern.split('.') if has_wildcard else None
            is_remainder_style = has_wildcard and pattern.endswith('.*')
            if (
                is_remainder_style
                and not namespace.endswith('[]')
                and len(pattern_segments) >= min_rule_segments
                and fnmatchcase(source_path, pattern)
            ):
                prefix = pattern[:-2]
                remainder = source_path[len(prefix) + 1:]
                return f'{namespace}.{remainder}' if remainder else namespace
            if (
                has_wildcard
                and not is_remainder_style
                and len(pattern_segments) == len(source_segments)
                and len(pattern_segments) >= min_rule_segments
                and fnmatchcase(source_path, pattern)
            ):
                return namespace
        return None

    def _resolve_whole_segment_wildcard_path(self, source_path, min_rule_segments=0):
        """Resolve a dict's own path via a whole-segment wildcard entry, or (None, False).

        Returns a `(namespace, is_child_collapse)` pair: `is_child_collapse`
        is True only for a "Prefix.*" + "Target[]" match, where `source_path`
        is one *child* of the dict the pattern names, and its own key (e.g.
        "QBSD" in a raw "Detectors.QBSD" reading) is meaningful sibling-
        distinguishing information the caller should preserve - unlike a
        plain "Prefix" whole-path match, where `source_path` *is* the
        pattern's own match and its key is exactly the noise the pattern
        was written to discard (see `_apply_mappings`).

        A pattern that does *not* end in ".*" is a whole-path match: a
        ".*" pattern describes a subtree to expand field-by-field during
        recursion, so it must never collapse an intermediate dict early
        just because a *shallower* "Prefix.*" rule also happens to match
        that dict's own path — a more specific "Prefix.Sub.*" rule for one
        of its children would otherwise never get the chance to apply (see
        `_apply_mappings`). A pattern wildcarding a whole, variable path
        segment instead (e.g. an index or generated ID) has no such
        subtree semantics, so a match here collapses the entire dict as
        one opaque unit under the target namespace (or, with a "Target[]"
        target, as one item in a list there - see `_apply_mappings`).

        The one exception is a ".*" pattern whose target *does* end in
        "[]": "Prefix.*" + "Target[]" means every immediate child of the
        dict at "Prefix" - regardless of its own key name (e.g. numbered
        "Detector-0"/"Detector-1" instances) - collapses into its own item
        in a list at "Target", rather than the vendor's per-instance key
        naming leaking into the output. This is the one place a ".*"
        pattern is allowed to collapse rather than expand, since "[]"
        semantics (independently mapping each match as its own list item)
        replace the remainder-preserving subtree-rename semantics that
        make plain ".*" unsafe to collapse with here.

        `min_rule_segments` (see `_apply_mappings`) excludes any pattern
        shorter than it, for the same reason `_resolve_wildcard_path`
        does. Either way, a match also requires equal segment count, not
        just `fnmatchcase` - otherwise the unanchored "*" would also match
        a *deeper* descendant dict's path, not just the dict (or dict
        child) this pattern was written for.
        """
        source_segment_count = len(source_path.split('.'))
        for pattern, namespace in self.mappings.items():
            has_wildcard = '*' in pattern
            pattern_segments = pattern.split('.') if has_wildcard else None
            is_child_collapse_style = (
                has_wildcard and pattern.endswith('.*') and namespace.endswith('[]')
            )
            is_whole_path_style = has_wildcard and not pattern.endswith('.*')
            if (
                (is_child_collapse_style or is_whole_path_style)
                and len(pattern_segments) == source_segment_count
                and len(pattern_segments) >= min_rule_segments
                and fnmatchcase(source_path, pattern)
            ):
                return namespace, is_child_collapse_style
        return None, False

    def _resolve_target_path(self, source_path, min_rule_segments=0):
        """Resolve a dotted source path to a dotted target path, or None.

        Tries mappings.json first: exact entries rename a single field, and
        wildcard entries remap a whole subtree or a single variable path
        segment (see `_resolve_wildcard_path`). Only when no mappings.json
        rule applies does this fall back to matching the path directly
        against the schema.
        """
        target = resolve_exact_path(source_path, self.mappings)
        if target is not None:
            return target

        target = self._resolve_wildcard_path(source_path, min_rule_segments)
        if target is not None:
            return target

        return self._resolve_schema_path(source_path)

    def _apply_mappings(self, metadata, result=None, path='', rule_path=None, min_rule_segments=0):
        """Map metadata onto the consolidated schema.

        Recurses into nested dictionaries, extending the dotted path as it
        goes, and writes every resolved field directly into the shared
        `result` dict. A dict is only moved as a whole (without recursing
        into it) when its own path has an exact or whole-segment wildcard
        mapping entry, so that a more specific "Prefix.Sub.*" rule for one
        of its children still gets the chance to apply, and so a shallower
        "Prefix.*" subtree rule never fires early on an intermediate node.
        A "Target[]" mapping entry (trailing "[]") treats the dict as one
        item of a list rather than moving it as an opaque unit: it is
        recursively mapped through this same method - using its own rule
        path, so every one of its fields still resolves via the normal
        rules - and the *mapped* result is appended to a plain list at
        "Target". Use this for a source key whose own name embeds an
        instance index (e.g. "Image:0", "Image:1"): the index becomes list
        position rather than part of an output key, and a second sibling
        instance appends a second list item rather than silently clobbering
        the first (which a plain "Target" collapse - no trailing "[]" -
        would do, since it always overwrites).

        A genuine list of dicts (e.g. a per-channel or per-detector record
        list already shaped as a JSON array) is treated the same way as a
        "[]" match: an exact/whole-segment match on the list's own path
        still moves it wholesale, unit, opaque; otherwise every dict item is
        independently mapped and the results collected into a list at the
        list's own resolved target. A list with no dict items (a plain
        value list) is always resolved and placed as a unit, like a scalar.

        `path` tracks where a field lands within the *current* result dict
        (it resets to '' for each list item / "[]" match, since each gets
        its own independent dict); `rule_path` tracks the true absolute
        path from the original root, which is what mapping rules and the
        schema fallback are always matched against, list nesting included.
        The two are identical outside of list items, which is the only
        place they diverge.

        `min_rule_segments` is the floor `rule_path` recursion has already
        crossed via a "[]" match: it only ever rises, at a "[]" boundary,
        to that boundary's own segment count, and is otherwise inherited
        unchanged - plain (non-"[]") recursion never resets it. This stops
        a *shallower* pre-existing rule (written before this "[]" entry
        existed, for the wider subtree the "[]" match now claims one item
        of) from reaching into that item's own fields, since their full
        absolute path still starts with the shallower rule's prefix (see
        `_resolve_wildcard_path`).

        Fields with no matching rule are kept at their original path so no
        data is silently dropped.
        """
        if result is None:
            result = {}
        if rule_path is None:
            rule_path = path
        for key, value in metadata.items():
            source_path = f'{path}.{key}' if path else str(key)
            rule_source_path = f'{rule_path}.{key}' if rule_path else str(key)
            if isinstance(value, dict):
                target_path = resolve_exact_path(rule_source_path, self.mappings)
                is_child_collapse = False
                if target_path is None:
                    target_path, is_child_collapse = self._resolve_whole_segment_wildcard_path(
                        rule_source_path, min_rule_segments)
                if target_path is not None and target_path.endswith('[]'):
                    item_min_segments = max(min_rule_segments, len(rule_source_path.split('.')))
                    mapped_item = self._apply_mappings(
                        value, rule_path=rule_source_path, min_rule_segments=item_min_segments)
                    if is_child_collapse and not str(key).isdigit():
                        label_key = 'id' if 'id' not in mapped_item and 'ID' not in mapped_item else None
                        if label_key is not None:
                            mapped_item[label_key] = key
                    append_nested_list_value(result, target_path[:-2], mapped_item)
                elif target_path is not None:
                    set_nested_value(result, target_path, value)
                else:
                    self._apply_mappings(value, result, source_path, rule_source_path, min_rule_segments)
            elif isinstance(value, list) and any(isinstance(item, dict) for item in value):
                target_path = resolve_exact_path(rule_source_path, self.mappings)
                if target_path is None:
                    target_path, _ = self._resolve_whole_segment_wildcard_path(
                        rule_source_path, min_rule_segments)
                if target_path is not None:
                    set_nested_value(result, target_path, value)
                else:
                    item_min_segments = max(min_rule_segments, len(rule_source_path.split('.')))
                    mapped_items = [
                        self._apply_mappings(
                            item, rule_path=rule_source_path, min_rule_segments=item_min_segments)
                        if isinstance(item, dict) else item
                        for item in value
                    ]
                    leaf_target = self._resolve_target_path(rule_source_path, min_rule_segments)
                    set_nested_value(result, leaf_target or source_path, mapped_items)
            else:
                target_path = self._resolve_target_path(rule_source_path, min_rule_segments)
                set_nested_value(result, target_path or source_path, value)
        return result

    def convert_metadata(self, metadata):
        """Map a single in-memory metadata dict onto the consolidated schema.

        Returns the converted dict.
        """
        if not isinstance(metadata, dict):
            raise TypeError('metadata must be a dict')

        return self._apply_mappings(metadata)


def resolve_exact_path(source_path, mappings):
    """Resolve a dotted source path via an exact mapping entry, or None."""
    target = mappings.get(source_path)
    if target is not None:
        return target

    # TALOS-style processing operations can embed a second copy of
    # acquisition metadata below a generated operation UUID. Reuse the
    # canonical mapping for that suffix instead of adding another branch.
    metadata_marker = '.metadata.'
    if metadata_marker in source_path:
        embedded_path = source_path.split(metadata_marker, 1)[1]
        return resolve_exact_path(embedded_path, mappings)
    return None


def set_nested_value(target, dotted_path, value):
    keys = dotted_path.split('.')
    node = target
    for key in keys[:-1]:
        child = node.get(key)
        if not isinstance(child, dict):
            child = {}
            node[key] = child
        node = child
    node[keys[-1]] = value


def append_nested_list_value(target, dotted_path, value):
    """Append `value` to the list at `dotted_path`, creating it if absent.

    Used for a "Target[]" mapping entry: a source key whose *name* embeds an
    instance index (e.g. "Image:0", "Detector-3") collapses into a plain
    list at "Target" instead of baking that index into an output key, so a
    second instance (e.g. "Image:1") appends a second list item rather than
    colliding with (and silently overwriting) the first.
    """
    keys = dotted_path.split('.')
    node = target
    for key in keys[:-1]:
        child = node.get(key)
        if not isinstance(child, dict):
            child = {}
            node[key] = child
        node = child
    existing = node.get(keys[-1])
    if not isinstance(existing, list):
        existing = []
        node[keys[-1]] = existing
    existing.append(value)
