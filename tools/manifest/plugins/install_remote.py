"""Runs ON the robot (install.py ships it): hook Manifest's server.py and live UI to the plugin loader, once.

    python3 install_remote.py <dreamapi dir> <pane dir>

- server.py: one hook before "# Dream wire." that asks manifest_plugins.dispatch() first; removes the older inline
  /v1/arms block (patch_manifest_arm_pane.py) since the arm_cooling plugin now serves those routes.
- ui/index.html: loads /v1/plugins/ui.js; removes the older /ui/arm-cooling.js tag.
Backs up each file it changes (.bak-plugins-<time>). Prints RESTART when server.py changed (manifest-live must restart).
"""

import re
import shutil
import sys
import time
from pathlib import Path

root, pane = Path(sys.argv[1]), Path(sys.argv[2])
server, index = root / "server.py", root / "ui" / "index.html"
stamp = time.strftime("%Y%m%dT%H%M%S")
MARK = "# manifest_plugins"
ANCHOR = "        # Dream wire.\n"
HOOK = f'''        if path.startswith('/v1/'):  {MARK}: hot-reloaded plugins from {pane}/plugins answer first
            try:
                if {str(pane)!r} not in sys.path:
                    sys.path.insert(0, {str(pane)!r})
                import manifest_plugins
                _plugin_reply = manifest_plugins.dispatch(method, path, body, query, app)
            except Exception as exc:
                _plugin_reply = (500, {{'error': f'plugins: {{exc}}'}})
            if _plugin_reply is not None:
                return self.reply(*_plugin_reply)
'''
SCRIPT = '<script src="/v1/plugins/ui.js"></script><!-- manifest_plugins -->'


def backup(path: Path) -> None:
    shutil.copy2(path, path.with_name(f"{path.name}.bak-plugins-{stamp}"))


src = server.read_text()
changed_server = False
if MARK not in src:
    # Drop the older inline /v1/arms block: from its marker line up to the anchor.
    start = src.find("        if path.startswith('/v1/arms/') and method in ('GET', 'POST'):  # arm_cooling_pane\n")
    if start != -1:
        end = src.find(ANCHOR, start)
        if end == -1:
            sys.exit("old arms block found but no anchor after it; nothing changed")
        src = src[:start] + src[end:]
    if src.count(ANCHOR) != 1:
        sys.exit("server.py anchor not found exactly once; nothing changed")
    src = src.replace(ANCHOR, HOOK + ANCHOR)
    backup(server)
    server.write_text(src)
    changed_server = True
    print("server.py: plugin hook installed")
else:
    print("server.py: hook already installed")

html = index.read_text()
new = re.sub(r'<script src="/ui/arm-cooling\.js[^"]*"></script>', "", html).replace("<!-- arm_cooling_pane -->", "")
if "manifest_plugins" not in new:
    if new.count("</body>") != 1:
        sys.exit("index.html has no single </body>; nothing changed")
    new = new.replace("</body>", SCRIPT + "</body>")
if new != html:
    backup(index)
    index.write_text(new)
    print("index.html: loads /v1/plugins/ui.js")
else:
    print("index.html: already loads plugins")
print("RESTART" if changed_server else "NO_RESTART")
