"""Stage 6 consistency: is the deployment config actually deployable, and does it match the design?"""

import pytest

from app.ai.contracts import InfraOutput
from app.models.enums import StageType
from app.services.consistency import ConsistencyError, check_consistency

PRIOR = {
    "lld": {
        "services": [
            {"name": "OrderService", "tech_stack": "-", "entities": [], "endpoints": [],
             "published_events": ["order.placed"], "consumed_events": [],
             "internal_logic_notes": "-"},
            {"name": "CatalogService", "tech_stack": "-", "entities": [], "endpoints": [],
             "published_events": [], "consumed_events": [], "internal_logic_notes": "-"},
        ]
    },
    "db_schema": {
        "services": [
            {"name": "OrderService", "engine": "PostgreSQL", "tables": [], "notes": "-"},
            {"name": "CatalogService", "engine": "MongoDB", "tables": [], "notes": "-"},
        ]
    },
}


def _service(name, port, depends_on, base_image="python:3.12-slim"):
    return {
        "name": name, "base_image": base_image,
        "build_steps": ["COPY . ."], "start_command": "python main.py",
        "port": port, "health_check_path": "/health", "env_vars": [],
        "replicas": 2, "cpu_request": "100m", "cpu_limit": "500m",
        "memory_request": "256Mi", "memory_limit": "512Mi", "depends_on": depends_on,
    }


VALID = {
    "services": [
        _service("OrderService", 8081, ["orders-postgres", "kafka"]),
        _service("CatalogService", 8082, ["catalog-mongo"]),
    ],
    "infra_components": [
        {"name": "orders-postgres", "image": "postgres:16-alpine", "port": 5432,
         "used_by": ["OrderService"]},
        {"name": "catalog-mongo", "image": "mongo:7", "port": 27017, "used_by": ["CatalogService"]},
        {"name": "kafka", "image": "bitnami/kafka:3.7", "port": 9092, "used_by": ["OrderService"]},
    ],
    "notes": "-",
}


def _check(infra: dict) -> None:
    check_consistency(StageType.INFRA, InfraOutput.model_validate(infra), PRIOR)


def test_valid_infra_passes() -> None:
    _check(VALID)


def test_port_collision_is_rejected() -> None:
    """Two services on one port cannot both bind it in docker-compose."""
    infra = {**VALID, "services": [
        VALID["services"][0], {**VALID["services"][1], "port": 8081},
    ]}
    with pytest.raises(ConsistencyError, match="both use port 8081"):
        _check(infra)


def test_unpinned_base_image_is_rejected() -> None:
    for image in ("python", "python:latest"):
        infra = {**VALID, "services": [
            {**VALID["services"][0], "base_image": image}, VALID["services"][1],
        ]}
        with pytest.raises(ConsistencyError, match="not pinned to a specific tag"):
            _check(infra)


def test_event_using_service_must_depend_on_kafka() -> None:
    infra = {**VALID, "services": [
        _service("OrderService", 8081, ["orders-postgres"]), VALID["services"][1],
    ]}
    with pytest.raises(ConsistencyError, match="does not depend on a Kafka component"):
        _check(infra)


def test_service_must_depend_on_a_component_running_its_engine() -> None:
    """CatalogService stores in MongoDB, so pointing it at Postgres is wrong."""
    infra = {**VALID, "services": [
        VALID["services"][0], _service("CatalogService", 8082, ["orders-postgres"]),
    ]}
    with pytest.raises(ConsistencyError, match="stores data in MongoDB but depends on no component"):
        _check(infra)


def test_dependency_on_undeclared_component_is_rejected() -> None:
    infra = {**VALID, "services": [
        _service("OrderService", 8081, ["orders-postgres", "kafka", "ghost-cache"]),
        VALID["services"][1],
    ]}
    with pytest.raises(ConsistencyError, match="'ghost-cache', which is not a declared"):
        _check(infra)


def test_missing_service_deployment_is_rejected() -> None:
    infra = {**VALID, "services": [
        VALID["services"][0], _service("GhostService", 8082, ["kafka"]),
    ]}
    with pytest.raises(ConsistencyError) as exc:
        _check(infra)
    assert "'CatalogService' has no deployment configuration" in str(exc.value)
    assert "GhostService" in str(exc.value)


def test_component_used_by_unknown_service_is_rejected() -> None:
    infra = {**VALID, "infra_components": VALID["infra_components"][:2] + [
        {"name": "kafka", "image": "bitnami/kafka:3.7", "port": 9092,
         "used_by": ["OrderService", "GhostService"]},
    ]}
    with pytest.raises(ConsistencyError, match="used_by unknown service 'GhostService'"):
        _check(infra)


def test_pascal_case_service_hostname_is_rejected() -> None:
    """A model writes 'InventoryService:8003' as a host; the generated DNS name is
    'inventory-service', so the PascalCase form never resolves."""
    bad = _service("OrderService", 8081, ["orders-postgres", "kafka"])
    bad["env_vars"] = [{"name": "CATALOG_HOST", "value": "CatalogService:8082",
                        "secret": False, "description": "-"}]
    infra = {**VALID, "services": [bad, VALID["services"][1]]}
    with pytest.raises(ConsistencyError, match="use 'catalog-service' or it will not resolve"):
        _check(infra)


def test_credentials_embedded_in_a_non_secret_value_are_rejected() -> None:
    """DATABASE_URL with the password inline, marked secret:false, would land in a ConfigMap."""
    bad = _service("OrderService", 8081, ["orders-postgres", "kafka"])
    bad["env_vars"] = [{"name": "DATABASE_URL", "secret": False, "description": "-",
                        "value": "postgresql://user:hunter2@orders-postgres:5432/orders"}]
    infra = {**VALID, "services": [bad, VALID["services"][1]]}
    with pytest.raises(ConsistencyError, match="embeds credentials .* not marked secret"):
        _check(infra)


def test_host_port_used_in_an_internal_connection_string_is_rejected() -> None:
    """orders-postgres publishes on host 5432 here, but a component mapped to a different host
    port is still reached on its container port from inside the network."""
    infra = {
        **VALID,
        "infra_components": [
            {"name": "orders-postgres", "image": "postgres:16-alpine", "port": 5433,
             "used_by": ["OrderService"]},
            *VALID["infra_components"][1:],
        ],
        "services": [
            {**VALID["services"][0], "env_vars": [
                {"name": "DATABASE_URL", "secret": False, "description": "-",
                 "value": "jdbc:postgresql://orders-postgres:5433/orders"}
            ]},
            VALID["services"][1],
        ],
    }
    with pytest.raises(ConsistencyError, match="port 5433, but inside the network it listens on 5432"):
        _check(infra)


# --- v0.9.0: the two failures found by reviewing the first real Stage 6 output ---


def test_sdk_image_as_runtime_is_rejected() -> None:
    """The live run shipped golang:1.22-alpine as a runtime — the whole Go toolchain in prod."""
    infra = {**VALID, "services": [
        {**VALID["services"][0], "base_image": "golang:1.22-alpine"}, VALID["services"][1],
    ]}
    with pytest.raises(ConsistencyError, match="SDK/build image"):
        _check(infra)


def test_jre_image_is_accepted_but_jdk_is_not() -> None:
    for image, ok in (("eclipse-temurin:21-jre-alpine", True), ("eclipse-temurin:21-jdk", False)):
        infra = {**VALID, "services": [
            {**VALID["services"][0], "base_image": image}, VALID["services"][1],
        ]}
        if ok:
            _check(infra)
        else:
            with pytest.raises(ConsistencyError, match="SDK/build image"):
                _check(infra)


def test_start_command_with_no_build_step_is_rejected() -> None:
    """The live run had CatalogService start 'node dist/main.js' with no build step at all."""
    broken = {**VALID["services"][0],
              "build_steps": ["COPY package*.json ./", "RUN npm ci --only=production", "COPY . ."],
              "start_command": "node dist/main.js"}
    infra = {**VALID, "services": [broken, VALID["services"][1]]}
    with pytest.raises(ConsistencyError, match="no build step produces 'dist/main.js'"):
        _check(infra)


def test_start_command_with_a_real_build_step_passes() -> None:
    fixed = {**VALID["services"][0],
             "build_steps": ["COPY package*.json ./", "RUN npm ci", "COPY . .", "RUN npm run build"],
             "start_command": "node dist/main.js"}
    _check({**VALID, "services": [fixed, VALID["services"][1]]})


def test_multi_stage_go_service_passes() -> None:
    go = {**VALID["services"][0],
          "base_image": "alpine:3.20",
          "builder_image": "golang:1.22-alpine",
          "builder_steps": ["COPY . .", "RUN go build -o cartservice ."],
          "copy_from_builder": ["/app/cartservice"],
          "build_steps": [],
          "start_command": "./cartservice"}
    _check({**VALID, "services": [go, VALID["services"][1]]})


def test_build_stage_that_copies_nothing_out_is_rejected() -> None:
    orphan = {**VALID["services"][0], "builder_image": "golang:1.22-alpine",
              "builder_steps": ["RUN go build -o svc ."], "copy_from_builder": []}
    infra = {**VALID, "services": [orphan, VALID["services"][1]]}
    with pytest.raises(ConsistencyError, match="copies nothing out of it"):
        _check(infra)


def test_builder_steps_without_a_builder_image_are_rejected() -> None:
    orphan = {**VALID["services"][0], "builder_steps": ["RUN go build ."]}
    infra = {**VALID, "services": [orphan, VALID["services"][1]]}
    with pytest.raises(ConsistencyError, match="builder_steps but no builder_image"):
        _check(infra)


def test_artifact_path_outside_the_builder_workdir_is_rejected() -> None:
    """The generated build stage runs in /app, so '/target/app.jar' does not exist."""
    bad = {**VALID["services"][0], "base_image": "eclipse-temurin:21-jre-alpine",
           "builder_image": "maven:3.9-eclipse-temurin-21-alpine",
           "builder_steps": ["RUN mvn package"], "copy_from_builder": ["/target/svc.jar"],
           "build_steps": [], "start_command": "java -jar svc.jar"}
    infra = {**VALID, "services": [bad, VALID["services"][1]]}
    with pytest.raises(ConsistencyError, match=r"should be '/app/target/svc.jar'"):
        _check(infra)


def test_start_command_port_must_match_the_declared_port() -> None:
    bad = {**VALID["services"][0], "start_command": "uvicorn main:app --host 0.0.0.0 --port 9999"}
    infra = {**VALID, "services": [bad, VALID["services"][1]]}
    with pytest.raises(ConsistencyError, match="starts on port 9999 but declares port 8081"):
        _check(infra)
