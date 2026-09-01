"""Export Generator — turns the approved stage artifacts into a repo scaffold.

Every file here is produced **deterministically from validated data**, never by asking the model to
write YAML. The model supplied facts (base image, port, env vars, dependencies) which Pydantic
already validated; this module turns those facts into files. That means the YAML is always
well-formed, and re-exporting the same project always produces the same bytes.
"""

import io
import json
import re
import zipfile
from typing import Any

from app.models.enums import StageType
from app.services import diagram

_SAFE = re.compile(r"[^a-z0-9-]")


def kebab(name: str) -> str:
    """OrderService -> order-service. Used for directories, compose keys and k8s object names."""
    # Two passes so acronym runs survive: APIGateway -> api-gateway, not a-p-i-gateway.
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", name.strip())
    spaced = re.sub(r"([a-z\d])([A-Z])", r"\1-\2", spaced)
    cleaned = _SAFE.sub("-", spaced.lower())
    return re.sub(r"-{2,}", "-", cleaned).strip("-") or "service"


def _yaml_scalar(value: Any) -> str:
    """Quote anything that YAML would otherwise reinterpret (numbers, yes/no, colons)."""
    text = str(value)
    if text == "" or re.search(r"[:#{}\[\]&*!|>'\"%@`]|^\s|\s$", text) or text.lower() in {
        "yes", "no", "true", "false", "null", "on", "off",
    }:
        return json.dumps(text)
    return text


# The prompt tells the model not to emit these, but a generator must not depend on that: a stray
# FROM or a second WORKDIR would produce a broken or confusing Dockerfile.
_GENERATED_DIRECTIVES = ("FROM ", "WORKDIR ", "EXPOSE ", "CMD ", "ENTRYPOINT ")


def dockerfile_for(service: dict[str, Any]) -> str:
    lines = [
        f"FROM {service['base_image']}",
        "",
        "WORKDIR /app",
        "",
    ]
    lines += [
        step
        for step in service.get("build_steps", [])
        if not step.strip().upper().startswith(_GENERATED_DIRECTIVES)
    ]
    lines += [
        "",
        f"EXPOSE {service['port']}",
        "",
        f"CMD {json.dumps(service['start_command'].split())}",
        "",
    ]
    return "\n".join(lines)


def compose_for(infra: dict[str, Any]) -> str:
    lines = ["services:"]

    for component in infra.get("infra_components", []):
        name = kebab(component["name"])
        lines += [
            f"  {name}:",
            f"    image: {_yaml_scalar(component['image'])}",
            "    ports:",
            f"      - \"{component['port']}:{component['port']}\"",
            "    restart: unless-stopped",
        ]

    for service in infra.get("services", []):
        name = kebab(service["name"])
        lines += [
            f"  {name}:",
            f"    build: ./services/{name}",
            "    ports:",
            f"      - \"{service['port']}:{service['port']}\"",
        ]
        env_vars = service.get("env_vars", [])
        if env_vars:
            lines.append("    environment:")
            for env in env_vars:
                lines.append(f"      {env['name']}: {_yaml_scalar(env['value'])}")
        depends = service.get("depends_on", [])
        if depends:
            lines.append("    depends_on:")
            lines += [f"      - {kebab(d)}" for d in depends]
        lines.append("    restart: unless-stopped")

    return "\n".join(lines) + "\n"


def k8s_deployment_for(service: dict[str, Any]) -> str:
    name = kebab(service["name"])
    lines = [
        "apiVersion: apps/v1",
        "kind: Deployment",
        "metadata:",
        f"  name: {name}",
        "spec:",
        f"  replicas: {service['replicas']}",
        "  selector:",
        "    matchLabels:",
        f"      app: {name}",
        "  template:",
        "    metadata:",
        "      labels:",
        f"        app: {name}",
        "    spec:",
        "      containers:",
        f"        - name: {name}",
        f"          image: {name}:latest",
        "          ports:",
        f"            - containerPort: {service['port']}",
    ]
    if service.get("env_vars"):
        lines.append("          envFrom:")
        lines.append("            - configMapRef:")
        lines.append(f"                name: {name}-config")
    lines += [
        "          readinessProbe:",
        "            httpGet:",
        f"              path: {_yaml_scalar(service['health_check_path'])}",
        f"              port: {service['port']}",
        "            initialDelaySeconds: 5",
        "            periodSeconds: 10",
        "          livenessProbe:",
        "            httpGet:",
        f"              path: {_yaml_scalar(service['health_check_path'])}",
        f"              port: {service['port']}",
        "            initialDelaySeconds: 15",
        "            periodSeconds: 20",
        "          resources:",
        "            requests:",
        f"              cpu: {_yaml_scalar(service['cpu_request'])}",
        f"              memory: {_yaml_scalar(service['memory_request'])}",
        "            limits:",
        f"              cpu: {_yaml_scalar(service['cpu_limit'])}",
        f"              memory: {_yaml_scalar(service['memory_limit'])}",
        "",
    ]
    return "\n".join(lines)


def k8s_service_for(service: dict[str, Any]) -> str:
    name = kebab(service["name"])
    return "\n".join(
        [
            "apiVersion: v1",
            "kind: Service",
            "metadata:",
            f"  name: {name}",
            "spec:",
            "  selector:",
            f"    app: {name}",
            "  ports:",
            "    - protocol: TCP",
            f"      port: {service['port']}",
            f"      targetPort: {service['port']}",
            "  type: ClusterIP",
            "",
        ]
    )


def k8s_configmap_for(service: dict[str, Any]) -> str:
    """Non-secret env vars only. Anything marked secret is referenced, never written to a file."""
    name = kebab(service["name"])
    lines = [
        "apiVersion: v1",
        "kind: ConfigMap",
        "metadata:",
        f"  name: {name}-config",
        "data:",
    ]
    public = [e for e in service.get("env_vars", []) if not e.get("secret")]
    if not public:
        lines.append("  {}")
    for env in public:
        lines.append(f"  {env['name']}: {_yaml_scalar(env['value'])}")
    secrets = [e for e in service.get("env_vars", []) if e.get("secret")]
    if secrets:
        lines.append("")
        lines.append("# Secrets are deliberately NOT written here. Create them out of band:")
        names = " ".join(f"--from-literal={e['name']}=..." for e in secrets)
        lines.append(f"#   kubectl create secret generic {name}-secrets {names}")
    return "\n".join(lines) + "\n"


_SQL_ENGINES = ("postgres", "mysql", "mariadb", "cockroach")


def ddl_for(service_schema: dict[str, Any]) -> str | None:
    """CREATE TABLE statements, for relational engines only.

    Returns None for Redis/MongoDB — emitting SQL for a document or key-value store would be
    actively misleading, so the export writes a note instead.
    """
    engine = service_schema.get("engine", "").lower()
    if not any(sql in engine for sql in _SQL_ENGINES):
        return None

    blocks: list[str] = [f"-- {service_schema['name']} ({service_schema['engine']})", ""]
    for table in service_schema.get("tables", []):
        blocks.append(f"CREATE TABLE {table['name']} (")
        parts = []
        for column in table.get("columns", []):
            null = "" if column.get("nullable") else " NOT NULL"
            parts.append(f"    {column['name']} {column['type']}{null}")
        primary = [c["name"] for c in table.get("columns", []) if c.get("primary_key")]
        if primary:
            parts.append(f"    PRIMARY KEY ({', '.join(primary)})")
        blocks.append(",\n".join(parts))
        blocks.append(");")
        for index in table.get("indexes", []):
            unique = "UNIQUE " if index.get("unique") else ""
            blocks.append(
                f"CREATE {unique}INDEX {index['name']} ON {table['name']} "
                f"({', '.join(index['columns'])});"
            )
        blocks.append("")
    return "\n".join(blocks)


def _service_readme(name: str, lld: dict[str, Any], infra: dict[str, Any]) -> str:
    lines = [f"# {name}", ""]
    if lld:
        lines += [f"**Stack:** {lld.get('tech_stack', 'n/a')}", ""]
    if infra:
        lines += [
            f"**Port:** {infra['port']}  ",
            f"**Health check:** `{infra['health_check_path']}`  ",
            f"**Replicas:** {infra['replicas']}",
            "",
        ]
    endpoints = lld.get("endpoints", []) if lld else []
    if endpoints:
        lines += ["## Endpoints", "", "| Method | Path | Called by | Summary |", "|---|---|---|---|"]
        for endpoint in endpoints:
            callers = ", ".join(endpoint.get("called_by", [])) or "-"
            lines.append(
                f"| {endpoint['method']} | `{endpoint['path']}` | {callers} | {endpoint['summary']} |"
            )
        lines.append("")
    published = lld.get("published_events", []) if lld else []
    consumed = lld.get("consumed_events", []) if lld else []
    if published or consumed:
        lines += ["## Events", ""]
        for event in published:
            lines.append(f"- publishes `{event}`")
        for event in consumed:
            lines.append(f"- consumes `{event}`")
        lines.append("")
    if lld and lld.get("internal_logic_notes"):
        lines += ["## Implementation notes", "", lld["internal_logic_notes"], ""]
    return "\n".join(lines)


def _root_readme(project_name: str, description: str, stages: dict[str, Any]) -> str:
    lines = [
        f"# {project_name}",
        "",
        description.strip(),
        "",
        "> Generated by AI Microservice Architect. Every artifact below was reviewed and approved",
        "> stage by stage before this scaffold was produced.",
        "",
        "## Services",
        "",
    ]
    boundaries = stages.get(StageType.BOUNDARIES.value) or {}
    hld = stages.get(StageType.HLD.value) or {}
    engines = {s["name"]: s.get("datastore", "-") for s in hld.get("services", [])}
    lld = {s["name"]: s for s in (stages.get(StageType.LLD.value) or {}).get("services", [])}

    lines += ["| Service | Domain | Datastore | Stack |", "|---|---|---|---|"]
    for service in boundaries.get("services", []):
        name = service["name"]
        lines.append(
            f"| [{name}](services/{kebab(name)}/) | {service.get('domain', '-')} | "
            f"{engines.get(name, '-')} | {lld.get(name, {}).get('tech_stack', '-')} |"
        )
    lines.append("")

    events = stages.get(StageType.KAFKA_EVENTS.value) or {}
    if events.get("topics"):
        lines += ["## Event topics", "", "| Topic | Producer | Consumers | Key |", "|---|---|---|---|"]
        for topic in events["topics"]:
            consumers = ", ".join(c["service"] for c in topic.get("consumers", []))
            lines.append(
                f"| `{topic['name']}` | {topic['producer']} | {consumers} | `{topic['partition_key']}` |"
            )
        lines.append("")

    lines += [
        "## Running it",
        "",
        "```bash",
        "docker compose up -d",
        "```",
        "",
        "Kubernetes manifests are under each service's `k8s/` directory.",
        "",
        "## Diagrams",
        "",
        "See [docs/](docs/) — Mermaid sources for the service map, ER diagram and event flow.",
        "",
    ]
    return "\n".join(lines)


# zipfile stamps every entry with the current time, which would make two exports of the same
# project differ byte-for-byte. A fixed timestamp keeps the output reproducible.
_FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _write(archive: zipfile.ZipFile, path: str, content: str) -> None:
    info = zipfile.ZipInfo(path, date_time=_FIXED_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, content)


def build_export(project_name: str, description: str, stages: dict[str, Any]) -> bytes:
    """Returns a zip archive of the whole scaffold. Byte-identical for identical input."""
    infra = stages.get(StageType.INFRA.value) or {}
    lld_services = {s["name"]: s for s in (stages.get(StageType.LLD.value) or {}).get("services", [])}
    db_services = {
        s["name"]: s for s in (stages.get(StageType.DB_SCHEMA.value) or {}).get("services", [])
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        _write(archive, "README.md", _root_readme(project_name, description, stages))

        if infra:
            _write(archive, "docker-compose.yml", compose_for(infra))

        for service in infra.get("services", []):
            name = service["name"]
            folder = f"services/{kebab(name)}"
            _write(archive, f"{folder}/Dockerfile", dockerfile_for(service))
            _write(archive, f"{folder}/k8s/deployment.yaml", k8s_deployment_for(service))
            _write(archive, f"{folder}/k8s/service.yaml", k8s_service_for(service))
            _write(archive, f"{folder}/k8s/configmap.yaml", k8s_configmap_for(service))
            _write(
                archive,
                f"{folder}/README.md",
                _service_readme(name, lld_services.get(name, {}), service),
            )
            schema = db_services.get(name)
            if schema:
                ddl = ddl_for(schema)
                if ddl:
                    _write(archive, f"{folder}/schema.sql", ddl)
                else:
                    _write(
                        archive,
                        f"{folder}/DATASTORE.md",
                        f"# {name} datastore\n\n**Engine:** {schema['engine']}\n\n"
                        f"{schema.get('notes', '')}\n\nNot a relational store, so no DDL is "
                        f"generated. See the schema JSON in `docs/` for the intended shape.\n",
                    )

        # The reviewed artifacts themselves, so the scaffold is self-documenting.
        for stage_type, output in stages.items():
            if output:
                _write(
                    archive, f"docs/{stage_type}.json", json.dumps(output, indent=2, sort_keys=True)
                )

        for stage_type in (StageType.HLD, StageType.DB_SCHEMA, StageType.KAFKA_EVENTS):
            output = stages.get(stage_type.value)
            if output:
                _write(
                    archive, f"docs/{stage_type.value}.mmd", diagram.render_stage(stage_type, output)
                )

    return buffer.getvalue()
