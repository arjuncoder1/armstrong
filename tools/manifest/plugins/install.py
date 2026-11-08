"""Install or sync Manifest plugins on the robot.

    uv run tools/manifest/plugins/install.py              # sync plugins; hook Manifest once (restart if needed)
    uv run tools/manifest/plugins/install.py --no-restart # never restart manifest-live (hook waits for a restart)
    uv run tools/manifest/plugins/install.py --machine test   # another Manifest host from .env.ssh (default: robot)

Manifest's folder is found from that machine's manifest-live service (its WorkingDirectory); --dreamapi overrides.

Layout here:  manifest_plugins.py (loader) · install_remote.py · plugins/<name>/{plugin.py, ui.js}
On the robot: ~/armstrong-pane/{manifest_plugins.py, plugins/...}  (outside every git repo)

Plugins hot-reload: after the one-time hook, syncing is enough. manifest-live restarts only when the hook is first
installed, and only while no Manifest task is starting or running.
"""

import argparse
import io
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SSH = str(REPO / "tools" / "ssh.sh")
PANE = "~/armstrong-pane"
DEFAULT_DREAMAPI = "~/Documents/Codex/2026-10-23/set-x20/outputs/dreamlab/halo/dreamapi"  # the halo's layout
MACHINE = "robot"


def ssh(command: str, data: bytes | None = None, check: bool = True) -> str:
    result = subprocess.run([SSH, MACHINE, command], input=data, capture_output=True)
    out = result.stdout.decode(errors="replace")
    if check and result.returncode != 0:
        sys.exit(f"robot command failed ({result.returncode}): {command[:80]}\n{out}{result.stderr.decode(errors='replace')}")
    return out


def bundle() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in [HERE / "manifest_plugins.py", HERE / "install_remote.py", *sorted((HERE / "plugins").rglob("*"))]:
            if path.is_file() and "__pycache__" not in path.parts:
                tar.add(path, arcname=str(path.relative_to(HERE)))
    return buf.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-restart", action="store_true")
    parser.add_argument("--machine", default="robot", help="SSH name from .env.ssh (default: robot, the halo)")
    parser.add_argument("--dreamapi", help="Manifest's folder there (default: from its manifest-live service)")
    args = parser.parse_args()
    global MACHINE
    MACHINE = args.machine
    found = ssh("systemctl --user show manifest-live -p WorkingDirectory --value 2>/dev/null", check=False).strip()
    dreamapi = args.dreamapi or found or DEFAULT_DREAMAPI
    print(f"machine {MACHINE}: Manifest at {dreamapi}")

    names = sorted(p.name for p in (HERE / "plugins").iterdir() if p.is_dir())
    print("syncing plugins:", ", ".join(names))
    ssh(f"mkdir -p {PANE} && rm -rf {PANE}/plugins.new && mkdir {PANE}/plugins.new && "
        f"tar -xzf - -C {PANE}/plugins.new && cp {PANE}/plugins.new/manifest_plugins.py {PANE}/plugins.new/install_remote.py {PANE}/ && "
        f"rm -rf {PANE}/plugins && mv {PANE}/plugins.new/plugins {PANE}/plugins && rm -rf {PANE}/plugins.new", data=bundle())

    out = ssh(f"python3 {PANE}/install_remote.py {dreamapi} {PANE}")
    print(out.strip())
    if "RESTART" not in out.splitlines()[-1] or out.strip().endswith("NO_RESTART"):
        print("done: plugins hot-reload, no restart needed")
        return
    py = ssh("systemctl --user show manifest-live -p ExecStart --value 2>/dev/null | grep -oE 'path=[^ ;]+' | head -1 | cut -d= -f2",
             check=False).strip() or "python3"
    ssh(f"{py} -m py_compile {dreamapi}/server.py")
    if args.no_restart:
        print("hook installed; restart manifest-live yourself when no task runs: systemctl --user restart manifest-live")
        return
    running = ssh("curl -s --max-time 5 http://$(hostname -I | cut -d' ' -f1):8100/v1/tasks | "
                  "python3 -c \"import sys,json;print(sum(t.get('status') in ('starting','running') for t in json.load(sys.stdin)['tasks']))\"").strip()
    if running != "0":
        print(f"{running} Manifest task(s) running: hook installed, NOT restarted. Re-run later to restart.")
        return
    ssh("systemctl --user restart manifest-live && for i in $(seq 30); do sleep 2; "
        "curl -s -o /dev/null --max-time 2 http://$(hostname -I | cut -d' ' -f1):8100/health && break; done")
    print("manifest-live restarted")


if __name__ == "__main__":
    main()
