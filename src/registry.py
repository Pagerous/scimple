from typing import TYPE_CHECKING, Any, Callable, Union

if TYPE_CHECKING:
    from src.container import SchemaURI
    from src.data.operator import BinaryAttributeOperator, UnaryAttributeOperator
    from src.data.schemas import ResourceSchema, BaseSchema, SchemaExtension


resources: dict[str, "ResourceSchema"] = {}
schemas: dict[str, Union["BaseSchema", "SchemaExtension"]] = {}


def register_resource_schema(resource_schema: "ResourceSchema"):
    if resource_schema.name in resources:
        raise RuntimeError(f"resource {resource_schema.name!r} already registered")
    resources[resource_schema.name] = resource_schema


def register_schema(schema_uri: "SchemaURI", schema_or_extension: Union["BaseSchema", "SchemaExtension"]):
    schemas[schema_uri] = schema_or_extension


Converter = Callable[[Any], Any]


unary_operators: dict[str, type["UnaryAttributeOperator"]] = {}
binary_operators: dict[str, type["BinaryAttributeOperator"]] = {}


def register_unary_operator(operator: type["UnaryAttributeOperator"]):
    op = operator.op().lower()

    if op in unary_operators:
        raise RuntimeError(f"unary operator {op!r} already registered")

    unary_operators[op] = operator


def register_binary_operator(operator: type["BinaryAttributeOperator"]):
    op = operator.op().lower()
    if op in binary_operators:
        raise RuntimeError(f"binary operator {op!r} already registered")

    binary_operators[op] = operator
