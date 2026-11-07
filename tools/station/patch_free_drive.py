"""Wire Zero-G (free_drive.py) into the station and Manifest's GUI. Idempotent; backs each file up before writing it.

    python3 patch_free_drive.py [--check] [--station DIR] [--gui DIR]

station DIR (default: next to this script): makerarm_control.py (route, guards, state), makerarm_teaching.py (teach
hand guidance uses Zero-G instead of going limp). gui DIR (default: Manifest's halo/dreamapi): server.py (the
/v1/arms/freedrive route and free_drive in /v1/arms/state), ui/index.html (loads ui/zero-g.js).
Every hook is an exact-text insertion; if any anchor of a file is missing or ambiguous that file is not written.
Takes effect when manifest-makerarm (station) and manifest-live (GUI server) restart; the UI script on page reload.
"""

import re
import shutil
import sys
import time
from pathlib import Path

MARK = "# free_drive"
HERE = Path(__file__).resolve().parent
GUI = Path.home() / "Documents/Codex/2026-10-23/set-x20/outputs/dreamlab/halo/dreamapi"

CONTROL = [
    ("  self.rest=ArmRest(self)  # arm_rest\n",
     "  self.rest=ArmRest(self)  # arm_rest\n"
     "  from free_drive import FreeDrive  # free_drive\n"
     "  self.fd=FreeDrive(self)  # free_drive\n"),
    ("  d['images']=[]\n",
     "  d['free_drive']=self.fd.public()  # free_drive\n"
     "  if d['free_drive']['active']:d['enabled_arms']=[a for a in d['enabled_arms'] if a not in d['free_drive']['active']]  # free_drive\n"
     "  d['images']=[]\n"),
    ("  if self.rest.blocks(b.get('arm')):raise ValueError(self.rest.blocks(b.get('arm')))  # arm_rest\n",
     "  if self.rest.blocks(b.get('arm')):raise ValueError(self.rest.blocks(b.get('arm')))  # arm_rest\n"
     "  if self.fd.blocks(b.get('arm')):raise ValueError(self.fd.blocks(b.get('arm')))  # free_drive\n"),
    ("  if self.c.state not in ('idle','error'):raise ValueError('Station must be idle before homing')\n",
     "  if self.fd.on():raise ValueError('Turn Zero-G off before homing')  # free_drive\n"
     "  if self.c.state not in ('idle','error'):raise ValueError('Station must be idle before homing')\n"),
    ("   if route=='/supervisor/arm/rest':r=api.call(br.rest.rest(b))  # arm_rest\n",
     "   if route in ('/supervisor/cv/start','/reset') and br.fd.on():raise ValueError('Turn Zero-G off first')  # free_drive\n"
     "   if route=='/supervisor/arm/rest':[br.fd.release(s) for s in br.fd.on() if b.get('arm') in (s,'both',None)]  # free_drive: hold first, then torque off\n"
     "   if route=='/supervisor/arm/rest':r=api.call(br.rest.rest(b))  # arm_rest\n"),
    ("   elif route=='/supervisor/cv/start':r=api.call(br.cv.start())\n",
     "   elif route=='/supervisor/arm/freedrive':r=br.fd.route(b)  # free_drive\n"
     "   elif route=='/supervisor/cv/start':r=api.call(br.cv.start())\n"),
]

TEACHING = [
    ("   return arm._driver.disengage()\n",
     "   fd=getattr(self.bridge,'fd',None)  # free_drive: hand guiding is weightless (Zero-G), not limp\n"
     "   if fd is None:return arm._driver.disengage()  # free_drive\n"
     "   try:fd.engage(side,teach=True);return True  # free_drive\n"
     "   except Exception:self.tokens.pop(side,None);raise  # free_drive\n"),
    ("  if method=='teach_keepalive':\n",
     "  if method=='teach_keepalive':\n"
     "   if side in getattr(getattr(self.bridge,'fd',None),'teach_sides',()) and not self.bridge.fd.active(side):raise ValueError('Zero-G stopped: '+self.bridge.fd.why(side))  # free_drive\n"),
    ("  if method=='teach_hold':\n",
     "  if method=='teach_hold':\n"
     "   if side in getattr(getattr(self.bridge,'fd',None),'teach_sides',()):self.bridge.fd.release(side);self.tokens.pop(side,None);return True  # free_drive: still energized, hold where it is\n"),
]

SERVER = [
    ("if kind not in ('state', 'rest', 'wake', 'use', 'lock', 'unlock') or",
     "if kind not in ('state', 'rest', 'wake', 'use', 'lock', 'unlock', 'freedrive') or"),
    ("'arm_rest': d.get('arm_rest'), 'problem': d.get('problem'),",
     "'arm_rest': d.get('arm_rest'), 'free_drive': d.get('free_drive'), 'problem': d.get('problem'),"),
]


def patch(path: Path, hooks, done: str, check: bool, regex: bool = False) -> bool:
    src = path.read_text()
    if done in src:
        print(f"{path}: already patched")
        return True
    for old, _ in hooks:
        n = len(re.findall(old, src)) if regex else src.count(old)
        if n != 1:
            print(f"{path}: anchor found {n} times, NOT written:\n  {old!r}")
            return False
    if check:
        print(f"{path}: all {len(hooks)} anchors found (check only)")
        return True
    for old, new in hooks:
        src = re.sub(old, lambda m: m.group(0) + new, src, count=1) if regex else src.replace(old, new, 1)
    backup = path.with_name(f"{path.name}.bak-freedrive-{time.strftime('%Y%m%dT%H%M%S')}")
    shutil.copy2(path, backup)
    path.write_text(src)
    print(f"patched {path} (backup {backup.name})")
    return True


def main() -> int:
    args = sys.argv[1:]
    check = "--check" in args
    station = Path(args[args.index("--station") + 1]) if "--station" in args else HERE
    gui = Path(args[args.index("--gui") + 1]) if "--gui" in args else GUI
    for need in (station / "free_drive.py", station / "maker_gravity.py", gui / "ui" / "zero-g.js"):
        if not need.exists():
            print(f"missing {need}: copy it there first")
            return 1
    ok = patch(station / "makerarm_control.py", CONTROL, MARK, check)
    ok &= patch(station / "makerarm_teaching.py", TEACHING, MARK, check)
    ok &= patch(gui / "server.py", SERVER, "'freedrive')", check)
    ok &= patch(gui / "ui" / "index.html", [(r'<script src="/ui/arm-cooling\.js(\?v=[^"]*)?"></script>',
                                              '<script src="/ui/zero-g.js?v=1"></script>')], "zero-g.js", check, regex=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
