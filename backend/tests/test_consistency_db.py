"""Stage 4 consistency: does the schema store exactly what the LLD defined, in the HLD's engine?"""

import pytest

from app.ai.contracts import DBSchemaOutput
from app.models.enums import StageType
from app.services.consistency import ConsistencyError, check_consistency

PRIOR = {
    "hld": {
        "services": [
            {"name": "OrderService", "datastore": "PostgreSQL", "scaling_notes": "-"},
            {"name": "CartService", "datastore": "Redis", "scaling_notes": "-"},
        ],
        "sync_calls": [],
        "async_flows": [],
        "external_dependencies": [],
        "design_notes": "-",
    },
    "lld": {
        "services": [
            {
                "name": "OrderService",
                "tech_stack": "-",
                "entities": [
                    {"name": "Order", "description": "-", "fields": []},
                    {"name": "OrderItem", "description": "-", "fields": []},
                ],
                "endpoints": [],
                "published_events": [],
                "consumed_events": [],
                "internal_logic_notes": "-",
            },
            {
                "name": "CartService",
                "tech_stack": "-",
                "entities": [{"name": "Cart", "description": "-", "fields": []}],
                "endpoints": [],
                "published_events": [],
                "consumed_events": [],
                "internal_logic_notes": "-",
            },
        ]
    },
}


def _col(name, pk=False):
    return {"name": name, "type": "UUID", "nullable": False, "primary_key": pk, "description": "-"}


def _table(name, entity, columns=None, indexes=(), fks=()):
    return {
        "name": name,
        "entity": entity,
        "columns": columns or [_col("id", pk=True)],
        "indexes": list(indexes),
        "foreign_keys": list(fks),
    }


VALID = {
    "services": [
        {
            "name": "OrderService",
            "engine": "PostgreSQL",
            "tables": [_table("orders", "Order"), _table("order_items", "OrderItem")],
            "notes": "-",
        },
        {"name": "CartService", "engine": "Redis", "tables": [_table("carts", "Cart")], "notes": "-"},
    ]
}


def _check(schema: dict) -> None:
    check_consistency(StageType.DB_SCHEMA, DBSchemaOutput.model_validate(schema), PRIOR)


def test_valid_schema_passes() -> None:
    _check(VALID)


def test_wrong_engine_is_rejected() -> None:
    """The HLD chose Redis for CartService; the schema must not quietly switch it to PostgreSQL."""
    schema = {"services": [VALID["services"][0], {**VALID["services"][1], "engine": "PostgreSQL"}]}
    with pytest.raises(ConsistencyError, match="the HLD chose 'Redis'"):
        _check(schema)


def test_entity_without_a_table_is_rejected() -> None:
    schema = {"services": [
        {**VALID["services"][0], "tables": [_table("orders", "Order")]},
        VALID["services"][1],
    ]}
    with pytest.raises(ConsistencyError, match="entity 'OrderItem' has no table"):
        _check(schema)


def test_storing_another_services_entity_is_rejected() -> None:
    """CartService must not own a table for OrderService's Order — that breaks data ownership."""
    schema = {"services": [
        VALID["services"][0],
        {**VALID["services"][1], "tables": [_table("carts", "Cart"), _table("orders_copy", "Order")]},
    ]}
    with pytest.raises(ConsistencyError, match="owned by OrderService"):
        _check(schema)


def test_table_without_primary_key_is_rejected() -> None:
    schema = {"services": [
        {**VALID["services"][0], "tables": [
            _table("orders", "Order", columns=[_col("id")]),  # no PK flag
            _table("order_items", "OrderItem"),
        ]},
        VALID["services"][1],
    ]}
    with pytest.raises(ConsistencyError, match="orders has no primary key"):
        _check(schema)


def test_index_on_a_nonexistent_column_is_rejected() -> None:
    bad_index = {"name": "ix_missing", "columns": ["customer_id"], "unique": False, "rationale": "-"}
    schema = {"services": [
        {**VALID["services"][0], "tables": [
            _table("orders", "Order", indexes=[bad_index]),
            _table("order_items", "OrderItem"),
        ]},
        VALID["services"][1],
    ]}
    with pytest.raises(ConsistencyError, match="column 'customer_id', which does not exist"):
        _check(schema)


def test_foreign_key_to_unknown_service_is_rejected() -> None:
    fk = {"column": "id", "references_table": "users", "references_service": "UserService"}
    schema = {"services": [
        {**VALID["services"][0], "tables": [
            _table("orders", "Order", fks=[fk]),
            _table("order_items", "OrderItem"),
        ]},
        VALID["services"][1],
    ]}
    with pytest.raises(ConsistencyError, match="unknown service 'UserService'"):
        _check(schema)


def test_missing_service_schema_is_rejected() -> None:
    schema = {"services": [VALID["services"][0], {
        "name": "GhostService", "engine": "PostgreSQL",
        "tables": [_table("ghosts", "Cart")], "notes": "-"}]}
    with pytest.raises(ConsistencyError) as exc:
        _check(schema)
    assert "GhostService" in str(exc.value)
    assert "'CartService' has no datastore schema" in str(exc.value)
