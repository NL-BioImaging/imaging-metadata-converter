"""Map per-source acquisition metadata onto the imaging model.

Uses the field mappings in mappings/mappings.json to translate vendor-
specific metadata trees into the imaging model (models/imaging.yaml, see
ModelPaths for the paths it uses). This module works purely with in-memory
dicts.

Fields with no entry in mappings.json are matched against the schema itself
as a fallback, since some sources (e.g. OME-derived metadata) already use
field names that match the schema, just without a vendor-specific prefix.
"""

import json
import math
import os.path
import re
from datetime import date, datetime, time, timedelta, timezone
from fnmatch import fnmatchcase

from .ModelPaths import DEFAULT_MODEL_FILE, ModelPaths


DEFAULT_SCHEMA_FILE = DEFAULT_MODEL_FILE
DEFAULT_MAPPINGS_FILE = os.path.join(os.path.dirname(__file__), 'mappings', 'mappings.json')
DEFAULT_COMBINATIONS_FILE = os.path.join(os.path.dirname(__file__), 'mappings', 'combinations.json')
SOURCE_MAP_KEY = 'SourceMap'
# a count of time points says how many there are, not which: its parts hold more than its value
# A Leica (LAS X) sequential confocal scan, as biomero-converter's LeicaSource passes it: each sequence names its
# active detectors and laser lines, and the spectral bands are stated once, numbered by detector (see
# `_map_leica_sequential_channels`)
LEICA_SETTINGS = 'HardwareSetting'
LEICA_SEQUENCES = 'LDM_Block_Sequential.LDM_Block_Sequential_List.ConfocalSettingDefinition'
LEICA_BANDS = 'ConfocalSettingDefinition.Spectro.MultiBand'
LEICA_LASERS = 'ConfocalSettingDefinition.LaserArray.Laser'
LEICA_WIDEFIELD_CHANNELS = 'CameraSettingDefinition.WideFieldChannelConfigurator.WideFieldChannelInfo'
LEICA_DETECTORS = 'ConfocalSettingDefinition.DetectorList.Detector'
LEICA_SEQUENTIAL_MASTER = 'LDM_Block_Sequential_Master'
# the detector types LAS X names that LiMi has a class for; any other is a GenericDetector
LEICA_DETECTOR_CLASSES = {'PMT': 'PhotoMultiplierTube', 'HyD': 'HybridPhotoDetector'}
# the detector a Velox (TALOS) image was taken with, by its name
VELOX_IMAGE_DETECTOR = 'DetectorMetadata.DetectorName'
# a detector's own values that are its settings for the image, by the source's name for them in any case
DETECTOR_SETTING_FIELDS = {'gain': 'AnalogGain', 'offset': 'Offset'}
# Windows FILETIME, as Leica's LMD software writes its acquisition time: 100 ns steps since 1601
FILETIME_EPOCH = datetime(1601, 1, 1)
FORMATS_KEEPING_PARTS = ('count',)
# a time written as text, in hours, minutes and seconds ("2min52s"), and a number written with its unit ("21.12µm")
DURATION = re.compile(r'(?:(\d+(?:\.\d+)?)\s*h)?\s*(?:(\d+(?:\.\d+)?)\s*min)?\s*(?:(\d+(?:\.\d+)?)\s*s)?')
QUANTITY = re.compile(r'([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*([^\d\s].*)')


class AcquisitionMetadataMapper:
    """Maps vendor-specific acquisition metadata onto the imaging model.

    Loads the model's paths and mappings.json once, then converts one or
    more metadata dicts using `convert_metadata`. Resolution for each field
    happens in two steps: first the explicit mappings.json rules (exact or
    "Prefix.*" wildcard), then, for anything left unmapped, a fallback match
    against the schema's own field names (e.g. standard OME metadata, which
    the schema is based on, already lines up with it directly). Fields that
    match neither step are kept at their original path so no data is lost.
    """

    def __init__(self, schema_file=DEFAULT_SCHEMA_FILE, mappings_file=DEFAULT_MAPPINGS_FILE,
                 combinations_file=DEFAULT_COMBINATIONS_FILE):
        # a LinkML model, or (for tests) a JSON tree of the same {name: subtree or type} shape
        model = ModelPaths(schema_file) if schema_file.endswith(('.yaml', '.yml')) else None
        self.schema = model.tree() if model else self._load_json(schema_file)
        self._root = model.root if model else None
        # each concrete detector class, with the class of its settings for an image (LiMi's Model_Settings)
        self._detector_settings = {name: model.classes[name].annotations['Model_Settings'].value
                                   for name in model.view.class_descendants('Detector')
                                   if not model.classes[name].abstract} if model else {}
        rules = self._load_json(mappings_file)
        # a rule may state the unit its source implies but never writes: {"target": ..., "unit": "mm"}
        self.mappings = {source: rule['target'] if isinstance(rule, dict) else rule for source, rule in rules.items()}
        self.implied_units = {source: rule['unit'] for source, rule in rules.items() if isinstance(rule, dict)}
        # a rule naming a field of each item a "Prefix.*": "Target[]" rule collapses ("Detectors.*.DetectorName":
        # "GenericDetector[].Name") renames inside those items only, so it takes no part in resolving other paths
        self.item_fields = {source: target for source, target in self.mappings.items()
                            if isinstance(target, str) and '[].' in target}
        for source in self.item_fields:
            del self.mappings[source]
        # only these take part in a wildcard search, and a path resolves the same way every time: a list's items
        # (Leica's thousands of tiles) share their paths
        self._wildcard_rules = [(pattern, namespace) for pattern, namespace in self.mappings.items() if '*' in pattern]
        self._resolved = {}
        self.combinations = self._load_json(combinations_file) if os.path.exists(combinations_file) else []
        self._schema_index = self._build_schema_index(self.schema)
        # "Detector.Name" in a source still names a field, of the model's default detector (GenericDetector)
        for alias, path in (model.aliases() if model else {}).items():
            self._schema_index.setdefault(tuple(part.lower() for part in alias.split('.')), path)
        self._known_keys, self._known_key_patterns = self._build_known_key_index(self.mappings, self.schema)
        self._model_fields = set(self._schema_leaf_paths(self.schema))
        # the model's spelling of each enumeration value a source may spell otherwise, by the field it is for
        spellings = model.spellings() if model else {}
        self._spellings = {path: spellings[value_range] for path, value_range in self._schema_leaf_ranges(self.schema)
                           if value_range in spellings}

    @staticmethod
    def _load_json(file_path):
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
    def _schema_leaf_ranges(cls, schema, path=''):
        """Yield (dotted path, range) for every leaf field in `schema`."""
        for key, value in schema.items():
            current = f'{path}.{key}' if path else key
            if isinstance(value, dict):
                yield from cls._schema_leaf_ranges(value, current)
            else:
                yield current, value

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

    @classmethod
    def _build_known_key_index(cls, mappings, schema):
        """The literal first path segment of every mapping rule plus every schema field name, and separately
        the first segments that contain a wildcard (the OME annotation rules), which must be matched."""
        known = set()
        patterns = set()
        for pattern in mappings:
            # a rule for one item of a value list ("PixelSpacing[0]") names the list's key
            first_segment = re.sub(r'\[\d+\]$', '', pattern.split('.')[0])
            if '*' in first_segment:
                patterns.add(first_segment)
            else:
                known.add(first_segment)
        for leaf_path in cls._schema_leaf_paths(schema):
            known.update(leaf_path.split('.'))
        return known, patterns

    def _is_known_key(self, key):
        """Whether any rule or the model itself names `key`."""
        return key in self._known_keys or any(fnmatchcase(key, pattern) for pattern in self._known_key_patterns)

    def _resolvable_leaf_count(self, metadata, prefix=''):
        """Count the leaves of `metadata` whose path (list items unindexed, as rules see them) resolves."""
        count = 0
        for key, value in metadata.items():
            path = f'{prefix}.{key}' if prefix else str(key)
            items = value if isinstance(value, list) and any(isinstance(item, dict) for item in value) else [value]
            for item in items:
                if isinstance(item, dict) and item:
                    count += self._resolvable_leaf_count(item, path)
                elif self._resolve_rule_path(path) is not None or self._resolve_schema_path(path) is not None:
                    count += 1
        return count

    def _vendor_wrapper(self, key, value):
        """(wrapper path, wrapped contents) when top-level `key` only wraps `value`, else None.

        A source that reads its metadata straight from a file's tags keys
        each vendor's blob by the tag it came from ("FEI_TITAN",
        "FibicsXML", ...), sometimes two levels deep ("FEI_TITAN.FeiImage",
        "FibicsXML.Fibics"): levels the rules know nothing about, which stop
        every rule below them from matching. A document of the model itself
        is wrapped in its root ("OME"). A level counts as wrapping when no
        rule and no model field names it (the model's root excepted), and
        the deepest one is taken below which strictly more leaves resolve.
        """
        if not isinstance(value, dict) or (self._is_known_key(str(key)) and key != self._root):
            return None
        levels = [(str(key), value)]
        while len(levels[-1][1]) == 1:
            inner_key, inner = next(iter(levels[-1][1].items()))
            if not isinstance(inner, dict) or self._is_known_key(str(inner_key)):
                break
            levels.append((f'{levels[-1][0]}.{inner_key}', inner))
        return next(((prefix, contents) for prefix, contents in reversed(levels)
                     if self._resolvable_leaf_count(contents) > self._resolvable_leaf_count(contents, prefix)), None)

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
        (an index, a generated ID, ...) has no place in the imaging
        model; the full source path stays in the SourceMap (see
        `convert_metadata`). A "Target[]" namespace is
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
        for pattern, namespace in self._wildcard_rules:
            has_wildcard = '*' in pattern
            pattern_segments = pattern.split('.') if has_wildcard else None
            is_remainder_style = has_wildcard and pattern.endswith('.*')
            if (
                is_remainder_style
                and not (isinstance(namespace, str) and namespace.endswith('[]'))
                and len(pattern_segments) >= min_rule_segments
                and fnmatchcase(source_path, pattern)
            ):
                prefix = pattern[:-2]
                remainder = source_path[len(prefix) + 1:]
                targets = [f'{target}.{remainder}' if remainder else target for target in rule_targets(namespace)]
                return targets if isinstance(namespace, list) else targets[0]
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
        for pattern, namespace in self._wildcard_rules:
            has_wildcard = '*' in pattern
            pattern_segments = pattern.split('.') if has_wildcard else None
            is_child_collapse_style = (
                has_wildcard and pattern.endswith('.*') and isinstance(namespace, str) and namespace.endswith('[]')
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

    def _resolve_rule_path(self, source_path, min_rule_segments=0):
        """Resolve a dotted source path via a mappings.json rule, or None.

        Exact entries rename a single field, and wildcard entries remap a
        whole subtree or a single variable path segment (see
        `_resolve_wildcard_path`).
        """
        key = (source_path, min_rule_segments)
        if key not in self._resolved:
            target = resolve_exact_path(source_path, self.mappings)
            self._resolved[key] = target if target is not None else self._resolve_wildcard_path(source_path,
                                                                                               min_rule_segments)
        return self._resolved[key]

    def _apply_mappings(self, metadata, result=None, path='', rule_path=None, min_rule_segments=0,
                        provenance=None, origin=None, root=None):
        """Map metadata onto the imaging model.

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
        position rather than part of an output key (the key itself is kept
        as an "id" or "SourceKey" label on the item), and a second sibling
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

        `provenance` collects {output path: source path} for every leaf
        written into `result` (output paths relative to `result`, list items
        as "[i]"), and `origin` is the true source path of `metadata` itself,
        list indices included - unlike `rule_path`, which leaves them out so
        rules match every item alike. A collapsed key kept as an "id" label
        maps to the source path of the dict it named.

        mappings.json targets are schema paths from the document root, so
        inside a list item (where `result` is the item's own dict) a
        rule-resolved field is written into `root`, the (result,
        provenance) pair of the whole document, falling back to its place
        in the item only if that would overwrite something. Unmapped item
        fields and schema-fallback matches stay in the item.
        """
        if result is None:
            result = {}
        if rule_path is None:
            rule_path = path
        if provenance is None:
            provenance = {}
        if origin is None:
            origin = rule_path
        if root is None:
            root = (result, provenance, [])
        root_result, root_provenance, _ = root
        for key, value in metadata.items():
            source_path = f'{path}.{key}' if path else str(key)
            rule_source_path = f'{rule_path}.{key}' if rule_path else str(key)
            origin_path = f'{origin}.{key}' if origin else str(key)
            if isinstance(value, dict) and value:
                target_path = resolve_exact_path(rule_source_path, self.mappings)
                is_child_collapse = False
                if target_path is None:
                    target_path, is_child_collapse = self._resolve_whole_segment_wildcard_path(
                        rule_source_path, min_rule_segments)
                single_target(target_path, rule_source_path)
                if target_path is not None and target_path.endswith('[]'):
                    item_min_segments = max(min_rule_segments, len(rule_source_path.split('.')))
                    item_provenance = {}
                    mapped_item = self._apply_mappings(
                        value, rule_path=rule_source_path, min_rule_segments=item_min_segments,
                        provenance=item_provenance, origin=origin_path, root=root)
                    label_keys = ('id', 'ID', 'SourceKey') if is_child_collapse else ('SourceKey',)
                    label_key = next((label for label in label_keys if label not in mapped_item), None)
                    if label_key is None:
                        raise ValueError(f'No free key to keep the source key of {origin_path}')
                    mapped_item[label_key] = key
                    item_provenance[label_key] = origin_path
                    # after the label, so a rule can name the label's field too ("Prefix.*.id")
                    self._name_item_fields(mapped_item, item_provenance, rule_source_path, target_path)
                    list_path = target_path[:-2]
                    if can_append(root_result, list_path):
                        index = append_nested_list_value(root_result, list_path, mapped_item)
                        for item_path, item_origin in item_provenance.items():
                            root_provenance[f'{list_path}[{index}].{item_path}'] = item_origin
                    else:
                        placed_at, _ = self._place(mapped_item, None, (result, source_path, None))
                        for item_path, item_origin in item_provenance.items():
                            provenance[f'{placed_at}.{item_path}'] = item_origin
                elif target_path is not None:
                    self._place(value, origin_path, (root_result, target_path, root_provenance),
                                (result, source_path, provenance))
                else:
                    self._apply_mappings(value, result, source_path, rule_source_path, min_rule_segments,
                                         provenance, origin_path, root)
            elif isinstance(value, list) and any(isinstance(item, dict) for item in value):
                target_path = resolve_exact_path(rule_source_path, self.mappings)
                if target_path is None:
                    target_path, _ = self._resolve_whole_segment_wildcard_path(
                        rule_source_path, min_rule_segments)
                single_target(target_path, rule_source_path)
                if target_path is not None:
                    self._place(value, origin_path, (root_result, target_path, root_provenance),
                                (result, source_path, provenance))
                else:
                    item_min_segments = max(min_rule_segments, len(rule_source_path.split('.')))
                    mapped_items = []
                    items_provenance = {}
                    for index, item in enumerate(value):
                        item_origin = f'{origin_path}[{index}]'
                        if isinstance(item, dict) and item:
                            item_provenance = {}
                            mapped_items.append(self._apply_mappings(
                                item, rule_path=rule_source_path, min_rule_segments=item_min_segments,
                                provenance=item_provenance, origin=item_origin, root=root))
                            for item_path, item_source in item_provenance.items():
                                items_provenance[f'[{index}].{item_path}'] = item_source
                        else:
                            mapped_items.append(item)
                            for suffix in leaf_suffixes(item):
                                items_provenance[f'[{index}]{suffix}'] = f'{item_origin}{suffix}'
                    single_target(self._resolve_rule_path(rule_source_path, min_rule_segments), rule_source_path)
                    candidates, _ = self._candidates(rule_source_path, source_path, min_rule_segments, result,
                                                     provenance, root, origin_path)
                    placed_at, placed_provenance = self._place(mapped_items, None, *candidates)
                    for item_path, item_source in items_provenance.items():
                        placed_provenance[f'{placed_at}{item_path}'] = item_source
            elif isinstance(value, list) and any(f'{rule_source_path}[{index}]' in self.mappings
                                                 for index in range(len(value))):
                self._place_items(value, rule_source_path, source_path, origin_path, min_rule_segments, result,
                                  provenance, root)
            else:
                candidates, copies = self._candidates(rule_source_path, source_path, min_rule_segments, result,
                                                      provenance, root, origin_path)
                placed_at, placed_provenance = self._place(value, origin_path, *candidates)
                if (placed_at, placed_provenance) == (candidates[0][1], root[1]):
                    self._imply_unit(rule_source_path, value, placed_at, origin_path, root)
                for copy_target in copies:
                    if is_free_path(root_result, copy_target):
                        self._place(value, origin_path, (root_result, copy_target, root_provenance))
        return result

    def _name_item_fields(self, item, item_provenance, rule_source_path, target_path):
        """Move the fields of `item`, which the "Target[]" `target_path` collapsed from `rule_source_path`, to the
        names the rules for "Prefix.*.field" give them in "Target[].Field", where that is free."""
        parent = rule_source_path.rsplit('.', 1)[0]
        for item_path in list(item_provenance):
            rule = f'{parent}.*.{item_path}'
            target = self.item_fields.get(rule)
            field = target[len(target_path) + 1:] if target and target.startswith(f'{target_path}.') else None
            # out of the way first, as "ExposureTime" may move to "ExposureTime.Value"
            value = pop_nested_value(item, item_path) if field is not None else None
            if field is not None and is_free_path(item, field):
                set_nested_value(item, field, value)
                origin = item_provenance.pop(item_path)
                item_provenance[field] = origin
                # the whole item is mapped by now, so a unit it states is in place already
                unit = self.implied_units.get(rule)
                if unit is not None and is_number(value) and is_free_path(item, unit_field(field)):
                    set_nested_value(item, unit_field(field), unit)
                    item_provenance[unit_field(field)] = [origin]
            elif field is not None:
                set_nested_value(item, item_path, value)

    def _place_items(self, items, rule_source_path, source_path, origin_path, min_rule_segments, result, provenance,
                     root):
        """Place a value list some of whose items a rule names ("PixelSpacing[0]", one of a row and column spacing):
        each such item goes to its rule's target where that is free, and the others stay in a list at the list's
        own place, their provenance naming the item each came from."""
        root_result, root_provenance, _ = root
        rest = []
        for index, item in enumerate(items):
            item_rule_path = f'{rule_source_path}[{index}]'
            item_origin = f'{origin_path}[{index}]'
            target = self.mappings.get(item_rule_path)
            single_target(target, item_rule_path)
            if target is not None and is_free_path(root_result, target):
                self._place(item, item_origin, (root_result, target, root_provenance))
                self._imply_unit(item_rule_path, item, target, item_origin, root)
            else:
                rest.append((index, item))
        if rest:
            candidates, _ = self._candidates(rule_source_path, source_path, min_rule_segments, result, provenance,
                                             root, origin_path)
            placed_at, placed_provenance = self._place([item for _, item in rest], None, *candidates)
            for position, (index, item) in enumerate(rest):
                for suffix in leaf_suffixes(item):
                    placed_provenance[f'{placed_at}[{position}]{suffix}'] = f'{origin_path}[{index}]{suffix}'

    def _imply_unit(self, rule_source_path, value, target, origin, root):
        """Note the unit a rule says its source implies, for a number `value` placed at that rule's `target`; the
        units are written once everything is mapped, so a unit the source states always comes first."""
        unit = self.implied_units.get(rule_source_path)
        if unit is not None and is_number(value):
            root[2].append((unit_field(target), unit, origin))

    def _candidates(self, rule_source_path, source_path, min_rule_segments, result, provenance, root, origin=''):
        """Where a value may go, in order - a rule's target from the root, else a schema match or its own
        path - and the further targets of a rule naming several, which get a copy where free.

        A target's "[*]" is the index of the list item the value comes from (its last index in `origin`),
        so a per-channel value goes to its own channel: ChannelData[1].LambdaEx -> Channel[1]....
        """
        rule_target = self._resolve_rule_path(rule_source_path, min_rule_segments)
        if rule_target is not None:
            indices = re.findall(r'\[(\d+)\]', origin)
            if any('[*]' in target for target in rule_targets(rule_target)) and not indices:
                raise ValueError(f'{rule_source_path} targets a list item ([*]) but is in no list')
            first, *copies = [target.replace('[*]', f'[{indices[-1]}]') if indices else target
                              for target in rule_targets(rule_target)]
            return ((root[0], first, root[1]), (result, source_path, provenance)), copies
        schema_target = self._resolve_schema_path(rule_source_path)
        return ((result, schema_target or source_path, provenance), (result, source_path, provenance)), []

    @staticmethod
    def _place(value, origin, *candidates):
        """Write `value` at the first (target dict, path, provenance) candidate that overwrites nothing.

        Returns the (path, provenance) used. With `origin`, records every
        leaf of `value` against its source path in that provenance.
        """
        for target, path, provenance in candidates:
            if is_free_path(target, path):
                set_nested_value(target, path, value)
                if origin is not None:
                    for suffix in leaf_suffixes(value):
                        provenance[f'{path}{suffix}'] = f'{origin}{suffix}'
                return path, provenance
        paths = ', '.join(path for _, path, _ in candidates)
        raise ValueError(f'{paths} are all taken; refusing to overwrite')

    def convert_metadata(self, metadata):
        """Map a single in-memory metadata dict onto the imaging model.

        Returns the converted dict, with a top-level SOURCE_MAP_KEY section
        mapping every output leaf path to the source path it came from, so
        renamed and collapsed keys stay recoverable from the output alone:
        a list of paths for a value derived from them, and {"Source": path,
        "SourceValue": spelling} for a value written in the model's spelling.
        A top-level vendor tag wrapper (see `_vendor_wrapper`) is left out
        of the paths rules are matched against, but nothing else about it
        is: its unmapped fields stay under it, and every source path keeps it.
        """
        if not isinstance(metadata, dict):
            raise TypeError('metadata must be a dict')
        metadata = as_lists(metadata)

        provenance = {}
        result = {}
        implied_units = []
        root = (result, provenance, implied_units)
        for key, value in metadata.items():
            wrapper = self._vendor_wrapper(key, value)
            if wrapper is not None:
                # Rules see the wrapper's contents as top-level fields, while unmapped ones stay under the
                # wrapper and the SourceMap keeps the full source path.
                prefix, contents = wrapper
                self._apply_mappings(contents, result, path=prefix, rule_path='', provenance=provenance,
                                     origin=prefix, root=root)
            else:
                self._apply_mappings({key: value}, result, provenance=provenance, root=root)
        # an implied unit is derived from the value it qualifies, recorded as a combination is from its parts
        for unit_path, unit, origin in implied_units:
            if is_free_path(result, unit_path):
                set_nested_value(result, unit_path, unit)
                provenance[unit_path] = [origin]
        self._map_leica_detectors(metadata, result, provenance)
        self._map_leica_sequential_channels(metadata, result, provenance)
        self._map_leica_microdissection_laser(metadata, result, provenance)
        self._map_leica_widefield_light_sources(metadata, result, provenance)
        self._map_detector_settings(metadata, result, provenance)
        self._apply_combinations(metadata, result, provenance)
        self._respell(result, provenance)
        if SOURCE_MAP_KEY in result:
            raise ValueError(f'Source metadata already has a top-level {SOURCE_MAP_KEY}')
        result[SOURCE_MAP_KEY] = provenance
        return result

    def _map_leica_detectors(self, metadata, result, provenance):
        """Describe each detector of a Leica confocal system as the class of the type LAS X states (PMT, HyD), or
        a GenericDetector for a type LiMi has no class for.

        The detectors are those of `leica_detectors`. Each gets an ID by its place (Detector:0), as the source
        has none, and its Name and Type move to it; the rest of its entry, its gain and whether it is on, are
        settings (see `_map_leica_sequential_channels`) and stay.
        """
        held = []
        for index, (detector, detector_path) in enumerate(leica_detectors(metadata)):
            detector_class = LEICA_DETECTOR_CLASSES.get(str(detector.get('Type')), 'GenericDetector')
            if isinstance(result.get(detector_class, []), list):
                record = f'{detector_class}[{len(result.get(detector_class, []))}]'
                set_nested_value(result, f'{record}.ID', f'Detector:{index}')
                provenance[f'{record}.ID'] = [f'{detector_path}.Type']
                for field, key in (('Name', 'Name'), ('Type', 'Type')):
                    if key in detector:
                        set_nested_value(result, f'{record}.{field}', detector[key])
                        provenance[f'{record}.{field}'] = f'{detector_path}.{key}'
                        held.append(f'{detector_path}.{key}')
        for path in held:
            if provenance.get(path) == path:
                pop_nested_value(result, path)
                del provenance[path]

    def _map_leica_sequential_channels(self, metadata, result, provenance):
        """Describe each channel of a Leica sequential confocal scan, where the source holds one.

        Channel k is the k-th active detector, taken sequence by sequence, so the sequences, not the spectral
        bands, give the channels' order (TileScan.lof's sequences use detectors 4, 5 and 1: ALEXA 488, mCherry,
        Cerulean, as their LUTs green, red and blue and their pixels, HyD, HyD and PMT, confirm). Its detector's
        band (MultiBand, numbered by detector) gives the dye, as the channel's Name and Fluorophore.Name, and
        its window, as a band-pass emission Filter; the sequence's laser lines on give a LightSourceSettings
        each, referring to the laser of that type (whose Role is Fluorescence where it excites a channel with
        a dye), and the excitation wavelength where only one is on. Its LightPath holds the settings of its
        detector (in the settings class of the detector's kind), which name that detector only: the gains
        LAS X states once for all sequences are not this sequence's own. The
        filters and lasers get IDs by their place, as the source has none for them. Every value written is
        derived, its SourceMap entry listing what it came from, and replaces those source values where it
        holds them (a dye, a band's limits, a single line): the detectors, the line intensities (whose
        attenuation LiMi does not define by them), and the lines of a sequence with several stay.
        """
        settings = metadata.get(LEICA_SETTINGS)
        sequences = _items(value_at_path(settings, LEICA_SEQUENCES), f'{LEICA_SETTINGS}.{LEICA_SEQUENCES}') \
            if isinstance(settings, dict) else []
        if not sequences:
            return
        bands = {str(band.get('Channel')): path
                 for band, path in _items(value_at_path(settings, LEICA_BANDS), f'{LEICA_SETTINGS}.{LEICA_BANDS}')}
        laser_ids = {str(laser.get('LightSourceType')): (index, path) for index, (laser, path) in
                     enumerate(_items(value_at_path(settings, LEICA_LASERS), f'{LEICA_SETTINGS}.{LEICA_LASERS}'))}
        detector_ids = {str(detector.get('Channel')): (index, detector)
                        for index, (detector, _) in enumerate(leica_detectors(metadata))}
        held = set()

        def derive(target, value, *origins):
            if is_free_path(result, target):
                set_nested_value(result, target, value)
                provenance[target] = list(origins)

        channel = 0
        for sequence, sequence_path in sequences:
            lines = [(line, line_path, str(aotf.get('LightSourceType')))
                     for aotf, aotf_path in _items(value_at_path(sequence, 'AotfList.Aotf'),
                                                   f'{sequence_path}.AotfList.Aotf')
                     for line, line_path in _items(aotf.get('LaserLineSetting'), f'{aotf_path}.LaserLineSetting')
                     if (_number(str(line.get('IntensityDev'))) or 0) > 0]
            detectors = [(detector, detector_path) for detector, detector_path in
                         _items(value_at_path(sequence, 'DetectorList.Detector'), f'{sequence_path}.DetectorList.Detector')
                         if str(detector.get('IsActive')) == '1']
            for detector, detector_path in detectors:
                target = f'Pixels.Channel[{channel}]'
                listed = detector_ids.get(str(detector.get('Channel')))
                if listed is not None:
                    index, described = listed
                    detector_class = LEICA_DETECTOR_CLASSES.get(str(described.get('Type')), 'GenericDetector')
                    settings_class = self._detector_settings.get(detector_class, 'GenericDetectorSettings')
                    derive(f'{target}.LightPath.{settings_class}[0].ID', f'Detector:{index}', f'{detector_path}.IsActive')
                band_path = bands.get(str(detector.get('Channel')))
                band = value_at_path(metadata, band_path) if band_path else {}
                if band.get('DyeName'):
                    derive(f'{target}.Name', band['DyeName'], f'{band_path}.DyeName')
                    derive(f'{target}.Fluorophore.Name', band['DyeName'], f'{band_path}.DyeName')
                    held.add(f'{band_path}.DyeName')
                left, right = (_number(str(band.get(edge))) for edge in ('LeftWorld', 'RightWorld'))
                filters = result.get('Filter', [])
                if left is not None and right is not None and right > left and isinstance(filters, list):
                    edges = (f'{band_path}.LeftWorld', f'{band_path}.RightWorld')
                    filter_path = f'Filter[{len(filters)}]'
                    filter_id = f'Filter:{len(filters)}'
                    derive(f'{filter_path}.ID', filter_id, *edges)
                    derive(f'{filter_path}.Type', 'BandPass', *edges)
                    derive(f'{filter_path}.TransmittanceRange.Wavelength', (left + right) / 2, *edges)
                    derive(f'{filter_path}.TransmittanceRange.FWHMBandwidth', right - left, *edges)
                    derive(f'{filter_path}.TransmittanceRange.WavelengthUnit', 'nm', *edges)
                    if is_free_path(result, f'{target}.LightPath.EmissionFilter'):
                        set_nested_value(result, f'{target}.LightPath.EmissionFilter', [filter_id])
                        provenance[f'{target}.LightPath.EmissionFilter[0]'] = list(edges)
                    held.update(edges)
                for position, (line, line_path, light_source_type) in enumerate(lines):
                    laser = laser_ids.get(light_source_type)
                    if laser is not None:
                        laser_index, laser_path = laser
                        derive(f'Laser[{laser_index}].ID', f'Laser:{laser_index}', f'{laser_path}.LightSourceType')
                        derive(f'{target}.LightPath.LightSourceSettings[{position}].ID', f'Laser:{laser_index}',
                               f'{line_path}.LaserLine', f'{laser_path}.LightSourceType')
                    # a light source's Role is a list: it may serve several
                    if laser is not None and band.get('DyeName') and is_free_path(result, f'Laser[{laser_index}].Role'):
                        set_nested_value(result, f'Laser[{laser_index}].Role', ['Fluorescence'])
                        provenance[f'Laser[{laser_index}].Role[0]'] = [f'{band_path}.DyeName', f'{line_path}.LaserLine']
                if len(lines) == 1:
                    line, line_path, _ = lines[0]
                    derive(f'{target}.Fluorophore.ExcitationWavelength', line['LaserLine'], f'{line_path}.LaserLine')
                    derive(f'{target}.Fluorophore.ExcitationWavelengthUnit', 'nm', f'{line_path}.LaserLine')
                    held.add(f'{line_path}.LaserLine')
                channel += 1
        for path in sorted(held):
            if provenance.get(path) == path:
                pop_nested_value(result, path)
                del provenance[path]

    def _map_leica_microdissection_laser(self, metadata, result, provenance):
        """Give the laser of a Leica laser microdissection system (its hardware setting's Application LMD) the
        role Microdissection: it cuts the specimen, while the images are taken in the microscope's own light."""
        settings = metadata.get(LEICA_SETTINGS)
        laser = settings.get('Laser') if isinstance(settings, dict) and settings.get('Application') == 'LMD' else None
        if isinstance(laser, dict) and laser.get('Lasertype') and is_free_path(result, 'Laser.Role'):
            set_nested_value(result, 'Laser.Role', ['Microdissection'])
            provenance['Laser.Role[0]'] = [f'{LEICA_SETTINGS}.Application', f'{LEICA_SETTINGS}.Laser.Lasertype']

    def _map_leica_widefield_light_sources(self, metadata, result, provenance):
        """Give each channel of a Leica widefield image the lamps its shutters open, as light sources.

        LAS X states per channel (WideFieldChannelInfo k, channel k) whether its transmitted-light (TL) and
        incident-light (IL) shutters are open, not what the lamps are. A channel with the TL shutter open
        uses the stand's transmitted lamp, a fluorescence channel (FLUO) with the IL shutter open its incident
        lamp: each a GenericExcitationSource, LiMi's light source of no stated type, with the Role
        Transmitted or Fluorescence, which the channel's LightSourceSettings name. The lamps get IDs by their
        place (LightSource:0), as the source has none; their intensities, on a scale without a unit, stay.
        """
        settings = metadata.get(LEICA_SETTINGS)
        channels = _items(value_at_path(settings, LEICA_WIDEFIELD_CHANNELS), f'{LEICA_SETTINGS}.{LEICA_WIDEFIELD_CHANNELS}') \
            if isinstance(settings, dict) else []
        lamps = {}
        for channel, (info, info_path) in enumerate(channels):
            used = [('Transmitted', f'{info_path}.TL_Shutter')] if str(info.get('TL_Shutter')) == '1' else []
            if str(info.get('IL_Shutter')) == '1' and info.get('ContrastingMethodName') == 'FLUO':
                used.append(('Fluorescence', f'{info_path}.IL_Shutter'))
            for position, (role, origin) in enumerate(used):
                if role not in lamps and isinstance(result.get('GenericExcitationSource', []), list):
                    index = len(result.get('GenericExcitationSource', []))
                    lamp = f'GenericExcitationSource[{index}]'
                    set_nested_value(result, f'{lamp}.ID', f'LightSource:{index}')
                    set_nested_value(result, f'{lamp}.Role', [role])
                    provenance[f'{lamp}.ID'] = [origin]
                    provenance[f'{lamp}.Role[0]'] = [origin]
                    lamps[role] = f'LightSource:{index}'
                target = f'Pixels.Channel[{channel}].LightPath.LightSourceSettings[{position}].ID'
                if role in lamps and is_free_path(result, target):
                    set_nested_value(result, target, lamps[role])
                    provenance[target] = [origin]

    def _map_detector_settings(self, metadata, result, provenance):
        """Give each detector's settings for the image the detector's ID, as LiMi has them: the settings, in the
        class of the detector's kind, in the LightPath of the image's channel, name the detector they are for.

        Of the detectors a source describes, the image is taken with the one it names (Velox's
        DetectorMetadata.DetectorName) or those mixed into it (Phenom's mixFactor above 0); their gain and offset
        move into the first channel's settings, while the other detectors' values stay as the source states
        them. The settings a source's rules write for its one detector (Cikteq's, a Leica camera's) are that
        detector's. A detector without an ID gets one by its place (Detector:0), as the source has none.
        """
        detectors = [(detector_class, record, record_path) for detector_class in self._detector_settings
                     for record, record_path in _items(result.get(detector_class), detector_class)]
        named = value_at_path(metadata, VELOX_IMAGE_DETECTOR)
        used = [detector for detector in detectors if named is not None and detector[1].get('Name') == named] or \
            [detector for detector in detectors if (_number(str(detector[1].get('mixFactor'))) or 0) > 0]
        for detector_class, record, record_path in used:
            settings_class = self._detector_settings[detector_class]
            written = value_at_path(result, f'Pixels.Channel[0].LightPath.{settings_class}')
            settings = f'Pixels.Channel[0].LightPath.{settings_class}[{len(written) if isinstance(written, list) else 0}]'
            reason = VELOX_IMAGE_DETECTOR if named is not None else provenance.get(f'{record_path}.mixFactor')
            set_nested_value(result, f'{settings}.ID', self._detector_id(result, provenance, detectors, record, record_path))
            provenance[f'{settings}.ID'] = record_origins(provenance, record_path) + ([reason] if reason else [])
            for key in [key for key in record if key.lower() in DETECTOR_SETTING_FIELDS]:
                field = f'{settings}.{DETECTOR_SETTING_FIELDS[key.lower()]}'
                set_nested_value(result, field, record.pop(key))
                provenance[field] = provenance.pop(f'{record_path}.{key}')
        written = value_at_path(result, 'LightPath.GenericDetectorSettings')
        generic = [detector for detector in detectors if self._detector_settings[detector[0]] == 'GenericDetectorSettings']
        if isinstance(written, dict) and 'ID' not in written and len(generic) == 1:
            _, record, record_path = generic[0]
            written['ID'] = self._detector_id(result, provenance, detectors, record, record_path)
            provenance['LightPath.GenericDetectorSettings.ID'] = record_origins(provenance, record_path)

    @staticmethod
    def _detector_id(result, provenance, detectors, record, record_path):
        """The ID of a detector `record`, given one by its place among `detectors` if the source has none."""
        if record.get('ID') is None:
            taken = {str(other.get('ID')) for _, other, _ in detectors}
            record['ID'] = next(f'Detector:{number}' for number in range(len(detectors) + 1)
                                if f'Detector:{number}' not in taken)
            provenance[f'{record_path}.ID'] = record_origins(provenance, record_path)
        return record['ID']

    def _respell(self, result, provenance):
        """Write the model's spelling of each enumeration value a source spells otherwise (Leica's "OIL" as Oil,
        "micron" as µm); the SourceMap entry of a source value respelled records the source's spelling too, as
        {"Source": path, "SourceValue": spelling}."""
        for path, origin in list(provenance.items()):
            spellings = self._spellings.get(re.sub(r'\[\d+\]', '', path), {})
            value = value_at_path(result, path)
            if isinstance(value, str) and value in spellings and not path.endswith(']'):
                set_nested_value(result, path, spellings[value])
                provenance[path] = {'Source': origin, 'SourceValue': value} if isinstance(origin, str) else origin

    def _apply_combinations(self, metadata, result, provenance):
        """Add each combinations.json value whose parts the source holds, e.g. Date + Time + Time Zone.

        The parts, looked up by source path, are joined with spaces, parsed
        with the entry's strptime format (or "unix", seconds since 1970) and written as ISO 8601 at its
        target, or with "split" taken as the entry's "item"-th number of them - only where that is free,
        and only when every part is there
        and parses. The combined value's SourceMap entry is the list of its parts, and it replaces those parts
        kept at their own path, as it holds them (see `drop_parts`). "count" gives last - first + 1 of two
        parts, "product" the parts multiplied (Aperio's Exposure Time x Exposure Scale), "ratio" the first part
        divided by the second (Exif's ExposureTime [41, 5000], a part naming a list item), "duration" a time written
        as text ("2min52s") in seconds, and "quantity" the number of a value written with its unit ("21.12µm");
        those two write the unit beside the value too, where free, as does any entry stating a "unit".
        "join" joins the parts with the entry's "separator" (LMD7's version 8, 5 and 9136 as "8.5.9136"),
        "filetime" reads a Windows FILETIME (100 ns steps since 1601, as Leica's LMD software writes its
        acquisition time) as ISO 8601 without a zone, as none is stated.
        "pattern" takes the first group of the entry's regular expression "pattern", as a number where it is
        one (the magnification 63.0 out of Leica's objective name "HCX APO L U-V-I  63.0x0.90 WATER  UV"). A
        source path may hold "*", for the first source path it matches (a turret named after its stand).

        A derived value may replace what a rule put at its target from its own parts, where that is no number
        (Cikteq's frame time "2min52s" under TALOS's rule for a number, Exif's exposure time as a list of two),
        or what its parts are at their own path, where it targets that path (an Exif rational becoming its
        number).
        """
        derived_parts = set()
        unused_parts = set()
        for combination in self.combinations:
            sources = [matching_path(metadata, path) for path in combination['sources']]
            target = combination['target']
            parts = [value_at_path(metadata, path) for path in sources]
            has_all_parts = all(part is not None for part in parts)
            text = ' '.join(map(str, parts))
            if combination['format'] == 'join':
                combined = combination.get('separator', ' ').join(map(str, parts)) if has_all_parts else None
            else:
                combined = parse_combination(text, combination['format'], combination.get('item'),
                                             combination.get('pattern')) if has_all_parts else None
            placed = value_at_path(result, target)
            own_path = placed_from_parts(provenance, target, sources) if placed is not None else None
            replaces_its_value = (own_path is not None and placed is not None and not is_number(placed)
                                  and (own_path == target or is_free_path(result, own_path)))
            if combined is not None and replaces_its_value and own_path == target:
                pop_nested_value(result, target)
                for path in [path for path in provenance if is_at_or_below(path, target)]:
                    del provenance[path]
            elif combined is not None and replaces_its_value:
                set_nested_value(result, own_path, pop_nested_value(result, target))
                for path in [path for path in provenance if is_at_or_below(path, target)]:
                    provenance[own_path + path[len(target):]] = provenance.pop(path)
            writes = combined is not None and is_free_path(result, target)
            if writes and combination['format'] not in FORMATS_KEEPING_PARTS:
                derived_parts.update(sources)
            elif has_all_parts and not writes:
                unused_parts.update(sources)
            if writes:
                set_nested_value(result, target, combined)
                provenance[target] = list(sources)
                unit = combination.get('unit') or combination_unit(text, combination['format'])
                if unit is not None and is_free_path(result, unit_field(target)):
                    set_nested_value(result, unit_field(target), unit)
                    provenance[unit_field(target)] = list(sources)
        drop_parts(result, provenance, derived_parts - unused_parts, self._model_fields)

    def unmatched_fields(self, metadata):
        """List the output paths of leaf fields not represented in the model.

        Converts `metadata`, then walks the *full* output and flags every
        leaf whose complete path is not itself a leaf declared in the
        schema. This deliberately looks past mappings.json's whole-segment
        wildcard rules (see `_resolve_whole_segment_wildcard_path`): a rule
        collapsing a vendor-specific subtree into a generic object-typed
        container (e.g. CustomProperties) makes conversion succeed, but the
        individual fields inside that subtree are still not modelled by the
        schema, so they must still count as unmatched here.
        """
        converted = self.convert_metadata(metadata)
        schema_leaf_paths = set(self._schema_leaf_paths(self.schema))

        unmatched = []

        def walk(node, path=''):
            for key, value in node.items():
                current = f'{path}.{key}' if path else str(key)
                if isinstance(value, dict):
                    walk(value, current)
                elif isinstance(value, list) and any(isinstance(item, dict) for item in value):
                    for item in value:
                        if isinstance(item, dict):
                            walk(item, current)
                elif current not in schema_leaf_paths:
                    unmatched.append(current)

        walk({key: value for key, value in converted.items() if key != SOURCE_MAP_KEY})
        return unmatched


def drop_parts(result, provenance, parts, model_fields):
    """Remove from `result` each of `parts` (source paths) that is in no model field, as a value derived from it
    holds it now: Exif's ExposureTime [41, 5000] once Plane.ExposureTime is 0.0082, Cikteq's User.TimeStamp
    that "User.*" moved to Experimenter. A list goes once all its items do; a part inside a list item stays."""
    dropped = {path for path, origin in provenance.items()
               if isinstance(origin, str) and origin in parts and re.sub(r'\[\d+\]', '', path) not in model_fields}
    for path in sorted({re.sub(r'(\[\d+\])+$', '', path) for path in dropped}):
        below = [entry for entry in provenance if is_at_or_below(entry, path)]
        if '[' not in path and all(entry in dropped for entry in below):
            pop_nested_value(result, path)
            for entry in below:
                del provenance[entry]


def matching_path(metadata, path):
    """`path`, or where it holds "*" the first path of a value in `metadata` it matches (else `path` itself)."""
    if '*' not in path:
        return path
    return next((candidate for candidate in _value_paths(metadata) if fnmatchcase(candidate, path)), path)


def _value_paths(node, path=''):
    """Yield the dotted path of every value below the dicts of `node`."""
    for key, value in node.items():
        current = f'{path}.{key}' if path else str(key)
        if isinstance(value, dict):
            yield from _value_paths(value, current)
        else:
            yield current


def leica_detectors(metadata):
    """(detector, its path) for each detector of a Leica confocal system: those of the image's own detector list,
    or, in a sequential scan without one, of its master sequence's; a sequence's own list names which of them it
    used."""
    settings = metadata.get(LEICA_SETTINGS)
    if not isinstance(settings, dict):
        return []
    masters = [path for path in _value_paths(settings) if path.endswith(f'{LEICA_SEQUENTIAL_MASTER}.{LEICA_DETECTORS}')]
    list_path = LEICA_DETECTORS if value_at_path(settings, LEICA_DETECTORS) is not None else min(masters, default=None)
    return _items(value_at_path(settings, list_path), f'{LEICA_SETTINGS}.{list_path}') if list_path else []


def record_origins(provenance, record_path):
    """The source paths of the values of the record at `record_path`, which a value derived from it comes from."""
    origins = []
    for path, entry in provenance.items():
        sources = entry if isinstance(entry, list) else [entry.get('Source') if isinstance(entry, dict) else entry]
        if path.startswith(f'{record_path}.'):
            origins += [source for source in sources if source not in origins]
    return origins


def _items(value, path):
    """(item, its path) for each item of a list at `path`, or the one dict a single item is written as."""
    if isinstance(value, list):
        return [(item, f'{path}[{index}]') for index, item in enumerate(value) if isinstance(item, dict)]
    return [(value, path)] if isinstance(value, dict) else []


def as_lists(value):
    """`value` as it would read from JSON, as the examples the rules and combinations are written against do:
    every tuple a list (tifffile gives Exif's fractions as tuples, (41, 5000)), and a date or time its text
    (tifffile reads Olympus's datetime as one: "2025-05-28 10:54:00")."""
    if isinstance(value, dict):
        return {key: as_lists(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_lists(item) for item in value]
    if isinstance(value, (datetime, date, time)):
        return str(value)
    return value


def rule_targets(target):
    """A rule's target paths: mappings.json names one, or a list of several for a single value; a rule stating a
    unit names its target in "target"."""
    if isinstance(target, dict):
        target = target['target']
    return target if isinstance(target, list) else [target]


def unit_field(target):
    """The field holding the unit of the value at `target`: PhysicalSizeX's is PhysicalSizeXUnit, and a Quantity's
    Value, or a QuantityRange's Begin or End, has its Unit beside it."""
    group, _, name = target.rpartition('.')
    return f'{group}.Unit' if name in ('Value', 'Begin', 'End') else f'{target}Unit'


def single_target(target, source_path):
    if isinstance(target, list):
        raise ValueError(f'{source_path}: a list of targets is only supported for a single value, '
                         f'not for a group or list moved as a whole')


def is_at_or_below(path, target):
    """Whether the output `path` is `target` itself, or a field or list item inside it."""
    return path == target or path.startswith((f'{target}.', f'{target}['))


def placed_from_parts(provenance, target, sources):
    """The source path of the value at `target`, where a rule put it there from the combination's `sources` (the
    value itself, or its items: "ExposureTime[0]", "ExposureTime[1]"), else None."""
    own_paths = set()
    for path, origin in provenance.items():
        suffix = path[len(target):]
        if is_at_or_below(path, target) and (not isinstance(origin, str) or origin not in sources
                                             or not origin.endswith(suffix)):
            return None
        if is_at_or_below(path, target):
            own_paths.add(origin[:len(origin) - len(suffix)])
    return own_paths.pop() if len(own_paths) == 1 else None


def pop_nested_value(target, dotted_path):
    """Remove the value at `dotted_path` from `target` and return it, dropping the dicts it leaves empty (but not
    a list item, whose place numbers the items after it)."""
    parent, _, key = dotted_path.rpartition('.')
    node = value_at_path(target, parent) if parent else target
    value = node.pop(key)
    if parent and not node and _list_segment(parent.rpartition('.')[2]) is None:
        pop_nested_value(target, parent)
    return value


def value_at_path(metadata, dotted_path):
    """The value at a dotted source path of `metadata` ("Key[1]" naming a list item), or None."""
    node = metadata
    for key in dotted_path.split('.'):
        segment = _list_segment(key)
        name, index = segment if segment is not None else (key, None)
        if not isinstance(node, dict) or name not in node:
            return None
        node = node[name]
        if index is not None and not (isinstance(node, list) and index < len(node)):
            return None
        if index is not None:
            node = node[index]
    return node


def parse_combination(text, date_format, item=None, pattern=None):
    """`text` parsed with the strptime `date_format`, as ISO 8601, or None if it does not parse. The format
    "unix" reads seconds since 1970 (UTC); 0 is taken as unset (TALOS writes "0" for a time it lacks), not
    as 1970-01-01. The format "split" takes the `item`-th of the whitespace-separated words of `text` as a
    number (BigDataViewer's size "1100 1100 1150"), or None if there is no number there."""
    if date_format == 'split':
        words = text.split()
        return _number(words[item]) if item < len(words) else None
    if date_format == 'product':
        factors = [_number(word) for word in text.split()]
        return math.prod(factors) if factors and None not in factors else None
    if date_format == 'filetime':
        steps = int(text) if text.strip().isdigit() else 0
        return (FILETIME_EPOCH + timedelta(microseconds=steps // 10)).isoformat() if steps > 0 else None
    if date_format == 'pattern':
        match = re.search(pattern, text)
        number = _number(match.group(1)) if match else None
        return (number if number is not None else match.group(1)) if match else None
    if date_format == 'ratio':
        terms = [_number(word) for word in text.split()]
        return terms[0] / terms[1] if len(terms) == 2 and None not in terms and terms[1] else None
    if date_format == 'count':
        ends = [_number(word) for word in text.split()]
        return ends[1] - ends[0] + 1 if len(ends) == 2 and all(isinstance(end, int) for end in ends) else None
    if date_format == 'duration':
        match = DURATION.fullmatch(text.strip())
        seconds = sum(_number(amount) * factor for amount, factor in zip(match.groups(), (3600, 60, 1))
                      if amount) if match and any(match.groups()) else None
        return int(seconds) if seconds is not None and seconds == int(seconds) else seconds
    if date_format == 'quantity':
        match = QUANTITY.fullmatch(text.strip())
        return _number(match.group(1)) if match else None
    if date_format == 'unix':
        seconds = int(text) if text.strip().isdigit() else 0
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat() if seconds > 0 else None
    try:
        return datetime.strptime(text, date_format).isoformat()
    except ValueError:
        return None


def combination_unit(text, value_format):
    """The unit a "duration" or "quantity" combination writes beside its value, else None."""
    if value_format == 'duration' and DURATION.fullmatch(text.strip()):
        return 's'
    match = QUANTITY.fullmatch(text.strip()) if value_format == 'quantity' else None
    return match.group(2) if match else None


def is_number(value):
    """Whether `value` is a number, or the text of one (TALOS writes "80000"): what a unit can qualify."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    return isinstance(value, str) and _number(value.strip()) is not None


def _number(text):
    """`text` as an int, or else a float, or None."""
    for parse in (int, float):
        try:
            return parse(text)
        except ValueError:
            pass
    return None


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


def _list_segment(key):
    """('Channel', 1) for a path segment 'Channel[1]', else None."""
    match = re.fullmatch(r'(.+)\[(\d+)\]', key)
    return (match.group(1), int(match.group(2))) if match else None


def set_nested_value(target, dotted_path, value):
    keys = dotted_path.split('.')
    node = target
    for key in keys[:-1]:
        segment = _list_segment(key)
        if segment is not None:
            name, index = segment
            items = node.get(name)
            if not isinstance(items, list):
                items = []
                node[name] = items
            while len(items) <= index:
                items.append({})
            child = items[index]
        else:
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
    colliding with (and silently overwriting) the first. Returns the new
    item's index.
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
    return len(existing) - 1


def can_append(target, dotted_path):
    """Whether `dotted_path` in `target` is free or already a list, so appending there overwrites nothing."""
    node = target
    keys = dotted_path.split('.')
    for key in keys[:-1]:
        if key not in node:
            return True
        node = node[key]
        if not isinstance(node, dict):
            return False
    return keys[-1] not in node or isinstance(node[keys[-1]], list)


def is_free_path(target, dotted_path):
    """Whether writing at `dotted_path` would leave every existing value in `target` intact."""
    node = target
    for key in dotted_path.split('.'):
        segment = _list_segment(key)
        name, index = segment if segment is not None else (key, None)
        if not isinstance(node, dict):
            return False
        if name not in node:
            return True
        node = node[name]
        if index is not None and not isinstance(node, list):
            return False
        if index is not None and len(node) <= index:
            return True
        if index is not None:
            node = node[index]
    return False


def leaf_suffixes(value):
    """Yield the path suffix of every leaf in `value` ('' for a scalar); empty dicts and lists count as leaves."""
    if isinstance(value, dict) and value:
        for key, child in value.items():
            for suffix in leaf_suffixes(child):
                yield f'.{key}{suffix}'
    elif isinstance(value, list) and value:
        for index, child in enumerate(value):
            for suffix in leaf_suffixes(child):
                yield f'[{index}]{suffix}'
    else:
        yield ''
