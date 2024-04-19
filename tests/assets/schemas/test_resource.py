from copy import deepcopy

from src.assets.schemas import user
from src.data.container import SCIMDataContainer
from src.data.schemas import validate_resource_type_consistency, validate_schemas_field


def test_correct_user_data_can_be_parsed(user_data_client):
    expected_data = deepcopy(user_data_client)
    user_data_client["unexpected"] = 123

    data = user.User.parse(user_data_client)

    assert data.to_dict() == expected_data
    assert "unexpected" not in data.to_dict()


def test_validation_fails_if_bad_types(user_data_client):
    user_data_client["userName"] = 123  # noqa
    user_data_client["name"]["givenName"] = 123  # noqa
    expected_issues = {
        "userName": {
            "_errors": [
                {
                    "code": 2,
                }
            ]
        },
        "name": {
            "givenName": {
                "_errors": [
                    {
                        "code": 2,
                    }
                ]
            }
        },
    }

    issues = user.User.validate(user_data_client)

    assert issues.to_dict() == expected_issues


def test_validate_schemas_field__unknown_additional_field_is_validated(user_data_client):
    user_data_client["schemas"].append("bad:user:schema")
    expected_issues = {"schemas": {"_errors": [{"code": 27}]}}
    schema = user.User

    issues = validate_schemas_field(
        SCIMDataContainer(user_data_client),
        schemas_=user_data_client["schemas"],
        main_schema=schema.schema,
        known_schemas=schema.schemas,
    )

    assert issues.to_dict() == expected_issues


def test_validate_schemas_field__fails_if_main_schema_is_missing(user_data_client):
    user_data_client["schemas"] = ["urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"]
    expected_issues = {"schemas": {"_errors": [{"code": 28}]}}
    schema = user.User

    issues = validate_schemas_field(
        SCIMDataContainer(user_data_client),
        schemas_=user_data_client["schemas"],
        main_schema=schema.schema,
        known_schemas=schema.schemas,
    )

    assert issues.to_dict() == expected_issues


def test_validate_schemas_field__fails_if_extension_schema_is_missing(user_data_client):
    user_data_client["schemas"] = ["urn:ietf:params:scim:schemas:core:2.0:User"]
    expected_issues = {"schemas": {"_errors": [{"code": 29}]}}
    schema = user.User

    issues = validate_schemas_field(
        SCIMDataContainer(user_data_client),
        schemas_=user_data_client["schemas"],
        main_schema=schema.schema,
        known_schemas=schema.schemas,
    )

    assert issues.to_dict() == expected_issues


def test_validate_schemas_field__multiple_errors(user_data_client):
    user_data_client["schemas"] = ["bad:user:schema"]
    expected_issues = {"schemas": {"_errors": [{"code": 27}, {"code": 28}, {"code": 29}]}}
    schema = user.User

    issues = validate_schemas_field(
        SCIMDataContainer(user_data_client),
        schemas_=user_data_client["schemas"],
        main_schema=schema.schema,
        known_schemas=schema.schemas,
    )

    assert issues.to_dict() == expected_issues


def test_validate_resource_type_consistency__fails_if_no_consistency():
    expected = {
        "meta": {
            "resourceType": {
                "_errors": [
                    {
                        "code": 17,
                    }
                ]
            }
        }
    }

    issues = validate_resource_type_consistency("Group", "User")

    assert issues.to_dict() == expected


def test_validate_resource_type_consistency__succeeds_if_consistency():
    issues = validate_resource_type_consistency("User", "User")

    assert issues.to_dict(msg=True) == {}