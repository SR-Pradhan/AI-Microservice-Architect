"""Export Generator — the files must be well-formed and deterministic, not model-authored."""

import io
import zipfile

import yaml

from app.services.export import (
    build_export,
    compose_for,
    ddl_for,
    dockerfile_for,
    k8s_configmap_for,
    k8s_deployment_for,
    kebab,
)

SERVICE = {
    "name": "OrderService",
    "base_image": "eclipse-temurin:21-jre-alpine",
    "build_steps": ["COPY target/app.jar app.jar"],
    "start_command": "java -jar app.jar",
    "port": 8081,
    "health_check_path": "/actuator/health",
    "env_vars": [
        {"name": "KAFKA_BROKERS", "value": "kafka:9092", "secret": False, "description": "-"},
        {"name": "DB_PASSWORD", "value": "changeme", "secret": True, "description": "-"},
    ],
    "replicas": 3,
    "cpu_request": "200m",
    "cpu_limit": "1",
    "memory_request": "512Mi",
    "memory_limit": "1Gi",
    "depends_on": ["orders-postgres", "kafka"],
}

INFRA = {
    "services": [SERVICE, {**SERVICE, "name": "PaymentService", "port": 8082, "depends_on": ["kafka"]}],
    "infra_components": [
        {"name": "orders-postgres", "image": "postgres:16-alpine", "port": 5432,
         "used_by": ["OrderService"]},
        {"name": "kafka", "image": "bitnami/kafka:3.7", "port": 9092,
         "used_by": ["OrderService", "PaymentService"]},
    ],
    "notes": "-",
}


def test_kebab_handles_acronyms_and_punctuation() -> None:
    assert kebab("OrderService") == "order-service"
    assert kebab("APIGateway") == "api-gateway"
    assert kebab("Payment Service!") == "payment-service"


def test_dockerfile_drops_directives_it_generates_itself() -> None:
    """Models sometimes include WORKDIR/FROM in build_steps despite the prompt; a duplicate
    WORKDIR or a stray second FROM would produce a broken Dockerfile."""
    noisy = {**SERVICE, "build_steps": ["WORKDIR /app", "FROM scratch", "COPY . .", "CMD ['x']"]}
    out = dockerfile_for(noisy)
    assert out.count("WORKDIR") == 1
    assert out.count("FROM") == 1
    assert "COPY . ." in out
    assert 'CMD ["java", "-jar", "app.jar"]' in out


def test_dockerfile_wraps_build_steps_correctly() -> None:
    out = dockerfile_for(SERVICE)
    assert out.startswith("FROM eclipse-temurin:21-jre-alpine")
    assert "COPY target/app.jar app.jar" in out
    assert "EXPOSE 8081" in out
    # CMD must be exec form (a JSON array), not shell form — shell form breaks signal handling.
    assert 'CMD ["java", "-jar", "app.jar"]' in out


def test_compose_is_valid_yaml_with_expected_shape() -> None:
    parsed = yaml.safe_load(compose_for(INFRA))
    assert set(parsed["services"]) == {"orders-postgres", "kafka", "order-service", "payment-service"}
    order = parsed["services"]["order-service"]
    assert order["build"] == "./services/order-service"
    assert order["ports"] == ["8081:8081"]
    assert order["environment"]["KAFKA_BROKERS"] == "kafka:9092"
    assert order["depends_on"] == ["orders-postgres", "kafka"]


def test_k8s_deployment_is_valid_yaml_with_probes_and_limits() -> None:
    parsed = yaml.safe_load(k8s_deployment_for(SERVICE))
    assert parsed["kind"] == "Deployment"
    assert parsed["spec"]["replicas"] == 3
    container = parsed["spec"]["template"]["spec"]["containers"][0]
    assert container["ports"][0]["containerPort"] == 8081
    assert container["readinessProbe"]["httpGet"]["path"] == "/actuator/health"
    assert container["resources"]["limits"]["memory"] == "1Gi"


def test_configmap_never_contains_a_secret_value() -> None:
    out = k8s_configmap_for(SERVICE)
    parsed = yaml.safe_load(out)
    assert "KAFKA_BROKERS" in parsed["data"]
    # The secret must be absent from the data block entirely, only mentioned as a kubectl hint.
    assert "DB_PASSWORD" not in parsed["data"]
    assert "changeme" not in out
    assert "kubectl create secret" in out


def test_ddl_only_for_relational_engines() -> None:
    relational = {
        "name": "OrderService",
        "engine": "PostgreSQL",
        "tables": [{
            "name": "orders",
            "entity": "Order",
            "columns": [
                {"name": "order_id", "type": "UUID", "nullable": False, "primary_key": True},
                {"name": "note", "type": "TEXT", "nullable": True, "primary_key": False},
            ],
            "indexes": [{"name": "ix_note", "columns": ["note"], "unique": True}],
            "foreign_keys": [],
        }],
        "notes": "-",
    }
    ddl = ddl_for(relational)
    assert ddl is not None
    assert "CREATE TABLE orders (" in ddl
    assert "order_id UUID NOT NULL" in ddl
    assert "note TEXT," in ddl  # nullable column carries no NOT NULL
    assert "PRIMARY KEY (order_id)" in ddl
    assert "CREATE UNIQUE INDEX ix_note ON orders (note);" in ddl

    # Emitting SQL for Redis would be actively misleading.
    assert ddl_for({**relational, "engine": "Redis"}) is None


def test_build_export_produces_the_expected_tree() -> None:
    stages = {"infra": INFRA, "lld": {"services": [
        {"name": "OrderService", "tech_stack": "Java / Spring Boot", "entities": [],
         "endpoints": [{"method": "POST", "path": "/orders", "summary": "Place an order",
                        "request_fields": [], "response_fields": [], "called_by": ["public"]}],
         "published_events": ["order.placed"], "consumed_events": [],
         "internal_logic_notes": "Outbox pattern."},
    ]}}
    names = zipfile.ZipFile(io.BytesIO(build_export("Shop", "A shop.", stages))).namelist()

    assert "README.md" in names
    assert "docker-compose.yml" in names
    for path in ("Dockerfile", "k8s/deployment.yaml", "k8s/service.yaml", "k8s/configmap.yaml",
                 "README.md"):
        assert f"services/order-service/{path}" in names
    assert "services/payment-service/Dockerfile" in names
    assert "docs/infra.json" in names


def test_export_is_deterministic() -> None:
    """Same input, same bytes — because nothing here is model-authored."""
    stages = {"infra": INFRA}
    assert build_export("Shop", "A shop.", stages) == build_export("Shop", "A shop.", stages)
