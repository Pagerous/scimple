import abc
import base64
import binascii
from collections import defaultdict
from copy import copy
from datetime import datetime
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Collection,
    Iterable,
    Optional,
    TypeVar,
    Union,
)
from urllib.parse import urlparse

import precis_i18n.profile
from precis_i18n import get_profile

from src.constants import SCIMType
from src.container import AttrRep, BoundedAttrRep, Invalid, Missing, SCIMDataContainer
from src.error import ValidationError, ValidationIssues, ValidationWarning
from src.registry import resource_schemas

if TYPE_CHECKING:
    from src.data.patch_path import PatchPath


class AttributeMutability(str, Enum):
    READ_WRITE = "readWrite"
    READ_ONLY = "readOnly"
    WRITE_ONLY = "writeOnly"
    IMMUTABLE = "immutable"


class AttributeReturn(str, Enum):
    DEFAULT = "default"
    ALWAYS = "always"
    NEVER = "never"
    REQUEST = "request"


class AttributeUniqueness(str, Enum):
    NONE = "none"
    SERVER = "server"
    GLOBAL = "global"


class AttributeIssuer(Enum):
    SERVER = "SERVER"
    CLIENT = "CLIENT"
    NOT_SPECIFIED = "NOT_SPECIFIED"


_AttributeProcessor = Callable[[Any], Any]
_AttributeValidator = Callable[[Any], ValidationIssues]
_AttrName = Union[str, AttrRep, BoundedAttrRep]


class Attribute(abc.ABC):
    SCIM_TYPE: str
    BASE_TYPES: tuple
    _global_serializer: Callable[[Any], Any]
    _global_deserializer: Callable[[Any], Any]

    def __init__(
        self,
        name: _AttrName,
        *,
        description: str = "",
        issuer: AttributeIssuer = AttributeIssuer.NOT_SPECIFIED,
        required: bool = False,
        multi_valued: bool = False,
        canonical_values: Optional[Collection] = None,
        restrict_canonical_values: bool = False,
        mutability: AttributeMutability = AttributeMutability.READ_WRITE,
        returned: AttributeReturn = AttributeReturn.DEFAULT,
        validators: Optional[list[_AttributeValidator]] = None,
        deserializer: Optional[_AttributeProcessor] = None,
        serializer: Optional[_AttributeProcessor] = None,
    ):
        self._rep = AttrRep(name) if isinstance(name, str) else name
        self._description = description
        self._issuer = issuer
        self._required = required
        self._canonical_values = canonical_values
        self._validate_canonical_values = restrict_canonical_values
        self._multi_valued = multi_valued
        self._mutability = mutability
        self._returned = returned
        self._validators = validators or []
        self._deserializer = deserializer
        self._serializer = serializer

    @classmethod
    def set_serializer(cls, serializer: Callable[[Any], Any]):
        cls._global_serializer = staticmethod(serializer)

    @classmethod
    def set_deserializer(cls, deserializer: Callable[[Any], Any]):
        cls._global_deserializer = staticmethod(deserializer)

    @property
    def rep(self) -> Union[AttrRep, BoundedAttrRep]:
        return self._rep

    @property
    def description(self) -> str:
        return self._description

    @property
    def issuer(self) -> AttributeIssuer:
        return self._issuer

    @property
    def required(self) -> bool:
        return self._required

    @property
    def multi_valued(self) -> bool:
        return self._multi_valued

    @property
    def canonical_values(self) -> Optional[list]:
        return self._canonical_values

    @property
    def mutability(self) -> AttributeMutability:
        return self._mutability

    @property
    def returned(self) -> AttributeReturn:
        return self._returned

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._rep})"

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return False

        return all(
            [
                self._rep == other._rep,
                self._required == other._required,
                self._canonical_values == other._canonical_values,
                self._multi_valued == other._multi_valued,
                self._mutability == other._mutability,
                self._returned == other._returned,
                self._validators == other._validators,
                self._deserializer == other._deserializer,
                self._serializer == other._serializer,
                self._validate_canonical_values == other._validate_canonical_values,
            ]
        )

    def _is_canonical(self, value: Any) -> bool:
        if self._canonical_values is None:
            return True
        return value in self._canonical_values

    def validate_type(self, value: Any) -> ValidationIssues:
        issues = ValidationIssues()
        if self.multi_valued:
            if not isinstance(value, list):
                issues.add_error(
                    issue=ValidationError.bad_type("list"),
                    proceed=False,
                )
                return issues
            for i, item in enumerate(value):
                issues_ = self._validate_type(item)
                issues.merge(
                    issues=issues_,
                    location=[i],
                )
                if not issues_.can_proceed():
                    value[i] = Invalid
            return issues
        issues.merge(self._validate_type(value))
        return issues

    def _validate_type(self, value: Any) -> ValidationIssues:
        issues = ValidationIssues()
        if not isinstance(value, self.BASE_TYPES):
            issues.add_error(
                issue=ValidationError.bad_type(self.SCIM_TYPE),
                proceed=False,
            )
        return issues

    def validate(self, value: Any) -> ValidationIssues:
        issues = ValidationIssues()
        if value is None:
            return issues

        issues.merge(self.validate_type(value))
        if not issues.can_proceed():
            return issues

        if self._multi_valued:
            for i, item in enumerate(value):
                if item is Invalid:
                    continue
                issues_ = self._validate(item)
                issues.merge(issues=issues_, location=[i])
                if not issues_.can_proceed():
                    value[i] = Invalid
        else:
            issues.merge(self._validate(value))
        for validator in self._validators:
            if not issues.can_proceed():
                break
            issues.merge(validator(value))
        return issues

    def _validate(self, value: Any) -> ValidationIssues:
        issues = ValidationIssues()
        if not self._is_canonical(value):
            if self._validate_canonical_values:
                issues.add_error(
                    issue=ValidationError.must_be_one_of(self._canonical_values),
                    proceed=False,
                )
            else:
                issues.add_warning(
                    issue=ValidationWarning.should_be_one_of(self._canonical_values),
                )
        return issues

    def serialize(self, value: Any) -> Any:
        if self._serializer is not None:
            return self._serializer(value)

        if self.multi_valued and isinstance(value, list):
            return [self._serialize(item) for item in value]
        return self._serialize(value)

    def _serialize(self, value: Any) -> Any:
        return self._global_serializer(value)

    def deserialize(self, value: Any) -> Any:
        if self._deserializer is not None:
            return self._deserializer(value)

        if self.multi_valued and isinstance(value, list):
            return [self._deserialize(item) for item in value]
        return self._deserialize(value)

    def _deserialize(self, value: Any) -> Any:
        return self._global_deserializer(value)

    def to_dict(self) -> dict:
        output = {
            "name": self.rep.attr,
            "type": str(self.SCIM_TYPE),
            "multiValued": self._multi_valued,
            "description": self.description,
            "required": self.required,
            "mutability": self.mutability.value,
            "returned": self.returned.value,
        }
        if self.canonical_values:
            output["canonicalValues"] = self.canonical_values
        return output

    def clone(
        self,
        attr_rep: Optional[Union[str, AttrRep, BoundedAttrRep]] = None,
        attr_filter: Optional[Callable[["Attribute"], bool]] = None,
    ) -> "Attribute":
        if attr_filter and not attr_filter(self):
            raise ValueError("attribute does not match the filter")
        clone = copy(self)
        if attr_rep:
            clone._rep = (
                attr_rep if not isinstance(attr_rep, str) else BoundedAttrRep.deserialize(attr_rep)
            )
        return clone


class AttributeWithUniqueness(Attribute, abc.ABC):
    def __init__(
        self,
        name: _AttrName,
        *,
        uniqueness: AttributeUniqueness = AttributeUniqueness.NONE,
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self._uniqueness = uniqueness

    @property
    def uniqueness(self) -> AttributeUniqueness:
        return self._uniqueness

    def __eq__(self, other):
        return super().__eq__(other) and self.uniqueness == other.uniqueness

    def to_dict(self):
        output = super().to_dict()
        output["uniqueness"] = self.uniqueness.value
        return output


class AttributeWithCaseExact(Attribute, abc.ABC):
    def __init__(self, name: _AttrName, *, case_exact: bool = False, **kwargs):
        super().__init__(name=name, **kwargs)
        self._case_exact = case_exact
        if not self._case_exact and self._canonical_values:
            self._canonical_values = [item.lower() for item in self._canonical_values]

    @property
    def case_exact(self) -> bool:
        return self._case_exact

    def _is_canonical(self, value: Any) -> bool:
        return super()._is_canonical(value) or (
            not self._case_exact and value.lower() in self._canonical_values
        )

    def __eq__(self, other):
        return super().__eq__(other) and self.case_exact == other.case_exact

    def to_dict(self):
        output = super().to_dict()
        output["caseExact"] = self.case_exact
        return output


class Unknown(Attribute):
    def _validate_type(self, value: Any) -> ValidationIssues:
        return ValidationIssues()

    def _serialize(self, value: Any) -> Any:
        return value

    def _deserialize(self, value: Any) -> Any:
        return value


class Boolean(Attribute):
    SCIM_TYPE = SCIMType.BOOLEAN
    BASE_TYPES = (bool,)
    _global_deserializer = bool
    _global_serializer = bool


class Decimal(AttributeWithUniqueness):
    SCIM_TYPE = SCIMType.DECIMAL
    BASE_TYPES = (float, int)
    _global_deserializer = float
    _global_serializer = float


class Integer(AttributeWithUniqueness):
    SCIM_TYPE = SCIMType.INTEGER
    BASE_TYPES = (int,)
    _global_deserializer = int
    _global_serializer = int


class String(AttributeWithCaseExact, AttributeWithUniqueness):
    SCIM_TYPE = "string"
    BASE_TYPES = (str,)
    _global_deserializer = str
    _global_serializer = str

    def __init__(
        self,
        name: _AttrName,
        *,
        precis: precis_i18n.profile.Profile = get_profile("OpaqueString"),
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self._precis = precis

    @property
    def precis(self) -> precis_i18n.profile.Profile:
        return self._precis


class Binary(AttributeWithCaseExact):
    SCIM_TYPE = SCIMType.BINARY
    BASE_TYPES = (str,)
    _global_deserializer = str
    _global_serializer = str

    def __init__(self, name: _AttrName, **kwargs):
        kwargs["case_exact"] = True
        super().__init__(name=name, **kwargs)

    def _validate_type(self, value: Any) -> ValidationIssues:
        issues = super()._validate_type(value)
        if not issues.can_proceed():
            return issues
        issues.merge(self._validate_encoding(value))
        return issues

    @staticmethod
    def _validate_encoding(value: Any) -> ValidationIssues:
        issues = ValidationIssues()
        if len(value) % 4 != 0:
            issues.add_error(
                issue=ValidationError.bad_encoding("base64"),
                proceed=False,
            )
            return issues
        try:
            base64.b64decode(value, validate=True)
        except binascii.Error:
            issues.add_error(
                issue=ValidationError.bad_encoding("base64"),
                proceed=False,
            )
        return issues


class _Reference(AttributeWithCaseExact, abc.ABC):
    SCIM_TYPE = SCIMType.REFERENCE
    BASE_TYPES = (str,)
    _global_deserializer = str
    _global_serializer = str

    def __init__(self, name: _AttrName, *, reference_types: Iterable[str], **kwargs):
        kwargs["case_exact"] = True
        super().__init__(name=name, **kwargs)
        self._reference_types = list(reference_types)

    @property
    def reference_types(self) -> list[str]:
        return self._reference_types

    def to_dict(self) -> dict:
        output = super().to_dict()
        output["referenceTypes"] = self.reference_types
        return output

    def __eq__(self, other):
        return super().__eq__(other) and set(self.reference_types) == set(other.reference_types)


class DateTime(Attribute):
    SCIM_TYPE = SCIMType.DATETIME
    BASE_TYPES = (str,)
    _global_deserializer = str
    _global_serializer = str

    def _validate_type(self, value: Any) -> ValidationIssues:
        issues = super()._validate_type(value)
        if not issues.can_proceed():
            return issues
        value = self._deserialize_xsd_datetime(value)
        if value is None:
            issues.add_error(
                issue=ValidationError.bad_value_syntax(),
                proceed=False,
            )
            return issues
        return issues

    @staticmethod
    def _deserialize_xsd_datetime(value: str) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None


class ExternalReference(_Reference):
    def __init__(self, name: _AttrName, **kwargs):
        kwargs["reference_types"] = ["external"]
        super().__init__(name=name, **kwargs)

    def _validate_type(self, value: Any) -> ValidationIssues:
        issues = super()._validate_type(value)
        if issues.can_proceed():
            result = urlparse(value)
            is_valid = all([result.scheme, result.netloc])
            if not is_valid:
                issues.add_error(
                    issue=ValidationError.bad_value_syntax(),
                    proceed=False,
                )
        return issues


class URIReference(_Reference):
    def __init__(self, name: _AttrName, **kwargs):
        kwargs["reference_types"] = ["uri"]
        super().__init__(name=name, **kwargs)


class SCIMReference(_Reference):
    def __init__(self, name: _AttrName, *, reference_types: Iterable[str], **kwargs):
        super().__init__(name=name, reference_types=reference_types, **kwargs)

    def _validate_type(self, value: Any) -> ValidationIssues:
        issues = super()._validate_type(value)
        if not issues.can_proceed():
            return issues

        for resource_schema in resource_schemas.values():
            if resource_schema.name in self._reference_types and resource_schema.endpoint in value:
                return issues

        issues.add_error(
            issue=ValidationError.bad_scim_reference(self._reference_types),
            proceed=False,
        )
        return issues


_default_sub_attrs = [
    Unknown("value"),
    String(
        "display",
        mutability=AttributeMutability.IMMUTABLE,
    ),
    String("type"),
    Boolean("primary"),
    URIReference("$ref"),
]


TMapping = TypeVar("TMapping", bound=[SCIMDataContainer, dict])
TData = TypeVar("TData", bound=[TMapping, list[TMapping]])


class Complex(Attribute):
    SCIM_TYPE = "complex"
    BASE_TYPES = (SCIMDataContainer, dict)
    _global_deserializer = SCIMDataContainer
    _global_serializer = SCIMDataContainer

    def __init__(
        self,
        name: _AttrName,
        *,
        sub_attributes: Optional[Collection[Attribute]] = None,
        **kwargs,
    ):
        validators = kwargs.pop("validators", None)
        super().__init__(name=name, **kwargs)

        default_sub_attrs = (
            [
                Unknown("value"),
                String(
                    "display",
                    mutability=AttributeMutability.IMMUTABLE,
                ),
                String("type"),
                Boolean("primary"),
                URIReference("$ref"),
            ]
            if self._multi_valued
            else []
        )
        self._sub_attributes = Attributes(sub_attributes or default_sub_attrs)

        validators = list(validators or [])
        if self._multi_valued:
            if (
                getattr(self.attrs, "primary", None)
                and validate_single_primary_value not in validators
            ):
                validators.append(validate_single_primary_value)
            if (
                all([getattr(self.attrs, "type", None), getattr(self.attrs, "value", None)])
                and validate_type_value_pairs not in validators
            ):
                validators.append(validate_type_value_pairs)
        self._validators = validators

    @property
    def attrs(self) -> "Attributes":
        return self._sub_attributes

    def filter(self, data: TData, attr_filter: Callable[[Attribute], bool]) -> TData:
        if isinstance(data, list):
            return [self.filter(item, attr_filter) for item in data]

        is_dict = isinstance(data, dict)
        if is_dict:
            data = SCIMDataContainer(data)

        filtered = SCIMDataContainer()
        for attr in self.attrs:
            if attr_filter(attr) and (value := data.get(attr.rep)) is not Missing:
                filtered.set(attr.rep, value, expand=False)

        return filtered.to_dict() if is_dict else filtered

    def clone(
        self,
        attr_rep: Optional[Union[AttrRep, BoundedAttrRep]] = None,
        attr_filter: Optional[Callable[["Attribute"], bool]] = None,
    ) -> "Attribute":
        cloned = super().clone(attr_rep, attr_filter)
        if attr_filter:
            cloned._sub_attributes = self._sub_attributes.clone(attr_filter)
        return cloned

    def _validate(self, value: Union[SCIMDataContainer, dict[str, Any]]) -> ValidationIssues:
        issues = ValidationIssues()
        value = SCIMDataContainer(value)
        for sub_attr in self._sub_attributes:
            sub_attr_value = value.get(sub_attr.rep)
            if sub_attr_value is Missing:
                continue
            issues_ = sub_attr.validate(sub_attr_value)
            if not issues_.can_proceed():
                value.set(sub_attr.rep, Invalid)
            issues.merge(
                location=(sub_attr.rep.attr,),
                issues=issues_,
            )
        return issues

    def _deserialize(self, value: Union[dict, SCIMDataContainer]) -> SCIMDataContainer:
        value = SCIMDataContainer(value)
        deserialized = SCIMDataContainer()
        for sub_attr in self._sub_attributes:
            sub_attr_value = value.get(sub_attr.rep)
            if sub_attr_value is Missing:
                continue
            deserialized.set(sub_attr.rep, sub_attr.deserialize(sub_attr_value))
        return deserialized

    def _serialize(self, value: Union[dict, SCIMDataContainer]) -> dict[str, Any]:
        value = SCIMDataContainer(value)
        serialized = SCIMDataContainer()
        for sub_attr in self._sub_attributes:
            sub_attr_value = value.get(sub_attr.rep)
            if sub_attr_value is Missing:
                continue
            serialized.set(sub_attr.rep, sub_attr.serialize(sub_attr_value))
        return serialized.to_dict()

    def to_dict(self) -> dict[str, Any]:
        output = super().to_dict()
        output["subAttributes"] = [sub_attr.to_dict() for sub_attr in self.attrs]
        return output


def validate_single_primary_value(value: Collection[SCIMDataContainer]) -> ValidationIssues:
    issues = ValidationIssues()
    primary_entries = 0
    for item in value:
        if item is not Invalid and item.get("primary") is True:
            primary_entries += 1
    if primary_entries > 1:
        issues.add_error(
            issue=ValidationError.multiple_primary_values(),
            proceed=True,
        )
    return issues


def validate_type_value_pairs(value: Collection[SCIMDataContainer]) -> ValidationIssues:
    issues = ValidationIssues()
    pairs = defaultdict(int)
    for item in value:
        if item is Invalid:
            continue
        type_ = item.get("type")
        value = item.get("value")
        if type_ and value:
            pairs[item.get("type"), item.get("value")] += 1
    for count in pairs.values():
        if count > 1:
            issues.add_warning(issue=ValidationWarning.multiple_type_value_pairs())
    return issues


class Attributes:
    def __init__(self, attrs: Optional[Iterable[Attribute]] = None):
        self._attrs = {attr.rep.attr: attr for attr in attrs or []}

    def __getattr__(self, name: str) -> Attribute:
        for attr in self._attrs.values():
            if attr.rep.attr.lower() == name.lower():
                return attr
        raise AttributeError(f"no {name!r} attribute")

    def __iter__(self):
        return iter(self._attrs.values())

    def get(self, attr_rep: AttrRep) -> Optional[Attribute]:
        for attr, attr_obj in self._attrs.items():
            if attr.lower() == attr_rep.attr.lower():
                return attr_obj
        return None

    def clone(self, filter_: Callable[[Attribute], bool]) -> "Attributes":
        cloned = Attributes()
        cloned._attrs = {key: attr for key, attr in self._attrs.items() if filter_(attr)}
        return cloned


class BoundedAttributes:
    def __init__(
        self,
        schema: str,
        attrs: Optional[Iterable[Attribute]] = None,
        extension: bool = False,
        extension_required: Optional[bool] = None,
        common_attrs: Optional[Iterable[str]] = None,
    ):
        self._raw_attrs = list(attrs or [])
        self._schema = schema
        self._core_attrs: list[Attribute] = []
        self._extensions: dict[str, BoundedAttributes] = {}
        self._attrs: dict[tuple[str, str], Attribute] = {}
        self._bounded_complex_sub_attrs: dict[int, dict[int, Attribute]] = {}
        self._common_attrs = {item.lower() for item in common_attrs or set()}
        self._extension = extension
        self._extension_required = extension_required

        self._refresh_attrs()

    def __getattr__(self, name: str) -> Attribute:
        parts = name.split("__", 1)
        attr_name = parts[0].lower()
        attr = None
        for attr_ in self._attrs.values():
            if attr_.rep.attr.lower() == attr_name:
                attr = attr_

        if attr is None:
            raise AttributeError(f"no {name!r} attribute")

        if len(parts) == 1:
            return attr

        if not isinstance(attr, Complex):
            raise TypeError(f"{attr.rep.attr!r} is not complex")

        sub_attr = getattr(attr.attrs, parts[1], None)
        if sub_attr is None:
            raise AttributeError(f"{parts[0]!r} has no {parts[1]!r} attribute")

        return self._bounded_complex_sub_attrs[id(attr)][id(sub_attr)]

    def __iter__(self):
        return iter(self._attrs.values())

    def _refresh_attrs(self):
        self._attrs.clear()
        self._core_attrs.clear()
        self._bounded_complex_sub_attrs.clear()

        for attr in self._raw_attrs:
            bounded_attr = attr.clone(
                BoundedAttrRep(
                    self._schema,
                    attr.rep.attr,
                    extension=self._extension,
                    extension_required=self._extension_required,
                )
            )
            self._attrs[bounded_attr.rep.schema, bounded_attr.rep.attr] = bounded_attr

            if bounded_attr.rep.attr.lower() not in self._common_attrs:
                self._core_attrs.append(bounded_attr)

            if isinstance(bounded_attr, Complex):
                self._bounded_complex_sub_attrs[id(bounded_attr)] = {
                    id(sub_attr): sub_attr.clone(
                        BoundedAttrRep(
                            bounded_attr.rep.schema,
                            bounded_attr.rep.attr,
                            sub_attr.rep.attr,
                            extension=bounded_attr.rep.extension,
                            extension_required=bounded_attr.rep.extension_required,
                        )
                    )
                    for sub_attr in bounded_attr.attrs
                }

        for attrs in self._extensions.values():
            for attr in attrs:
                self._attrs[attr.rep.schema, attr.rep.attr] = attr
            self._bounded_complex_sub_attrs.update(attrs._bounded_complex_sub_attrs)

    @property
    def core_attrs(self) -> list[Attribute]:
        return self._core_attrs

    @property
    def extensions(self) -> dict[str, "BoundedAttributes"]:
        return self._extensions

    def extend(self, attrs: Attributes, schema: str, required: bool = False) -> None:
        self._extensions[schema.lower()] = BoundedAttributes(
            schema, attrs, extension=True, extension_required=required
        )
        self._refresh_attrs()

    def clone(self, attr_filter: Callable[[Attribute], bool]) -> "BoundedAttributes":
        cloned = BoundedAttributes(schema=self._schema)
        cloned._raw_attrs = [
            attr.clone(attr_filter=attr_filter) for attr in self._raw_attrs if attr_filter(attr)
        ]
        cloned._extensions = {
            schema: bounded_attrs.clone(attr_filter)
            for schema, bounded_attrs in self._extensions.items()
        }
        cloned._refresh_attrs()
        return cloned

    def get(self, attr_rep: BoundedAttrRep) -> Optional[Attribute]:
        if attr_rep.schema.lower() in self._extensions:
            return self._extensions[attr_rep.schema.lower()].get(attr_rep)

        top_level_rep = BoundedAttrRep(attr_rep.schema, attr_rep.attr)
        attr_obj = None
        for (schema, attr), attr_obj_ in self._attrs.items():
            if BoundedAttrRep(schema, attr) == top_level_rep:
                attr_obj = attr_obj_

        if attr_obj is None or not attr_rep.sub_attr:
            return attr_obj

        if not isinstance(attr_obj, Complex):
            raise TypeError(f"{attr_obj.rep.attr!r} is not complex")

        sub_attr_obj = getattr(attr_obj.attrs, attr_rep.sub_attr, None)
        if sub_attr_obj is None:
            return None

        return self._bounded_complex_sub_attrs[id(attr_obj)][id(sub_attr_obj)]

    def get_by_path(self, path: "PatchPath") -> Optional[Attribute]:
        attr = self.get(path.attr_rep)
        if attr is None or (path.has_filter and not attr.multi_valued):
            return None

        if path.sub_attr_rep is None:
            return attr

        return self.get(
            BoundedAttrRep(
                schema=path.attr_rep.schema,
                attr=path.attr_rep.attr,
                sub_attr=path.sub_attr_rep.attr,
            )
        )
