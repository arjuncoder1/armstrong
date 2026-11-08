"""Hand-guided MakerArm recordings in Manifest's existing demonstration format."""
import asyncio,base64,datetime,json,os,sys,time,threading,uuid
from pathlib import Path
from robots import bodies,config
HERE=Path(os.environ.get('ARMSTRONG_STATION_DIR',Path(__file__).resolve().parent)).resolve()
sys.path.insert(0,str(HERE.parents[1]/'macos-support'))
import mac_teach

def joint_data(controller):
 import dataclasses
 out={}
 for side,state in controller.arm_states().items():
  d=dataclasses.asdict(state)
  out[side]={k:v.tolist() if hasattr(v,'tolist') else v for k,v in d.items()}
 return out
mac_teach.joint_data=joint_data
class Teaching(mac_teach.Teaching):
 def __init__(self,bridge):
  bridge.controller=bridge.c;bridge.observations=bridge.obs
  super().__init__(bridge);self.bridge=bridge;self.tokens={};self.hook_arms();self.install_interlocks()
 def hook_arms(self):
  for side,arm in self.c._arms.items():
   arm.call=lambda method,token,side=side:self.driver_call(side,method,token)
 def driver_call(self,side,method,token):
  arm=self.c._arms[side]
  if method=='teach_enter':
   if side in self.tokens:raise ValueError('This arm is already guided')
   self.tokens[side]=token
   fd=getattr(self.bridge,'fd',None)  # free_drive: hand guiding is weightless (Zero-G), not limp
   if fd is None:return arm._driver.disengage()  # free_drive
   try:fd.engage(side,teach=True);return True  # free_drive
   except Exception:self.tokens.pop(side,None);raise  # free_drive
  if self.tokens.get(side)!=token:raise ValueError('Wrong teaching ownership token')
  if method=='teach_keepalive':
   if side in getattr(getattr(self.bridge,'fd',None),'teach_sides',()) and not self.bridge.fd.active(side):raise ValueError('Zero-G stopped: '+self.bridge.fd.why(side))  # free_drive
   if not arm.is_alive():raise ValueError('Guided arm feedback stopped')
   return True
  if method=='teach_hold':
   if side in getattr(getattr(self.bridge,'fd',None),'teach_sides',()):self.bridge.fd.release(side);self.tokens.pop(side,None);return True  # free_drive: still energized, hold where it is
   # Native MakerArm drivers resume by reopening at the measured pose, never home.
   cfg=config.load(HERE/'makerarm-station.yaml');arm_cfg=cfg.follower_l if side=='left' else cfg.follower_r
   self.c._set_state('resetting')
   try:
    arm._driver.close()
    new=bodies.for_config(cfg).open_arm(arm_cfg,side)
    self.c._arms[side]=new;self.bridge.install_scopes();self.hook_arms()
    self.tokens.pop(side,None);self.c._set_state('idle');return True
   except Exception as exc:
    self.c._record_error(exc);self.c._set_state('error');raise
  raise ValueError('Unsupported teaching driver command')
 async def start(self,body):
  # Native reset replaces the arm objects after returning its response.
  # Refresh callbacks on those current objects before entering guidance.
  self.hook_arms()
  return await (self.start_cv(body) if body.get('mode')=='cv' else super().start(body))
 async def start_cv(self,body):
  """Records while CV teleop (Manifest's laptop camera or the LiveKit bridge) drives the arms: nothing goes limp.
  Ends on Finish (teach/stop), when CV stops (any cause: the station's stop ends teaching first), or at the 2-minute limit."""
  objective=body.get('objective');lease=self.bridge.lease
  if body.get('ready') is not True:raise ValueError('Confirm the workspace is clear')
  if not isinstance(objective,str) or not 1<=len(objective.strip())<=500:raise ValueError('Describe the skill to demonstrate')
  if self.active:raise ValueError('Already recording')
  if not (lease and lease.get('active') and lease.get('backend')=='cv_teleop'):raise ValueError('Enable CV Teleop first, then record')
  if self.c.state!='idle':raise ValueError('Finish the current action before teaching')
  self.supervisor.checked_observation(body.get('observation_id'))
  if problem:=self.supervisor.health_problem():raise ValueError(problem)
  token=uuid.uuid4().hex;self.directory=mac_teach.ROOT/token;self.directory.mkdir(parents=True)
  self.session={'id':token,'objective':objective.strip(),'arm':'both',
   'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
   'status':'recording','samples':0,'duration_s':0,'reason':None,'markers':[],
   'frames':[],'videos':{},'exporting':False,'kind':'cv_teleop_reference',
   'note':'Driven by camera hand tracking (CV Teleop), so no hands in view; measured motion and video references. Never automatically replay this trajectory.'}
  self.reason=None;self.started=self.last_heartbeat=time.monotonic()
  self.save();self.supervisor.observations.clear()
  self.task=asyncio.create_task(self._record_cv(lease['id']),name='cv-teleop-demo')
  return self.public()
 async def _record_cv(self,lease_id):
  try:
   last_frame=-1.
   with (self.directory/'joints.jsonl').open('a') as stream:
    while self.active and not self.reason:
     elapsed=time.monotonic()-self.started
     if not self.bridge.cv.valid(lease_id):self.reason='cv_stopped';break
     if elapsed>=mac_teach.MAX_SECONDS:self.reason='two_minute_limit';break
     if self.c.state!='idle':self.reason='station_changed';break
     if problem:=self.supervisor.health_problem():self.reason=problem;break
     reading=await asyncio.to_thread(joint_data,self.c)
     stream.write(json.dumps({'t_s':round(elapsed,4),'arms':reading},allow_nan=False)+'\n')
     self.session['samples']+=1;self.session['duration_s']=round(elapsed,2)
     if elapsed-last_frame>=.2:await asyncio.to_thread(self.snapshot,elapsed);last_frame=elapsed
     await asyncio.sleep(.05)
  except Exception as exc:self.reason=type(exc).__name__+': '+str(exc)
  finally:
   self.session.update(status='recorded' if self.reason=='operator_finished' else 'interrupted',reason=self.reason,
    duration_s=round(time.monotonic()-self.started,2),exporting=True)
   self.supervisor.observations.clear();self.save()
   threading.Thread(target=mac_teach.render_videos,args=(self.directory,dict(self.session)),daemon=True).start()
 def public(self):
  result=super().public()
  if result:result['robot_body']='makers'
  return result
 def save(self):
  self.session.update(robot_body='makers',robot_profile=json.loads((HERE/'makerarm-profile.json').read_text()))
  super().save()
 def snapshot(self,t_s):
  images={};stamps={}
  for native,role in [('scene','top'),('wrist_l','left'),('wrist_r','right')]:
   frame=self.c.frames.get(native)
   if not frame or not frame.jpeg:continue
   name=f'{len(self.session["frames"]):05d}-{role}.jpg';(self.directory/name).write_bytes(base64.b64decode(frame.jpeg));images[role]=name;stamps[role]=round(frame.jpeg_timestamp_s-self.started,4)
  self.session['frames'].append({'t_s':round(t_s,4),'image_t_s':stamps,'images':images})
