"""The hand teleop's live web dashboard: tracking view, robot cameras, arm state, control and home.

`hand-teleop --dashboard` serves it for the local webcam; `--browser` also takes the camera from the viewing
browser (open the page through an SSH tunnel to http://localhost:<port>). Every route but the page itself needs
the token in the printed URL's fragment.
"""
import asyncio
import collections
import hmac
import json
import queue
import secrets
import time

import cv2
import numpy as np
from aiohttp import WSMsgType, web

COMMANDS = {"c", "release", "home"}  # take or release control, release only, home (confirmed on the page)
VIEW_FPS = {"tracking": 24}  # MJPEG rate per view; robot cameras default to 10

PAGE = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Hand Teleop</title>
<style>
:root{--bg:#141414;--panel:#1f1f1f;--line:#333;--text:#ececec;--muted:#9a9a9a;--ok:#4cd964;--warn:#ffb340;--bad:#ff5f57}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,-apple-system,sans-serif}
main{max-width:1320px;margin:0 auto;padding:20px;display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:16px}
header{grid-column:1/-1;display:flex;align-items:center;gap:12px}h1{font-size:22px;margin:0;font-weight:650}
.muted{color:var(--muted)}.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px}
.pill{display:inline-flex;align-items:center;gap:8px;padding:6px 12px;border-radius:999px;border:1px solid var(--line);font-weight:600}
.dot{width:9px;height:9px;border-radius:50%;background:var(--muted)}.ok .dot{background:var(--ok)}.warn .dot{background:var(--warn)}.bad .dot{background:var(--bad)}
.view{width:100%;aspect-ratio:4/3;background:#000;border-radius:10px;display:block;object-fit:contain}
.cams{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:12px}.cams figure{margin:0}
figcaption{font-size:12px;color:var(--muted);margin-top:4px}
button{font:inherit;color:var(--text);background:#2a2a2a;border:1px solid #444;border-radius:999px;padding:9px 16px;cursor:pointer}
button:hover{background:#333}button:disabled{opacity:.45;cursor:default}button.primary{background:#e9e9e9;color:#111;border-color:#e9e9e9}
.row{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}aside{display:flex;flex-direction:column;gap:16px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}td,th{padding:3px 4px;text-align:right}
th{color:var(--muted);font-weight:500}td:first-child,th:first-child{text-align:left;color:var(--muted)}
.stats{display:grid;grid-template-columns:1fr 1fr;gap:6px 12px}.stats b{font-variant-numeric:tabular-nums}
#log{height:180px;overflow:auto;font:12px/1.5 ui-monospace,Menlo,monospace;white-space:pre-wrap;color:#cfcfcf}
.follow span{display:inline-flex;align-items:center;gap:6px;margin-right:14px}
dialog{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:16px;max-width:460px;padding:22px}
dialog::backdrop{background:rgba(0,0,0,.55)}video{display:none}
</style></head><body><main>
<header><h1>Hand Teleop</h1><span class="muted">MediaPipe + IK · room <b id="room">-</b></span>
<span style="flex:1"></span><span id="link" class="pill bad"><span class="dot"></span><span>connecting</span></span></header>
<section class="panel">
 <img id="tracking" class="view" alt="hand tracking">
 <div class="cams" id="cams"></div>
 <p class="muted" style="margin:10px 0 0">Curl middle, ring and pinky to grip an arm; move and turn your hand; pinch thumb and
 index to set its gripper. Open your hand to let go: the arm holds.</p>
</section>
<aside>
 <div class="panel">
  <div id="control" class="pill"><span class="dot"></span><span>-</span></div>
  <div class="row"><button id="take" class="primary">Take control</button><button id="release">Release &amp; hold</button>
  <button id="homeOpen">Home arms</button></div>
  <div class="row" id="camRow" hidden><button id="camStart">Start laptop camera</button><button id="camStop">Stop camera</button></div>
  <div class="follow"><span id="fl"><span class="dot"></span>Left</span><span id="fr"><span class="dot"></span>Right</span>
  <span class="muted">following</span></div>
 </div>
 <div class="panel"><table><thead><tr><th>Joint</th><th>Left</th><th>Right</th></tr></thead><tbody id="joints"></tbody></table></div>
 <div class="panel stats">
  <span class="muted">Webcam</span><b id="fps">-</b><span class="muted">IK solve</span><b id="ik">-</b>
  <span class="muted">Robot view</span><b id="fresh">-</b><span class="muted">Operator</span><b id="who">-</b>
 </div>
 <div class="panel"><div class="muted" style="margin-bottom:6px">Events</div><div id="log"></div></div>
</aside></main>
<dialog id="home"><h2 style="margin-top:0">Home arms</h2>
<p>Both arms walk to their home pose and <strong>both grippers open</strong>. Make sure neither gripper holds anything and the
path is clear. Whoever has control loses it.</p>
<div class="row" style="justify-content:flex-end"><button id="homeCancel">Cancel</button><button id="homeGo" class="primary">Home both arms</button></div></dialog>
<video autoplay muted playsinline></video>
<script>
const token=location.hash.slice(1), q='?t='+encodeURIComponent(token), $=s=>document.querySelector(s);
const JOINTS=['Pan','Lift','Elbow','Wrist flex','Wrist yaw','Wrist roll'];
let views=[], camera=false;
async function command(c){const r=await fetch('/command'+q,{method:'POST',body:c});if(!r.ok)note(await r.text());}
function note(t){const l=$('#log');l.textContent+=t+'\n';l.scrollTop=l.scrollHeight;}
function pill(el,cls,text){el.className='pill '+cls;el.lastElementChild.textContent=text;}
$('#take').onclick=()=>command('c');$('#release').onclick=()=>command('release');
$('#homeOpen').onclick=()=>$('#home').showModal();$('#homeCancel').onclick=()=>$('#home').close();
$('#homeGo').onclick=()=>{$('#home').close();command('home');};
async function poll(){
 try{const r=await fetch('/state'+q);if(!r.ok)throw Error(r.status===403?'Use the full URL printed in the terminal':'HTTP '+r.status);
  const s=await r.json();render(s);}
 catch(e){pill($('#link'),'bad',e.message);}
 setTimeout(poll,200);}
function render(s){
 $('#room').textContent=s.room;pill($('#link'),s.connected?'ok':'warn',s.connected?'connected':'offline');
 if(views.join()!==s.views.join()){views=s.views;$('#cams').innerHTML=views.map(v=>
  `<figure><img class="view" src="/view/${v}${q}" alt="${v}"><figcaption>${v.replace(/_/g,' ')}</figcaption></figure>`).join('');}
 if(!$('#tracking').src)$('#tracking').src='/view/tracking'+q;
 const c=s.control;pill($('#control'),c==='you'?'ok':c==='nobody'?'':'warn',
  c==='you'?(s.fresh?'You have control':'You have control · no fresh robot view'):c==='nobody'?'Nobody has control':c+' has control');
 $('#take').textContent=c==='you'?'Release control':'Take control';$('#release').disabled=c!=='you';
 for(const [id,side] of [['#fl','left'],['#fr','right']])$(id).className=s.following.includes(side)?'ok':'';
 $('#fps').textContent=s.webcam_fps==null?'-':s.webcam_fps.toFixed(0)+' fps';$('#ik').textContent=s.ik_ms.toFixed(1)+' ms';
 $('#fresh').textContent=s.fresh?'fresh':'stale';$('#who').textContent=s.identity;
 const j=s.joints;$('#joints').innerHTML=j?JOINTS.map((n,i)=>`<tr><td>${n}</td><td>${j.left[i].toFixed(1)}°</td><td>${j.right[i].toFixed(1)}°</td></tr>`).join('')
  +`<tr><td>Gripper</td><td>${j.left[6].toFixed(0)} mm</td><td>${j.right[6].toFixed(0)} mm</td></tr>`:'<tr><td>No robot state yet</td></tr>';
 const l=$('#log'),text=s.log.join('\n');if(l.textContent!==text){l.textContent=text;l.scrollTop=l.scrollHeight;}
 if(s.camera!==camera){camera=s.camera;$('#camRow').hidden=!camera;}
}
// Browser camera (--browser): 640x480 JPEGs over a socket, one in flight.
const video=$('video'),canvas=Object.assign(document.createElement('canvas'),{width:640,height:480});let socket,stream,running=false;
function camStop(){running=false;stream?.getTracks().forEach(t=>t.stop());if(socket){socket.onclose=null;socket.close();}video.srcObject=null;}
async function sendFrame(){if(!running||socket.readyState!==1)return;canvas.getContext('2d').drawImage(video,0,0,640,480);
 const blob=await new Promise(r=>canvas.toBlob(r,'image/jpeg',0.8));if(running&&socket.readyState===1)socket.send(blob);}
$('#camStop').onclick=camStop;
$('#camStart').onclick=async()=>{try{
 if(!window.isSecureContext)throw Error('The camera needs HTTPS or an SSH tunnel opened at http://localhost.');
 stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:640},height:{ideal:480}},audio:false});
 video.srcObject=stream;await video.play();
 socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/camera${q}`);
 socket.onopen=()=>{running=true;sendFrame();};socket.onmessage=()=>setTimeout(sendFrame,33);
 socket.onclose=camStop;socket.onerror=()=>{camStop();note('camera connection failed');};
}catch(e){camStop();note(e.message);}};
document.addEventListener('visibilitychange',()=>{if(document.hidden)camStop();});window.addEventListener('pagehide',camStop);
poll();
</script></body></html>'''


class BrowserCapture:
    """Latest frame only; arrival time is preserved through the inference thread."""

    def __init__(self):
        self.frames = queue.Queue(maxsize=1)
        self.at = 0.0

    def isOpened(self):
        return True

    def set(self, *args):
        pass

    def release(self):
        self.clear()

    def clear(self):
        try:
            self.frames.get_nowait()
        except queue.Empty:
            pass

    def put(self, image):
        self.clear()
        self.frames.put_nowait((time.monotonic(), image))

    def read(self):
        try:
            self.at, image = self.frames.get(timeout=0.1)
            return True, image
        except queue.Empty:
            return False, None


def encode(image: np.ndarray) -> bytes:
    ok, jpeg = cv2.imencode(".jpg", cv2.cvtColor(image, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 75])
    return jpeg.tobytes() if ok else b""


class Dashboard:
    """Serves the page; the operator loop feeds it views, status and log lines and drains its commands."""

    def __init__(self, browser_camera: bool = False):
        self.capture = BrowserCapture() if browser_camera else None
        self.token = secrets.token_urlsafe(32)
        self.status: dict = {}
        self.robot_views: list[str] = []
        self._views: dict[str, tuple[int, np.ndarray]] = {}
        self._log: collections.deque[str] = collections.deque(maxlen=60)
        self._commands: set[str] = set()
        self._socket = None
        self._last_frame = 0.0
        self._runner = None

    @property
    def fresh(self) -> bool:
        """With the browser camera: a frame arrived in the last 0.25 s."""
        return self._socket is not None and time.monotonic() - self._last_frame < 0.25

    def drain(self) -> set[str]:
        commands, self._commands = self._commands, set()
        return commands

    def show(self, view: str, image: np.ndarray) -> None:
        """The latest RGB image of a view; encoded only when a page is watching."""
        seq = self._views.get(view, (0, None))[0] + 1
        self._views[view] = (seq, image)
        if view != "tracking" and view not in self.robot_views:
            self.robot_views.append(view)

    def log(self, line: str) -> None:
        self._log.append(time.strftime("%H:%M:%S ") + line)

    def _check(self, request: web.Request) -> None:
        if not hmac.compare_digest(request.query.get("t", ""), self.token):
            raise web.HTTPForbidden(text="Use the full URL printed in the terminal")

    async def _page(self, request):
        return web.Response(text=PAGE, content_type="text/html")

    async def _state(self, request):
        self._check(request)
        body = {**self.status, "views": self.robot_views, "log": list(self._log), "camera": self.capture is not None}
        return web.Response(text=json.dumps(body), content_type="application/json")

    async def _command(self, request):
        self._check(request)
        command = (await request.text()).strip()
        if command not in COMMANDS:
            raise web.HTTPBadRequest(text=f"unknown command {command!r}")
        self._commands.add(command)
        return web.Response(text="ok")

    async def _view(self, request):
        self._check(request)
        name = request.match_info["name"]
        response = web.StreamResponse(headers={"Content-Type": "multipart/x-mixed-replace; boundary=frame",
                                               "Cache-Control": "no-store"})
        await response.prepare(request)
        sent, period = 0, 1 / VIEW_FPS.get(name, 10)
        try:
            while True:
                seq, image = self._views.get(name, (0, None))
                if image is not None and seq != sent:
                    sent = seq
                    jpeg = await asyncio.to_thread(encode, image)
                    await response.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n%s\r\n"
                                         % (len(jpeg), jpeg))
                await asyncio.sleep(period)
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        return response

    async def _camera(self, request):
        self._check(request)
        if self.capture is None:
            raise web.HTTPNotFound(text="Started without --browser: the local webcam is the camera")
        if self._socket is not None:
            raise web.HTTPConflict(text="Another camera is connected")
        ws = web.WebSocketResponse(max_msg_size=512 * 1024, heartbeat=2)
        self._socket = ws
        try:
            await ws.prepare(request)
            self.log("browser camera connected")
            async for message in ws:
                if message.type != WSMsgType.BINARY:
                    continue
                image = await asyncio.to_thread(cv2.imdecode, np.frombuffer(message.data, np.uint8), cv2.IMREAD_COLOR)
                if image is None or image.shape != (480, 640, 3):
                    await ws.close(code=1003, message=b"Expected 640x480 JPEG")
                    break
                self._last_frame = time.monotonic()
                self.capture.put(image)
                await ws.send_json({"next": True})
        finally:
            self._socket = None
            self._last_frame = 0.0
            self.capture.clear()
            self.log("browser camera disconnected: arms hold")
        return ws

    async def start(self, host: str, port: int) -> None:
        app = web.Application(client_max_size=512 * 1024)
        app.router.add_get("/", self._page)
        app.router.add_get("/state", self._state)
        app.router.add_post("/command", self._command)
        app.router.add_get("/view/{name}", self._view)
        app.router.add_get("/camera", self._camera)
        self._runner = web.AppRunner(app, shutdown_timeout=1)
        await self._runner.setup()
        await web.TCPSite(self._runner, host, port).start()
        # scripts/cv-teleop.sh finds the browser-camera URL by "laptop camera:".
        print(f"[hands] {'laptop camera' if self.capture else 'dashboard'}: http://localhost:{port}/#{self.token}")

    async def stop(self) -> None:
        if self._socket is not None:
            await self._socket.close()
        if self._runner is not None:
            await self._runner.cleanup()
