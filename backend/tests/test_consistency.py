"""Cross-stage consistency checks — the guard against a schema-valid but contradictory HLD."""

import pytest

from app.ai.contracts import HLDOutput
from app.models.enums import StageType
from app.services.consistency import ConsistencyError, check_consistency

BOUNDARIES = {
    "boundaries": {
        "services": [
            {"name": "OrderService"},
            {"name": "PaymentService"},
            {"name": "ShippingService"},
        ],
        "boundaries_rationale": "...",
    }
}

VALID_HLD = {
    "services": [
        {"name": "OrderService", "datastore": "PostgreSQL", "scaling_notes": "read heavy"},
        {"name": "PaymentService", "datastore": "PostgreSQL", "scaling_notes": "write heavy"},
        {"name": "ShippingService", "datastore": "PostgreSQL", "scaling_notes": "low volume"},
    ],
    "sync_calls": [
        {"caller": "OrderService", "callee": "PaymentService", "purpose": "authorise", "protocol": "REST"}
    ],
    "async_flows": [
        {
            "event": "order.created",
            "producer": "OrderService",
            "consumers": ["PaymentService"],
            "purpose": "start payment",
        }
    ],
    "external_dependencies": [{"name": "Stripe", "used_by": ["PaymentService"], "purpose": "cards"}],
    "design_notes": "...",
}


def _check(hld: dict) -> None:
    check_consistency(StageType.HLD, HLDOutput.model_validate(hld), BOUNDARIES)


def test_consistent_hld_passes() -> None:
    _check(VALID_HLD)


def test_invented_service_is_rejected() -> None:
    hld = {**VALID_HLD, "services": VALID_HLD["services"] + [
        {"name": "GhostService", "datastore": "none", "scaling_notes": "-"}
    ]}
    with pytest.raises(ConsistencyError) as exc:
        _check(hld)
    assert "GhostService" in str(exc.value)


def test_dropped_service_is_rejected() -> None:
    """Schema-valid (still 2 services) but ShippingService silently vanished from the design."""
    hld = {**VALID_HLD, "services": VALID_HLD["services"][:2]}
    with pytest.raises(ConsistencyError, match="ShippingService.*missing"):
        _check(hld)


def test_unknown_service_in_sync_call_is_rejected() -> None:
    hld = {**VALID_HLD, "sync_calls": [
        {"caller": "OrderService", "callee": "InventoryService", "purpose": "x", "protocol": "REST"}
    ]}
    with pytest.raises(ConsistencyError, match="InventoryService"):
        _check(hld)


def test_unknown_consumer_in_async_flow_is_rejected() -> None:
    hld = {**VALID_HLD, "async_flows": [
        {"event": "order.created", "producer": "OrderService", "consumers": ["EmailService"], "purpose": "x"}
    ]}
    with pytest.raises(ConsistencyError, match="EmailService"):
        _check(hld)


def test_self_call_and_self_consumption_are_rejected() -> None:
    hld = {**VALID_HLD,
           "sync_calls": [{"caller": "OrderService", "callee": "OrderService", "purpose": "x", "protocol": "REST"}],
           "async_flows": [{"event": "order.created", "producer": "OrderService",
                            "consumers": ["OrderService"], "purpose": "x"}]}
    with pytest.raises(ConsistencyError) as exc:
        _check(hld)
    assert "self-call" in str(exc.value)
    assert "consuming its own event" in str(exc.value)


def test_boundaries_stage_has_no_cross_stage_check() -> None:
    # Stage 1 has nothing before it, so it is schema-validated only. Must not raise.
    from app.ai.contracts import BoundariesOutput

    output = BoundariesOutput.model_validate(
        {
            "services": [
                {"name": "A", "responsibility": "x", "domain": "d", "key_entities": []},
                {"name": "B", "responsibility": "y", "domain": "d", "key_entities": []},
            ],
            "boundaries_rationale": "r",
        }
    )
    check_consistency(StageType.BOUNDARIES, output, {})
