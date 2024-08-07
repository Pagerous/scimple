from typing import Optional

from scimpler import registry
from scimpler.config import ServiceProviderConfig
from scimpler.container import AttrName, AttrRep, AttrRepFactory, Missing, SCIMData
from scimpler.data.attrs import Attribute, Integer, String
from scimpler.data.filter import Filter
from scimpler.data.schemas import AttrFilter, BaseSchema
from scimpler.error import ValidationError, ValidationIssues


def _validate_attr_reps(value: list[str]) -> ValidationIssues:
    issues = ValidationIssues()
    for i, item in enumerate(value):
        issues.merge(issues=AttrRepFactory.validate(item), location=(i,))
    return issues


def _deserialize_attr_reps(value: list[str]) -> list[AttrRep]:
    return [AttrRepFactory.deserialize(item.strip()) for item in value]


def _serialize_attr_reps(value: list[AttrRep]) -> list[str]:
    return [str(item) for item in value]


def _process_start_index(value: int) -> int:
    if value < 1:
        value = 1
    return value


def _process_count(value: int) -> int:
    if value < 0:
        value = 0
    return value


class SearchRequestSchema(BaseSchema):
    schema = "urn:ietf:params:scim:api:messages:2.0:SearchRequest"
    base_attrs: list[Attribute] = [
        String(
            name="attributes",
            multi_valued=True,
            validators=[_validate_attr_reps],
            deserializer=_deserialize_attr_reps,
            serializer=_serialize_attr_reps,
        ),
        String(
            name="excludeAttributes",
            multi_valued=True,
            validators=[_validate_attr_reps],
            deserializer=_deserialize_attr_reps,
            serializer=_serialize_attr_reps,
        ),
        String(
            name="filter",
            validators=[Filter.validate],
            deserializer=Filter.deserialize,
            serializer=lambda f: f.serialize(),
        ),
        String(
            name="sortBy",
            validators=[AttrRepFactory.validate],
            deserializer=AttrRepFactory.deserialize,
            serializer=lambda value: str(value),
        ),
        String(
            name="sortOrder",
            canonical_values=["ascending", "descending"],
        ),
        Integer(
            name="startIndex",
            serializer=_process_start_index,
            deserializer=_process_start_index,
        ),
        Integer(name="count", serializer=_process_count, deserializer=_process_count),
    ]

    def __init__(self, attr_filter: Optional[AttrFilter] = None):
        super().__init__(attr_filter=attr_filter)

    @classmethod
    def from_config(cls, config: Optional[ServiceProviderConfig] = None) -> "SearchRequestSchema":
        exclude = set()
        config = config or registry.service_provider_config
        if not config.filter.supported:
            exclude.add(AttrName("filter"))
        if not config.sort.supported:
            exclude.add(AttrName("sortBy"))
            exclude.add(AttrName("sortOrder"))
        return cls(attr_filter=AttrFilter(attr_names=exclude, include=False))

    def _validate(self, data: SCIMData, **kwargs) -> ValidationIssues:
        issues = ValidationIssues()
        to_include = data.get("attributes")
        to_exclude = data.get("excludeAttributes")
        if to_include not in [None, Missing] and to_exclude not in [None, Missing]:
            issues.add_error(
                issue=ValidationError.can_not_be_used_together("attributes"),
                proceed=False,
                location=["attributes"],
            )
            issues.add_error(
                issue=ValidationError.can_not_be_used_together("excludeAttributes"),
                proceed=False,
                location=["excludeAttributes"],
            )
        return issues
