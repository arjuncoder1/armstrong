import * as THREE from './vendor/three.module.min.js';
import {loadURDF} from './urdf.js';
import {createViewCamera} from './view-camera.js';
import {createCardDeck,CARD_DISPLAY_SCALE} from './cards.js';
const SUIT_NAME={'♠':'spades','♥':'hearts','♦':'diamonds','♣':'clubs'};
export async function createScene(canvas){
 const [spec,xml]=await Promise.all([fetch('/robot-model.json').then(r=>r.json()),fetch('/yam-station.urdf').then(r=>r.text())]);
 const renderer=new THREE.WebGLRenderer({canvas,antialias:true,alpha:true,powerPreference:'low-power'});
 renderer.setPixelRatio(Math.min(devicePixelRatio,1.7));renderer.setClearColor(0x090a0b,1);
 renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.VSMShadowMap;
 renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.05;
 const scene=new THREE.Scene();scene.background=new THREE.Color(0x090a0b);scene.fog=new THREE.Fog(0x090a0b,3.5,7);
 const camera=new THREE.PerspectiveCamera(34,1,.05,12);camera.up.set(0,0,1);
 const ambient=new THREE.HemisphereLight(0xf5efe4,0x17201b,2.2);scene.add(ambient);
 const key=new THREE.DirectionalLight(0xfff4df,3.4);key.position.set(-1,-.8,2);key.castShadow=true;
 key.shadow.mapSize.set(2048,2048);Object.assign(key.shadow.camera,{left:-1.5,right:1.5,top:1.5,bottom:-1.5,near:.1,far:6});key.shadow.bias=-.00015;key.shadow.normalBias=.0003;key.shadow.radius=4;scene.add(key);
 const fill=new THREE.DirectionalLight(0xbccedb,2.1);fill.position.set(.8,.8,1.1);scene.add(fill);
 const rim=new THREE.DirectionalLight(0xffe9cb,1.6);rim.position.set(-1.2,1,.5);scene.add(rim);
 const table=new THREE.Mesh(new THREE.BoxGeometry(200,200,.035),new THREE.MeshStandardMaterial({color:0x030405,roughness:.94}));table.position.set(-.36675,.24,-.0175);table.receiveShadow=true;scene.add(table);
 const outlines=new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(1.84,1.59,.001)),new THREE.LineBasicMaterial({color:0x34392e,transparent:true,opacity:.06}));outlines.position.set(-.36675,.24,-.006);// No decorative perimeter: the table fills the viewport.
 const geometries=spec.meshes.map(m=>{const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(m.vertices.flat(),3));g.setIndex(m.faces.flat());g.computeVertexNormals();return g;});
 const armColors={left:0x35b8b1,right:0xe29650};
 const arms={};
 for(const side of ['left','right']){
  const shell=new THREE.MeshStandardMaterial({color:armColors[side],roughness:.32,metalness:.42});
  const arm=loadURDF(xml,geometries,shell);const base=new THREE.Group();base.matrixAutoUpdate=false;base.matrix.set(...spec.rig.arms[side].T_table_base.flat());base.add(arm.root);base.visible=false;scene.add(base);arms[side]={...arm,base};
 }
 const navigation=createViewCamera(camera,canvas,arms);
 let telemetryAt=0,telemetryFresh=false, game=null,lastKey='',size='',animations=[];
 let cameraMode=false,transferReplay=false,lastPose=null,observation=null,observationID=null;
 const observedGroup=new THREE.Group();scene.add(observedGroup);observedGroup.visible=false;
 const cards=new Map(),observedCards=new Map(),reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
 const deck=await createCardDeck(renderer),makeCard=card=>deck.make(card);
 function removeCard(mesh){mesh.parent?.remove(mesh);if(mesh.userData.fadeMaterials)mesh.userData.fadeMaterials.forEach(m=>m.dispose());}
 function fadeIn(mesh){
  if(reduce)return;
  mesh.userData.fadeMaterials=[];mesh.traverse(child=>{if(!child.isMesh)return;child.material=child.material.clone();child.material.transparent=true;child.material.opacity=0;mesh.userData.fadeMaterials.push(child.material);});
  animations.push({kind:'observed',mesh,start:performance.now(),duration:650});
 }
 function practicePath(destination){
  const point=(side,fallback)=>{const ee=lastPose?.fresh&&lastPose.measured?.[side]?.ee_mm;
   return Array.isArray(ee)&&ee.length===3&&ee.every(Number.isFinite)?new THREE.Vector3(...ee.map(v=>v/1000)).applyMatrix4(arms[side].base.matrix):fallback;};
  const left=point('left',new THREE.Vector3(-.68,.28,.20)),right=point('right',new THREE.Vector3(-.10,.28,.20));
  left.z=Math.max(.15,left.z);right.z=Math.max(.15,right.z);
  const handoff=left.clone().add(right).multiplyScalar(.5);handoff.z=Math.max(left.z,right.z)+.06;
  // Explicit practice choreography through measured grasp landmarks, not a recorded physical trajectory.
  return new THREE.CatmullRomCurve3([shoePos.clone(),left,handoff,right,destination.clone().add(new THREE.Vector3(0,0,.07)),destination.clone()],false,'centripetal');
 }
 // Display placement beside LEFT; table registration remains nominal.
 const shoePos=new THREE.Vector3(-.7335-.18,.30,.038);
 const shoe=new THREE.Group();shoe.position.copy(shoePos);shoe.rotation.z=-.12;scene.add(shoe);
 const shoeBox=new THREE.Mesh(new THREE.BoxGeometry(.166,.228,.055),new THREE.MeshStandardMaterial({color:0x1d231c,roughness:.38,metalness:.25}));shoeBox.position.z=-.03;shoeBox.castShadow=true;shoe.add(shoeBox);
 for(let i=0;i<9;i++){const top=makeCard({rank:'?',suit:'',id:'shoe:'+i});top.position.z=i*.0013;shoe.add(top);}
 const cut=new THREE.Mesh(new THREE.BoxGeometry(.156,.216,.0006),new THREE.MeshStandardMaterial({color:0xb99b50,roughness:.8}));cut.position.set(.008,0,-.018);shoe.add(cut);
 function positions(g){
  const targets=[];const center=-.36675;
  const arrange=(list,id,y,mid,width)=>{
   const step=Math.min(.17,width/Math.max(1,list.length));
   list.forEach((card,i)=>targets.push({card,target:id,pos:new THREE.Vector3(mid+(i-(list.length-1)/2)*step,y,.0007+i*.0011),angle:(i-(list.length-1)/2)*-.022}));
  };
  arrange(g.dealer.cards,'dealer',.58,center,.8);
  const n=g.hands.length,area=n>1?1.06:.8;
  g.hands.forEach((h,i)=>arrange(h.cards,h.id,-.13,center+(i-(n-1)/2)*(area/n),n>1?area/n-.03:.8));
  return targets;
 }
 function sync(g){
  game=g;const items=positions(g);const ids=new Set(items.map(i=>i.card.id));
  for(const [id,mesh]of cards){if(!ids.has(id)){removeCard(mesh);cards.delete(id);}}
  animations=animations.filter(a=>a.kind==='observed'||ids.has(a.mesh.userData.card.id));
  for(const item of items){
   let mesh=cards.get(item.card.id);
   if(!mesh){mesh=makeCard(item.card);cards.set(item.card.id,mesh);scene.add(mesh);
    if(g.mode==='practice'&&!reduce){mesh.position.copy(shoePos);mesh.rotation.set(0,Math.PI,-.12);animations.push({kind:'practice',mesh,to:item.pos,path:practicePath(item.pos),angle:item.angle,start:performance.now(),duration:1800});}
    else{mesh.position.copy(item.pos);mesh.rotation.z=item.angle;}
   }else if(!animations.some(a=>a.mesh===mesh)){mesh.position.copy(item.pos);mesh.rotation.z=item.angle;}
  }
  for(const mesh of cards.values())mesh.visible=!cameraMode;
  cut.material.color.set(g.shoe.cut_reached?0xe1b96d:0x8e7b4d);
  cut.position.z=g.shoe.cut_reached?.014:-.018;
 }
 function pose(data){
  lastPose=data;if(transferReplay)return;
  navigation.sample(data);
  applyPose(data);
 }
 function applyPose(data){
  telemetryAt=performance.now();telemetryFresh=data.fresh===true;
  for(const [side,arm]of Object.entries(arms)){
   const m=data.measured?.[side],q=m?.positions_rad;
   if(!telemetryFresh||!q||q.length!==6||!q.every(Number.isFinite)){arm.base.visible=false;continue;}
   const grip=Number.isFinite(m.gripper)?Math.max(0,Math.min(1,m.gripper))*.0475:0;
   // Apply measured samples directly. Never use targets or a decorative idle animation.
   arm.update([...q,grip,grip]);arm.base.visible=true;
  }
 }
 function observe(result,active=true,replay=false){
  const replayChanged=transferReplay!==(active&&replay);transferReplay=active&&replay;if(replayChanged)observationID=null;
  cameraMode=active;observation=result;observedGroup.visible=active;
  for(const mesh of cards.values())mesh.visible=!active;
  if(!active){if(lastPose)applyPose(lastPose);return;}
  if(!result){observedGroup.visible=false;observationID=null;return;}
  if(transferReplay)applyPose({fresh:true,measured:result.measured||{}});else if(lastPose)applyPose(lastPose);
  if(observationID===result.scan_id)return;observationID=result.scan_id;
  if(transferReplay)navigation.sample({fresh:true,measured:result.measured||{}},true);
  const seen=result.cards||[],keep=new Set();
  const rows={top:seen.filter(c=>c.y<.34),bottom:seen.filter(c=>c.y>=.34)};
  for(const [side,list]of Object.entries(rows)){
   const occurrences={};list.sort((a,b)=>a.x-b.x).forEach((card,i)=>{
    const face=card.rank+card.suit;occurrences[face]=(occurrences[face]||0)+1;const id=side+':'+face+':'+occurrences[face];keep.add(id);
    let mesh=observedCards.get(id);if(!mesh){mesh=makeCard({...card,id});observedCards.set(id,mesh);observedGroup.add(mesh);fadeIn(mesh);}
    const line=Math.floor(i/6),n=Math.min(6,list.length-line*6),col=i%6;
    mesh.position.set(-.36675+(col-(n-1)/2)*.17,(side==='top'?.58:-.13)+(side==='top'?-1:1)*line*.23,.0007);
    mesh.rotation.z=(col-(n-1)/2)*-.018;mesh.userData.observed=true;mesh.userData.cameraRow=side;
   });
  }
  const transfer=result.transfer||{};
  if(transferReplay&&['left','right','both'].includes(transfer.holder)){
   const sides=transfer.holder==='both'?['left','right']:[transfer.holder],points=[];
   for(const side of sides){const ee=result.measured?.[side]?.ee_mm;if(Array.isArray(ee)&&ee.length===3&&ee.every(Number.isFinite))points.push(new THREE.Vector3(...ee.map(v=>v/1000)).applyMatrix4(arms[side].base.matrix));}
   if(points.length===sides.length){
    const id='held:'+result.scan_id;keep.add(id);let mesh=observedCards.get(id);
    if(!mesh){mesh=makeCard({rank:transfer.rank||'?',suit:transfer.suit||'',id});observedCards.set(id,mesh);observedGroup.add(mesh);fadeIn(mesh);}
    mesh.position.copy(points[0]);if(points.length===2)mesh.position.add(points[1]).multiplyScalar(.5);
    mesh.userData.transfer=true;mesh.userData.holder=transfer.holder;
   }
  }
  for(const [id,mesh]of observedCards)if(!keep.has(id)){removeCard(mesh);observedCards.delete(id);}
  animations=animations.filter(a=>a.kind!=='observed'||a.mesh.parent);
 }
 function paint(now){
  const w=canvas.clientWidth,h=canvas.clientHeight;if(!w||!h)return;
  const next=w+':'+h;if(size!==next){size=next;renderer.setSize(w,h,false);camera.aspect=w/h;
   camera.updateProjectionMatrix();}
  navigation.tick(now,camera.aspect);
  if(!transferReplay&&telemetryFresh&&performance.now()-telemetryAt>1700){telemetryFresh=false;Object.values(arms).forEach(a=>a.base.visible=false);window.dispatchEvent(new Event('pose-stale'));}
  animations=animations.filter(a=>{
   const t=Math.min(1,(now-a.start)/a.duration),ease=t*t*(3-2*t);
   if(a.kind==='observed'){for(const m of a.mesh.userData.fadeMaterials||[]){m.opacity=ease;if(t===1)m.transparent=false;}return t<1;}
   a.mesh.position.copy(a.path.getPoint(ease));
   const flip=THREE.MathUtils.clamp((t-.72)/.24,0,1),turn=flip*flip*(3-2*flip);
   a.mesh.rotation.set(.06*Math.sin(Math.PI*t),Math.PI*(1-turn),-.12*(1-ease)+a.angle*ease+.08*Math.sin(Math.PI*2*t));
   return t<1;
  });
  renderer.render(scene,camera);
 }
 renderer.setAnimationLoop(now=>{if(!document.hidden)paint(now);});
 return {sync,pose,observe,observedGroup,navigation,deck,cards,get animations(){return animations;},get cameraMode(){return cameraMode;},arms,spec,camera,renderer,scene,get busy(){return animations.some(a=>a.kind==='practice');},dispose(){navigation.dispose();deck.dispose();renderer.setAnimationLoop(null);renderer.dispose();}};
}
