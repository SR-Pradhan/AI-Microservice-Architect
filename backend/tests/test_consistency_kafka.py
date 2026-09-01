"""Stage 5 consistency — the spec's explicit requirement:

    "validate that every consumer listed actually has a corresponding subscriber defined in
     Stage 3's LLD, or flag inconsistency back to the user"
"""

import pytest

from app.ai.contracts import KafkaEventsOutput
from app.models.enums import StageType
from app.services.consistency import ConsistencyError, check_consistency

PRIOR = {
    "hld": {
        "services": [],
        "sync_calls": [],
        "async_flows": [
            {
                "event": "order.placed",
                "producer": "OrderService",
                "consumers": ["CartService", "NotificationService"],
                "purpose": "-",
            }
        ],
        "external_dependencies": [],
        "design_notes": "-",
    },
    "lld": {
        "services": [
            {
                "name": "OrderService", "tech_stack": "-", "entities": [], "endpoints": [],
                "published_events": ["order.placed"], "consumed_events": [],
                "internal_logic_notes": "-",
            },
            {
                "name": "CartService", "tech_stack": "-", "entities": [], "endpoints": [],
                "published_events": [], "consumed_events": ["order.placed"],
                "internal_logic_notes": "-",
            },
            {
                "name": "NotificationService", "tech_stack": "-", "entities": [], "endpoints": [],
                "published_events": [], "consumed_events": ["order.placed"],
                "internal_logic_notes": "-",
            },
        ]
    },
}


def _field(name):
    return {"name": name, "type": "uuid", "required": True, "description": "-"}


def _topic(**overrides):
    topic = {
        "name": "order.placed",
        "producer": "OrderService",
        "consumers": [
            {"service": "CartService", "consumer_group": "cart-group", "purpose": "-"},
            {"service": "NotificationService", "consumer_group": "notif-group", "purpose": "-"},
        ],
        "partition_key": "orderId",
        "partitions": 6,
        "retention": "7 days",
        "payload_fields": [_field("orderId"), _field("userId")],
        "ordering_notes": "-",
    }
    topic.update(overrides)
    return topic


def _events(**overrides):
    out = {
        "topics": [_topic()],
        "dead_letter_strategy": "3 retries, exponential backoff, then DLQ",
        "schema_evolution_notes": "-",
    }
    out.update(overrides)
    return out


def _check(events: dict) -> None:
    check_consistency(StageType.KAFKA_EVENTS, KafkaEventsOutput.model_validate(events), PRIOR)


def test_valid_events_pass() -> None:
    _check(_events())


def test_missing_topic_for_an_hld_event_is_rejected() -> None:
    events = _events(topics=[_topic(name="something.else")])
    with pytest.raises(ConsistencyError) as exc:
        _check(events)
    assert "HLD event 'order.placed' has no topic" in str(exc.value)
    assert "does not correspond to any event in the HLD" in str(exc.value)


def test_consumer_not_declared_in_its_lld_is_rejected() -> None:
    """The exact case the spec calls out: a topic claims a subscriber the LLD never defined."""
    prior = {
        **PRIOR,
        "lld": {"services": [
            PRIOR["lld"]["services"][0],
            PRIOR["lld"]["services"][1],
            {**PRIOR["lld"]["services"][2], "consumed_events": []},  # no longer subscribes
        ]},
    }
    with pytest.raises(ConsistencyError, match="LLD does not declare 'order.placed' in consumed_events"):
        check_consistency(StageType.KAFKA_EVENTS, KafkaEventsOutput.model_validate(_events()), prior)


def test_consumer_set_must_match_the_hld() -> None:
    events = _events(topics=[_topic(consumers=[
        {"service": "CartService", "consumer_group": "cart-group", "purpose": "-"}
    ])])
    with pytest.raises(ConsistencyError, match="does not list NotificationService"):
        _check(events)


def test_wrong_producer_is_rejected() -> None:
    events = _events(topics=[_topic(producer="CartService")])
    with pytest.raises(ConsistencyError) as exc:
        _check(events)
    assert "produced by CartService, but the HLD says OrderService" in str(exc.value)


def test_shared_consumer_group_is_rejected() -> None:
    """Two services in one group steal each other's messages instead of both receiving them."""
    events = _events(topics=[_topic(consumers=[
        {"service": "CartService", "consumer_group": "shared", "purpose": "-"},
        {"service": "NotificationService", "consumer_group": "shared", "purpose": "-"},
    ])])
    with pytest.raises(ConsistencyError, match="steal each other's messages"):
        _check(events)


def test_partition_key_must_be_a_payload_field() -> None:
    events = _events(topics=[_topic(partition_key="nonexistent")])
    with pytest.raises(ConsistencyError, match="not one of its payload fields"):
        _check(events)


def test_unknown_consumer_service_is_rejected() -> None:
    prior = {**PRIOR, "hld": {**PRIOR["hld"], "async_flows": [
        {"event": "order.placed", "producer": "OrderService",
         "consumers": ["CartService", "NotificationService", "GhostService"], "purpose": "-"}
    ]}}
    events = _events(topics=[_topic(consumers=[
        {"service": "CartService", "consumer_group": "cart-group", "purpose": "-"},
        {"service": "NotificationService", "consumer_group": "notif-group", "purpose": "-"},
        {"service": "GhostService", "consumer_group": "ghost-group", "purpose": "-"},
    ])])
    with pytest.raises(ConsistencyError, match="unknown service 'GhostService'"):
        check_consistency(StageType.KAFKA_EVENTS, KafkaEventsOutput.model_validate(events), prior)
