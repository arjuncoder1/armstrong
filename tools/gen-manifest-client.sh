#!/usr/bin/env bash
# Regenerate manifest_client/ from the live Manifest OpenAPI spec on the robot machine.
#
#   tools/gen-manifest-client.sh            # machine "robot" from .env.ssh
#   tools/gen-manifest-client.sh <machine>
#
# The spec is fetched over SSH and kept in a temp dir only: no Manifest source or spec goes in the repo,
# just the generated client. The spec lacks operationIds and {id} path parameters; they are added here.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
machine="${1:-robot}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# MANIFEST_URL (from .env.config) directly if Manifest is reachable from here; else over SSH from the robot's localhost.
url="${MANIFEST_URL:-$(grep -m1 '^MANIFEST_URL=' "$root/.env.config" 2>/dev/null | cut -d= -f2-)}"
url="${url:-http://127.0.0.1:8100/v1}"
if ! curl -sf --max-time 10 "$url/openapi.json" -o "$tmp/raw.json"; then
  echo "spec not reachable at $url; fetching over SSH from $machine" >&2
  "$root/tools/ssh.sh" "$machine" 'curl -sf --max-time 10 http://127.0.0.1:8100/v1/openapi.json' > "$tmp/raw.json"
fi

python3 - "$tmp/raw.json" "$tmp/spec.json" <<'EOF'
import json, sys

spec = json.load(open(sys.argv[1]))
NAMES = {
    ("get", "/health"): "health",
    ("get", "/robot"): "get_robot",
    ("post", "/tasks"): "start_task",
    ("get", "/tasks"): "list_tasks",
    ("get", "/tasks/{id}"): "get_task",
    ("post", "/tasks/{id}/messages"): "steer_task",
    ("post", "/tasks/{id}/stop"): "stop_task",
    ("get", "/routines"): "list_routines",
    ("get", "/routines/{id}"): "get_routine",
    ("put", "/routines/{id}"): "replace_routine",
    ("get", "/runs"): "list_runs",
    ("get", "/runs/{id}"): "get_run",
    ("get", "/runs/scoreboard"): "get_scoreboard",
    ("get", "/settings"): "get_settings",
    ("patch", "/settings"): "update_settings",
    ("get", "/models"): "list_models",
    ("post", "/get_action"): "get_action",
    ("post", "/end_session"): "end_session",
}
for path, ops in spec["paths"].items():
    for method, op in ops.items():
        op["operationId"] = NAMES.get((method, path)) or f"{method}_{path.strip('/').replace('/', '_').replace('{', '').replace('}', '')}"
        if "{id}" in path and not any(p.get("name") == "id" for p in op.get("parameters", [])):
            op.setdefault("parameters", []).append(
                {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}})
def add_array_items(node):  # untyped arrays (routine nodes/recoveries) become arrays of objects
    if isinstance(node, dict):
        if node.get("type") == "array" and "items" not in node and "prefixItems" not in node:
            node["items"] = {"type": "object"}
        for value in node.values():
            add_array_items(value)
    elif isinstance(node, list):
        for value in node:
            add_array_items(value)

add_array_items(spec)

# Every endpoint repeats the same inline error schema and a bare `object` success schema, which generates
# ~70 near-identical models. Hoist them into three shared ones: ApiError, ErrorResponse, JsonObject.
schemas = spec.setdefault("components", {}).setdefault("schemas", {})
for ops in spec["paths"].values():
    for op in ops.values():
        for code, response in op.get("responses", {}).items():
            content = response.get("content", {}).get("application/json")
            if not content:
                continue
            schema = content.get("schema", {})
            if code == "default":
                error = schema.get("properties", {}).get("error")
                if error and "ApiError" not in schemas:
                    schemas["ApiError"] = error
                content["schema"] = {"$ref": "#/components/schemas/ErrorResponse"}
            elif schema == {"type": "object"}:
                content["schema"] = {"$ref": "#/components/schemas/JsonObject"}
# The spec only lists 200, but e.g. POST /tasks answers 202 ("202 with the task record"); without this the
# client parses a 202 as an error. Accept 201/202 with the 200 body everywhere.
for ops in spec["paths"].values():
    for op in ops.values():
        responses = op.get("responses", {})
        if "200" in responses:
            for code in ("201", "202"):
                responses.setdefault(code, responses["200"])

schemas["ErrorResponse"] = {"type": "object", "properties": {"error": {"$ref": "#/components/schemas/ApiError"}}}
schemas["JsonObject"] = {"type": "object", "additionalProperties": True,
                         "description": "Manifest's JSON reply; the spec does not type it further."}

spec["servers"] = [{"url": "http://127.0.0.1:8100/v1"}]  # via `tools/ssh.sh robot -N -L 8100:127.0.0.1:8100`
json.dump(spec, open(sys.argv[2], "w"), indent=1)
EOF

cat > "$tmp/config.yaml" <<'EOF'
project_name_override: manifest-client
package_name_override: manifest_client
post_hooks: []
EOF

uvx openapi-python-client@0.30.0 generate --path "$tmp/spec.json" --config "$tmp/config.yaml" \
  --meta uv --output-path "$root/manifest_client" --overwrite

# Manifest has no auth (no securitySchemes, no token checks), so drop the generator's AuthenticatedClient.
python3 - "$root/manifest_client/manifest_client" <<'EOF'
import pathlib, re, sys

pkg = pathlib.Path(sys.argv[1])
client = pkg / "client.py"
text = client.read_text()
text = text[: text.index("@define\nclass AuthenticatedClient")].rstrip() + "\n"
client.write_text(text)
for path in pkg.rglob("*.py"):
    src = path.read_text()
    new = (src.replace("AuthenticatedClient | Client", "Client")
              .replace("import AuthenticatedClient, Client", "import Client")
              .replace('    "AuthenticatedClient",\n', ""))
    if new != src:
        path.write_text(new)
left = [str(p) for p in pkg.rglob("*.py") if "AuthenticatedClient" in p.read_text()]
assert not left, f"AuthenticatedClient still referenced in {left}"
EOF

cat > "$root/manifest_client/README.md" <<'EOF'
# manifest-client

Generated Python client for the Manifest robot API (runs on the robot machine, `127.0.0.1:8100/v1`).
**Generated code: don't edit by hand.** Regenerate with `tools/gen-manifest-client.sh`.

Use it through the wrapper, which returns plain dicts and raises `ManifestError`:

```python
from armstrong.manifest import Manifest

m = Manifest()          # MANIFEST_URL, default http://127.0.0.1:8100/v1
m.health(); m.robot()
```

From another machine, run `tools/manifest-tunnel.sh` first: Manifest only listens on the robot's localhost.
EOF
echo "generated $root/manifest_client ($(ls "$root/manifest_client/manifest_client/models" | grep -c '\.py$') model files)"
