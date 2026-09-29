"""Convert the LiMi XSD (reference/LiMi_XMLSchema.xsd) into the LinkML master model (the packaged imaging.yaml).

Written in the style of the OME LinkML schema (gouttegd/yamf-playground,
linkml/ome/ome.yaml): each field is defined once, on the class the XSD
defines it on; subtypes inherit it through `is_a`. An abstract substitution
group (LightSourceGroup) becomes a slot ranging over its abstract type
(LightSource), with a type designator saying which subtype an item is, and a
*Ref element becomes a slot referring to the target's ID (`inlined: false`).
Nothing is copied per parent, unlike reference/fullSchema.json.

Units enums go to a separate schema that the main one imports. Descriptions the
LiMi XSD leaves out are taken from the OME XSD it extends, or derived (an enum
from the slot using it, XUnit from X); each says where it came from.
"""

import argparse
import collections
import os.path
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / 'src' / 'imaging_metadata_converter' / 'models'
DEFAULT_XSD_FILE = str(ROOT / 'reference' / 'LiMi_XMLSchema.xsd')
DEFAULT_LINKML_FILE = str(MODELS_DIR / 'imaging.yaml')
DEFAULT_UNITS_FILE = str(MODELS_DIR / 'imaging_units.yaml')
DEFAULT_OME_XSD_FILE = str(ROOT / 'reference' / 'ome-2016-06.xsd')
OME_SOURCE = 'OME 2016-06 ome.xsd (CC BY 3.0, Open Microscopy Environment)'
SCHEMA_NAME = 'imaging'
SCHEMA_ID = f'https://github.com/NL-BioImaging/imaging-metadata-consolidator/models/{SCHEMA_NAME}'
UNITS_SCHEMA_NAME = f'{SCHEMA_NAME}_units'
# the model's own version: it starts from the LiMi XSD but is extended beyond it
SCHEMA_VERSION = '0.1.0'

XS = '{http://www.w3.org/2001/XMLSchema}'
ROOT_CLASS = 'OME'
REFERENCE_TYPE = 'Reference'
TYPE_DESIGNATOR = 'ObjectType'
ROLE_SLOT = 'Role'

BUILTIN_RANGES = {
    'string': 'string', 'normalizedString': 'string', 'token': 'string', 'base64Binary': 'string',
    'hexBinary': 'string', 'float': 'float', 'double': 'double', 'decimal': 'decimal', 'int': 'integer',
    'integer': 'integer', 'long': 'integer', 'short': 'integer', 'positiveInteger': 'integer',
    'nonNegativeInteger': 'integer', 'boolean': 'boolean', 'date': 'date', 'dateTime': 'datetime',
    'anyURI': 'uri',
}
BUILTIN_MINIMUMS = {'positiveInteger': 1, 'nonNegativeInteger': 0}
# XSD facets that LinkML types and slots express directly; the rest are kept as annotations
FACETS = {'pattern': 'pattern', 'minInclusive': 'minimum_value', 'maxInclusive': 'maximum_value'}

# Local elements defined identically in several parents, or whose own name is too generic, get one
# class; the name follows ome.yaml where it has one (MapEntry).
LOCAL_CLASS_NAMES = {('Detector', 'WavelengthRange'): 'ComponentWavelengthRange',
                     ('PolarizationOptics', 'WavelengthRange'): 'ComponentWavelengthRange',
                     ('Prism', 'WavelengthRange'): 'ComponentWavelengthRange',
                     ('Map', 'M'): 'MapEntry'}


def _local(name):
    return name.split(':')[-1] if name else name


def _builtin(name):
    return name.startswith('xsd:') or name.startswith('xs:')


def _documentation(node):
    """(description, annotations) from an XSD node's `Key=Value` documentation entries."""
    annotation = node.find(XS + 'annotation')
    descriptions, annotations = [], {}
    if annotation is None:
        return None, annotations
    for doc in annotation.findall(XS + 'documentation'):
        text = (doc.text or '').strip()
        match = re.match(r'(\w+)=(.*)', text, re.S)
        if match and match.group(1) == 'Description':
            descriptions.append(match.group(2).strip())
        elif match:
            key = match.group(1)
            annotations[key] = f'{annotations[key]}; {match.group(2).strip()}' if key in annotations \
                else match.group(2).strip()
        elif text:
            descriptions.append(text)
    for appinfo in annotation.findall(XS + 'appinfo'):
        for hints in appinfo:
            for hint in hints:
                annotations[f'xsdfu_{hint.tag}'] = (hint.text or '').strip() or 'true'
    return '\n\n'.join(descriptions) or None, annotations


class OmeDocumentation:
    """Descriptions from the OME XSD, which LiMi extends; OME documents some of what LiMi's XSD leaves out."""

    def __init__(self, filename):
        root = ET.parse(filename).getroot()
        parent = {child: node for node in root.iter() for child in node}
        self.top = {}
        self.members = {}
        self.values = {}
        for node in root.iter():
            text = self._text(node)
            is_definition = node.tag in (XS + 'element', XS + 'attribute', XS + 'complexType', XS + 'simpleType')
            name = node.get('name') or _local(node.get('ref'))
            if is_definition and text and parent.get(node) is root:
                self.top[name] = text
            elif is_definition and text and name:
                self.members.setdefault((self._owner(node, parent), name), text)
            elif is_definition and text and node.tag == XS + 'simpleType' and parent[node].tag == XS + 'attribute':
                # OME documents some attributes (Shape FillRule) on their anonymous simpleType
                self.members.setdefault((self._owner(parent[node], parent), parent[node].get('name')), text)
            if node.tag == XS + 'enumeration' and text:
                simple = parent[parent[node]]
                enum = simple.get('name') or f'{self._owner(simple, parent)}{parent[simple].get("name")}'
                self.values[(enum, node.get('value'))] = text

    @staticmethod
    def _text(node):
        docs = node.findall(f'{XS}annotation/{XS}documentation')
        return ' '.join(' '.join((doc.text or '').split()) for doc in docs).strip()

    @staticmethod
    def _owner(node, parent):
        while node in parent:
            node = parent[node]
            if node.tag in (XS + 'element', XS + 'complexType', XS + 'simpleType') and node.get('name'):
                return node.get('name')
        return None


class LinkmlConverter:
    def __init__(self, xsd_filename=DEFAULT_XSD_FILE, ome_xsd_filename=DEFAULT_OME_XSD_FILE):
        self.ome = OmeDocumentation(ome_xsd_filename) if ome_xsd_filename else None
        self.root = ET.parse(xsd_filename).getroot()
        self.elements = {node.get('name'): node for node in self.root.findall(XS + 'element')}
        self.complex_types = {node.get('name'): node for node in self.root.findall(XS + 'complexType')}
        self.simple_types = {node.get('name'): node for node in self.root.findall(XS + 'simpleType')}
        self.classes = {}
        self.enums = {}
        self.unit_enums = {}
        self.types = {}
        self.local_classes = {}
        self.pending_refs = []
        self.id_types = {}
        self.settings_classes = set()
        self.shared_id_types = {}
        self.unresolved_refs = []

    # --- which XSD definitions become classes

    def _is_reference_type(self, type_name):
        return self._is_reference_content(self.complex_types.get(type_name))

    def _is_reference_content(self, node):
        """A *Ref: extends Reference with nothing but an ID (Settings extends Reference too, with content)."""
        if node is None:
            return False
        base = self._base(node)
        if base != REFERENCE_TYPE and not (base != node.get('name') and self._is_reference_type(base)):
            return False
        members = [child for child in node.iter() if child.tag in (XS + 'element', XS + 'attribute')]
        # StageInsertRef and LightSensorRef name it StageInsertID and LightSensorID
        return all(member.tag == XS + 'attribute' and member.get('name').endswith('ID') for member in members)

    def _refers_by_id(self, node):
        """Settings and its subtypes: their ID is the ID of the component they configure, not their own."""
        base = self._base(node) if node is not None else None
        while base and base != REFERENCE_TYPE:
            node = self.complex_types[base]
            base = self._base(node)
        return base == REFERENCE_TYPE

    @staticmethod
    def _base(node):
        extension = node.find(f'{XS}complexContent/{XS}extension')
        if extension is None:
            extension = node.find(f'{XS}complexContent/{XS}restriction')
        return _local(extension.get('base')) if extension is not None else None

    def _is_reference_element(self, element):
        inline = element.find(XS + 'complexType')
        if inline is not None:
            return self._is_reference_content(inline)
        return self._is_reference_type(_local(element.get('type')))

    def _is_text_element(self, element):
        type_name = element.get('type')
        if element.find(XS + 'complexType') is not None:
            return False
        if element.find(XS + 'simpleType') is not None:
            return True
        return type_name is not None and (_builtin(type_name) or _local(type_name) in self.simple_types)

    def _merged_type(self, type_name):
        """A named complexType whose only element is one global element: that element's class holds it. Not the
        type of an abstract group: MaskingPlateSettings is one of OpticalApertureSettingsGroup's members, and its
        siblings must not inherit from it."""
        users = [name for name, element in self.elements.items() if _local(element.get('type')) == type_name
                 and element.get('abstract') != 'true']
        group_users = [name for name, element in self.elements.items() if _local(element.get('type')) == type_name
                       and element.get('abstract') == 'true']
        local_users = [node for node in self.root.iter(XS + 'element')
                       if _local(node.get('type')) == type_name and node.get('name') not in self.elements]
        return users[0] if len(users) == 1 and not local_users and not group_users else None

    def class_of_type(self, type_name):
        return self._merged_type(type_name) or type_name

    def _never_bare(self, type_name):
        """The type of an abstract group (AcoustoOpticalDevice of AcoustoOpticalDeviceGroup) only occurs as one of
        the group's members, even where a member uses the type as is; a named type no element uses
        (WavelengthRangeSettingsType) only occurs as a base."""
        users = [node for node in self.root.iter(XS + 'element') if _local(node.get('type')) == type_name]
        return type_name in self.complex_types and (not users or any(node.get('abstract') == 'true' for node in users))

    def _head_type(self, element):
        head = self.elements.get(element.get('substitutionGroup'))
        if head is None:
            return None
        return _local(head.get('type')) or self._head_type(head)

    # --- conversion

    def convert(self):
        for type_name, node in self.complex_types.items():
            if type_name != REFERENCE_TYPE and not self._is_reference_type(type_name) \
                    and self._merged_type(type_name) is None:
                self._add_class(type_name, node, node)
        for name, element in self.elements.items():
            if element.get('abstract') != 'true' and not self._is_reference_element(element) \
                    and not self._is_text_element(element):
                self._add_element_class(name, element)
        self._add_simple_types()
        self._collect_id_types()
        self._resolve_refs()
        self._add_type_designators()
        self._add_roles()
        if self.ome:
            self._add_ome_descriptions()
        self._add_derived_descriptions()
        return self._schema(), self._units_schema()

    # --- descriptions the LiMi XSD leaves out; each says where it came from

    @staticmethod
    def _describe(element, text, source):
        element['description'] = text
        element.setdefault('annotations', {})['description_source'] = source

    def _slots(self):
        return [(class_name, slot_name, slot) for class_name, cls in self.classes.items()
                for slot_name, slot in cls.get('attributes', {}).items()]

    def _add_ome_descriptions(self):
        for name, cls in self.classes.items():
            if not cls.get('description') and name in self.ome.top:
                self._describe(cls, self.ome.top[name], OME_SOURCE)
        for class_name, slot_name, slot in self._slots():
            xsd_name = slot.get('annotations', {}).get('xsd_element', slot_name)
            text = self.ome.members.get((class_name, xsd_name)) or self.ome.members.get((class_name, slot_name))
            if not slot.get('description') and text:
                self._describe(slot, text, OME_SOURCE)
        users = collections.defaultdict(list)
        for class_name, slot_name, slot in self._slots():
            users[slot.get('range')].append((class_name, slot.get('annotations', {}).get('xsd_element', slot_name)))
        for name, enum in {**self.enums, **self.unit_enums}.items():
            text = self.ome.top.get(name) or next(
                (self.ome.members[user] for user in users[name] if user in self.ome.members), None)
            if not enum.get('description') and text:
                self._describe(enum, text, OME_SOURCE)
            for value, spec in enum['permissible_values'].items():
                if not spec.get('description') and (name, value) in self.ome.values:
                    self._describe(spec, self.ome.values[(name, value)], OME_SOURCE)

    def _add_derived_descriptions(self):
        users = collections.defaultdict(list)
        for class_name, slot_name, slot in self._slots():
            users[slot.get('range')].append((f'{class_name}.{slot_name}', slot))
        for name, enum in {**self.enums, **self.unit_enums}.items():
            described = [(where, slot) for where, slot in users[name] if slot.get('description')
                         and slot.get('annotations', {}).get('description_source') is None]
            if not enum.get('description') and described:
                self._describe(enum, described[0][1]['description'], f'derived from {described[0][0]}')
        for class_name, slot_name, slot in self._slots():
            value_slot = slot_name.removesuffix('Unit')
            if not slot.get('description') and slot_name.endswith('Unit') \
                    and value_slot in self.classes[class_name]['attributes']:
                self._describe(slot, f'The unit of {value_slot}.', f'derived from {class_name}.{value_slot}')

    def _add_element_class(self, name, element):
        inline = element.find(XS + 'complexType')
        type_name = _local(element.get('type'))
        if inline is not None:
            self._add_class(name, element, inline)
        elif type_name and self._merged_type(type_name) == name:
            self._add_class(name, element, self.complex_types[type_name])
        elif type_name and type_name != name:
            self._add_class(name, element, None, is_a=self.class_of_type(type_name))
        elif type_name is None:
            head_type = self._head_type(element)
            self._add_class(name, element, None, is_a=self.class_of_type(head_type) if head_type else None)

    def _add_class(self, name, documented, content, is_a=None):
        assert name not in self.classes, name
        description, annotations = _documentation(documented)
        if content is not None and content is not documented:
            type_description, type_annotations = _documentation(content)
            description = description or type_description
            annotations = {**type_annotations, **annotations}
        cls = {}
        if description:
            cls['description'] = description
        base = self._base(content) if content is not None else None
        if base and base != REFERENCE_TYPE:
            is_a = self.class_of_type(base)
        if is_a:
            cls['is_a'] = is_a
        if annotations.pop('xsdfu_abstract', None) or documented.get('abstract') == 'true' \
                or self._never_bare(name):
            cls['abstract'] = True
        attributes = {}
        cls['attributes'] = attributes
        if annotations:
            cls['annotations'] = annotations
        self.classes[name] = cls
        if self._refers_by_id(content):
            self.settings_classes.add(name)
        if content is not None:
            self._add_content(name, content, attributes, required=True, multivalued=False, choice=None)
        if not attributes:
            del cls['attributes']
        return cls

    def _add_content(self, owner, node, attributes, required, multivalued, choice):
        for child in node:
            tag = child.tag.replace(XS, '')
            if tag == 'attribute':
                self._add_attribute(owner, child, attributes)
            elif tag == 'element':
                self._add_child_element(owner, child, attributes, required, multivalued, choice)
            elif tag in ('sequence', 'choice', 'all'):
                group_required = required and child.get('minOccurs', '1') != '0'
                group_multivalued = multivalued or child.get('maxOccurs', '1') != '1'
                group_choice = choice
                if tag == 'choice':
                    group_choice = f'{owner}_choice_{sum(1 for key in attributes) + 1}'
                self._add_content(owner, child, attributes, group_required and tag != 'choice', group_multivalued,
                                  group_choice)
            elif tag in ('complexContent', 'simpleContent', 'extension', 'restriction'):
                if tag in ('extension', 'restriction') and node.tag == XS + 'simpleContent':
                    self._add_value_slot(owner, child, attributes)
                self._add_content(owner, child, attributes, required, multivalued, choice)
            elif tag == 'any':
                attributes['Value'] = {'range': 'string', 'annotations': {'xsd_any': child.get('processContents')}}

    def _add_value_slot(self, owner, extension, attributes):
        slot = self._simple_range(_local(extension.get('base')) if not _builtin(extension.get('base'))
                                  else extension.get('base'), owner, 'Value')
        slot['annotations'] = {'xsd_text_content': True}
        attributes['Value'] = slot

    def _add_attribute(self, owner, node, attributes):
        # a dot would split the slot's path (the XSD's MaskingPlate has an attribute "ApertureNr.")
        name = node.get('name').replace('.', '')
        description, annotations = _documentation(node)
        if name != node.get('name'):
            annotations['xsd_name'] = node.get('name')
        inline = node.find(XS + 'simpleType')
        slot = self._simple_range(node.get('type'), owner, name, inline)
        if description:
            slot['description'] = description
        if node.get('use') == 'required':
            slot['required'] = True
        if node.get('default') is not None:
            slot['ifabsent'] = self._ifabsent(slot['range'], node.get('default'))
        if name == 'ID' and owner in self.settings_classes:
            slot['inlined'] = False
            self.pending_refs.append((slot, slot.pop('range'), f'{owner}.ID', owner.removesuffix('Settings')))
        elif name == 'ID':
            slot['identifier'] = True
        if annotations:
            slot['annotations'] = annotations
        existing = attributes.pop(name, None)
        if existing is not None:
            # XML keeps attribute and element names apart (BeamSplitter has both a TransmittanceProfileFile
            # attribute and element); the attribute keeps the name, as in fullSchema.json
            existing.setdefault('annotations', {})['xsd_element'] = name
            self._put(owner, attributes, f'{name}Element', existing)
        self._put(owner, attributes, name, slot)

    @staticmethod
    def _ifabsent(range_name, value):
        if range_name in ('float', 'double', 'decimal'):
            return f'float({value})'
        if range_name == 'integer':
            return f'int({value})'
        if range_name == 'boolean':
            return 'true' if value in ('true', '1') else 'false'
        return f'string({value})'

    def _simple_range(self, type_name, owner, name, inline=None):
        """A slot dict with the range (and facets) of a simple type, named, builtin or inline."""
        if inline is not None:
            restriction = inline.find(XS + 'restriction')
            if restriction.find(XS + 'enumeration') is not None:
                enum_name = f'{owner}{name}'
                self._add_enum(enum_name, inline)
                return {'range': enum_name}
            slot = self._simple_range(restriction.get('base'), owner, name)
            for facet in restriction:
                self._add_facet(slot, facet)
            return slot
        if type_name is None:
            return {'range': 'string'}
        if _builtin(type_name):
            slot = {'range': BUILTIN_RANGES[_local(type_name)]}
            if _local(type_name) in BUILTIN_MINIMUMS:
                slot['minimum_value'] = BUILTIN_MINIMUMS[_local(type_name)]
            return slot
        return {'range': _local(type_name)}

    @staticmethod
    def _add_facet(target, facet):
        tag = facet.tag.replace(XS, '')
        value = facet.get('value')
        if tag in FACETS:
            target[FACETS[tag]] = value if tag == 'pattern' else float(value) if '.' in value else int(value)
        elif tag != 'annotation':
            target.setdefault('annotations', {})[f'xsd_{tag}'] = value

    def _add_child_element(self, owner, node, attributes, required, multivalued, choice):
        min_occurs = node.get('minOccurs', '1')
        max_occurs = node.get('maxOccurs', '1')
        slot_required = required and choice is None and min_occurs != '0'
        slot_multivalued = multivalued or max_occurs != '1'
        description, annotations = _documentation(node)
        ref = _local(node.get('ref'))
        referenced = self.elements.get(ref) if ref else None
        if referenced is not None:
            slot_description, slot_annotations = _documentation(referenced)
            description = description or slot_description
            annotations = {**slot_annotations, **annotations} if not (description and slot_description) \
                else annotations
        if ref and referenced is not None and referenced.get('abstract') == 'true':
            slot_name = _local(referenced.get('type'))
            slot = {'range': self.class_of_type(slot_name), 'inlined': True}
            annotations['xsd_element'] = ref
        elif ref and self._is_reference_element(referenced):
            slot_name, slot = self._reference_slot(owner, ref, referenced)
        elif ref and self._is_text_element(referenced):
            slot_name = ref
            slot = self._simple_range(referenced.get('type'), ref, '', referenced.find(XS + 'simpleType'))
        elif ref:
            slot_name = ref
            slot = {'range': ref, 'inlined': True}
        elif self._is_reference_element(node):
            slot_name, slot = self._reference_slot(owner, node.get('name'), node)
        elif self._is_text_element(node):
            slot_name = node.get('name')
            slot = self._simple_range(node.get('type'), owner, slot_name, node.find(XS + 'simpleType'))
        elif node.find(XS + 'complexType') is not None:
            slot_name = node.get('name')
            slot = {'range': self._local_class(owner, node), 'inlined': True}
        else:
            slot_name = node.get('name')
            slot = {'range': self.class_of_type(_local(node.get('type'))), 'inlined': True}
        if slot_multivalued:
            slot['multivalued'] = True
            if slot.get('inlined'):
                slot['inlined_as_list'] = True
        if slot_required:
            slot['required'] = True
        if max_occurs not in ('1', 'unbounded'):
            slot['maximum_cardinality'] = int(max_occurs)
        if min_occurs not in ('0', '1'):
            slot['minimum_cardinality'] = int(min_occurs)
        if choice:
            annotations['xsd_choice'] = choice
        if description:
            slot['description'] = description
        if annotations:
            slot['annotations'] = {**slot.get('annotations', {}), **annotations}
        self._put(owner, attributes, slot_name, slot)

    def _reference_slot(self, owner, element_name, element):
        """A *Ref element: a slot named without the Ref suffix, whose range is resolved once all IDs are known."""
        id_type = self._reference_id_type(element)
        if id_type is None and element_name in self.elements and element is not self.elements[element_name]:
            # a local AnnotationRef without its own ID refers to what the global AnnotationRef refers to
            id_type = self._reference_id_type(self.elements[element_name])
        slot = {'inlined': False, 'annotations': {'xsd_element': element_name}}
        self.pending_refs.append((slot, id_type, f'{owner}.{element_name}', element_name))
        return element_name.removesuffix('Ref'), slot

    def _reference_id_type(self, element):
        inline = element.find(XS + 'complexType')
        type_node = inline if inline is not None else self.complex_types[_local(element.get('type'))]
        id_attribute = next((attribute for attribute in type_node.iter(XS + 'attribute')
                             if attribute.get('name').endswith('ID')), None)
        return _local(id_attribute.get('type')) if id_attribute is not None else None

    def _local_class(self, owner, node):
        name = LOCAL_CLASS_NAMES.get((owner, node.get('name')), f'{owner}{node.get("name")}')
        if name in self.local_classes:
            assert _signature(self.local_classes[name]) == _signature(node), name
            return name
        self.local_classes[name] = node
        self._add_class(name, node, node.find(XS + 'complexType'))
        return name

    def _put(self, owner, attributes, name, slot):
        assert name not in attributes, f'{owner}.{name}'
        attributes[name] = slot

    # --- simple types: enums, units, restricted types

    def _add_simple_types(self):
        for name, node in self.simple_types.items():
            restriction = node.find(XS + 'restriction')
            if restriction.find(XS + 'enumeration') is not None:
                self._add_enum(name, node)
            else:
                self._add_type(name, node, restriction)

    def _add_enum(self, name, node):
        description, annotations = _documentation(node)
        values = {}
        for enumeration in node.find(XS + 'restriction').findall(XS + 'enumeration'):
            value_description, value_annotations = _documentation(enumeration)
            value = {}
            if value_description:
                value['description'] = value_description
            unit = enumeration.find(f'{XS}annotation/{XS}appinfo/xsdfu/enum')
            if unit is not None:
                value_annotations = {key: value for key, value in value_annotations.items() if key != 'xsdfu_enum'}
                value_annotations.update({f'xsdfu_{key}': text for key, text in unit.attrib.items()})
            if value_annotations:
                value['annotations'] = value_annotations
            values[enumeration.get('value')] = value
        enum = {}
        if description:
            enum['description'] = description
        enum['permissible_values'] = values
        if annotations:
            enum['annotations'] = annotations
        (self.unit_enums if name.startswith('Units') else self.enums)[name] = enum

    def _add_type(self, name, node, restriction):
        description, annotations = _documentation(node)
        base = restriction.get('base')
        typedef = {'typeof': BUILTIN_RANGES[_local(base)] if _builtin(base) else _local(base)}
        if _builtin(base) and _local(base) in BUILTIN_MINIMUMS:
            typedef['minimum_value'] = BUILTIN_MINIMUMS[_local(base)]
        if description:
            typedef['description'] = description
        for facet in restriction:
            self._add_facet(typedef, facet)
        if annotations:
            typedef['annotations'] = {**typedef.get('annotations', {}), **annotations}
        if typedef['typeof'] in ('float', 'double') and 'minExclusive' in str(typedef.get('annotations')):
            typedef.setdefault('minimum_value', 0)
        self.types[name] = typedef

    # --- references, type designators, roles

    def _collect_id_types(self):
        for name, cls in self.classes.items():
            id_slot = cls.get('attributes', {}).get('ID')
            if id_slot and id_slot.get('identifier'):
                self.id_types.setdefault(id_slot['range'], []).append(name)

    def _resolve_refs(self):
        for slot, id_type, where, element_name in self.pending_refs:
            target = self._reference_target(id_type, element_name)
            is_settings_id = where.endswith('.ID')
            if target is None and is_settings_id:
                # TIRFSettings has a generic LSID of its own (TIRFSettingsRef refers to it), not a component's
                del slot['inlined']
                slot['identifier'] = True
                slot['range'] = id_type
            elif target is None:
                self.unresolved_refs.append((where, id_type))
                slot['range'] = 'string'
            else:
                slot['range'] = target

    def _reference_target(self, id_type, element_name):
        """The class a reference points to: the one owning its ID type, else the one the ID type or the element
        is named after (the XSD reuses LensID on OpticsHolder, OpticalAperture and Lens, and gives FilterCubeRef
        the generic LSID)."""
        owners = self.id_types.get(id_type, [])
        general = [name for name in owners if not any(self._inherits(name, other) for other in owners
                                                      if other != name)]
        if len(general) > 1:
            self.shared_id_types[id_type] = general
        named_after_id = id_type.removesuffix('ID') if id_type else None
        named_after_element = element_name.removesuffix('Ref') if element_name else None
        if len(general) == 1:
            return general[0]
        if named_after_id in self.classes and (named_after_id in general or not general):
            return named_after_id
        if named_after_element in self.classes:
            return named_after_element
        return None

    def _inherits(self, name, ancestor):
        parent = self.classes[name].get('is_a')
        return parent == ancestor or (parent is not None and self._inherits(parent, ancestor))

    def _add_type_designators(self):
        # A slot ranging over a class with subclasses can hold any of them; the designator says which.
        ranges = {slot['range'] for cls in self.classes.values() for slot in cls.get('attributes', {}).values()}
        parents = {cls['is_a'] for cls in self.classes.values() if 'is_a' in cls}
        for name in sorted(ranges & parents):
            if not any(self._inherits(name, other) for other in ranges & parents):
                self.classes[name].setdefault('slots', []).append(TYPE_DESIGNATOR)

    def _add_roles(self):
        # The XSD's Split annotation lists the roles a light source can play; fullSchema.json made a copy of the
        # light source per role (Transmitted_LightSource_Filament ...). Here the role is a field instead.
        split = {name: [value.strip().removesuffix('_LightSource') for value in
                        cls['annotations']['Split'].strip('[]').split(';')]
                 for name, cls in self.classes.items() if 'Split' in cls.get('annotations', {})}
        ancestors = [self._ancestors(name) for name in split]
        common = next(name for name in ancestors[0] if all(name in chain for chain in ancestors))
        roles = sorted({role for values in split.values() for role in values})
        self.enums[f'{common}{ROLE_SLOT}'] = {
            'description': 'The role a light source plays in this instrument, from the Split annotation of the XSD.',
            'permissible_values': {role: {} for role in roles}}
        self.classes[common].setdefault('attributes', {})[ROLE_SLOT] = {
            'range': f'{common}{ROLE_SLOT}', 'multivalued': True,
            'description': 'The illumination role(s) this light source serves: Transmitted light, or excitation '
                           'of Fluorescence. Recorded in the XSD as the Split annotation of each light source.'}
        for name, values in split.items():
            if sorted(values) != roles:
                enum_name = f'{"".join(values)}{common}{ROLE_SLOT}'
                self.enums[enum_name] = {'description': f'The roles a {name} can play.',
                                         'permissible_values': {role: {} for role in values}}
                self.classes[name].setdefault('slot_usage', {})[ROLE_SLOT] = {'range': enum_name}

    def _ancestors(self, name):
        chain = []
        while name:
            chain.append(name)
            name = self.classes[name].get('is_a')
        return chain

    # --- output

    def _schema(self):
        self.classes[ROOT_CLASS]['tree_root'] = True
        return {
            'id': SCHEMA_ID,
            'name': SCHEMA_NAME,
            'title': 'Imaging metadata model',
            'description': 'Microscopy imaging metadata, based on the LiMi (4DN-BINA-OME) model: converted from '
                           f'models/LiMi_XMLSchema.xsd (version {self.root.get("version")}, namespace '
                           f'{self.root.get("targetNamespace")}).',
            'version': SCHEMA_VERSION,
            'comments': ['Descriptions annotated with description_source "OME 2016-06 ome.xsd" are from '
                         'the OME Data Model (Copyright (C) 2002 - 2016 Open Microscopy Environment), '
                         'licensed under CC BY 3.0: http://www.openmicroscopy.org/info/attribution'],
            'see_also': ['https://www.openmicroscopy.org/Schemas/Documentation/Generated/OME-2016-06/ome.html',
                         'https://github.com/gouttegd/yamf-playground/blob/main/linkml/ome/ome.yaml'],
            'prefixes': {'linkml': 'https://w3id.org/linkml/', SCHEMA_NAME: f'{SCHEMA_ID}/'},
            'default_prefix': SCHEMA_NAME,
            'default_range': 'string',
            'imports': ['linkml:types', UNITS_SCHEMA_NAME],
            'types': self.types,
            'slots': {TYPE_DESIGNATOR: {'description': 'The class of this object, where a slot can hold several.',
                                        'range': 'string', 'designates_type': True}},
            'classes': self.classes,
            'enums': self.enums,
        }

    def _units_schema(self):
        return {
            'id': f'{SCHEMA_ID}/units',
            'name': UNITS_SCHEMA_NAME,
            'title': 'Imaging metadata units',
            'description': 'The units enumerations of the imaging metadata model, from models/LiMi_XMLSchema.xsd.',
            'version': SCHEMA_VERSION,
            'prefixes': {'linkml': 'https://w3id.org/linkml/', SCHEMA_NAME: f'{SCHEMA_ID}/'},
            'default_prefix': SCHEMA_NAME,
            'enums': self.unit_enums,
        }


def _signature(node):
    """The content of a local element, without its documentation."""
    text = ET.tostring(node.find(XS + 'complexType'), encoding='unicode')
    return re.sub(r'\s+', ' ', re.sub(r'<\w+:annotation>.*?</\w+:annotation>', '', text, flags=re.S))


def write_schema(schema, filename):
    with open(filename, 'w', encoding='utf-8') as file:
        yaml.safe_dump(schema, file, sort_keys=False, allow_unicode=True, width=120)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--xsd', default=DEFAULT_XSD_FILE, help='Path to the LiMi XSD')
    parser.add_argument('--ome-xsd', default=DEFAULT_OME_XSD_FILE,
                        help='Path to the OME XSD, for descriptions the LiMi XSD leaves out')
    parser.add_argument('--output', default=DEFAULT_LINKML_FILE, help='Path to write the LinkML model to')
    parser.add_argument('--units-output', default=DEFAULT_UNITS_FILE, help='Path to write the LinkML units schema to')
    parser.add_argument('--force', action='store_true', help='Overwrite an existing model, discarding any edits to it')
    args = parser.parse_args(argv)

    # the model is edited by hand once created; regenerating it would discard those edits
    existing = [filename for filename in (args.output, args.units_output) if os.path.exists(filename)]
    if existing and not args.force:
        raise FileExistsError(f'The master model already exists ({", ".join(existing)}); use --force to overwrite')
    converter = LinkmlConverter(args.xsd, args.ome_xsd)
    schema, units = converter.convert()
    write_schema(schema, args.output)
    write_schema(units, args.units_output)
    print(f'Wrote {args.output}: {len(schema["classes"])} classes, {len(schema["enums"])} enums, '
          f'{len(schema["types"])} types; {args.units_output}: {len(units["enums"])} unit enums')
    for where, id_type in converter.unresolved_refs:
        print(f'  unresolved reference {where} ({id_type}), kept as a string')


if __name__ == '__main__':
    main()
