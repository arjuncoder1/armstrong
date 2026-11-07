"""Wire arm_rest.py into the station's makerarm_control.py (idempotent; backs the file up first).

    python3 patch_arm_rest.py [path/to/makerarm_control.py]      # default: next to this script

Every hook is an exact-text insertion; if any anchor is missing or ambiguous nothing is written.
"""

import shutil
import sys
import time
from pathlib import Path

MARK = "# arm_rest"
target = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("makerarm_control.py"))
src = target.read_text()
if MARK in src:
    print(f"{target}: already patched")
    sys.exit(0)

HOOKS = [
    # 1. Create the ArmRest helper with the other station helpers.
    ("  self.cv=CVTeleop(self)\n",
     "  self.cv=CVTeleop(self)\n"
     "  from arm_rest import ArmRest  # arm_rest\n"
     "  self.rest=ArmRest(self)  # arm_rest\n"),
    # 2. Never send commands to a resting (disengaged) arm.
    ("   def write(command,side=side,original=original):\n",
     "   def write(command,side=side,original=original):\n"
     "    if getattr(self,'rest',None) and side in self.rest.resting:return  # arm_rest: torque is off, send nothing\n"),
    # 3. Report it, so Manifest's agent only plans for the awake arm.
    ("  if self.teaching.active:d['mode']='teaching';d['enabled_arms']=[a for a in ('left','right') if a!=self.teaching.session['arm']]\n",
     "  if self.teaching.active:d['mode']='teaching';d['enabled_arms']=[a for a in ('left','right') if a!=self.teaching.session['arm']]\n"
     "  d['arm_rest']=self.rest.public()  # arm_rest\n"
     "  if self.rest.resting:d['enabled_arms']=[a for a in d['enabled_arms'] if a not in self.rest.resting];d['locked_arms']=sorted(self.rest.resting)  # arm_rest\n"),
    # 4. Refuse actions that would drive the resting arm.
    ("  if self.teaching.active:raise ValueError('Finish teaching before movement')\n",
     "  if self.teaching.active:raise ValueError('Finish teaching before movement')\n"
     "  if self.rest.blocks(b.get('arm')):raise ValueError(self.rest.blocks(b.get('arm')))  # arm_rest\n"),
    # 5. Native home walks both arms.
    ("  if self.teaching.active:raise ValueError('Finish teaching before homing')\n",
     "  if self.teaching.active:raise ValueError('Finish teaching before homing')\n"
     "  if self.rest.resting:raise ValueError('Wake the resting arm before homing')  # arm_rest\n"),
    # 6. Routes; reset, CV teleop and teaching would drive or re-home the resting arm.
    ("   if route=='/supervisor/cv/start':r=api.call(br.cv.start())\n",
     "   if route in ('/supervisor/cv/start','/reset','/supervisor/teach/start') and br.rest.resting:raise ValueError('Wake the resting arm first')  # arm_rest\n"
     "   if route=='/supervisor/arm/rest':r=api.call(br.rest.rest(b))  # arm_rest\n"
     "   elif route=='/supervisor/arm/wake':r=api.call(br.rest.wake(b))  # arm_rest\n"
     "   elif route=='/supervisor/cv/start':r=api.call(br.cv.start())\n"),
]

for old, _ in HOOKS:
    if src.count(old) != 1:
        sys.exit(f"anchor not found exactly once, nothing changed:\n{old!r}")
for old, new in HOOKS:
    src = src.replace(old, new)
backup = target.with_name(f"{target.name}.bak-armrest-{time.strftime('%Y%m%dT%H%M%S')}")
shutil.copy2(target, backup)
target.write_text(src)
print(f"patched {target} (backup {backup.name})")
