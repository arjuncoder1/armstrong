"""Chat with the VLM (SGLang, OpenAI-compatible) in your browser: text + images, streaming, timings.

    uv run tools/vlm_chat.py                 # http://127.0.0.1:8099 ; URL from VLM_URL (.env.config)
    VLM_URL=https://... uv run tools/vlm_chat.py --port 8099

The page talks to this local server, which relays to the model (browsers can't call the endpoint directly).
"Robot camera" attaches the newest frame from the AMD Halo's cameras (top / left / right wrist) to each message,
through Manifest's station_proxy plugin at MANIFEST_URL.
Standard library only.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def setting(key: str) -> str:
    """From the environment, else .env.local, else .env.config."""
    if os.environ.get(key):
        return os.environ[key]
    for name in (".env.local", ".env.config"):
        path = ROOT / name
        if path.exists():
            for line in path.read_text().splitlines():
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip()
    return ""


def vlm_url() -> str:
    url = setting("VLM_URL")
    if not url:
        sys.exit("set VLM_URL (e.g. in .env.config)")
    return url.rstrip("/").removesuffix("/v1")


class CameraFeed:
    """Keeps the newest JPEG of one robot camera, read continuously from Manifest's MJPEG relay."""

    feeds: dict[str, "CameraFeed"] = {}

    def __init__(self, camera: str) -> None:
        self.camera, self.jpeg, self.at, self.error = camera, b"", 0.0, ""
        self.ready = threading.Event()
        threading.Thread(target=self._run, name=f"cam-{camera}", daemon=True).start()

    @classmethod
    def get(cls, camera: str) -> "CameraFeed":
        if camera not in cls.feeds:
            cls.feeds[camera] = cls(camera)
        return cls.feeds[camera]

    def _run(self) -> None:
        base = (setting("MANIFEST_URL") or "http://amd-halo.local:8100/v1").rstrip("/").removesuffix("/v1")
        while True:
            try:
                with urllib.request.urlopen(f"{base}/internal/cameras/{self.camera}.mjpg", timeout=10) as r:
                    buf = b""
                    while True:
                        chunk = r.read(16384)
                        if not chunk:
                            break
                        buf += chunk
                        end = buf.rfind(b"\xff\xd9")
                        start = buf.rfind(b"\xff\xd8", 0, end) if end > 0 else -1
                        if start >= 0:
                            self.jpeg, self.at, self.error = buf[start:end + 2], time.time(), ""
                            self.ready.set()
                            buf = buf[end + 2:]
                        if len(buf) > 4_000_000:
                            buf = b""
            except Exception as exc:  # noqa: BLE001 - reconnect
                self.error = str(exc)
            time.sleep(1.0)

    def frame(self, wait_s: float = 4.0) -> str:
        if not self.ready.wait(wait_s):
            raise LookupError(f"no frame from the {self.camera} camera yet ({self.error or 'connecting'})")
        if time.time() - self.at > 5:
            raise LookupError(f"the {self.camera} camera feed is stale ({self.error or 'no new frames'})")
        return "data:image/jpeg;base64," + base64.b64encode(self.jpeg).decode()


def robot_frame(camera: str) -> str:
    """The newest JPEG from the robot's camera (top|left|right) as a data URL; instant once its feed is warm."""
    return CameraFeed.get(camera).frame()


class Handler(BaseHTTPRequestHandler):
    upstream = ""

    def log_message(self, *args) -> None:
        pass

    def do_GET(self) -> None:
        if self.path.startswith("/api/robot_frame"):
            camera = self.path.partition("camera=")[2].split("&")[0] or "top"
            try:
                self._send(200, json.dumps({"url": robot_frame(camera)}).encode(), "application/json")
            except Exception as exc:  # noqa: BLE001
                self._send(502, json.dumps({"error": f"robot camera: {exc}"}).encode(), "application/json")
            return
        if self.path == "/api/models":
            try:
                with urllib.request.urlopen(self.upstream + "/v1/models", timeout=20) as r:
                    body = r.read()
                self._send(200, body, "application/json")
            except Exception as exc:  # noqa: BLE001
                self._send(502, json.dumps({"error": str(exc)}).encode(), "application/json")
            return
        self._send(200, PAGE.encode(), "text/html; charset=utf-8")

    def do_POST(self) -> None:
        if self.path != "/api/chat":
            return self._send(404, b"{}", "application/json")
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        body.update(stream=True, stream_options={"include_usage": True})
        body.setdefault("model", "vlm")
        req = urllib.request.Request(self.upstream + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            upstream = urllib.request.urlopen(req, timeout=300)
        except urllib.error.HTTPError as exc:
            return self._send(exc.code, exc.read() or b'{"error":"upstream error"}', "application/json")
        except Exception as exc:  # noqa: BLE001
            return self._send(502, json.dumps({"error": f"cannot reach the model: {exc}"}).encode(), "application/json")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            for line in upstream:
                self.wfile.write(line)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            upstream.close()

    def _send(self, code: int, body: bytes, kind: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


PAGE = r"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>VLM Chat</title>
<style>
:root{--bg:#f7f6f3;--card:#fff;--ink:#1d1d1b;--mut:#6d6c66;--line:#e4e2dc;--acc:#2f5fa7;--me:#e9eef8}
@media (prefers-color-scheme:dark){:root{--bg:#151514;--card:#1f1f1d;--ink:#ecebe6;--mut:#9b9a92;--line:#33322e;--acc:#7da2e8;--me:#24304a}}
*{box-sizing:border-box}html,body{height:100%}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif;display:flex;flex-direction:column}
header{padding:12px 16px;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
header b{font-size:16px}#meta{color:var(--mut);font-size:13px}header button{margin-left:auto}
#log{flex:1;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:12px;max-width:860px;width:100%;margin:0 auto}
.msg{padding:10px 14px;border-radius:12px;max-width:85%;white-space:pre-wrap;word-wrap:break-word;border:1px solid var(--line)}
.me{align-self:flex-end;background:var(--me)}.bot{align-self:flex-start;background:var(--card)}
.msg img{max-width:240px;max-height:180px;border-radius:8px;display:block;margin-bottom:6px}
.t{font-size:12px;color:var(--mut);margin-top:4px}
form{border-top:1px solid var(--line);padding:12px 16px;max-width:860px;width:100%;margin:0 auto;display:flex;flex-direction:column;gap:8px}
#prev{display:flex;gap:8px;flex-wrap:wrap}#prev div{position:relative}#prev img{height:64px;border-radius:6px;border:1px solid var(--line)}
#prev span{position:absolute;top:-6px;right:-6px;background:var(--ink);color:var(--bg);border-radius:50%;width:18px;height:18px;font-size:12px;text-align:center;line-height:18px;cursor:pointer}
.row{display:flex;gap:8px;align-items:flex-end}textarea{flex:1;resize:none;min-height:44px;max-height:180px;padding:10px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--ink);font:inherit}
button{font:inherit;font-weight:600;border:0;border-radius:10px;padding:10px 14px;cursor:pointer;background:var(--acc);color:#fff}
button.ghost{background:transparent;color:var(--ink);border:1px solid var(--line)}button:disabled{opacity:.5}
label.file{cursor:pointer;color:var(--mut);font-size:13px}.hint{color:var(--mut);font-size:12px}
</style>
<header><b>VLM Chat</b><span id=meta>connecting…</span><button class=ghost id=clear type=button>New chat</button></header>
<div id=log></div>
<form id=f>
  <div id=prev></div>
  <div class=row>
    <textarea id=q placeholder="Ask something… (Enter to send, Shift+Enter for a new line; paste or drop images)"></textarea>
    <button id=send>Send</button>
  </div>
  <div class=hint><label class=file>📎 attach image<input id=file type=file accept="image/*" multiple hidden></label> · max tokens <input id=max type=number value=512 min=16 max=8192 style="width:80px">
   · <label><input type=checkbox id=robot> Robot camera</label> <select id=cam><option value=top>top</option><option value=left>left wrist</option><option value=right>right wrist</option></select>
   <button type=button class=ghost id=snap style="padding:3px 8px">📷 Preview</button></div>
</form>
<script>
const $=id=>document.getElementById(id);let history=[],pending=[],busy=false;
fetch('/api/models').then(r=>r.json()).then(d=>{$('meta').textContent=d.data?('model: '+d.data.map(m=>m.id).join(', ')+' · context '+(d.data[0].max_model_len||'?')):(d.error||'no model')}).catch(e=>$('meta').textContent='cannot reach model');
function addImg(file){if(!file.type.startsWith('image/'))return;const r=new FileReader();r.onload=()=>{pending.push(r.result);showPrev()};r.readAsDataURL(file)}
function showPrev(){$('prev').innerHTML=pending.map((u,i)=>`<div><img src="${u}"><span onclick="pending.splice(${i},1);showPrev()">×</span></div>`).join('')}
$('file').onchange=e=>{[...e.target.files].forEach(addImg);e.target.value=''};
try{$('robot').checked=localStorage.getItem('robotcam')==='1';$('cam').value=localStorage.getItem('robotcamname')||'top'}catch(e){}
const warm=()=>{if($('robot').checked)fetch('/api/robot_frame?camera='+$('cam').value).catch(()=>{})};
$('robot').onchange=()=>{try{localStorage.setItem('robotcam',$('robot').checked?'1':'0')}catch(e){};warm()};
$('cam').onchange=()=>{try{localStorage.setItem('robotcamname',$('cam').value)}catch(e){};warm()};warm();
async function grab(){const r=await fetch('/api/robot_frame?camera='+$('cam').value);const d=await r.json();if(!r.ok)throw new Error(d.error||'no frame');return d.url}
$('snap').onclick=async()=>{$('snap').disabled=true;try{pending.push(await grab());showPrev()}catch(e){bubble('bot','⚠ '+esc(e.message))}$('snap').disabled=false};
document.addEventListener('paste',e=>{[...(e.clipboardData||{}).files||[]].forEach(addImg)});
document.addEventListener('dragover',e=>e.preventDefault());document.addEventListener('drop',e=>{e.preventDefault();[...e.dataTransfer.files].forEach(addImg)});
$('q').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('f').requestSubmit()}});
$('clear').onclick=()=>{history=[];$('log').innerHTML=''};
function bubble(cls,html){const d=document.createElement('div');d.className='msg '+cls;d.innerHTML=html;$('log').appendChild(d);$('log').scrollTop=1e9;return d}
const esc=s=>s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
$('f').onsubmit=async e=>{e.preventDefault();if(busy)return;const text=$('q').value.trim();if(!text&&!pending.length)return;
 if($('robot').checked){try{pending.push(await grab())}catch(err){bubble('bot','⚠ '+esc(err.message));return}}
 const content=[...pending.map(u=>({type:'image_url',image_url:{url:u}}))];if(text)content.push({type:'text',text});
 bubble('me',pending.map(u=>`<img src="${u}">`).join('')+esc(text));history.push({role:'user',content});
 pending=[];showPrev();$('q').value='';busy=true;$('send').disabled=true;
 const out=bubble('bot','<span class=a>…</span><div class=t></div>'),a=out.querySelector('.a'),t=out.querySelector('.t');
 const t0=performance.now();let first=null,answer='',usage=null;
 try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:history,max_tokens:+$('max').value||512})});
  if(!r.ok){a.textContent='Error: '+(await r.text()).slice(0,300);throw 0}
  const rd=r.body.getReader(),dec=new TextDecoder();let buf='';
  for(;;){const {done,value}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});let i;
   while((i=buf.indexOf('\n'))>=0){const line=buf.slice(0,i).trim();buf=buf.slice(i+1);if(!line.startsWith('data:')||line==='data: [DONE]')continue;
    const j=JSON.parse(line.slice(5));if(j.usage)usage=j.usage;const d=j.choices&&j.choices[0]&&j.choices[0].delta&&j.choices[0].delta.content;
    if(d){if(first===null)first=performance.now()-t0;answer+=d;a.textContent=answer;$('log').scrollTop=1e9}}}
  const total=(performance.now()-t0)/1000,toks=usage?usage.completion_tokens:answer.split(/\s+/).length,gen=total-(first||0)/1000;
  t.textContent=`first token ${((first||0)/1000).toFixed(2)}s · ${total.toFixed(2)}s total · ${toks} tokens · ${gen>0?Math.round(toks/gen):0} tok/s`;
  history.push({role:'assistant',content:answer});
 }catch(err){if(err)a.textContent='Error: '+err;history.pop()}
 busy=false;$('send').disabled=false;$('q').focus()};
</script>"""


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--port", type=int, default=8099)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()
    Handler.upstream = vlm_url()
    url = f"http://127.0.0.1:{args.port}"
    print(f"VLM Chat on {url}  (model at {Handler.upstream.split('//')[1].split('.')[0]}…; Ctrl-C to quit)")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    if not args.no_browser and sys.stdout.isatty():
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
