"""Plugin loader for Manifest's server (server.py imports this once; see install.py).

Plugins live in PLUGINS_DIR (default ~/armstrong-pane/plugins), one folder each:

    plugins/<name>/plugin.py   optional: server routes, `def handle(req) -> tuple[int, object] | None`
    plugins/<name>/ui.js       optional: script for Manifest's live UI (served concatenated at /v1/plugins/ui.js)

`handle` gets a Request and returns (status, json_object) or (status, (bytes, content_type)) to answer, or None to
pass. Plugins are hot-reloaded when their files change, so adding or editing one needs no server restart.
Built-in routes: GET /v1/plugins (list, with load errors) and GET /v1/plugins/ui.js.
A plugin that raises answers 500 with the error; it never takes the server down.
"""

from __future__ import annotations

import importlib.util
import json
import os
import traceback
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PLUGINS_DIR = Path(os.environ.get("MANIFEST_PLUGINS_DIR", str(Path.home() / "armstrong-pane" / "plugins")))


@dataclass
class Request:
    method: str
    path: str
    body: dict
    query: dict
    app: Any  # Manifest's App: .settings, .config, .station
    plugin: str = ""
    extra: dict = field(default_factory=dict)

    def station(self, route: str, data: dict | None = None, timeout: float = 5.0) -> dict:
        """POST to the station (127.0.0.1:8091); raises StationError with its status and message."""
        req = urllib.request.Request(self.app.station + route, data=json.dumps(data or {}).encode(),
                                     headers={"Content-Type": "application/json", "X-DreamLab-Supervisor": "1"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                message = json.loads(exc.read() or b"{}").get("error") or f"station HTTP {exc.code}"
            except ValueError:
                message = f"station HTTP {exc.code}"
            raise StationError(exc.code, message) from None

    @property
    def motion_allowed(self) -> bool:
        return self.app.config.get("body") == "makers" and bool(self.app.settings.get("execute_allowed"))


class StationError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


_cache: dict[str, dict] = {}  # name -> {"mtime", "module", "error"}


def _plugins() -> dict[str, dict]:
    if not PLUGINS_DIR.is_dir():
        return {}
    seen = {}
    for folder in sorted(p for p in PLUGINS_DIR.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
        name, code = folder.name, folder / "plugin.py"
        entry = _cache.get(name, {})
        mtime = code.stat().st_mtime if code.exists() else None
        if code.exists() and entry.get("mtime") != mtime:
            try:
                spec = importlib.util.spec_from_file_location(f"manifest_plugin_{name}", code)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                entry = {"mtime": mtime, "module": module, "error": None}
            except Exception:  # noqa: BLE001 - report, don't crash Manifest
                entry = {"mtime": mtime, "module": None, "error": traceback.format_exc(limit=3)}
        elif not code.exists():
            entry = {"mtime": None, "module": None, "error": None}
        entry["dir"] = folder
        seen[name] = _cache[name] = entry
    return seen


def dispatch(method: str, path: str, body: dict, query: dict, app: Any):
    """Called by server.py before its own routes; returns (status, payload) to answer, or None."""
    if not path.startswith("/v1/"):
        return None
    if path == "/v1/plugins" and method == "GET":
        return 200, {"dir": str(PLUGINS_DIR), "plugins": [
            {"name": n, "server": e.get("module") is not None, "ui": (e["dir"] / "ui.js").exists(), "error": e.get("error")}
            for n, e in _plugins().items()]}
    if path == "/v1/plugins/ui.js" and method == "GET":
        parts = []
        for name, entry in _plugins().items():
            ui = entry["dir"] / "ui.js"
            if ui.exists():
                parts.append(f"// ---- plugin: {name}\ntry {{\n{ui.read_text()}\n}} catch (e) {{ console.error('plugin {name}', e); }}\n")
        return 200, ("\n".join(parts).encode(), "application/javascript; charset=utf-8")
    for name, entry in _plugins().items():
        module = entry.get("module")
        handle = getattr(module, "handle", None) if module else None
        if handle is None:
            continue
        try:
            result = handle(Request(method, path, body or {}, query or {}, app, plugin=name))
        except StationError as exc:
            return exc.code, {"error": exc.message}
        except Exception as exc:  # noqa: BLE001
            return 500, {"error": f"plugin {name}: {exc}"}
        if result is not None:
            return result
    return None
