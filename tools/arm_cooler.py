"""Arm Cooler: a small web GUI to rest one MakerArm (torque off) while Manifest uses the other, and swap them.

    uv run tools/arm_cooler.py                 # opens a tunnel to the robot's station and serves http://127.0.0.1:8098
    STATION_URL=http://127.0.0.1:8091 python3 tools/arm_cooler.py    # on the robot itself: no tunnel

Live temperatures of all 14 motors come from the station's /supervisor/preview (observation only). Rest/Wake
call the station add-on in tools/station/arm_rest.py (POST /supervisor/arm/rest|wake); until that is installed
the buttons report it. Standard library only.

The arms have no brakes: a rested arm goes LIMP. Rest it only when it is supported or at its rest pose.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.environ.get("ARM_COOLER_PORT", "8098"))
TUNNEL_PORT = 18091
WARN_C, STOP_C = 55.0, 60.0  # robots.makers ARM.temp_warn_c; stop is a display guess
MOTORS = ["base", "shoulder", "elbow", "wrist 1", "wrist 2", "wrist 3", "gripper"]


def station(path: str, body: dict | None = None, timeout: float = 8.0) -> tuple[int, dict]:
    req = urllib.request.Request(STATION + path, data=json.dumps(body or {}).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {"error": f"HTTP {e.code}"}
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return 0, {"error": f"station unreachable: {e}"}


def state() -> dict:
    code, d = station("/supervisor/preview")
    if code != 200:
        return {"ok": False, "error": d.get("error", f"HTTP {code}")}
    st = d.get("status") or {}
    arms = {}
    for side in ("left", "right"):
        m = (d.get("measured") or {}).get(side) or {}
        temps = m.get("motor_temps_c") or []
        arms[side] = {"temps": temps, "max": max(temps) if temps else None}
    rest = d.get("arm_rest")
    return {"ok": True, "mode": d.get("mode"), "state": st.get("state"), "problem": d.get("problem"),
            "enabled": d.get("enabled_arms") or [], "arms": arms, "addon": rest is not None,
            "rest": rest or {"resting": [], "resting_s": {}, "awake": ["left", "right"]},
            "lease": bool((d.get("lease") or {}).get("active")), "time": time.strftime("%H:%M:%S")}


def act(kind: str, body: dict) -> tuple[int, dict]:
    if kind == "swap":  # wake the resting arm, then rest the one that was working
        use = body.get("use")
        other = {"left": "right", "right": "left"}.get(use)
        if not other:
            return 400, {"error": "swap needs use: left or right"}
        code, d = station("/supervisor/arm/wake", {"arm": use}, timeout=30)
        if code != 200:
            return code, d
        return station("/supervisor/arm/rest", {"arm": other, "confirm_supported": body.get("confirm_supported")})
    path = {"rest": "/supervisor/arm/rest", "wake": "/supervisor/arm/wake"}[kind]
    code, d = station(path, body, timeout=30)
    if "Unsupported MakerArm operation" in str(d.get("error")):
        d = {"error": "The station add-on isn't installed on the robot yet (tools/station/arm_rest.py): "
                      "deploy it and restart manifest-makerarm."}
    return code, d


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    def _send(self, code: int, body: bytes, kind: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/api/state":
            self._send(200, json.dumps(state()).encode())
        else:
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")

    def do_POST(self) -> None:
        kind = self.path.rsplit("/", 1)[-1]
        if kind not in ("rest", "wake", "swap"):
            return self._send(404, b'{"error":"unknown"}')
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        code, d = act(kind, body)
        print(time.strftime("%H:%M:%S"), kind, body.get("arm") or body.get("use"), "->", code, d.get("error", "ok"))
        self._send(200 if code == 200 else 409, json.dumps(d).encode())


PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Arm Cooler</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1c1c1a;--mut:#6b6a66;--ok:#2f8f5b;--warn:#c98a1b;--hot:#c4372d;--line:#e3e1db}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--card:#1f1f1d;--ink:#eceae4;--mut:#9a988f;--line:#33322e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.4 system-ui,sans-serif;padding:20px}
h1{font-size:20px;margin:0 0 4px}.sub{color:var(--mut);margin-bottom:16px}
.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.head{display:flex;justify-content:space-between;align-items:baseline}.side{font-size:18px;font-weight:600;text-transform:capitalize}
.badge{font-size:12px;font-weight:600;padding:3px 8px;border-radius:99px;color:#fff}
.max{font-size:34px;font-weight:700;margin:6px 0 10px;font-variant-numeric:tabular-nums}
.m{display:grid;grid-template-columns:70px 1fr 44px;gap:8px;align-items:center;font-size:13px;margin:3px 0}
.bar{height:8px;border-radius:4px;background:var(--line);overflow:hidden}.bar i{display:block;height:100%}
.n{text-align:right;font-variant-numeric:tabular-nums}
button{font:inherit;font-weight:600;border:0;border-radius:8px;padding:9px 14px;cursor:pointer;margin-top:12px}
button:disabled{opacity:.4;cursor:default}.rest{background:#2c4a7a;color:#fff}.wake{background:var(--ok);color:#fff}
.swap{background:var(--ink);color:var(--bg)}label{display:flex;gap:8px;align-items:center;margin-top:12px;color:var(--mut);font-size:13px}
#banner{padding:10px 14px;border-radius:10px;margin-bottom:14px;display:none}#msg{margin-top:12px;min-height:20px;color:var(--hot)}
.bar2{display:flex;gap:16px;flex-wrap:wrap;color:var(--mut);font-size:13px;margin-bottom:14px}
</style>
<h1>Arm Cooler</h1><div class=sub>Rest one arm (torque off) while Manifest uses the other. Rested arms go <b>limp</b>: no brakes.</div>
<div class=bar2 id=meta></div><div id=banner></div>
<div class=row id=arms></div>
<div class=card style="margin-top:16px"><label><input type=checkbox id=ok> The arm I'm resting is supported or at its rest pose, and hands are clear.</label>
<div id=swapbox></div><div id=msg></div></div>
<script>
const color=t=>t==null?'var(--line)':t>=55?'var(--hot)':t>=48?'var(--warn)':'var(--ok)';
const names=%MOTORS%;
let S=null,busy=false;
async function post(kind,body){if(busy)return;busy=true;msg('Working…','var(--mut)');
 try{const r=await fetch('/api/'+kind,{method:'POST',body:JSON.stringify(body)});const d=await r.json();
  msg(r.ok?'Done.':(d.error||'Failed'),r.ok?'var(--ok)':'var(--hot)')}catch(e){msg(String(e),'var(--hot)')}
 busy=false;load()}
function msg(t,c){const m=document.getElementById('msg');m.textContent=t;m.style.color=c}
function needOk(){if(!document.getElementById('ok').checked){msg('Tick the box first: the rested arm goes limp.','var(--hot)');return false}return true}
function rest(side){if(needOk())post('rest',{arm:side,confirm_supported:true})}
function wake(side){post('wake',{arm:side})}
function swap(use){if(needOk())post('swap',{use,confirm_supported:true})}
function restBoth(){if(needOk())post('rest',{arm:'both',confirm_supported:true})}
function wakeBoth(){post('wake',{arm:'both'})}
function render(){const a=document.getElementById('arms'),meta=document.getElementById('meta'),b=document.getElementById('banner');
 if(!S.ok){a.innerHTML='';meta.textContent='';b.style.display='block';b.style.background='var(--hot)';b.style.color='#fff';b.textContent='Station: '+S.error;return}
 meta.innerHTML=`<span>station <b>${S.state}</b></span><span>Manifest can use: <b>${S.enabled.join(' + ')||'none'}</b></span><span>${S.lease?'action running':'no action running'}</span><span>${S.addon?'rest add-on installed':'rest add-on NOT installed'}</span><span>${S.time}</span>`;
 const resting=S.rest.resting;let html='';
 for(const side of ['left','right']){const A=S.arms[side],r=resting.includes(side);
  const st=r?['RESTING · torque off','#2c4a7a']:['ACTIVE','var(--ok)'];const secs=S.rest.resting_s[side];
  html+=`<div class=card><div class=head><span class=side>${side} arm</span><span class=badge style="background:${st[1]}">${st[0]}${r&&secs!=null?' · '+Math.floor(secs/60)+'m'+String(secs%60).padStart(2,'0'):''}</span></div>
  <div class=max style="color:${color(A.max)}">${A.max??'–'}°C</div>`;
  A.temps.forEach((t,i)=>{html+=`<div class=m><span>${names[i]||'m'+i}</span><span class=bar><i style="width:${Math.min(100,Math.max(4,(t-25)/40*100))}%;background:${color(t)}"></i></span><span class=n>${t}°</span></div>`});
  html+=r?`<button class=wake onclick="wake('${side}')">Wake ${side} (torque on)</button>`:`<button class=rest onclick="rest('${side}')">Rest ${side} (torque off)</button>`;
  html+='</div>'}
 a.innerHTML=html;
 const sw=document.getElementById('swapbox');
 if(resting.length===1){const use=resting[0],other=use==='left'?'right':'left';
  sw.innerHTML=`<button class=swap onclick="swap('${use}')">Swap: wake ${use}, rest ${other}</button>`}else sw.innerHTML='';
 sw.innerHTML+=` <button class=rest onclick="restBoth()" ${resting.length===2?'disabled':''}>Turn both OFF (torque off)</button> <button class=wake onclick="wakeBoth()" ${resting.length?'':'disabled'}>Turn both ON (torque on)</button>`;
 const L=S.arms.left.max,R=S.arms.right.max;let tip='';
 if(S.problem){tip='Station problem: '+S.problem}
 else if(resting.length===1){const use=resting[0],act=use==='left'?'right':'left';
  if(S.arms[act].max>=52&&S.arms[use].max<=47)tip=`The ${act} arm is at ${S.arms[act].max}°C and the ${use} arm has cooled to ${S.arms[use].max}°C: swap.`}
 else if(L!=null&&R!=null&&Math.max(L,R)>=50){const hot=L>=R?'left':'right';tip=`The ${hot} arm is warm (${Math.max(L,R)}°C): rest it while Manifest uses the other.`}
 b.style.display=tip?'block':'none';b.style.background=S.problem?'var(--hot)':'var(--warn)';b.style.color='#fff';b.textContent=tip}
async function load(){try{S=await (await fetch('/api/state')).json()}catch(e){S={ok:false,error:String(e)}}render()}
load();setInterval(()=>{if(!busy)load()},1500);
</script>""".replace("%MOTORS%", json.dumps(MOTORS))


def main() -> None:
    global STATION
    tunnel = None
    STATION = os.environ.get("STATION_URL", "")
    if not STATION:
        machine = os.environ.get("ARM_COOLER_MACHINE", "robot")
        print(f"opening a tunnel to {machine}'s station (port 8091 -> 127.0.0.1:{TUNNEL_PORT})")
        tunnel = subprocess.Popen([str(ROOT / "tools/ssh.sh"), "--tunnel", f"8091:{TUNNEL_PORT}", machine],
                                  stdout=subprocess.DEVNULL)
        STATION = f"http://127.0.0.1:{TUNNEL_PORT}"
        for _ in range(40):
            if station("/supervisor/preview", timeout=2)[0] == 200:
                break
            time.sleep(0.5)
    url = f"http://127.0.0.1:{PORT}"
    print(f"Arm Cooler on {url}  (station {STATION}; Ctrl-C to quit)")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    if sys.stdout.isatty():
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if tunnel:
            tunnel.terminate()


STATION = ""
if __name__ == "__main__":
    main()
