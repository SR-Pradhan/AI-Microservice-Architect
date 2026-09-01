"""Mermaid rendering of the HLD."""

import pytest

from app.models.enums import StageType
from app.services.diagram import (
    db_schema_to_mermaid,
    hld_to_mermaid,
    kafka_events_to_mermaid,
    render_stage,
)

HLD = {
    "services": [
        {"name": "OrderService", "datastore": "PostgreSQL", "scaling_notes": "-"},
        {"name": "Payment Service!", "datastore": "", "scaling_notes": "-"},
    ],
    "sync_calls": [
        {"caller": "OrderService", "callee": "Payment Service!", "purpose": "x", "protocol": "gRPC"}
    ],
    "async_flows": [
        {"event": "order.created", "producer": "OrderService", "consumers": ["Payment Service!"], "purpose": "x"}
    ],
    "external_dependencies": [{"name": "Stripe", "used_by": ["Payment Service!"], "purpose": "cards"}],
    "design_notes": "-",
}


def test_renders_nodes_edges_and_broker() -> None:
    out = hld_to_mermaid(HLD)
    assert out.startswith("flowchart LR")
    # Names with spaces/punctuation become safe ids but keep the real label.
    assert 'Payment_Service_["Payment Service!"]' in out
    assert 'OrderService["OrderService<br/>(PostgreSQL)"]' in out
    assert 'OrderService -->|"gRPC"| Payment_Service_' in out
    # Async edges are dotted and routed through the broker node.
    assert 'broker{{"Event Broker (Kafka)"}}' in out
    assert 'OrderService -.->|"order.created"| broker' in out
    assert 'broker -.->|"order.created"| Payment_Service_' in out
    assert 'Payment_Service_ --> ext_Stripe' in out


def test_no_broker_node_when_there_are_no_events() -> None:
    out = hld_to_mermaid({**HLD, "async_flows": []})
    assert "broker" not in out


def test_quotes_in_names_do_not_break_labels() -> None:
    out = hld_to_mermaid({"services": [{"name": 'Od"d', "datastore": "", "scaling_notes": ""}]})
    assert '"' not in out.split("[", 1)[1].split("]")[0].strip('"')


SCHEMA = {
    "services": [
        {
            "name": "OrderService",
            "engine": "PostgreSQL",
            "tables": [
                {
                    "name": "orders",
                    "entity": "Order",
                    "columns": [
                        {"name": "id", "type": "UUID", "primary_key": True},
                        {"name": "total", "type": "NUMERIC(12,2)"},
                        {"name": "user_id", "type": "UUID"},
                    ],
                    "indexes": [],
                    "foreign_keys": [
                        {"column": "user_id", "references_table": "users",
                         "references_service": "UserService"},
                    ],
                }
            ],
            "notes": "-",
        },
        {
            "name": "UserService",
            "engine": "PostgreSQL",
            "tables": [{"name": "users", "entity": "User",
                        "columns": [{"name": "id", "type": "UUID", "primary_key": True}],
                        "indexes": [], "foreign_keys": []}],
            "notes": "-",
        },
    ]
}


def test_er_diagram_marks_keys_and_sanitises_types() -> None:
    out = db_schema_to_mermaid(SCHEMA)
    assert out.startswith("erDiagram")
    assert "UUID id PK" in out
    # NUMERIC(12,2) would break Mermaid's parser; it must be reduced to an identifier.
    assert "NUMERIC_12_2 total" in out
    assert "(" not in out
    # Ownership is a Mermaid comment, never an attribute row.
    assert "%% OrderService" in out


def test_cross_service_reference_is_drawn_as_a_dotted_link() -> None:
    """A FK across a service boundary is logical only, and must look different from a real one."""
    out = db_schema_to_mermaid(SCHEMA)
    assert 'orders }o..|| users : "user_id"' in out


def test_reference_to_an_unknown_table_is_skipped() -> None:
    schema = {"services": [{
        "name": "OrderService", "engine": "PostgreSQL", "notes": "-",
        "tables": [{"name": "orders", "entity": "Order",
                    "columns": [{"name": "id", "type": "UUID", "primary_key": True}],
                    "indexes": [],
                    "foreign_keys": [{"column": "id", "references_table": "elsewhere",
                                      "references_service": "Other"}]}],
    }]}
    out = db_schema_to_mermaid(schema)
    assert "elsewhere" not in out


EVENTS = {
    "topics": [
        {
            "name": "order.placed",
            "producer": "OrderService",
            "partition_key": "orderId",
            "partitions": 6,
            "consumers": [
                {"service": "CartService", "consumer_group": "cart-group"},
                {"service": "NotificationService", "consumer_group": "notif-group"},
            ],
        }
    ]
}


def test_event_flow_shows_topic_producer_and_consumer_groups() -> None:
    out = kafka_events_to_mermaid(EVENTS)
    assert out.startswith("flowchart LR")
    # The topic node carries the partition key and count — the two things that decide ordering.
    assert 'topic_order_placed[/"order.placed<br/>key: orderId · 6p"/]' in out
    assert "OrderService --> topic_order_placed" in out
    # Consumer edges are labelled by group, so a shared group is visible in the picture.
    assert 'topic_order_placed -.->|"cart-group"| CartService' in out
    assert 'topic_order_placed -.->|"notif-group"| NotificationService' in out
    # Each service appears exactly once even though it may touch several topics.
    assert out.count('CartService["CartService"]') == 1


def test_unsupported_stage_raises() -> None:
    with pytest.raises(NotImplementedError):
        render_stage(StageType.LLD, {})
