from typing import Iterable, Optional, cast

from marshmallow import Schema, fields, post_dump

from src.assets.schemas import ListResponse
from src.container import AttrName, BoundedAttrRep, AttrRep
from src.data.attrs import (
    Attribute,
    AttributeReturn,
    Binary,
    Boolean,
    Complex,
    DateTime,
    Decimal,
    ExternalReference,
    Integer,
    SCIMReference,
    String,
    Unknown,
    URIReference,
)
from src.request.validator import Validator


_marshmallow_field_by_attr_type = {
    Unknown: fields.Raw,
    Boolean: fields.Boolean,
    Integer: fields.Integer,
    Decimal: fields.Float,
    DateTime: fields.DateTime,
    Binary: fields.String,
    ExternalReference: fields.String,
    URIReference: fields.String,
    SCIMReference: fields.String,
    String: fields.String,
}


def _get_fields(
    attrs: Iterable[tuple[BoundedAttrRep, Attribute]],
    field_by_attr_rep: Optional[dict[AttrRep, fields.Field]] = None,
) -> dict[str, fields.Field]:
    field_by_attr_rep = field_by_attr_rep or {}
    fields_: dict[str, fields.Field] = {}
    for attr_rep, attr in attrs:
        if attr_rep in field_by_attr_rep:
            field = field_by_attr_rep[attr_rep]
        else:
            kwargs = _get_kwargs(attr)
            if attr.multi_valued:
                field = fields.List(_get_field(attr), **kwargs)
            else:
                field = _get_field(attr, **kwargs)
        fields_[attr_rep.attr] = field
    return fields_


def _get_complex_sub_fields(
    attrs: Iterable[tuple[AttrName, Attribute]],
    field_by_attr_name: Optional[dict[str, fields.Field]] = None,
) -> dict[str, fields.Field]:
    field_by_attr_name = field_by_attr_name or {}
    fields_: dict[str, fields.Field] = {}
    for name, attr in attrs:
        if name in field_by_attr_name:
            field = field_by_attr_name[name]
        else:
            kwargs = _get_kwargs(attr)
            if attr.multi_valued:
                field = fields.List(_get_field(attr), **kwargs)
            else:
                field = _get_field(attr, **kwargs)
        fields_[name] = field
    return fields_


def _get_field(attr, **kwargs):
    if isinstance(attr, Complex):
        return fields.Nested(_get_complex_sub_fields(attr.attrs))
    return _marshmallow_field_by_attr_type[type(attr)](**kwargs)


def _get_kwargs(attr: Attribute):
    return {"required": attr.returned == AttributeReturn.ALWAYS}


def _apply_validator_on_schema(schema, validator: Validator):
    def _post_dump(self, data, **kwargs):
        context_ = {k: v() if callable(v) else v for k, v in self.context.items()}
        issues = validator.validate_response(
            status_code=context_.get("status_code"),
            body=data,
            headers=context_.get("headers", {}),
            **context_,
        )
        return data

    class_ = type(
        schema.__name__, (schema,), {"_post_dump": post_dump(_post_dump, pass_many=False)}
    )
    return class_


def response_serializer(validator: Validator):
    scimple_schema = validator.response_schema
    if isinstance(scimple_schema, ListResponse) and len(scimple_schema.contained_schemas) == 1:
        resources_attr = cast(Attribute, scimple_schema.attrs.get("resources"))
        base_fields = _get_fields(
            scimple_schema.attrs.core_attrs,
            field_by_attr_rep={
                scimple_schema.attrs.resources: fields.List(
                    fields.Nested(_get_fields(scimple_schema.contained_schemas[0].attrs)),
                    **_get_kwargs(resources_attr),
                )
            },
        )
    else:
        base_fields = _get_fields(scimple_schema.attrs.core_attrs)
    extension_fields = {
        str(extension_name): fields.Nested(_get_fields(attrs))
        for extension_name, attrs in scimple_schema.attrs.extensions.items()
    }
    schema = Schema.from_dict(
        fields={**base_fields, **extension_fields},
        name=scimple_schema.__class__.__name__,
    )
    return _apply_validator_on_schema(schema, validator)
