import * as T from './vendor/three.module.min.js';
// RENDERING ONLY: this module has no HTTP, station, motor or CAN interface.
const ease=t=>t*t*t*(t*(t*6-15)+10);
function linearSolve(A,b){A=A.map((r,i)=>[...r,b[i]]);for(let i=0;i<b.length;i++){let p=i;for(let j=i+1;j<b.length;j++)if(Math.abs(A[j][i])>Math.abs(A[p][i]))p=j;[A[i],A[p]]=[A[p],A[i]];if(Math.abs(A[i][i])<1e-12)return b.map(()=>0);const d=A[i][i];for(let k=i;k<=b.length;k++)A[i][k]/=d;for(let j=0;j<b.length;j++)if(j!==i){const f=A[j][i];for(let k=i;k<=b.length;k++)A[j][k]-=f*A[i][k];}}return A.map(r=>r[b.length]);}
export function createDealerMotion(arms,scene,navigation){
 const V=(x,y,z)=>new T.Vector3(x,y,z),orientation=new T.Quaternion(),limits={},state={},ready={},tools={},audit={maxPositionError:0,maxOrientationError:0,plans:0,failures:[],samples:[]};
 for(const side of ['left','right']){const a=arms[side],tip=new T.Group();tip.name=side+'-render-grasp';tip.position.z=-.105;a.links.gripper.add(tip);tools[side]=tip;limits[side]=Array.from({length:6},(_,i)=>[a.joints['joint'+(i+1)].lower,a.joints['joint'+(i+1)].upper]);state[side]=[1.57,-.6,.9,0,.8,0];}
 function apply(side,q,grip=.018){arms[side].update([...q,grip,grip]);arms[side].base.visible=true;arms[side].base.updateMatrixWorld(true);}
 function solve(side,target,quat=orientation,seed=state[side]){
  const a=arms[side],q=seed.slice(),end=new T.Vector3(),rot=new T.Quaternion();let error=1,angle=1;
  for(let it=0;it<140;it++){
   apply(side,q);tools[side].getWorldPosition(end);tools[side].getWorldQuaternion(rot);
   const ep=target.clone().sub(end),er=quat.clone().multiply(rot.invert());if(er.w<0){er.x*=-1;er.y*=-1;er.z*=-1;er.w*=-1;}
   const av=new T.Vector3(er.x,er.y,er.z);angle=2*Math.atan2(av.length(),er.w);if(av.length()>1e-10)av.normalize().multiplyScalar(angle);error=ep.length();if(error<.0006&&angle<.008)break;
   const columns=[];for(let j=0;j<6;j++){const joint=a.joints['joint'+(j+1)],axis=joint.axis.clone().applyQuaternion(joint.frame.getWorldQuaternion(new T.Quaternion())),p=joint.frame.getWorldPosition(new T.Vector3()),lin=axis.clone().cross(end.clone().sub(p));columns.push([...lin.toArray(),...axis.multiplyScalar(.17).toArray()]);}
   const e=[...ep.toArray(),...av.multiplyScalar(.17).toArray()],A=columns.map((c,i)=>columns.map((d,j)=>c.reduce((s,v,k)=>s+v*d[k],0)+(i===j?.00012:0))),b=columns.map(c=>c.reduce((s,v,k)=>s+v*e[k],0)),dq=linearSolve(A,b);
   q.forEach((v,i)=>q[i]=T.MathUtils.clamp(v+T.MathUtils.clamp(dq[i],-.20,.20),...limits[side][i]));
  }
  return {q,error,angle};
 }
 function qualified(side,point,quat=orientation,seed=state[side]){let r=solve(side,point,quat,seed);if(r.error>.003||r.angle>.03){for(const offset of [-1,1,-2,2]){const q=seed.slice();q[1]+=offset;q[2]-=offset;const n=solve(side,point,quat,q);if(n.error+n.angle*.1<r.error+r.angle*.1)r=n;}}
  audit.maxPositionError=Math.max(audit.maxPositionError,r.error);audit.maxOrientationError=Math.max(audit.maxOrientationError,r.angle);
  if(r.error>.006||r.angle>.06){audit.failures.push({side,target:point.toArray(),error:r.error,angle:r.angle});throw Error('Practice pose outside the qualified display workspace');}return r.q;
 }
 for(const side of ['left','right']){ready[side]=qualified(side,V(side==='left'?-.72:-.015,.28,.22));state[side]=ready[side].slice();apply(side,state[side]);}
 function restore(){for(const s of ['left','right'])apply(s,state[s]);}
 const cache=new Map();
 function prepare(destination,shoe){
  const key=destination.toArray().map(v=>v.toFixed(3)).join(',');if(cache.has(key))return cache.get(key);
  const handoff=V(-.36675,.26,.24),offsetL=V(0,.043,0),offsetR=V(0,-.043,0),rightQ=new T.Quaternion().setFromAxisAngle(V(0,0,1),Math.PI);
  const receiver=destination.x<-.40?'left':'right';
  const rightPlace=destination.clone().sub(receiver==='right'?offsetR:offsetL);rightPlace.z=.035;
  const leftPick=shoe.clone().sub(offsetL),leftHigh=leftPick.clone().add(V(0,0,.07));
  let l=state.left.slice(),r=state.right.slice();const rows=[];
  function row(t,lp,rp,lg=.018,rg=.018,rquat=rightQ){if(lp)l=qualified('left',lp,orientation,l);if(rp)r=qualified('right',rp,rquat,r);rows.push({t,left:l.slice(),right:r.slice(),lg,rg});}
  rows.push({t:0,left:state.left.slice(),right:state.right.slice(),lg:.018,rg:.018});
  row(.15,leftHigh,null);row(.23,leftPick,null,.001);
  if(receiver==='right'){
   row(.43,handoff.clone().sub(offsetL),handoff.clone().sub(offsetR),.001,.018);row(.50,null,null,.018,.001);
   row(.70,V(-.72,.28,.22),rightPlace.clone().add(V(0,0,.04)),.018,.001);row(.78,null,rightPlace,.018,.001);row(.85,null,rightPlace.clone().add(V(0,0,.045)),.018,.018);row(1,null,V(-.015,.28,.22),.018,.018,orientation);
  }else{
   row(.43,V(-.60,.24,.25),null,.001);row(.50,null,null,.001);row(.70,rightPlace.clone().add(V(0,0,.04)),null,.001);row(.78,rightPlace,null,.001);row(.85,rightPlace.clone().add(V(0,0,.045)),null);row(1,V(-.72,.28,.22),null);
  }
  rows.receiver=receiver;restore();audit.plans++;cache.set(key,rows);return rows;
 }
 function start(mesh,to,shoe,angle){const rows=prepare(to,shoe);mesh.position.copy(shoe);mesh.rotation.set(0,Math.PI,0);mesh.userData.practicePhase='reach';return {kind:'practice',mesh,to:to.clone(),angle,rows,start:performance.now(),duration:2400,phase:'reach',parentSide:null,receiver:rows.receiver};}
 function tick(a,now){const t=Math.min(1,(now-a.start)/a.duration);let i=1;while(i<a.rows.length-1&&t>a.rows[i].t)i++;const p=a.rows[i-1],n=a.rows[i],f=ease(T.MathUtils.clamp((t-p.t)/(n.t-p.t),0,1));for(const s of ['left','right']){state[s]=p[s].map((v,k)=>v+(n[s][k]-v)*f);apply(s,state[s],p[s==='left'?'lg':'rg']+(n[s==='left'?'lg':'rg']-p[s==='left'?'lg':'rg'])*f);}
  if(t>=.23&&!a.parentSide){tools.left.attach(a.mesh);a.parentSide='left';a.phase='draw';window.dispatchEvent(new CustomEvent('dealer-foley',{detail:'slide'}));}
  if(t>=.50&&a.parentSide==='left'&&a.receiver==='right'){tools.right.attach(a.mesh);a.parentSide='right';a.phase='pass';}
  if(t>=.78&&a.parentSide===a.receiver){scene.attach(a.mesh);a.parentSide='released';a.landedFrom=a.mesh.position.clone();a.releaseQuaternion=a.mesh.quaternion.clone();a.phase='place';}
  if(a.parentSide==='released'){
   const settle=ease(T.MathUtils.clamp((t-.78)/.04,0,1));
   const u=ease(T.MathUtils.clamp((t-.82)/.12,0,1));
   const turn=Math.PI*(1-u),half=.0315;
   const flipStart=a.to.clone().add(V(.063,.01,.0004));
   if(t<.82){a.mesh.position.copy(a.landedFrom).lerp(flipStart,settle);a.mesh.quaternion.copy(a.releaseQuaternion).slerp(new T.Quaternion().setFromEuler(new T.Euler(0,Math.PI,a.angle)),settle);}
   else{a.mesh.position.copy(a.to);a.mesh.position.x+=half*(1-Math.cos(turn));a.mesh.position.y+=.01*(1-u);a.mesh.position.z+=half*Math.sin(turn)+.0004;a.mesh.rotation.set(0,turn,a.angle);}
   a.phase=u<1?'flip':'retract';
   if(u===1&&!a.sound){a.sound=true;window.dispatchEvent(new CustomEvent('dealer-foley',{detail:'place'}));}
  }
  a.mesh.userData.practicePhase=a.phase;navigation.attention(a.mesh.getWorldPosition(new T.Vector3()),400);
  if(audit.samples.length<600)audit.samples.push({phase:a.phase,parent:a.mesh.parent.name,qLeft:state.left.slice(),qRight:state.right.slice()});
  if(t===1){a.mesh.position.copy(a.to);a.mesh.rotation.set(0,0,a.angle);a.mesh.userData.practicePhase='rest';return false;}return true;
 }
 return {start,tick,solve,prepare,restore,tools,state,ready,audit,limits};
}
