"""Manifest adapter for the vendor MakerArm station. Native limits and thermal guards remain in force."""
import asyncio, dataclasses, json, math, os, sys, time, uuid
from pathlib import Path
import numpy as np
from robots import config, station, station_api, types
# Runtime assets remain in the station deployment; maintained source lives in Armstrong.
HERE=Path(os.environ.get('ARMSTRONG_STATION_DIR', Path(__file__).resolve().parent)).resolve()
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(Path(__file__).resolve().parent))
ROLE={'scene':'top','wrist_l':'left','wrist_r':'right'}

def plain(x):
 if isinstance(x,np.ndarray):return x.tolist()
 if dataclasses.is_dataclass(x):return {k:plain(v) for k,v in dataclasses.asdict(x).items()}
 if isinstance(x,dict):return {k:plain(v) for k,v in x.items()}
 if isinstance(x,(tuple,list)):return [plain(v) for v in x]
 return x

class Bridge:
 def __init__(self,api):
  self.api=api;self.c=api.controller;self.lease=None;self.watch=None;self.obs={};self.scope=None;self.native_task=None
  from camera_stream import PreviewFrames
  self.preview_frames=PreviewFrames()
  self.install_scopes()
  from makerarm_teaching import Teaching
  self.teaching=Teaching(self)
  from cv_teleop import CVTeleop
  self.cv=CVTeleop(self)
  from arm_rest import ArmRest  # arm_rest
  self.rest=ArmRest(self)  # arm_rest
  from free_drive import FreeDrive  # free_drive
  self.fd=FreeDrive(self)  # free_drive
 def checked_observation(self,ident):
  entry=self.obs.get(ident)
  if not entry or time.monotonic()-entry[0]>15:raise ValueError('Get current feedback before movement or teaching')
  return entry
 def health_problem(self):
  if not all(self.c.arms_alive().values()):return 'Motor feedback unavailable'
  alarms=self.c._alarms()
  return '; '.join(alarms.values()) if alarms else None
 def install_scopes(self):
  for side,arm in self.c._arms.items():
   if getattr(arm,'_manifest_wrapped',False):continue
   original=arm.write
   def write(command,side=side,original=original):
    if getattr(self,'rest',None) and side in self.rest.resting:return  # arm_rest: torque is off, send nothing
    scope=self.scope
    if scope:
     hold=scope['hold'][side]
     if scope['arm'] not in (side,'both'):command=types.ArmCommand(np.array(hold[:6]),hold[6])
     elif scope['gripper_mode']=='hold':command=types.ArmCommand(command.positions_rad,hold[6])
    original(command)
   arm.write=write;arm._manifest_wrapped=True
 def status(self):
  d=self.c.status();d['body']='makers'
  for key in ('cameras','capture_fps','exposure'):d[key]={ROLE.get(k,k):v for k,v in d.get(key,{}).items()}
  if self.native_task and not self.native_task.done():d['state']='running'
  d['control_adapter']='manifest-makerarm-v1';return d
 def measured(self):
  out={k:plain(v) for k,v in self.c.arm_states().items()}
  for v in out.values():v['body']='makers';v['gripper_motor_effort']=v.get('gripper_effort')
  return out
 def observe(self,images=True):
  ident=uuid.uuid4().hex;t=time.monotonic();measured=self.measured();self.obs[ident]=(t,measured)
  for k in list(self.obs):
   if t-self.obs[k][0]>=90:self.obs.pop(k,None)
  st=self.status();problem=None
  if not all(st['arms'].get(a) for a in ('left','right')):problem='A MakerArm driver is unavailable; see current station error.'
  if st.get('last_error'):problem=st['last_error'].get('message',str(st['last_error']))
  d={'observation_id':ident,'status':st,'measured':measured,'problem':problem,'motion_problem':problem,'lease':self.lease,'mode':'idle' if st['state']=='idle' else st['state'],'enabled_arms':['left','right'],'locked_arms':[],'capabilities':{'body':'makers','dreamlabs_move':True,'stationary_gripper':True,'makerarm_native_control':True,'native_home':True,'teaching':True,'hand_guidance':True,'legacy_yam_routines':False}}
  d['teaching']=self.teaching.public()
  if self.teaching.active:d['mode']='teaching';d['enabled_arms']=[a for a in ('left','right') if a!=self.teaching.session['arm']]
  d['arm_rest']=self.rest.public()  # arm_rest
  if self.rest.held():d['enabled_arms']=[a for a in d['enabled_arms'] if a not in self.rest.held()];d['locked_arms']=self.rest.held()  # arm_rest
  d['free_drive']=self.fd.public()  # free_drive
  if d['free_drive']['active']:d['enabled_arms']=[a for a in d['enabled_arms'] if a not in d['free_drive']['active']]  # free_drive
  d['images']=[]
  if images:
   for role,f in self.c.frames.items():
    if f.jpeg:d['images'].append({'camera':ROLE.get(role,role),'jpeg':f.jpeg,'age_s':round(max(0,t-f.jpeg_timestamp_s),3)})
  return d
 def response(self):return {'status':self.status(),'lease':self.lease}
 async def stop(self,reason='operator_stop',lease_id=None):
  if lease_id and (not self.lease or lease_id!=self.lease['id']):raise ValueError('Unknown action lease')
  if self.lease and self.lease.get('backend')=='cv_teleop':self.lease['active']=False
  if self.native_task and not self.native_task.done():
   self.native_task.cancel()
   try:await self.native_task
   except asyncio.CancelledError:pass
  await self.c.stop()
  for arm in self.c._arms.values():
   if arm.is_alive():arm.hold()
  if self.lease and self.lease['active']:self.lease.update(active=False,reason=reason,holding=all(self.c.arms_alive().values()),measured_after=self.measured(),finished=time.time())
  self.scope=None
  return self.response()
 async def watchdog(self,ident,seconds):
  running_since=None;start=time.monotonic()
  while self.lease and self.lease['id']==ident and self.lease['active']:
   await asyncio.sleep(.1);now=time.monotonic();st=self.status()
   if now-self.lease['heartbeat']>3:return await self.stop('heartbeat_expired',ident)
   if st['state']=='running' and (st.get('chunks',0)>0 or self.native_task and not self.native_task.done()):
    if running_since is None:running_since=now
    if now-running_since>=seconds:return await self.stop('duration_complete',ident)
   elif st['state'] in ('error','idle') and now-start>.25:
    return await self.stop('station_error' if st['state']=='error' else 'action_complete',ident)
   if now-start>45:return await self.stop('start_timeout',ident)
 async def action(self,b):
  if self.cv.busy or self.lease and self.lease['active']:raise ValueError('An action is already running')
  if self.teaching.active:raise ValueError('Finish teaching before movement')
  if self.rest.blocks(b.get('arm')):raise ValueError(self.rest.blocks(b.get('arm')))  # arm_rest
  if self.fd.blocks(b.get('arm')):raise ValueError(self.fd.blocks(b.get('arm')))  # free_drive
  if self.health_problem():raise ValueError(self.health_problem())
  if self.c.state not in ('idle','error'):raise ValueError('Station must be idle: '+self.c.state)
  # reset() returns before replacing _arms. Guard the CURRENT drivers before every action.
  self.install_scopes()
  if b.get('reference') or b.get('motion'):raise ValueError('YAM actions cannot run on MakerArm')
  stored=self.obs.get(b.get('observation_id'))
  if not stored or time.monotonic()-stored[0]>90:raise ValueError('Get a current observation first')
  before=self.measured()
  if len(before)!=2:raise ValueError('Both arm drivers must be connected')
  for side in before:
   if max(abs(x-y) for x,y in zip(before[side]['positions_rad'],stored[1][side]['positions_rad']))>.08:raise ValueError('Arm moved since observation; observe again')
  side=b.get('arm');mode=b.get('gripper_mode','hold')
  if side not in ('left','right','both') or mode not in ('hold','active'):raise ValueError('Specify arm and gripper scope')
  seconds=b.get('seconds',4)
  if isinstance(seconds,bool) or not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or not .5<=seconds<=12:raise ValueError('Duration must be 0.5–12 seconds')
  hold={k:[*(v.get('commanded_rad') or v['positions_rad']),v['commanded_gripper'] if v.get('commanded_gripper') is not None else v['gripper']] for k,v in before.items()}
  self.scope={'arm':side,'gripper_mode':mode,'hold':hold}
  self.lease={'id':uuid.uuid4().hex,'active':True,'holding':False,'created':time.time(),'heartbeat':time.monotonic(),'measured_before':before,'owner_task_id':b.get('owner_task_id'),'arm':side,'seconds':seconds,'instruction':b.get('instruction',''),'backend':'makerarm_native' if 'gripper_target' in b else 'dreamlabs_makers_eef'}
  try:
   if 'gripper_target' in b:
    target=b['gripper_target']
    if side=='both' or isinstance(target,bool) or not isinstance(target,(int,float)) or not math.isfinite(target) or not 0<=target<=1:raise ValueError('Gripper target must be 0–1 for one arm')
    self.scope['gripper_mode']='active';self.native_task=asyncio.create_task(self.jaw(side,target,hold))
   else:
    prompt=b.get('instruction','').strip()
    if not prompt:raise ValueError('A movement instruction is required')
    await self.c.start(prompt,'dreamlabs/dream-1-beta','eef')
   self.watch=asyncio.create_task(self.watchdog(self.lease['id'],seconds))
  except Exception:
   self.scope=None;self.lease.update(active=False,reason='start_rejected');raise
  return self.response()
 async def jaw(self,side,target,hold):
  try:
   start=hold[side][6]
   for i in range(1,121):
    self.c._arms[side].write(types.ArmCommand(np.array(hold[side][:6]),start+(target-start)*min(1,i/100)))
    await asyncio.sleep(1/60)
  finally:
   for arm in self.c._arms.values():
    if arm.is_alive():arm.hold()
 async def heartbeat(self,b):
  if not self.lease or self.lease['id']!=b.get('lease_id'):raise ValueError('Unknown action lease')
  self.lease['heartbeat']=time.monotonic();return self.response()
 async def home(self,b):
  """Use the station's native homing, then verify actual feedback, not policy prose."""
  if self.cv.busy or self.lease and self.lease['active']:raise ValueError('Stop active control before homing')
  if self.teaching.active:raise ValueError('Finish teaching before homing')
  if self.rest.held():raise ValueError('Wake or unlock the held arm before homing')  # arm_rest
  if self.fd.on():raise ValueError('Turn Zero-G off before homing')  # free_drive
  if self.c.state not in ('idle','error'):raise ValueError('Station must be idle before homing')
  if self.health_problem():raise ValueError(self.health_problem())
  if b.get('grippers_empty') is not True:raise ValueError('Native home opens both grippers; confirm both are empty')
  stored=self.checked_observation(b.get('observation_id'))
  before=self.measured()
  if set(before)!= {'left','right'}:raise ValueError('Both arm drivers must be connected')
  from robots import makers
  limits=np.radians([j.limits_deg for j in makers.JOINTS])
  targets={}
  for side,arm in self.c._arms.items():
   q=np.asarray(before[side]['positions_rad'],dtype=float)
   if q.shape!=(6,) or not np.isfinite(q).all():raise ValueError('Invalid joint feedback')
   if np.max(np.abs(q-np.asarray(stored[1][side]['positions_rad'])))>.08:raise ValueError('Arm moved since observation; observe again')
   # The MakerArm driver's soft limits also apply to configured home zeros.
   targets[side]=np.clip(np.asarray(arm.home_rad),limits[:,0],limits[:,1])
  old_duration=self.c._home_duration_s
  duration=max(old_duration,1+max(float(np.max(np.abs(targets[s]-before[s]['positions_rad']))) for s in targets)/.25)
  self.scope=None
  self.lease={'id':uuid.uuid4().hex,'active':True,'backend':'makerarm_home','created':time.time(),
              'owner_task_id':b.get('owner_task_id'),'measured_before':before,'targets_rad':plain(targets)}
  try:
   # Allow the existing native ramp time to reach its target; retain all driver guards.
   self.c._home_duration_s=duration
   result=await self.c.home()
   after=self.measured();errors={}
   for side in targets:
    q=np.asarray(after.get(side,{}).get('positions_rad',[]),dtype=float)
    errors[side]=float(np.max(np.abs(q-targets[side]))) if q.shape==(6,) and np.isfinite(q).all() else None
   reached=result.get('state')=='idle' and all(e is not None and e<=.04 for e in errors.values())
   self.lease.update(reason='home_reached' if reached else 'home_not_reached',reached_home=reached,
                     max_joint_error_rad=errors,tolerance_rad=.04,measured_after=after)
  except Exception:
   self.lease.update(reason='home_failed',reached_home=False);raise
  finally:
   self.c._home_duration_s=old_duration
   self.lease.update(active=False,finished=time.time(),holding=all(self.c.arms_alive().values()))
  return self.response()
 async def recover(self):
  # The native reset owns reopening and homing asynchronously. Action installs guards
  # after the station returns to idle, when the replacement drivers are available.
  await self.stop();return await self.c.reset()

OriginalApiInit=station_api.StationApi.__init__
def init(self,*a,**kw):OriginalApiInit(self,*a,**kw);self.manifest=Bridge(self)
station_api.StationApi.__init__=init
class Handler(station_api._Handler):
 def do_GET(self):
  import camera_stream
  camera=camera_stream.camera_name(self.path)
  if camera:
   role={v:k for k,v in ROLE.items()}[camera]
   def frame():
    f=self.server.api.controller.frames.get(role)
    return self.server.api.manifest.preview_frames.get(camera,f)
   return camera_stream.serve(self,frame)
  if self.path.split('?')[0]=='/status':return self._reply(200,self.server.api.manifest.status())
  return super().do_GET()
 def do_POST(self):
  route=self.path.split('?')[0];api=self.server.api;br=api.manifest
  try:
   b=self._read_json()
   if route in ('/supervisor/cv/start','/reset','/supervisor/teach/start') and br.rest.held():raise ValueError('Wake or unlock the held arm first')  # arm_rest
   if route in ('/supervisor/cv/start','/reset') and br.fd.on():raise ValueError('Turn Zero-G off first')  # free_drive
   if route=='/supervisor/arm/rest':[br.fd.release(s) for s in br.fd.on() if b.get('arm') in (s,'both',None)]  # free_drive: hold first, then torque off
   if route=='/supervisor/arm/rest':r=api.call(br.rest.rest(b))  # arm_rest
   elif route in ('/supervisor/arm/lock','/supervisor/arm/unlock','/supervisor/arm/use'):r=api.call(getattr(br.rest,route.rsplit('/',1)[1])(b))  # arm_rest
   elif route=='/supervisor/arm/wake':r=api.call(br.rest.wake(b))  # arm_rest
   elif route=='/supervisor/arm/freedrive':r=br.fd.route(b)  # free_drive
   elif route=='/supervisor/cv/start':r=api.call(br.cv.start())
   elif route=='/supervisor/cv/frame':r=api.call(br.cv.frame(b))
   elif route=='/supervisor/cv/stop':r=api.call(br.cv.stop(b.get('lease_id')))
   elif route in ('/supervisor/observe','/supervisor/preview'):r=br.observe(not route.endswith('preview'))
   elif route=='/supervisor/action':r=api.call(br.action(b))
   elif route in ('/supervisor/home','/home'):r=api.call(br.home(b))
   elif route=='/supervisor/heartbeat':r=api.call(br.heartbeat(b))
   elif route in ('/supervisor/stop','/stop'):r=api.call(br.stop(lease_id=b.get('lease_id')))
   elif route=='/reset':r=api.call(br.recover())
   elif route=='/supervisor/teach/start':
    if b.get('mode')!='cv' and (br.cv.busy or br.lease and br.lease.get('active')):raise ValueError('Stop active control before teaching')
    if 'observation_id' not in b:b['observation_id']=br.observe(False)['observation_id']
    r=api.call(br.teaching.start(b))
   elif route=='/supervisor/teach/heartbeat':r=api.call(br.teaching.heartbeat(b))
   elif route=='/supervisor/teach/mark':r=api.call(br.teaching.mark(b))
   elif route=='/supervisor/teach/stop':r=api.call(br.teaching.stop(b))
   else:return self._reply(404,{'error':'Unsupported MakerArm operation: '+route})
   self._reply(200,r)
  except Exception as e:self._reply(409,{'error':str(e)})
station_api._Handler=Handler

def resolved_config():
 profile=json.loads((HERE/'makerarm-profile.json').read_text());raw={'body':'makers','checkpoint':'dreamlabs/dream-1-beta','action_space':'eef','control_hz':60,'action_horizon':48,'stale_after_s':.2,'max_stall_ticks':240,'max_ee_speed_m_s':.15,'ramp_max_rad_s':.3,'home_on_key_refused':False,'face_blur':False,'policy_image_size':'640x480','cameras':[],'rollouts':{'enabled':True,'dir':str(HERE/'log/makerarm-rollouts'),'robot_name':'manifest-makerarm'}}
 for side,key in [('left','follower_l'),('right','follower_r')]:
  found=[]
  for net in Path('/sys/class/net').glob('can*'):
   for parent in net.resolve().parents:
    f=parent/'serial'
    if f.is_file() and f.read_text().strip()==profile[side]['serial']:found.append(net.name);break
  if len(found)!=1:raise RuntimeError(f'Could not uniquely resolve {side} adapter')
  raw[key]={'can_channel':found[0]}
 from makerarm_devices import camera_path
 TOP_W,TOP_H=(int(v) for v in __import__('os').environ.get('MAKERARM_TOP_SIZE','1440x1080').split('x'))  # top cam reads cards; 4:3 like policy 640x480
 for role,alias in [('top','scene'),('left','wrist_l'),('right','wrist_r')]:raw['cameras'].append({'name':alias,'device':camera_path(profile['camera_ports'][role]),'width':(TOP_W if role=='top' else 640),'height':(TOP_H if role=='top' else 480),'fps':15})
 import yaml
 path=HERE/'makerarm-station.yaml';path.write_text(yaml.safe_dump(raw));return config.load(path)
if __name__=='__main__':
 import logging,sys
 logging.basicConfig(level=logging.INFO)
 cfg=resolved_config()
 if '--check' in sys.argv:
  from robots import run
  print(json.dumps({'body':cfg.body,'channels':[cfg.follower_l.can_channel,cfg.follower_r.can_channel],'ik':run.policy_config(cfg)['ik']}));station.warm_client_ik(run.policy_config(cfg))
 else:asyncio.run(station.serve(cfg,host='127.0.0.1',api_port=8091,sys0=False))
