import * as THREE from './vendor/three.module.min.js';
// A seated observer, never a camera orbit controller or a hardware command.
export function createViewCamera(camera,canvas,arms){
 const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
 const rest=new THREE.Vector3(-.36675,1.34,.48),look=new THREE.Vector3(-.36675,.22,.085);
 const pointer=new THREE.Vector2(),target=look.clone();let focus=null,until=0,last=0,previous=null;
 camera.position.copy(rest);camera.lookAt(look);camera.updateMatrixWorld();
 canvas.setAttribute('aria-label','Seated blackjack table view. Camera position is fixed; no orbit or zoom.');canvas.removeAttribute('tabindex');
 function mouse(e){pointer.set((e.clientX/innerWidth-.5)*2,(e.clientY/innerHeight-.5)*2);}
 canvas.addEventListener('pointermove',mouse);const leave=()=>pointer.set(0,0);canvas.addEventListener('pointerleave',leave);
 function attention(point,duration=700){if(reduced)return;focus=point.clone();until=performance.now()+duration;}
 function sample(data,snapshot=false){if(snapshot||!data?.fresh)return;const moving=[];for(const side of ['left','right']){const q=data.measured?.[side]?.positions_rad,prev=previous?.[side]?.positions_rad,ee=data.measured?.[side]?.ee_mm;if(q&&prev&&q.some((v,i)=>Math.abs(v-prev[i])>.01)&&ee){moving.push(side);attention(new THREE.Vector3(...ee.map(v=>v/1000)).applyMatrix4(arms[side].base.matrix),900);}}if(moving.length)window.dispatchEvent(new CustomEvent('measured-arm-motion',{detail:{sides:moving}}));previous=data.measured;}
 function tick(now,aspect){const dt=last?Math.min(.1,(now-last)/1000):.016;last=now;target.copy(look);if(focus&&now<until)target.lerp(focus,.055);target.x+=reduced?0:pointer.x*.008;const desired=rest.clone();desired.x+=reduced?0:pointer.x*.009;desired.z+=reduced?0:-pointer.y*.004;camera.position.lerp(desired,1-Math.exp(-dt*2));const current=new THREE.Vector3();camera.getWorldDirection(current);current.multiplyScalar(rest.distanceTo(look)).add(camera.position);current.lerp(target,1-Math.exp(-dt*2));camera.lookAt(current);camera.updateMatrixWorld();}
 return {tick,sample,attention,preset(){},get mode(){return 'seated';},dispose(){canvas.removeEventListener('pointermove',mouse);canvas.removeEventListener('pointerleave',leave);}};
}
