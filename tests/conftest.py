from copy import deepcopy
from datetime import datetime

import pytest

from src.assets.config import create_service_provider_config
from src.data import type as at
from src.data.attributes import Attribute, ComplexAttribute
from src.data.schemas import ResourceSchema


@pytest.fixture
def user_data_client():
    return {
        "schemas": [
            "urn:ietf:params:scim:schemas:core:2.0:User",
            "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User",
        ],
        "externalId": "1",
        "userName": "bjensen@example.com",
        "name": {
            "formatted": "Ms. Barbara J Jensen, III",
            "familyName": "Jensen",
            "givenName": "Barbara",
            "middleName": "Jane",
            "honorificPrefix": "Ms.",
            "honorificSuffix": "III",
        },
        "displayName": "Babs Jensen",
        "nickName": "Babs",
        "profileUrl": "https://login.example.com/bjensen",
        "emails": [
            {"value": "bjensen@example.com", "type": "work", "primary": True},
            {"value": "babs@jensen.org", "type": "home"},
        ],
        "addresses": [
            {
                "streetAddress": "100 Universal City Plaza",
                "locality": "Hollywood",
                "region": "CA",
                "postalCode": "91608",
                "country": "USA",
                "formatted": "100 Universal City Plaza\nHollywood, CA 91608 USA",
                "type": "work",
            },
            {
                "streetAddress": "456 Hollywood Blvd",
                "locality": "Hollywood",
                "region": "CA",
                "postalCode": "91608",
                "country": "USA",
                "formatted": "456 Hollywood Blvd\nHollywood, CA 91608 USA",
                "type": "home",
            },
        ],
        "phoneNumbers": [
            {"value": "555-555-5555", "type": "work"},
            {"value": "555-555-4444", "type": "mobile"},
        ],
        "ims": [{"value": "someaimhandle", "type": "aim"}],
        "photos": [
            {"value": "https://photos.example.com/profilephoto/72930000000Ccne/F", "type": "photo"},
            {
                "value": "https://photos.example.com/profilephoto/72930000000Ccne/T",
                "type": "thumbnail",
            },
        ],
        "userType": "Employee",
        "title": "Tour Guide",
        "preferredLanguage": "en-US",
        "locale": "en-US",
        "timezone": "America/Los_Angeles",
        "active": True,
        "password": "t1meMa$heen",
        "groups": [
            {
                "value": "e9e30dba-f08f-4109-8486-d5c6a331660a",
                "$ref": "../Groups/e9e30dba-f08f-4109-8486-d5c6a331660a",
                "display": "Tour Guides",
            },
            {
                "value": "fc348aa8-3835-40eb-a20b-c726e15c55b5",
                "$ref": "../Groups/fc348aa8-3835-40eb-a20b-c726e15c55b5",
                "display": "Employees",
            },
            {
                "value": "71ddacd2-a8e7-49b8-a5db-ae50d0a5bfd7",
                "$ref": "../Groups/71ddacd2-a8e7-49b8-a5db-ae50d0a5bfd7",
                "display": "US Employees",
            },
        ],
        "x509Certificates": [
            {
                "value": (
                    "MIIDQzCCAqygAwIBAgICEAAwDQYJKoZIhvcNAQEFBQAwTjELMAkGA1UEBhMCVVMx"
                    "EzARBgNVBAgMCkNhbGlmb3JuaWExFDASBgNVBAoMC2V4YW1wbGUuY29tMRQwEgYD"
                    "VQQDDAtleGFtcGxlLmNvbTAeFw0xMTEwMjIwNjI0MzFaFw0xMjEwMDQwNjI0MzFa"
                    "MH8xCzAJBgNVBAYTAlVTMRMwEQYDVQQIDApDYWxpZm9ybmlhMRQwEgYDVQQKDAtl"
                    "eGFtcGxlLmNvbTEhMB8GA1UEAwwYTXMuIEJhcmJhcmEgSiBKZW5zZW4gSUlJMSIw"
                    "IAYJKoZIhvcNAQkBFhNiamVuc2VuQGV4YW1wbGUuY29tMIIBIjANBgkqhkiG9w0B"
                    "AQEFAAOCAQ8AMIIBCgKCAQEA7Kr+Dcds/JQ5GwejJFcBIP682X3xpjis56AK02bc"
                    "1FLgzdLI8auoR+cC9/Vrh5t66HkQIOdA4unHh0AaZ4xL5PhVbXIPMB5vAPKpzz5i"
                    "PSi8xO8SL7I7SDhcBVJhqVqr3HgllEG6UClDdHO7nkLuwXq8HcISKkbT5WFTVfFZ"
                    "zidPl8HZ7DhXkZIRtJwBweq4bvm3hM1Os7UQH05ZS6cVDgweKNwdLLrT51ikSQG3"
                    "DYrl+ft781UQRIqxgwqCfXEuDiinPh0kkvIi5jivVu1Z9QiwlYEdRbLJ4zJQBmDr"
                    "SGTMYn4lRc2HgHO4DqB/bnMVorHB0CC6AV1QoFK4GPe1LwIDAQABo3sweTAJBgNV"
                    "HRMEAjAAMCwGCWCGSAGG+EIBDQQfFh1PcGVuU1NMIEdlbmVyYXRlZCBDZXJ0aWZp"
                    "Y2F0ZTAdBgNVHQ4EFgQU8pD0U0vsZIsaA16lL8En8bx0F/gwHwYDVR0jBBgwFoAU"
                    "dGeKitcaF7gnzsNwDx708kqaVt0wDQYJKoZIhvcNAQEFBQADgYEAA81SsFnOdYJt"
                    "Ng5Tcq+/ByEDrBgnusx0jloUhByPMEVkoMZ3J7j1ZgI8rAbOkNngX8+pKfTiDz1R"
                    "C4+dx8oU6Za+4NJXUjlL5CvV6BEYb1+QAEJwitTVvxB/A67g42/vzgAtoRUeDov1"
                    "+GFiBZ+GNF/cAYKcMtGcrs2i97ZkJMo="
                )
            }
        ],
        "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
            "employeeNumber": "1",
            "costCenter": "4130",
            "organization": "Universal Studios",
            "division": "Theme Park",
            "department": "Tour Operations",
            "manager": {
                "value": "26118915-6090-4610-87e4-49d8ca9f808d",
                "$ref": "../Users/26118915-6090-4610-87e4-49d8ca9f808d",
                "displayName": "John Smith",
            },
        },
    }


@pytest.fixture
def user_data_server(user_data_client):
    data = deepcopy(user_data_client)
    data["id"] = "2819c223-7f76-453a-919d-413861904646"
    data["meta"] = {
        "resourceType": "User",
        "created": "2010-01-23T04:56:22Z",
        "lastModified": "2011-05-13T04:42:34Z",
        "version": r'W\/"3694e05e9dff591"',
        "location": "https://example.com/v2/Users/2819c223-7f76-453a-919d-413861904646",
    }
    data.pop("password")
    return data


@pytest.fixture
def list_user_data(user_data_server):
    resources = [deepcopy(user_data_server), deepcopy(user_data_server)]
    resources[0]["urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"]["manager"][
        "displayName"
    ] = "Jan Kowalski"
    resources[1]["id"] = "2819c223-7f76-453a-919d-413861904645"
    resources[1]["externalId"] = "2"
    resources[1]["userName"] = "sven"
    resources[1]["name"]["formatted"] = "Ms. Barbara J Sven III"
    resources[1]["name"]["familyName"] = "Sven"
    resources[1]["emails"] = [
        {
            "value": "sven@example.com",
            "type": "work",
            "primary": True,
        },
        {
            "value": "babs@sven.org",
            "type": "home",
        },
    ]
    resources[1]["urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"][
        "employeeNumber"
    ] = "2"
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": 2,
        "startIndex": 1,
        "Resources": resources,
    }


@pytest.fixture
def error_data():
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
        "status": "400",
        "scimType": "tooMany",
        "detail": "you did wrong, bro",
    }


class SchemaForTests(ResourceSchema):
    def __init__(self):
        super().__init__(
            schema="schema:for:tests",
            attrs=[
                Attribute(name="int", type_=at.Integer),
                Attribute(name="str", type_=at.String),
                Attribute(name="str_cs", type_=at.String, case_exact=True),
                Attribute(name="str_mv", type_=at.String, multi_valued=True),
                Attribute(name="str_cs_mv", type_=at.String, case_exact=True, multi_valued=True),
                Attribute(name="bool", type_=at.Boolean),
                Attribute(name="datetime", type_=at.DateTime),
                Attribute(name="decimal", type_=at.Decimal),
                Attribute(name="binary", type_=at.Binary),
                Attribute(name="external_ref", type_=at.ExternalReference),
                Attribute(name="uri_ref", type_=at.URIReference),
                Attribute(
                    name="scim_ref", type_=at.SCIMReference, reference_types=["SchemaForTests"]
                ),
                ComplexAttribute(
                    name="c",
                    sub_attributes=[Attribute(name="value", type_=at.String)],
                ),
                ComplexAttribute(
                    name="c_mv",
                    sub_attributes=[Attribute(name="value", type_=at.String, multi_valued=True)],
                    multi_valued=True,
                ),
                ComplexAttribute(
                    name="c2",
                    sub_attributes=[
                        Attribute(name="str", type_=at.String),
                        Attribute(name="int", type_=at.Integer),
                        Attribute(name="bool", type_=at.Boolean),
                    ],
                ),
                ComplexAttribute(
                    name="c2_mv",
                    sub_attributes=[
                        Attribute(name="str", type_=at.String),
                        Attribute(name="int", type_=at.Integer),
                        Attribute(name="bool", type_=at.Boolean, required=True),
                    ],
                    multi_valued=True,
                ),
                Attribute(name="userName", type_=at.String, case_exact=True),
                Attribute(name="title", type_=at.Integer),
            ],
            name="SchemaForTests",
            plural_name="SchemasForTests",
        )


CONFIG = create_service_provider_config(
    patch={"supported": True},
    bulk={"max_operations": 10, "max_payload_size": 4242, "supported": True},
    filter_={"max_results": 100, "supported": True},
    change_password={"supported": True},
    sort={"supported": True},
    etag={"supported": True},
)
