import functools
from collections.abc import MutableMapping
from typing import Any, Generic, Optional, Sequence, TypeVar, Union, cast

from typing_extensions import Self

from scimpler.container import AttrRep, Missing, SCIMData
from scimpler.data.attrs import Attribute, AttributeWithCaseExact, Complex, String
from scimpler.data.schemas import BaseResourceSchema


class AlwaysLastKey:
    def __lt__(self, _):
        return False

    def __gt__(self, _):
        return True


class StringKey:
    def __init__(self, value: str, attr: Attribute):
        self._value = value
        self._attr = attr

    def __lt__(self, other):
        if not isinstance(other, StringKey):
            if isinstance(other, AlwaysLastKey):
                return True
            raise TypeError(
                f"'<' not supported between instances of 'StringKey' and '{type(other).__name__}'"
            )

        value = self._value
        other_value = other._value

        if isinstance(self._attr, String):
            value = self._attr.precis.enforce(value)
        if isinstance(other._attr, String):
            other_value = other._attr.precis.enforce(other_value)

        if (
            isinstance(self._attr, AttributeWithCaseExact)
            and self._attr.case_exact
            or isinstance(other._attr, AttributeWithCaseExact)
            and other._attr.case_exact
        ):
            return value < other_value

        return value.lower() < other_value.lower()


TData = TypeVar("TData", bound=Union[list[SCIMData], list[dict[str, Any]]])
TAttrRep = TypeVar("TAttrRep", bound=AttrRep)


class Sorter(Generic[TAttrRep]):
    def __init__(self, attr_rep: TAttrRep, asc: bool = True):
        self._attr_rep = attr_rep
        self._asc = asc
        self._default_value = AlwaysLastKey()

    @property
    def attr_rep(self) -> TAttrRep:
        return self._attr_rep

    @property
    def asc(self) -> bool:
        return self._asc

    @classmethod
    def from_data(cls, data: MutableMapping) -> Optional[Self]:
        if sort_by := data.get("sortBy"):
            return cls(
                attr_rep=sort_by,
                asc=data.get("sortOrder") == "ascending",
            )
        return None

    def __call__(
        self,
        data: TData,
        schema: Union[BaseResourceSchema, Sequence[BaseResourceSchema]],
    ) -> TData:
        if not data:
            return data
        normalized = [SCIMData(item) for item in data]
        if isinstance(data[0], dict):
            return cast(TData, [item.to_dict() for item in self._sort(normalized, schema)])
        return cast(TData, self._sort(normalized, schema))

    def _sort(
        self,
        data: list[SCIMData],
        schema: Union[BaseResourceSchema, Sequence[BaseResourceSchema]],
    ) -> list[SCIMData]:
        if not any(item.get(self._attr_rep) for item in data):
            return data

        if not isinstance(schema, BaseResourceSchema) and len(set(schema)) == 1:
            schema = schema[0]
        if isinstance(schema, BaseResourceSchema):
            key = functools.partial(self._attr_key, schema=schema)
        else:
            key = self._attr_key_many_schemas(data, schema)
        return sorted(data, key=key, reverse=not self._asc)

    def _get_key(self, value: Any, attr: Optional[Attribute]):
        if not value or attr is None:
            return self._default_value

        if not isinstance(value, str):
            return value

        if str not in attr.base_types():
            return self._default_value

        return StringKey(value, attr)

    def _attr_key_many_schemas(self, data: list[SCIMData], schemas: Sequence[BaseResourceSchema]):
        def attr_key(item):
            schema = schemas[data.index(item)]
            return self._attr_key(item, schema)

        return attr_key

    def _attr_key(self, item: SCIMData, schema: BaseResourceSchema):
        attr = schema.attrs.get(self._attr_rep)
        if attr is None:
            return self._get_key(None, None)

        value = None
        item_value = item.get(self._attr_rep)
        if item_value is not Missing and attr.multi_valued:
            if isinstance(attr, Complex):
                attr = attr.attrs.get("value")
                for i, v in enumerate(item_value):
                    if i == 0:
                        value = v.get("value")
                    elif v.get("primary") is True:
                        value = v.get("value")
                        break
            else:
                value = item_value[0]
        else:
            value = item_value
        return self._get_key(value, attr)
