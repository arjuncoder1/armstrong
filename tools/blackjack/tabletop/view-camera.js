import * as THREE from './vendor/three.module.min.js';

// Display navigation only. No robot commands or task-phase assumptions.
export function createViewCamera(camera, canvas, arms) {
 const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
 const center=new THREE.Vector3(-.36675,.16,.08);
 const current={target:center.clone(),yaw:0,elevation:1.02,distance:2.05};
 const goal={target:center.clone(),yaw:0,elevation:1.02,distance:2.05};
 let mode=reduced?'table':'follow',aspect=null,lastTime=0,lastSample=0,activeUntil=0,previous=null,manualUntil=0,resumeFollow=false;
 const pointers=new Map(),cleanup=[];
 const nav=document.createElement('div');nav.className='view-nav';nav.setAttribute('aria-label','3D camera views');
 nav.innerHTML='<div><button data-view="follow">Follow</button><button data-view="table">Table</button><button data-view="overhead">Overhead</button></div><span>Drag to orbit · scroll to zoom</span>';
 document.getElementById('details').append(nav);
 canvas.tabIndex=0;canvas.setAttribute('aria-label','3D table. Drag or arrow keys to orbit; scroll or plus and minus to zoom. Shift-drag to pan. R resets the view.');
 function on(node,event,fn,options){node.addEventListener(event,fn,options);cleanup.push(()=>node.removeEventListener(event,fn,options));}
 const clamp=THREE.MathUtils.clamp;
 function limits(){goal.elevation=clamp(goal.elevation,.18,1.54);goal.distance=clamp(goal.distance,.55,4);goal.target.x=clamp(goal.target.x,-1.15,.42);goal.target.y=clamp(goal.target.y,-.3,.85);goal.target.z=clamp(goal.target.z,.02,.7);}
 function label(){for(const button of nav.querySelectorAll('button'))button.setAttribute('aria-pressed',String(button.dataset.view===mode));nav.querySelector('span').textContent=mode==='manual'?'Orbit · shift-drag to pan · pinch to zoom':'Drag to orbit · scroll to zoom';}
 function wide(){return aspect&&aspect<1.2?Math.min(4,Math.max(2.65,1.85/aspect)):1.85;}
 function preset(next){mode=next;resumeFollow=next==='follow';goal.target.copy(center);goal.yaw=0;goal.elevation=next==='overhead'?1.53:1.02;goal.distance=wide();activeUntil=0;label();}
 function manual(){if(mode==='follow')resumeFollow=true;manualUntil=performance.now()+8000;mode='manual';label();}
 function pan(dx,dy){const scale=goal.distance/Math.max(200,canvas.clientHeight);goal.target.x+=(-dx*Math.cos(goal.yaw)+dy*Math.sin(goal.yaw))*scale;goal.target.y+=(-dx*Math.sin(goal.yaw)-dy*Math.cos(goal.yaw))*scale;}
 on(nav,'click',e=>{const next=e.target.dataset.view;if(next)preset(next);});
 on(canvas,'pointerdown',e=>{if(e.button>1)return;manual();pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});canvas.setPointerCapture(e.pointerId);canvas.focus({preventScroll:true});});
 on(canvas,'pointermove',e=>{
  const old=pointers.get(e.pointerId);if(!old)return;manualUntil=performance.now()+8000;
  const others=[...pointers.entries()].filter(([id])=>id!==e.pointerId);
  if(others.length){const other=others[0][1],before=Math.hypot(old.x-other.x,old.y-other.y),after=Math.hypot(e.clientX-other.x,e.clientY-other.y);if(before>8&&after>8)goal.distance*=before/after;pan((e.clientX-old.x)/2,(e.clientY-old.y)/2);}
  else if(e.shiftKey||e.buttons===4)pan(e.clientX-old.x,e.clientY-old.y);
  else{goal.yaw-=(e.clientX-old.x)*.006;goal.elevation+=(e.clientY-old.y)*.005;}
  pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});limits();
 });
 for(const event of ['pointerup','pointercancel','lostpointercapture'])on(canvas,event,e=>pointers.delete(e.pointerId));
 on(canvas,'wheel',e=>{e.preventDefault();manual();goal.distance*=Math.exp(clamp(e.deltaY*(e.deltaMode===1?16:1),-150,150)*.002);limits();},{passive:false});
 on(canvas,'keydown',e=>{
  if(['f','o'].includes(e.key.toLowerCase())){e.preventDefault();preset(e.key.toLowerCase()==='f'?'follow':'overhead');return;}
  if(e.key.toLowerCase()==='r'){e.preventDefault();preset('table');return;}
  if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','=','-','_'].includes(e.key))return;
  e.preventDefault();manual();
  if(e.key==='ArrowLeft')goal.yaw+=.12;if(e.key==='ArrowRight')goal.yaw-=.12;
  if(e.key==='ArrowUp')goal.elevation+=.08;if(e.key==='ArrowDown')goal.elevation-=.08;
  if(['+','='].includes(e.key))goal.distance*=.9;if(['-','_'].includes(e.key))goal.distance*=1.1;limits();
 });
 function sample(data,snapshot=false){
  const now=performance.now(),valid=data?.fresh===true;const measured=valid?data.measured||{}:{};
  if(mode==='manual'&&resumeFollow&&!reduced&&!pointers.size&&now>manualUntil)preset('follow');
  if(mode==='follow'&&valid){
   const moving=[];
   for(const side of ['left','right']){
    const row=measured[side],ee=row?.ee_mm,q=row?.positions_rad,prev=previous?.[side]?.positions_rad;
    if(!Array.isArray(ee)||ee.length!==3||!ee.every(Number.isFinite)||!Array.isArray(q)||q.length!==6||!q.every(Number.isFinite))continue;
    const delta=prev&&now-lastSample<2500?Math.max(...q.map((v,i)=>Math.abs(v-prev[i]))):0;
    const prevEE=previous?.[side]?.ee_mm,eeDelta=prevEE&&now-lastSample<2500?Math.hypot(...ee.map((v,i)=>v-prevEE[i])):0;
    const gripDelta=Number.isFinite(previous?.[side]?.gripper)&&Number.isFinite(row.gripper)?Math.abs(row.gripper-previous[side].gripper):0;
    if(snapshot||delta>.003||eeDelta>1.5||gripDelta>.015)moving.push({side,point:new THREE.Vector3(...ee.map(v=>v/1000)).applyMatrix4(arms[side].base.matrix)});
   }
   if(moving.length){
    const focus=moving.reduce((sum,m)=>sum.add(m.point),new THREE.Vector3()).multiplyScalar(1/moving.length);
    goal.target.copy(center).lerp(focus,aspect<1.2?.25:.55);goal.yaw=moving.length>1?0:moving[0].side==='left'?.42:-.42;
    goal.elevation=focus.z<.16?.95:.72;goal.distance=wide()*(aspect<1.2?1:moving.length>1?.98:.92);limits();activeUntil=now+4000;
   }
  }
  if(!snapshot){previous=measured;lastSample=now;}
 }
 function tick(now,nextAspect){
  if(aspect===null){aspect=nextAspect;goal.distance=wide();current.distance=goal.distance;}
  else if(aspect!==nextAspect){const old=wide();aspect=nextAspect;goal.distance*=wide()/old;limits();}
  if(mode==='follow'&&activeUntil&&now>activeUntil){goal.target.copy(center);goal.yaw=0;goal.elevation=1.02;goal.distance=wide();activeUntil=0;}
  const dt=lastTime?Math.min((now-lastTime)/1000,.1):.016;lastTime=now;
  const blend=reduced?1:1-Math.exp(-dt*(mode==='manual'?16:3));
  current.target.lerp(goal.target,blend);for(const key of ['yaw','elevation','distance'])current[key]+=(goal[key]-current[key])*blend;
  const horizontal=current.distance*Math.cos(current.elevation);
  camera.position.set(current.target.x+Math.sin(current.yaw)*horizontal,current.target.y-Math.cos(current.yaw)*horizontal,current.target.z+Math.sin(current.elevation)*current.distance);
  camera.lookAt(current.target);camera.updateMatrixWorld();
 }
 label();
 return {tick,sample,preset,get mode(){return mode;},dispose(){cleanup.forEach(fn=>fn());nav.remove();}};
}
