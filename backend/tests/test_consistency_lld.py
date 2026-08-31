"""Stage 3 consistency: does the LLD actually implement the HLD?"""

import pytest

from app.ai.contracts import LLDOutput
from app.models.enums import StageType
from app.services.consistency import ConsistencyError, check_consistency

HLD = {
    "hld": {
        "services": [
            {"name": "OrderService", "datastore": "PostgreSQL", "scaling_notes": "-"},
            {"name": "PaymentService", "datastore": "PostgreSQL", "scaling_notes": "-"},
        ],
        "sync_calls": [
            {"caller": "OrderService", "callee": "PaymentService", "purpose": "-", "protocol": "REST"}
        ],
        "async_flows": [
            {
                "event": "order.created",
                "producer": "OrderService",
                "consumers": ["PaymentService"],
                "purpose": "-",
            }
        ],
        "external_dependencies": [],
        "design_notes": "-",
    }
}


def _service(name, *, endpoints, published=(), consumed=()):
    return {
        "name": name,
        "tech_stack": "Python / FastAPI",
        "entities": [
            {
                "name": "E",
                "description": "-",
                "fields": [{"name": "id", "type": "uuid", "required": True, "description": "-"}],
            }
        ],
        "endpoints": endpoints,
        "published_events": list(published),
        "consumed_events": list(consumed),
        "internal_logic_notes": "-",
    }


def _endpoint(path, called_by, method="POST"):
    return {
        "method": method,
        "path": path,
        "summary": "-",
        "request_fields": [],
        "response_fields": [],
        "called_by": list(called_by),
    }


VALID_LLD = {
    "services": [
        _service("OrderService", endpoints=[_endpoint("/orders", ["public"])],
                 published=["order.created"]),
        _service("PaymentService", endpoints=[_endpoint("/payments", ["OrderService"])],
                 consumed=["order.created"]),
    ]
}


def _check(lld: dict) -> None:
    check_consistency(StageType.LLD, LLDOutput.model_validate(lld), HLD)


def test_consistent_lld_passes() -> None:
    _check(VALID_LLD)


def test_sync_call_with_no_receiving_endpoint_is_rejected() -> None:
    """The HLD says OrderService calls PaymentService, but no endpoint accepts that caller."""
    lld = {"services": [
        VALID_LLD["services"][0],
        _service("PaymentService", endpoints=[_endpoint("/payments", ["public"])],
                 consumed=["order.created"]),
    ]}
    with pytest.raises(ConsistencyError, match="no endpoint on PaymentService lists 'OrderService'"):
        _check(lld)


def test_unpublished_event_is_rejected() -> None:
    lld = {"services": [
        _service("OrderService", endpoints=[_endpoint("/orders", ["public"])]),  # publishes nothing
        VALID_LLD["services"][1],
    ]}
    with pytest.raises(ConsistencyError, match="publishes 'order.created'.*does not list it"):
        _check(lld)


def test_unconsumed_event_is_rejected() -> None:
    lld = {"services": [
        VALID_LLD["services"][0],
        _service("PaymentService", endpoints=[_endpoint("/payments", ["OrderService"])]),
    ]}
    with pytest.raises(ConsistencyError, match="consumes 'order.created'.*does not list it"):
        _check(lld)


def test_missing_service_is_rejected() -> None:
    lld = {"services": [VALID_LLD["services"][0], _service(
        "GhostService", endpoints=[_endpoint("/ghost", ["public"])])]}
    with pytest.raises(ConsistencyError) as exc:
        _check(lld)
    assert "GhostService" in str(exc.value)
    assert "PaymentService' has no low-level design" in str(exc.value)


def test_unknown_caller_in_called_by_is_rejected() -> None:
    lld = {"services": [
        VALID_LLD["services"][0],
        _service("PaymentService",
                 endpoints=[_endpoint("/payments", ["OrderService", "FraudService"])],
                 consumed=["order.created"]),
    ]}
    with pytest.raises(ConsistencyError, match="FraudService.*neither a known service nor 'public'"):
        _check(lld)


def test_no_hld_means_nothing_to_check() -> None:
    check_consistency(StageType.LLD, LLDOutput.model_validate(VALID_LLD), {})
