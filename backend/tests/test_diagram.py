"""Mermaid rendering of the HLD."""

import pytest

from app.models.enums import StageType
from app.services.diagram import hld_to_mermaid, render_stage

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


def test_unsupported_stage_raises() -> None:
    with pytest.raises(NotImplementedError):
        render_stage(StageType.LLD, {})
