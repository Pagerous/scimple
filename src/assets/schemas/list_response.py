from typing import Any, Optional, Sequence, Union

from src.container import Invalid, Missing, SCIMDataContainer, SchemaURI
from src.data.attr_presence import AttrPresenceConfig
from src.data.attrs import Integer, Unknown
from src.data.schemas import BaseResourceSchema, BaseSchema
from src.error import ValidationError, ValidationIssues
from src.registry import schemas


def _validate_resources_type(value) -> ValidationIssues:
    issues = ValidationIssues()
    for i, item in enumerate(value):
        if not isinstance(item, SCIMDataContainer):
            issues.add_error(
                issue=ValidationError.bad_type("complex"),
                proceed=True,
                location=[i],
            )
            value[i] = Invalid
    return issues


def _serialize_resources(value: Sequence[Any]) -> list[dict[str, Any]]:
    serialized = []
    for resource in value:
        if not isinstance(resource, SCIMDataContainer):
            serialized.append({})
            continue

        schema_uris = resource.get("schemas")
        if not isinstance(schema_uris, list) or len(schema_uris) < 1:
            serialized.append({})
            continue

        for schema_uri in schema_uris:
            if (schema := schemas.get(SchemaURI(schema_uri))) is not None and isinstance(schema, BaseSchema):
                serialized.append(schema.serialize(resource))
                break
        else:
            serialized.append({})
    return serialized


class ListResponse(BaseSchema):
    def __init__(self, resource_schemas: Sequence[BaseResourceSchema]):
        super().__init__(
            schema="urn:ietf:params:scim:api:messages:2.0:ListResponse",
            attrs=[
                Integer("totalResults", required=True),
                Integer("startIndex"),
                Integer("itemsPerPage"),
                Unknown(
                    name="Resources",
                    multi_valued=True,
                    validators=[_validate_resources_type],
                    serializer=_serialize_resources,
                ),
            ],
        )
        self._contained_schemas = list(resource_schemas)

    @property
    def contained_schemas(self) -> list[BaseResourceSchema]:
        return self._contained_schemas

    def _validate(self, data: SCIMDataContainer, **kwargs) -> ValidationIssues:
        issues = ValidationIssues()

        resources_rep = self.attrs.resources
        resources = data.get(resources_rep)
        if resources in [Missing, Invalid]:
            return issues

        if (items_per_page_ := data.get(self.attrs.itemsperpage)) is not Invalid:
            issues.merge(
                validate_items_per_page_consistency(
                    resources_=resources,
                    items_per_page_=items_per_page_,
                )
            )

        resource_presence_config = kwargs.get("resource_presence_config")
        if resource_presence_config is None:
            resource_presence_config = AttrPresenceConfig("RESPONSE")

        resource_schemas = self.get_schemas_for_resources(resources)
        for i, (resource, schema) in enumerate(zip(resources, resource_schemas)):
            if resource is Invalid:
                continue

            resource_location: tuple[Union[str, int], ...] = (*resources_rep.location, i)
            if schema is None:
                issues.add_error(
                    issue=ValidationError.unknown_schema(),
                    proceed=False,
                    location=resource_location,
                )
                continue

            issues.merge(
                issues=schema.validate(resource, resource_presence_config),
                location=resource_location,
            )
        return issues

    def get_schemas_for_resources(
        self,
        resources: list[Any],
    ) -> list[Optional[BaseResourceSchema]]:
        resource_schemas: list[Optional[BaseResourceSchema]] = []
        n_schemas = len(self._contained_schemas)
        for resource in resources:
            if isinstance(resource, dict):
                resource = SCIMDataContainer(resource)
            if not isinstance(resource, SCIMDataContainer):
                resource_schemas.append(None)
            elif n_schemas == 1:
                resource_schemas.append(self._contained_schemas[0])
            else:
                resource_schemas.append(self._infer_schema_from_data(resource))
        return resource_schemas

    def _infer_schema_from_data(self, data: SCIMDataContainer) -> Optional[BaseResourceSchema]:
        schemas_value = data.get("schemas")
        if isinstance(schemas_value, list) and len(schemas_value) > 0:
            schemas_value = {
                item.lower() if isinstance(item, str) else item for item in schemas_value
            }
            for schema in self._contained_schemas:
                if schema.schema in schemas_value:
                    return schema
        return None


def validate_items_per_page_consistency(
    resources_: list[Any], items_per_page_: Any
) -> ValidationIssues:
    issues = ValidationIssues()
    if not isinstance(items_per_page_, int):
        return issues

    n_resources = len(resources_)
    if items_per_page_ != n_resources:
        issues.add_error(
            issue=ValidationError.must_be_equal_to(value="number of resources"),
            location=["itemsPerPage"],
            proceed=True,
        )
        issues.add_error(
            issue=ValidationError.must_be_equal_to("itemsPerPage"),
            location=["Resources"],
            proceed=True,
        )
    return issues
