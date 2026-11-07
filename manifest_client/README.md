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
