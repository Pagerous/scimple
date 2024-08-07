import re
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any, Optional, Union, cast

from scimpler.error import ValidationError, ValidationIssues
from scimpler.registry import schemas

_ATTR_NAME = re.compile(r"([a-zA-Z][\w$-]*|\$ref)")
_URI_PREFIX = re.compile(r"(?:[\w.-]+:)*")
_ATTR_REP = re.compile(
    rf"({_URI_PREFIX.pattern})?({_ATTR_NAME.pattern}(\.([a-zA-Z][\w$-]*|\$ref))?)"
)


class AttrName(str):
    def __new__(cls, value: str) -> "AttrName":
        if not isinstance(value, AttrName) and not _ATTR_NAME.fullmatch(value):
            raise ValueError(f"{value!r} is not valid attr name")
        return cast(AttrName, str.__new__(cls, value))

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            other = other.lower()
        return self.lower() == other

    def __hash__(self):
        return hash(self.lower())


class SchemaURI(str):
    def __new__(cls, value: str) -> "SchemaURI":
        if not isinstance(value, SchemaURI) and not _URI_PREFIX.fullmatch(value + ":"):
            raise ValueError(f"{value!r} is not a valid schema URI")
        return cast(SchemaURI, str.__new__(cls, value))

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            other = other.lower()
        return self.lower() == other

    def __hash__(self):
        return hash(self.lower())


class AttrRep:
    def __init__(self, attr: str, sub_attr: Optional[str] = None):
        attr = AttrName(attr)
        str_: str = attr
        if sub_attr is not None:
            sub_attr = AttrName(sub_attr)
            str_ += "." + sub_attr

        self._attr = attr
        self._sub_attr = sub_attr
        self._str = str_

    def __str__(self) -> str:
        return self._str

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({str(self)})"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, AttrRep):
            return False

        return bool(self._attr == other._attr and self._sub_attr == other._sub_attr)

    def __hash__(self):
        return hash((self._attr, self._sub_attr))

    @property
    def attr(self) -> AttrName:
        return self._attr

    @property
    def sub_attr(self) -> AttrName:
        if self._sub_attr is None:
            raise AttributeError(f"{self!r} has no sub-attribute")
        return self._sub_attr

    @property
    def is_sub_attr(self) -> bool:
        return self._sub_attr is not None

    @property
    def location(self) -> tuple[str, ...]:
        if self._sub_attr:
            return self._attr, self._sub_attr
        return (self._attr,)


class BoundedAttrRep(AttrRep):
    def __init__(
        self,
        schema: str,
        attr: str,
        sub_attr: Optional[str] = None,
    ):
        super().__init__(attr, sub_attr)
        schema = SchemaURI(schema)
        is_extension = schemas.get(schema)
        if is_extension is None:
            raise ValueError(f"unknown schema {schema!r}")

        self._str = f"{schema}:{self._str}"
        self._schema = schema
        self._extension = is_extension

    def __eq__(self, other: Any) -> bool:
        parent_equals = super().__eq__(other)
        if not isinstance(other, BoundedAttrRep):
            return parent_equals

        return parent_equals and self._schema == other._schema

    def __hash__(self):
        return hash((self._attr, self._schema, self._sub_attr))

    @property
    def schema(self) -> SchemaURI:
        return self._schema

    @property
    def extension(self) -> bool:
        return self._extension

    @property
    def location(self) -> tuple[str, ...]:
        return ((self._schema,) if self.extension else tuple()) + super().location


class AttrRepFactory:
    @classmethod
    def validate(cls, value: str) -> ValidationIssues:
        issues = ValidationIssues()
        match = _ATTR_REP.fullmatch(value)
        if match is not None:
            schema = match.group(1)
            schema = schema[:-1] if schema else ""
            if not schema or SchemaURI(schema) in schemas:
                return issues
        issues.add_error(
            issue=ValidationError.bad_attribute_name(value),
            proceed=False,
        )
        return issues

    @classmethod
    def deserialize(cls, value: str) -> Union[AttrRep, BoundedAttrRep]:
        try:
            return cls._deserialize(value)
        except Exception as e:
            raise ValueError(f"{value!r} is not valid attribute representation") from e

    @classmethod
    def _deserialize(cls, value: str) -> Union[AttrRep, BoundedAttrRep]:
        if isinstance(value, AttrName):
            return AttrRep(attr=value)

        match = _ATTR_REP.fullmatch(value)
        if match is None:
            raise

        schema, attr = match.group(1), match.group(2)
        schema = schema[:-1] if schema else ""
        if "." in attr:
            attr, sub_attr = attr.split(".")
        else:
            attr, sub_attr = attr, None
        if schema:
            return BoundedAttrRep(
                schema=schema,
                attr=attr,
                sub_attr=sub_attr,
            )
        return AttrRep(attr=attr, sub_attr=sub_attr)


class InvalidType:
    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "Invalid"


Invalid = InvalidType()


class MissingType:
    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "Missing"


Missing = MissingType()


@dataclass
class _SchemaKey:
    schema: str


@dataclass
class _AttrKey:
    attr: str
    sub_attr: Optional[str]


@dataclass
class _BoundedAttrKey(_AttrKey):
    schema: str
    extension: bool


class SCIMData(MutableMapping):
    def __init__(
        self, d: Optional[Union[Mapping[str, Any], Mapping[AttrRep, Any], "SCIMData"]] = None
    ):
        self._data: dict[str, Any] = {}
        self._lower_case_to_original: dict[str, str] = {}

        if isinstance(d, SCIMData):
            self._data = d._data
            self._lower_case_to_original = d._lower_case_to_original
        elif isinstance(d, Mapping):
            for key, value in d.items():
                if isinstance(key, AttrRep):
                    self.set(key, value)

                if not isinstance(key, str):
                    continue

                if original_key := self._lower_case_to_original.get(key.lower()):
                    self._data.pop(original_key, None)
                self._lower_case_to_original[key.lower()] = key
                if isinstance(value, Mapping):
                    self._data[key] = SCIMData(value)
                elif isinstance(value, list):
                    self._data[key] = [
                        SCIMData(item) if isinstance(item, Mapping) else item for item in value
                    ]
                else:
                    self._data[key] = value

    def __repr__(self):
        return f"{self.__class__.__name__}({str(self._data)})"

    def __getitem__(self, key: Union[str, AttrRep, _SchemaKey, _AttrKey]):
        value = self.get(key)
        if value is Missing:
            raise KeyError(key)
        return value

    def __setitem__(self, key: Union[str, AttrRep, _SchemaKey, _AttrKey], value: Any):
        self.set(key, value)

    def __delitem__(self, key: Union[str, AttrRep, _SchemaKey, _AttrKey]):
        value = self.pop(key)
        if value is Missing:
            raise KeyError(key)

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self):
        return iter(self._data)

    def set(
        self,
        key: Union[str, AttrRep, _SchemaKey, _AttrKey],
        value: Any,
    ) -> None:
        if not isinstance(key, (_SchemaKey, _AttrKey)):
            key = self._normalize(key)

        if isinstance(key, _SchemaKey):
            extension = self._lower_case_to_original.get(key.schema.lower())
            if extension is None:
                extension = key.schema
                self._lower_case_to_original[key.schema.lower()] = key.schema
            self._data[extension] = value
            return

        elif isinstance(key, _BoundedAttrKey) and key.extension:
            extension = self._lower_case_to_original.get(key.schema.lower())
            if extension is None:
                extension = key.schema
                self._lower_case_to_original[key.schema.lower()] = extension
                self._data[extension] = SCIMData()
            self._data[extension].set(_AttrKey(attr=key.attr, sub_attr=key.sub_attr), value)
            return

        if not key.sub_attr:
            if original_key := self._lower_case_to_original.get(key.attr.lower()):
                self._data.pop(original_key, None)
            self._lower_case_to_original[key.attr.lower()] = key.attr
            self._data[key.attr] = value
            return

        parent_attr_key = self._lower_case_to_original.get(key.attr.lower())
        if parent_attr_key is None:
            parent_attr_key = key.attr
            self._lower_case_to_original[parent_attr_key.lower()] = parent_attr_key
            self._data[parent_attr_key] = SCIMData()

        parent_value = self._data[self._lower_case_to_original[parent_attr_key.lower()]]
        if not self._is_child_value_compatible(parent_value, value):
            raise KeyError(f"can not assign ({key.sub_attr}, {value}) to '{key.attr}'")

        if not isinstance(value, list):
            self._data[parent_attr_key].set(_AttrKey(attr=key.sub_attr, sub_attr=None), value)
            return

        self._data[parent_attr_key].set(_AttrKey(attr=key.sub_attr, sub_attr=None), value)

    def get(self, key: Union[str, AttrRep, _SchemaKey, _AttrKey], default: Any = Missing) -> Any:
        if not isinstance(key, (_SchemaKey, _AttrKey)):
            key = self._normalize(key)

        if isinstance(key, _SchemaKey):
            extension = self._lower_case_to_original.get(key.schema.lower())
            if extension is None:
                return default
            return self._data.get(extension, default)

        if isinstance(key, _BoundedAttrKey) and key.extension:
            extension = self._lower_case_to_original.get(key.schema.lower())
            if extension is None:
                return default
            return self._data[extension].get(_AttrKey(attr=key.attr, sub_attr=key.sub_attr))

        attr = self._lower_case_to_original.get(key.attr.lower())
        if attr is None:
            return default

        if key.sub_attr:
            attr_value = self._data[attr]
            if isinstance(attr_value, SCIMData):
                return attr_value.get(_AttrKey(attr=key.sub_attr, sub_attr=None))
            if isinstance(attr_value, list):
                return [
                    item.get(_AttrKey(attr=key.sub_attr, sub_attr=None))
                    if isinstance(item, SCIMData)
                    else default
                    for item in attr_value
                ]
            return default
        return self._data.get(attr, default)

    def pop(self, key: Union[str, AttrRep, _SchemaKey, _AttrKey], default: Any = Missing) -> Any:
        if not isinstance(key, (_SchemaKey, _AttrKey)):
            key = self._normalize(key)

        if isinstance(key, _SchemaKey):
            extension = self._lower_case_to_original.get(key.schema.lower())
            if extension is None:
                return default
            return self._data.pop(extension, default)

        elif isinstance(key, _BoundedAttrKey) and key.extension:
            extension = self._lower_case_to_original.get(key.schema.lower())
            if extension is None:
                return default
            return self._data[extension].pop(
                _AttrKey(attr=key.attr, sub_attr=key.sub_attr), default
            )

        attr = self._lower_case_to_original.get(key.attr.lower())
        if attr is None:
            return default

        if key.sub_attr:
            attr_value = self._data[attr]
            if isinstance(attr_value, SCIMData):
                return attr_value.pop(key.sub_attr, default)
            elif isinstance(attr_value, list):
                return [
                    item.pop(key.sub_attr, default) if isinstance(item, SCIMData) else default
                    for item in attr_value
                ]
            return default

        self._lower_case_to_original.pop(key.attr.lower())
        return self._data.pop(attr, default)

    @staticmethod
    def _normalize(value: Union[str, AttrRep]) -> Union[_SchemaKey, _AttrKey]:
        if isinstance(value, SchemaURI):
            return _SchemaKey(schema=str(value))

        if isinstance(value, str):
            try:
                value = SchemaURI(value)
                if value in schemas:
                    return _SchemaKey(schema=str(value))
            except ValueError:
                pass
            value = AttrRepFactory.deserialize(value)

        if isinstance(value, BoundedAttrRep):
            return _BoundedAttrKey(
                schema=str(value.schema),
                attr=str(value.attr),
                sub_attr=value.sub_attr if value.is_sub_attr else None,
                extension=value.extension,
            )
        return _AttrKey(
            attr=str(value.attr),
            sub_attr=str(value.sub_attr) if value.is_sub_attr else None,
        )

    @staticmethod
    def _is_child_value_compatible(
        parent_value: Any,
        child_value: Any,
    ) -> bool:
        if isinstance(parent_value, list):
            if not isinstance(child_value, list):
                return False
            return True

        if not isinstance(parent_value, SCIMData):
            return False

        return True

    def to_dict(self) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in self._data.items():
            if isinstance(value, SCIMData):
                output[key] = value.to_dict()
            elif isinstance(value, list):
                value_output = []
                for item in value:
                    if isinstance(item, SCIMData):
                        value_output.append(item.to_dict())
                    elif isinstance(item, dict):
                        value_output.append(
                            {
                                k: v.to_dict() if isinstance(v, SCIMData) else v
                                for k, v in item.items()
                            }
                        )
                    else:
                        value_output.append(item)
                output[key] = value_output
            else:
                output[key] = value
        return output

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Mapping):
            other = SCIMData(other)

        if not isinstance(other, SCIMData):
            return False

        if len(self) != len(other):
            return False

        for key, value in self._data.items():
            if other.get(key) == value:
                continue

            return other.get(SchemaURI(key)) == value

        return True
