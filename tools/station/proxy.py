"""The real Fieldwork site, served by the Manifest robot server: everything we have not taken over is forwarded to the
old harness on :8095 byte for byte, so the page looks and works exactly as before while routes move underneath.

Taken over (the page's own calls, answered by the new brain):
  POST /api/task      the Command tab's "Run task": the objective picks a routine ("tap cycle: slot 3", "tap pickup:",
                      "tap place:", "Swift card cycle:") or goes to the agent as a prompt; Look only = observation-only
  POST /api/stop      stops our task or routine run, then the harness's too
  GET  /api/status    the harness's answer plus: while our task runs, active/phase/message/events/task/metrics come from
                      it ("In the loop" shows the nodes); on a simulated server the robot block is the simulated station;
                      always a `halo` block (shield, routing, rig measure, workspace)
  GET  /api/runs      our tasks prepended as history rows; /api/runs/<id> for our ids
The browser talks to one origin; the harness's Origin/host check is satisfied by rewriting Origin and Host to its
loopback address; the X-Robot-Control header the page sends passes through.
"""
import os
import datetime
import http.client
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

PANEL_TAG = b'<script src="/sim-panel.js" defer></script>'

UPSTREAM = ('127.0.0.1', 8095)
PASS_REQUEST_HEADERS = ('Content-Type', 'Content-Length', 'X-Robot-Control', 'Accept', 'Range', 'If-None-Match', 'If-Modified-Since')
PASS_RESPONSE_HEADERS = ('Content-Type', 'Content-Length', 'Cache-Control', 'Content-Security-Policy', 'ETag', 'Last-Modified',
                         'Accept-Ranges', 'Content-Range', 'Location')
# The page's objectives → routines. The fully taught deal (card_deal_taught) is the one the runner can execute end to
# end; card_deal_layout's fast handoff (card_program) still holds in the runner, so "swift"/"deal" go to the taught route.
ROUTINE_PREFIXES = (('tap cycle', 'tap_cycle'), ('tap pickup', 'card_deal_layout'), ('tap place', 'card_deal_layout'),
                    ('swift card cycle', 'card_deal_taught'), ('swift card transfer', 'card_deal_taught'), ('deal', 'card_deal_taught'),
                    ('card cycle', 'card_deal_taught'))


def _upstream(method, path, body=b'', headers=None, timeout=30):
    conn = http.client.HTTPConnection(*UPSTREAM, timeout=timeout)
    try:
        h = {'Content-Type': 'application/json', 'Host': f'{UPSTREAM[0]}:{UPSTREAM[1]}', 'Origin': f'http://{UPSTREAM[0]}:{UPSTREAM[1]}', **(headers or {})}
        conn.request(method, path, body=body or None, headers=h)
        resp = conn.getresponse()
        data = resp.read()
        try:
            return resp.status, json.loads(data)
        except ValueError:
            return resp.status, data
    finally:
        conn.close()


# -- our task as the page sees it -----------------------------------------------------------------------------
def _current(app):
    """The most recent of our tasks (prompt or routine), as a record, or None."""
    cands = []
    if app.runner.current:
        cands.append(('prompt', app.runner.current.record))
    runs = app.graph_runner.list()
    if runs:
        rec = app.graph_runner.get(runs[-1]['id'])
        if rec:
            cands.append(('routine', rec))
    if not cands:
        return None
    kind, rec = max(cands, key=lambda c: c[1].get('created') or '')
    return {'kind': kind, **rec}


def _objective(rec):
    if rec['kind'] == 'prompt':
        return rec.get('prompt')
    params = rec.get('params') or {}
    extra = ' '.join(f'{k} {v}' for k, v in params.items() if k in ('slot', 'slots', 'replay_run', 'entry', 'max_cycles'))
    return f"{rec.get('graph')}{' · ' + extra if extra else ''}" + (' (shadow replay)' if rec.get('mode') == 'shadow' else '')


def _events(rec):
    out = []
    created = rec.get('created')
    try:
        base = datetime.datetime.fromisoformat(created.replace('Z', '+00:00')).timestamp() if created else time.time()
    except ValueError:
        base = time.time()
    if rec['kind'] == 'routine':
        for i, step in enumerate(rec.get('path') or []):
            node = step if isinstance(step, str) else step.get('node')
            outcome = '' if isinstance(step, str) else f" · {step.get('outcome', '')}"
            at = base + (step.get('t', i) if isinstance(step, dict) else i)
            out.append({'at': at, 'message': f'{node}{outcome}'})
        for h in rec.get('holds') or []:
            out.append({'at': base + len(out), 'message': 'hold: ' + str(h.get('reason'))[:160]})
        for r in rec.get('rules_fired') or []:
            out.append({'at': base + len(out), 'message': 'rule: ' + str(r)[:160]})
    else:
        for c in rec.get('tool_calls') or []:
            out.append({'at': base + float(c.get('t') or 0), 'message': f"{c.get('tool')} {json.dumps(c.get('arguments') or {})[:80]}"})
        if rec.get('final'):
            out.append({'at': base + 1 + len(out), 'message': str(rec['final'])[:200]})
    if rec.get('error'):
        out.append({'at': base + 1 + len(out), 'message': 'error: ' + str(rec['error'])[:160]})
    return out


def _phase(rec):
    s = rec.get('status')
    if s in ('starting', 'running'):
        return 'acting'
    if s == 'done':
        return 'done' if (rec.get('outcome') in ('end', None) or rec['kind'] == 'prompt') else 'uncertain'
    if s == 'stopped':
        return 'stopped'
    return 'uncertain'


def _message(rec):
    if rec['kind'] == 'routine':
        path = rec.get('path') or []
        last = path[-1] if path else None
        node = last if isinstance(last, str) else (last or {}).get('node')
        if rec.get('status') in ('starting', 'running'):
            return f"Running {rec.get('graph')} · at {node or rec.get('params', {}).get('entry') or 'entry'}"
        holds = rec.get('holds') or []
        if holds:
            return f"Held at {node}: {holds[-1].get('reason')}"
        return f"{rec.get('graph')} {rec.get('outcome') or rec.get('status')} after {len(path)} nodes"
    if rec.get('status') in ('starting', 'running'):
        calls = rec.get('tool_calls') or []
        return f"Agent working · {calls[-1]['tool'] if calls else 'thinking'}"
    return (rec.get('final') or rec.get('error') or rec.get('status') or '')[:300]


def _sim_robot(app):
    obs = app.observation_cache(max_age_s=1.0)
    if not obs:
        return {'state': 'error', 'problem': 'simulated station is not answering', 'arms': {'left': False, 'right': False},
                'camera_age_s': {}, 'mode': 'both_arms', 'enabled_arms': ['left', 'right'], 'last_error': None, 'simulated': True}
    st = obs.get('status') or {}
    return {'state': st.get('state'), 'run': st.get('run'), 'prompt': st.get('prompt'), 'problem': obs.get('problem'),
            'arms': st.get('arms') or {}, 'camera_age_s': {k: 0.1 for k in ('top', 'left', 'right')}, 'mode': obs.get('mode', 'both_arms'),
            'enabled_arms': obs.get('enabled_arms') or ['left', 'right'], 'last_error': st.get('last_error'), 'measured': obs.get('measured'),
            'lease': obs.get('lease'), 'simulated': True}


def _sim_camera(app, name):
    """The simulated station's rendered view as JPEG bytes (all three fetched together, cached for a second)."""
    import base64
    import urllib.request
    cache = getattr(app, '_sim_frames', None)
    if cache is None or time.time() - cache[0] > 1.0:
        try:
            req = urllib.request.Request(app.station + '/supervisor/observe', data=b'{}', method='POST',
                                         headers={'Content-Type': 'application/json', 'X-DreamLab-Supervisor': '1'})
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.load(r)
            frames = {i['camera']: base64.b64decode(i['jpeg']) for i in d.get('images') or []}
        except Exception:
            frames = {}
        cache = (time.time(), frames)
        app._sim_frames = cache
    return cache[1].get(name)


def _status_augment(app, status):
    status['ball_routine'] = app.paddle_practice.snapshot()
    if app.config.get('body')=='makers':
        obs=app.observation_cache(max_age_s=.5) or {}
        status['teaching']=obs.get('teaching')
        if (status['teaching'] or {}).get('status')=='recording':status.update(active=True,phase='teaching')
    try:
        rec = _current(app)
        simulated = bool(app.config.get('simulated'))
        if simulated:
            status['robot'] = _sim_robot(app)
            status['planner_ready'] = True
            status['model_label'] = 'Manifest · simulated'
        if rec is not None:
            running = rec.get('status') in ('starting', 'running')
            status['active'] = running
            status['phase'] = _phase(rec)
            status['message'] = _message(rec)
            status['events'] = _events(rec)
            status['task'] = {'id': rec['id'], 'objective': _objective(rec), 'kind': rec['kind'], 'status': rec.get('status'), 'outcome': rec.get('outcome')}
            status['model_label'] = 'Manifest' + (' · simulated' if simulated else '')
            metrics = status.get('metrics') or {}
            metrics['actions'] = len(rec.get('path') or rec.get('tool_calls') or [])
            metrics['elapsed_s'] = rec.get('elapsed_s')
            status['metrics'] = metrics
        measure = None
        obs = app.observation_cache(max_age_s=2.0)
        if obs and obs.get('measured'):
            q = {arm: [*obs['measured'][arm]['positions_rad'][:6], float(obs['measured'][arm].get('gripper', 1.0))] for arm in ('left', 'right')}
            measure = app.rig.measure(q)
        status['halo'] = {'server': f"http://127.0.0.1:{app.config.get('port', 8100)}", 'simulated': simulated,
                          'shield': {'enabled': app.shield['enabled'], **app.stats}, 'routes': app.routes, 'rig_nominal': app.rig.nominal,
                          'camera_nominal': bool((app.rig.cameras.get('top') or {}).get('nominal', True)), 'measure': measure,
                          'workspace': app.workspace_state, 'execute_allowed': bool(app.settings.get('execute_allowed')),
                          'task': {'id': rec['id'], 'kind': rec['kind'], 'status': rec.get('status')} if rec else None}
    except Exception as e:                                   # never break the page over a decoration
        status['halo'] = {'error': repr(e)[:200]}
    return status


def _runs_augment(app, rows):
    if not isinstance(rows, list):
        return rows
    ours = []
    for t in list(app.runner.list()) + list(app.graph_runner.list()):
        rec = app.runner.get(t['id']) or app.graph_runner.get(t['id'])
        if not rec:
            continue
        rec = {'kind': 'prompt' if 'prompt' in rec else 'routine', **rec}
        phase = _phase(rec)
        ours.append({'id': rec['id'], 'objective': _objective(rec), 'outcome': {'done': 'done', 'stopped': 'stopped'}.get(phase, 'uncertain'),
                     'controller_outcome': rec.get('outcome') or rec.get('status'), 'started_at': rec.get('created'), 'operator_outcome': None,
                     'halo': True, 'kind': rec['kind']})
    ours.sort(key=lambda r: r.get('started_at') or '', reverse=True)
    return ours + rows


def _task_takeover(app, method, body_bytes, query):
    try:
        body = json.loads(body_bytes or b'{}')
    except ValueError:
        return 400, {'error': 'body is not JSON'}
    objective = str(body.get('objective') or '').strip()
    if not 1 <= len(objective) <= 1500:
        return 400, {'error': 'Enter a task of 1-1500 characters'}
    look_only = bool(body.get('observe_only'))
    execute = (not look_only) and bool(app.settings.get('execute_allowed'))
    low = objective.lower()
    routine = next((g for prefix, g in ROUTINE_PREFIXES if low.startswith(prefix)), None)
    try:
        if routine and not look_only and app.config.get('body')!='makers':
            params = {}
            m = re.search(r'slot\s*(\d)', low)
            if m:
                params['slot'] = int(m.group(1))
                if routine == 'tap_cycle':
                    params['slots'] = [int(m.group(1))]
            m = re.search(r'replay\s+([a-f0-9]{8,32})', low)
            if m:
                params['replay_run'] = m.group(1)
            if low.startswith('tap place'):
                params['entry'] = 'pl_lift_or_clear'
            mode = 'live' if execute else 'shadow'
            if mode == 'shadow' and 'replay_run' not in params:
                return 403, {'error': 'Executing is not allowed on this server (settings.execute_allowed is false). '
                                      'Add "replay <run id>" to the objective for a shadow replay, or use Look only.'}
            rec = app.graph_runner.start(routine, params, mode)
            app.log({'fieldwork_task': {'routine': routine, 'params': params, 'mode': mode, 'id': rec.get('id')}})
            return 200, {'kind': 'routine', 'id': rec.get('id'), 'graph': routine, 'mode': mode, 'params': params}
        rec = app.runner.start(objective, execute=execute)
        app.log({'fieldwork_task': {'prompt': objective[:200], 'execute': execute, 'id': rec['id']}})
        return 200, {'kind': 'prompt', 'id': rec['id'], 'execute': execute}
    except ValueError as e:
        return 409, {'error': str(e)}


def _stop_takeover(app, method, body_bytes, query):
    stopped = []
    if app.paddle_practice.snapshot()['state'] in ('awaiting_handle','waiting_for_handle','gripping','leveling','awaiting_grip','waiting_for_ball','balancing','paused'):
        app.paddle_practice.stop()
        stopped.append('ball-routine')
    for owner in (app.runner, app.graph_runner):
        for t in owner.list():
            if t.get('status') in ('starting', 'running'):
                try:
                    owner.stop(t['id'])
                    stopped.append(t['id'])
                except ValueError:
                    pass
    if app.config.get('body')=='makers':
        import urllib.request
        req=urllib.request.Request(app.station+'/stop',data=b'{}',headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as response:upstream=json.load(response)
        return 200, {'stopped':stopped,'harness':upstream}
    code, upstream = _upstream('POST', '/api/stop', body_bytes or b'{}', {'X-Robot-Control': '1'})
    return 200, {'stopped': stopped, 'harness': upstream if isinstance(upstream, dict) else None}


def _run_detail(app, method, body_bytes, query, run_id):
    rec = app.runner.get(run_id) or app.graph_runner.get(run_id)
    if not rec:
        return None
    rec = {'kind': 'prompt' if 'prompt' in rec else 'routine', **rec}
    evidence = [e['message'] for e in _events(rec)]
    return 200, {'id': rec['id'], 'objective': _objective(rec), 'outcome': {'done': 'done', 'stopped': 'stopped'}.get(_phase(rec), 'uncertain'),
                 'started_at': rec.get('created'), 'task': {'summary': _message(rec), 'evidence': evidence}, 'actions': [], 'images': [],
                 'decisions': [], 'halo': rec}


TAKEOVERS = {'/api/task': _task_takeover, '/api/stop': _stop_takeover}
AUGMENT = {'/api/status': _status_augment, '/api/runs': _runs_augment}


def forward(handler, app):
    """Answer the current request: a takeover, or the harness's answer (augmented for some routes), or 502."""
    method = handler.command
    parts = urlsplit(handler.path)
    route = parts.path
    length = int(handler.headers.get('Content-Length') or 0)
    body = handler.rfile.read(length) if length else b''
    query = {k: v[-1] for k, v in parse_qs(parts.query).items()}

    def send_json(code, obj):
        data = json.dumps(obj, separators=(',', ':')).encode()
        handler.send_response(code)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Content-Length', str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)
        return True

    if app.config.get('body')=='makers' and method=='GET' and route in ('/api/demos','/api/skills'):
        if route=='/api/skills':return send_json(200,[])
        rows=[]
        for demo_path in (Path(os.environ.get('ARMSTRONG_STATION_DIR',Path(__file__).resolve().parent)).parents[1]/'teaching/demos').glob('*/demo.json'):
            try:
                demo=json.loads(demo_path.read_text())
                if demo.get('robot_body')=='makers':rows.append({k:v for k,v in demo.items() if k not in ('frames','robot_profile')})
            except (OSError,ValueError):pass
        return send_json(200,sorted(rows,key=lambda x:x.get('created_at',''),reverse=True)[:20])
    if app.config.get('body')=='makers' and method=='POST' and route in ('/api/recover','/api/home','/api/teach/start','/api/teach/heartbeat','/api/teach/mark','/api/teach/stop'):
        try:
            import urllib.request
            if route=='/api/home':
                home_body=json.loads(body or b'{}')
                if home_body.get('grippers_empty') is not True:
                    return send_json(409,{'error':'Native home opens both grippers; confirm both are empty'})
                if not home_body.get('observation_id'):
                    observation=urllib.request.Request(app.station+'/supervisor/observe',data=b'{}',headers={'Content-Type':'application/json'})
                    with urllib.request.urlopen(observation,timeout=10) as response:
                        home_body['observation_id']=json.load(response)['observation_id']
                body=json.dumps(home_body).encode()
            endpoint='/supervisor/teach/'+route.rsplit('/',1)[1] if route.startswith('/api/teach/') else '/supervisor/home' if route=='/api/home' else '/reset'
            req=urllib.request.Request(app.station+endpoint,data=body or b'{}',headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=60) as response:result=json.load(response)
            return send_json(200,result)
        except urllib.error.HTTPError as exc:
            try:
                result=json.loads(exc.read())
                message=result.get('error') if isinstance(result,dict) else None
            except (ValueError,UnicodeDecodeError):
                message=None
            return send_json(exc.code,{'error':message or str(exc)})
        except Exception as exc:return send_json(409,{'error':str(exc)})
    if method == 'POST' and route in ('/api/recover','/api/home','/api/teach/start','/api/task'):
        if app.paddle_practice.snapshot()['state'] in ('waiting_for_handle','gripping','leveling','waiting_for_ball','balancing'):
            app.paddle_practice.stop(pause=True)
    if method == 'POST' and route in TAKEOVERS:
        return send_json(*TAKEOVERS[route](app, method, body, query))
    if method == 'GET' and route == '/sim-panel.js':           # the Simulation panel the page gets on the Runs tab
        data = (Path(os.environ.get('ARMSTRONG_STATION_DIR',Path(__file__).resolve().parent)) / 'ui' / 'sim-panel.js').read_bytes()
        handler.send_response(200)
        handler.send_header('Content-Type', 'text/javascript')
        handler.send_header('Cache-Control', 'no-store')
        handler.send_header('Content-Length', str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)
        return True
    cam = re.fullmatch(r'/camera/(top|left|right)\.jpg', route)
    if method == 'GET' and cam and app.config.get('simulated'):
        jpeg = _sim_camera(app, cam.group(1))
        if jpeg is not None:
            handler.send_response(200)
            handler.send_header('Content-Type', 'image/jpeg')
            handler.send_header('Cache-Control', 'no-store')
            handler.send_header('Content-Length', str(len(jpeg)))
            handler.end_headers()
            handler.wfile.write(jpeg)
            return True
    m = re.fullmatch(r'/api/runs/([a-f0-9]{32})', route)
    if method == 'GET' and m:
        answer = _run_detail(app, method, body, query, m.group(1))
        if answer:
            return send_json(*answer)
    headers = {k: v for k, v in handler.headers.items() if k in PASS_REQUEST_HEADERS}
    headers['Host'] = f'{UPSTREAM[0]}:{UPSTREAM[1]}'
    if 'Origin' in handler.headers or method != 'GET':
        headers['Origin'] = f'http://{UPSTREAM[0]}:{UPSTREAM[1]}'
    t0 = time.perf_counter()
    conn = http.client.HTTPConnection(*UPSTREAM, timeout=120)
    try:
        conn.request(method, handler.path, body=body if length else None, headers=headers)
        resp = conn.getresponse()
        content_type = resp.getheader('Content-Type') or ''
        augment = AUGMENT.get(route) if method == 'GET' and resp.status == 200 and 'json' in content_type else None
        page = method == 'GET' and resp.status == 200 and route in ('/', '/index.html') and 'text/html' in content_type
        if augment or page:
            data = resp.read()
            if augment:
                try:
                    data = json.dumps(augment(app, json.loads(data)), separators=(',', ':')).encode()
                except ValueError:
                    pass
            elif b'</body>' in data and PANEL_TAG not in data:      # the Simulation panel joins the Runs tab
                data = data.replace(b'</body>', PANEL_TAG + b'</body>', 1)
            handler.send_response(resp.status)
            for k in PASS_RESPONSE_HEADERS:
                v = resp.getheader(k)
                if v and k != 'Content-Length':
                    handler.send_header(k, v)
            handler.send_header('Content-Length', str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            return True
        handler.send_response(resp.status)
        for k in PASS_RESPONSE_HEADERS:
            v = resp.getheader(k)
            if v:
                handler.send_header(k, v)
        chunked = resp.getheader('Content-Length') is None
        if chunked:
            handler.send_header('Connection', 'close')
        handler.end_headers()
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            handler.wfile.write(chunk)
            if chunked:
                handler.wfile.flush()
        if chunked:
            handler.close_connection = True
        return True
    except (OSError, http.client.HTTPException) as e:
        return send_json(502, {'error': f'Fieldwork harness on :{UPSTREAM[1]} is not answering ({e})'})
    finally:
        conn.close()
        app.stats['proxied'] = app.stats.get('proxied', 0) + 1
        app.stats['proxy_last_ms'] = round((time.perf_counter() - t0) * 1000, 1)
