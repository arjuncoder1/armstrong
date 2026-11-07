"""Single-client browser camera transport for the existing MediaPipe/IK operator."""
import asyncio
import hmac
import queue
import secrets
import time

import cv2
import numpy as np
from aiohttp import web, WSMsgType

PAGE = r'''<!doctype html><meta name="viewport" content="width=device-width"><title>CV Teleop</title>
<style>body{font:18px system-ui;background:#101820;color:#eee;max-width:850px;margin:30px auto;padding:20px}button{padding:14px;margin:6px;font:inherit}video{width:100%;transform:scaleX(-1)}pre{white-space:pre-wrap}</style>
<h1>CV Teleop · MediaPipe + IK</h1>
<p>Your laptop camera drives the arms. Curl middle, ring and pinky to engage; move and turn your hand; pinch thumb/index for the gripper. Open your hand to hold.</p>
<button id="start">Start laptop camera</button><button id="control" disabled>Take / release arm control</button><button id="park" disabled>Park / power up</button><button id="stop">Stop camera & hold</button>
<pre id="status">Camera stopped. Keep the arms' paths apart.</pre><video autoplay muted playsinline></video>
<script>
const video=document.querySelector('video'), status=document.querySelector('#status');
const start=document.querySelector('#start'), control=document.querySelector('#control'), park=document.querySelector('#park');
const canvas=document.createElement('canvas');canvas.width=640;canvas.height=480;
let socket,stream,running=false;
const token=location.hash.slice(1);
function stop(){running=false;stream?.getTracks().forEach(t=>t.stop());if(socket){socket.onclose=null;socket.close();}video.srcObject=null;control.disabled=park.disabled=true;start.disabled=false;status.textContent='Camera stopped; arm motion held.';}
document.querySelector('#stop').onclick=stop;
async function sendFrame(){if(!running || socket.readyState!==1)return;canvas.getContext('2d').drawImage(video,0,0,640,480);const blob=await new Promise(r=>canvas.toBlob(r,'image/jpeg',0.8));if(running && socket.readyState===1)socket.send(blob);}
start.onclick=async()=>{start.disabled=true;try{
if(!window.isSecureContext)throw Error('Camera requires HTTPS or an SSH tunnel opened at http://localhost:8081.');
stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:640},height:{ideal:480},aspectRatio:{ideal:4/3}},audio:false});
video.srcObject=stream;await video.play();
socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/camera?token=${encodeURIComponent(token)}`);
socket.onopen=()=>{running=true;control.disabled=park.disabled=false;sendFrame();};
socket.onmessage=e=>{const s=JSON.parse(e.data);status.textContent=s.status;if(s.next)setTimeout(sendFrame,33);};
socket.onclose=()=>stop();socket.onerror=()=>{stop();status.textContent='Connection failed. Use the full URL printed in the terminal.';};
stream.getVideoTracks()[0].onended=stop;
}catch(e){stop();status.textContent=e.message;}};
control.onclick=()=>socket?.readyState===1&&socket.send('c');
park.onclick=()=>socket?.readyState===1&&socket.send('p');
document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
window.addEventListener('pagehide',stop);
</script>'''


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


class BrowserHands:
    def __init__(self):
        self.capture = BrowserCapture()
        self.token = secrets.token_urlsafe(32)
        self.socket = None
        self.keys = set()
        self.last_frame = 0.0
        self.status = 'Connected. Waiting for camera / robot state.'
        self.runner = None

    @property
    def fresh(self):
        return self.socket is not None and time.monotonic() - self.last_frame < 0.25

    def drain(self):
        keys, self.keys = self.keys, set()
        return keys

    async def page(self, request):
        return web.Response(text=PAGE, content_type='text/html')

    async def camera(self, request):
        if not hmac.compare_digest(request.query.get('token', ''), self.token):
            raise web.HTTPForbidden()
        if self.socket is not None:
            raise web.HTTPConflict(text='Another camera is connected')
        ws = web.WebSocketResponse(max_msg_size=512 * 1024, heartbeat=2)
        self.socket = ws
        try:
            await ws.prepare(request)
            async for message in ws:
                if message.type == WSMsgType.BINARY:
                    image = await asyncio.to_thread(cv2.imdecode, np.frombuffer(message.data, np.uint8), cv2.IMREAD_COLOR)
                    if image is None or image.shape != (480, 640, 3):
                        await ws.close(code=1003, message=b'Expected 640x480 JPEG')
                        break
                    self.last_frame = time.monotonic()
                    self.capture.put(image)
                    await ws.send_json({'next': True, 'status': self.status})
                elif message.type == WSMsgType.TEXT and message.data in ('c', 'p'):
                    if self.fresh:
                        self.keys.add(message.data)
        finally:
            self.socket = None
            self.last_frame = 0.0
            self.keys.clear()
            self.capture.clear()
        return ws

    async def start(self, host, port):
        app = web.Application(client_max_size=512 * 1024)
        app.router.add_get('/', self.page)
        app.router.add_get('/camera', self.camera)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        await web.TCPSite(self.runner, host, port).start()
        print(f'[hands] laptop camera: http://localhost:{port}/#{self.token}')

    async def stop(self):
        if self.socket is not None:
            await self.socket.close()
        if self.runner is not None:
            await self.runner.cleanup()
