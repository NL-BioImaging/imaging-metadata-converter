"""Generate a metaseed profile specification from the LinkML master model (the packaged imaging.yaml).

metaseed has no inheritance, so every concrete class reachable from the tree
root becomes an entity with its inherited slots written out. A slot ranging
over a class with subclasses (Instrument.LightSource) becomes one field per
concrete class (Laser, Arc, ...), since a metaseed field nests one entity
type; the type designator is then implicit in the field. A reference
(`inlined: false`) becomes a string field holding the target's ID.
"""

import argparse
import collections
import os.path
import re
from pathlib import Path

import yaml
from linkml_runtime.utils.schemaview import SchemaView

from imaging_metadata_converter.ModelPaths import DEFAULT_MODEL_FILE

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE_FILE = str(ROOT / 'profile' / 'imaging.metaseed.yaml')

# LiMi documents at three levels; a field the XSD requires is needed only at its level (MechanicalCalibration is 4)
LIMI_TIERS = {'1': 'required', '2': 'recommended', '3': 'optional', '4': 'optional'}

RANGES = {'string': 'string', 'integer': 'integer', 'float': 'float', 'double': 'float', 'decimal': 'float',
          'boolean': 'boolean', 'date': 'date', 'datetime': 'datetime', 'uri': 'uri', 'uriorcurie': 'uri'}


class MetaseedGenerator:
    def __init__(self, model_filename=DEFAULT_MODEL_FILE):
        # an absolute path, so the model's imports resolve next to it
        self.view = SchemaView(os.path.abspath(model_filename))
        self.classes = self.view.all_classes()
        self.enums = self.view.all_enums()
        self.types = self.view.all_types()
        self.entities = {}
        self.expanded = collections.defaultdict(list)

    def generate(self, name=None, version=None):
        schema = self.view.schema
        root = next(class_name for class_name, cls in self.classes.items() if cls.tree_root)
        queue = collections.deque([root])
        while queue:
            class_name = queue.popleft()
            if class_name not in self.entities:
                self.entities[class_name] = None
                self.entities[class_name] = self._entity(class_name, queue)
        for entity in self.entities.values():
            for field in entity['fields']:
                # LightSensor is referenced (LightSensorRef) but contained nowhere, so it is no entity
                if field.get('reference', '').split('.')[0] not in self.entities:
                    field.pop('reference', None)
        return {
            'name': name or schema.name,
            # metaseed versions are MAJOR.MINOR
            'version': version or '.'.join(schema.version.split('.')[:2]),
            'description': f'Generated from {schema.name} {schema.version} ({schema.id}). {schema.description}',
            'root_entity': root,
            'entities': _containment_order(self.entities),
        }

    def _entity(self, class_name, queue):
        entity = {}
        description = self.classes[class_name].description
        if description:
            entity['description'] = description
        fields = []
        slots = [slot for slot in self.view.class_induced_slots(class_name) if not slot.designates_type]
        for slot in slots:
            fields += self._fields(class_name, slot, queue)
        model_required = {slot.name: bool(slot.required) for slot in slots}
        # metaseed keys an entity by its is_identifier field, else by its first field that is no reference
        inferred = next((field for field in fields if not field.get('reference')), None)
        weak = inferred is None or (inferred['type'] == 'string' and not inferred['required']
                                    and 'constraints' not in inferred)
        if not any(field.get('is_identifier') for field in fields) and weak:
            if inferred is not None and model_required.get(inferred['name']):
                # required in the model, optional only through its LiMi tier (StageLabel.Name): it keeps being
                # the identifier, now declared, so a new profile version does not re-key existing datasets
                inferred['is_identifier'] = True
            elif not any(field['name'] == 'ID' for field in fields):
                # metaseed would take that optional free-text field as the identifier
                fields.insert(0, {'name': 'ID', 'type': 'string', 'required': False, 'is_identifier': True,
                                  'description': 'An identifier for this record; the model defines none.'})
        names = [field['name'] for field in fields]
        assert len(names) == len(set(names)), (class_name, [name for name in names if names.count(name) > 1])
        entity['fields'] = fields
        return entity

    def _concrete(self, class_name):
        return [name for name in self.view.class_descendants(class_name, reflexive=True)
                if not self.classes[name].abstract]

    def _fields(self, class_name, slot, queue):
        tier = self._tier(class_name, slot)
        required = bool(slot.required) and tier in (None, 'required')
        is_nested = slot.range in self.classes and (slot.inlined or slot.inlined_as_list)
        if is_nested and not self.classes[slot.range].abstract:
            # as in the XSD, only an abstract group holds other types; SpecsFile (a FileAnnotation) does not
            # hold a TransmittanceProfileFile, although that is a FileAnnotation too
            queue.append(slot.range)
            return [self._nested_field(slot.name, slot, slot.range, required, tier)]
        if is_nested:
            concrete = self._concrete(slot.range)
            queue.extend(concrete)
            # one field per concrete class; a field can't require "one of these", so none is required
            self.expanded[f'{class_name}.{slot.name}'] = concrete
            return [self._nested_field(slot.name if name == slot.range else name, slot, name, False, tier)
                    for name in concrete]
        return [self._value_field(slot, required, tier)]

    def _tier(self, class_name, slot):
        """The metaseed tier of `slot` on `class_name`: the higher LiMi tier of the field and its class."""
        tiers = [_annotation(slot, 'Tier'), _annotation(self.classes[class_name], 'Tier')]
        known = [tier for tier in tiers if tier in LIMI_TIERS]
        return LIMI_TIERS[max(known)] if known else None

    def _nested_field(self, name, slot, items, required, tier):
        field = {'name': name, 'type': 'list' if slot.multivalued else 'entity', 'required': required}
        if slot.description:
            field['description'] = slot.description
        if tier:
            field['tier'] = tier
        field['items'] = items
        field['owns'] = True
        self._add_cardinality(field, slot)
        return field

    def _value_field(self, slot, required, tier):
        base, constraints = self._base_range(slot)
        field = {'name': slot.name}
        if slot.multivalued:
            field['type'] = 'list'
            field['items'] = base
        else:
            field['type'] = base
        field['required'] = required
        description = slot.description
        if slot.range in self.classes:
            reference = f'The ID of a {slot.range}.'
            description = f'{description} ({reference})' if description else reference
        if description:
            field['description'] = description
        if slot.range in self.classes and not self.classes[slot.range].abstract:
            field['reference'] = f'{slot.range}.{self._identifier(slot.range)}'
        if tier:
            field['tier'] = tier
        if slot.identifier:
            field['is_identifier'] = True
        if constraints:
            field['constraints'] = constraints
        if slot.ifabsent:
            # metaseed has no default; keep it as an example rather than drop it
            field['example'] = re.sub(r'^\w+\((.*)\)$', r'\1', slot.ifabsent)
        self._add_cardinality(field, slot)
        return field

    def _identifier(self, class_name):
        return next(slot.name for slot in self.view.class_induced_slots(class_name) if slot.identifier)

    def _base_range(self, slot):
        """The metaseed type of a value slot, and the constraints its range and the slot carry."""
        constraints = {}
        range_name = slot.range or self.view.schema.default_range
        if range_name in self.enums:
            constraints['enum'] = [str(value) for value in self.enums[range_name].permissible_values]
            range_name = 'string'
        elif range_name in self.classes:
            range_name = 'string'
        while range_name in self.types and range_name not in RANGES:
            typedef = self.types[range_name]
            for key, value in (('pattern', typedef.pattern), ('minimum', typedef.minimum_value),
                               ('maximum', typedef.maximum_value)):
                if value is not None:
                    constraints.setdefault(key, value)
            range_name = typedef.typeof or typedef.base
        for key, value in (('pattern', slot.pattern), ('minimum', slot.minimum_value),
                           ('maximum', slot.maximum_value)):
            if value is not None:
                constraints[key] = value
        base = RANGES.get(range_name, 'string')
        if base == 'uri' and 'pattern' in constraints:
            # metaseed applies a pattern to a uri field's parsed URL rather than its text, and fails on any
            # value (OME.UUID); as a string the pattern is checked as intended
            base = 'string'
        return base, constraints

    @staticmethod
    def _add_cardinality(field, slot):
        for key, value in (('min_items', slot.minimum_cardinality), ('max_items', slot.maximum_cardinality)):
            if value is not None:
                field.setdefault('constraints', {})[key] = value


def _containment_order(entities):
    """`entities` with every entity after all the entities nesting it, the order otherwise kept: metaseed's
    own order (metaseed.specs.ordering), so a profile loads without its "out of containment order" warning."""
    names = list(entities)
    children = {name: [field['items'] for field in entity['fields']
                       if field['type'] in ('list', 'entity') and field.get('items') in entities and field['items'] != name]
                for name, entity in entities.items()}
    parents_left = {name: 0 for name in names}
    for kids in children.values():
        for child in set(kids):
            parents_left[child] += 1
    ready = [name for name in names if parents_left[name] == 0]
    ordered = []
    while ready:
        name = ready.pop(0)
        ordered.append(name)
        for child in set(children[name]):
            parents_left[child] -= 1
            if parents_left[child] == 0:
                ready.append(child)
        ready.sort(key=names.index)
    ordered += [name for name in names if name not in ordered]
    return {name: entities[name] for name in ordered}


def _annotation(element, name):
    annotations = element.annotations
    return str(annotations[name].value) if annotations is not None and name in annotations else None


def write_profile(profile, filename):
    with open(filename, 'w', encoding='utf-8') as file:
        yaml.safe_dump(profile, file, sort_keys=False, allow_unicode=True, width=120)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--model', default=DEFAULT_MODEL_FILE, help='Path to the LinkML model')
    parser.add_argument('--output', default=DEFAULT_PROFILE_FILE, help='Path to write the metaseed profile YAML to')
    parser.add_argument('--name', default=None, help="Profile name (default: the model's name)")
    parser.add_argument('--version', default=None,
                        help="Profile version, in x.y format (default: from the model's version)")
    args = parser.parse_args(argv)

    generator = MetaseedGenerator(args.model)
    profile = generator.generate(args.name, args.version)
    write_profile(profile, args.output)
    print(f'Wrote {args.output}: profile {profile["name"]} {profile["version"]}, {len(profile["entities"])} entities, '
          f'{sum(len(entity["fields"]) for entity in profile["entities"].values())} fields; '
          f'{len(generator.expanded)} slots over an abstract class written as one field per subtype')


if __name__ == '__main__':
    main()
