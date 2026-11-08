import * as THREE from './vendor/three.module.min.js';
import {imagePoint,poseFromCorners} from './card-pose.js';
import {createDealerMotion} from './dealer-motion.js';
import {createFinish} from './finish.js';
import {createCasinoSet} from './casino-set.js';
import {HDRLoader} from './vendor/HDRLoader.js';
import {toCreasedNormals} from './vendor/BufferGeometryUtils.js';
import {loadURDF} from './urdf.js';
import {createViewCamera} from './view-camera.js';
import {createCardDeck,CARD_DISPLAY_SCALE} from './cards.js';
const SUIT_NAME={'♠':'spades','♥':'hearts','♦':'diamonds','♣':'clubs'};
export async function createScene(canvas){
 const [spec,xml]=await Promise.all([fetch('/robot-model.json').then(r=>r.json()),fetch('/yam-station.urdf').then(r=>r.text())]);
 const renderer=new THREE.WebGLRenderer({canvas,antialias:true,alpha:false,powerPreference:'high-performance'});
 renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.setClearColor(0x090a0b,1);
 renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.VSMShadowMap;
 renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.0;renderer.outputColorSpace=THREE.SRGBColorSpace;
 const scene=new THREE.Scene();scene.background=new THREE.Color(0x090a0b);scene.fog=new THREE.Fog(0x090a0b,3.5,7);
 const camera=new THREE.PerspectiveCamera(39,1,.025,8);camera.up.set(0,0,1);
 const ambient=new THREE.HemisphereLight(0xc9d2db,0x17150e,.18);scene.add(ambient);
 const key=new THREE.SpotLight(0xffe2b2,5,3.4,.85,.85,2);key.position.set(-.36675,.42,1.05);key.target.position.set(-.36675,.40,0);key.castShadow=true;
 key.shadow.mapSize.set(2048,2048);key.shadow.camera.near=.1;key.shadow.camera.far=3.5;key.shadow.bias=-.000035;key.shadow.normalBias=.0005;key.shadow.radius=4;key.shadow.blurSamples=8;scene.add(key,key.target);
 const rim=new THREE.DirectionalLight(0xb1c4d1,1.3);rim.position.set(-.5,-.5,.9);scene.add(rim);
 const fill=new THREE.DirectionalLight(0xe0dccf,.45);fill.position.set(-.3,1.2,.7);scene.add(fill);
 const floor=new THREE.Mesh(new THREE.PlaneGeometry(12,12),new THREE.MeshPhysicalMaterial({color:0x080908,roughness:.95}));floor.position.z=-.78;floor.receiveShadow=true;scene.add(floor);
 const casino=createCasinoSet(THREE,scene);
 let environmentTarget=null;const environmentReady=new HDRLoader().loadAsync(casino.environmentURL).then(hdr=>{const generator=new THREE.PMREMGenerator(renderer);environmentTarget=generator.fromEquirectangular(hdr);scene.environment=environmentTarget.texture;scene.environmentIntensity=.26;hdr.dispose();generator.dispose();return true;}).catch(()=>false);
 const outlines=new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(1.84,1.59,.001)),new THREE.LineBasicMaterial({color:0x34392e,transparent:true,opacity:.06}));outlines.position.set(-.36675,.24,-.006);// No decorative perimeter: the table fills the viewport.
 const geometries=spec.meshes.map(m=>{const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(m.vertices.flat(),3));g.setIndex(m.faces.flat());const smooth=toCreasedNormals(g,Math.PI/3);if(smooth!==g)g.dispose();return smooth;});
 const armColors={left:0x606b70,right:0x706c60};
 const arms={};
 for(const side of ['left','right']){
  const shell=new THREE.MeshPhysicalMaterial({color:0x24282a,roughness:.48,metalness:.65});
  const paint=new THREE.MeshPhysicalMaterial({color:0x8b918f,roughness:.40,metalness:.8});
  const accent=new THREE.MeshPhysicalMaterial({color:armColors[side],roughness:.5,metalness:.65});
  const arm=loadURDF(xml,geometries,shell);for(const name of ['link2','link4'])arm.links[name]?.traverse(m=>{if(m.isMesh)m.material=paint;});arm.links.link6?.traverse(m=>{if(m.isMesh)m.material=accent;});const base=new THREE.Group();base.matrixAutoUpdate=false;base.matrix.set(...spec.rig.arms[side].T_table_base.flat());base.add(arm.root);base.visible=false;scene.add(base);arms[side]={...arm,base};
 }
 const navigation=createViewCamera(camera,canvas,arms);
 const dealerMotion=createDealerMotion(arms,scene,navigation);
 let telemetryAt=0,telemetryFresh=false, game=null,lastKey='',size='',animations=[];
 let cameraMode=false,transferReplay=false,lastPose=null,observation=null,observationID=null,tracking=null,trackingAt=0;
 const observedGroup=new THREE.Group();scene.add(observedGroup);observedGroup.visible=false;
 const cards=new Map(),observedCards=new Map(),reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
 const deck=await createCardDeck(renderer),makeCard=card=>deck.make(card);
 const liveCardTexture=new THREE.Texture();liveCardTexture.colorSpace=THREE.SRGBColorSpace;liveCardTexture.minFilter=THREE.LinearFilter;liveCardTexture.magFilter=THREE.LinearFilter;liveCardTexture.generateMipmaps=false;
 let photoAt=null;
 function cameraFace(mesh,corners){
  const face=mesh.children[1];if(!face||!liveCardTexture.image)return;
  if(!face.userData.livePhoto){if(face.userData.ownedMaterial)face.material.dispose();face.material=new THREE.MeshBasicMaterial({map:liveCardTexture,toneMapped:false,polygonOffset:true,polygonOffsetFactor:-1,polygonOffsetUnits:-1});face.userData.livePhoto=true;face.userData.ownedMaterial=true;}
  const original=face.userData.originalPositions,uv=face.geometry.attributes.uv,{width,height}=mesh.userData.physicalSize;
  for(let i=0;i<uv.count;i++){
   const u=(original[i*3]+width/2)/width,v=(original[i*3+1]+height/2)/height;
   const weights=[(1-u)*v,u*v,u*(1-v),(1-u)*(1-v)];
   uv.setXY(i,corners.reduce((n,p,k)=>n+p[0]*weights[k],0),1-corners.reduce((n,p,k)=>n+p[1]*weights[k],0));
  }
  uv.needsUpdate=true;
 }
 function removeCard(mesh){mesh.userData.heldTexture?.dispose();mesh.parent?.remove(mesh);mesh.traverse(c=>{if(c.userData.ownedGeometry)c.geometry.dispose();if(c.userData.ownedMaterial)c.material.dispose();});if(mesh.userData.fadeMaterials)mesh.userData.fadeMaterials.forEach(m=>m.dispose());}
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
 const shoePos=new THREE.Vector3(-.88,.25,.098);
 const shoe=new THREE.Group();shoe.position.copy(shoePos);shoe.rotation.z=0;scene.add(shoe);
 const stock=new THREE.Mesh(new THREE.BoxGeometry(.063,.088,.093),new THREE.MeshPhysicalMaterial({color:0xc6c1b5,roughness:.85}));stock.position.z=-.047;stock.castShadow=true;shoe.add(stock);
 for(let i=0;i<12;i++){const top=makeCard({rank:'?',suit:'',id:'shoe:'+i});top.position.z=-i*.00033;shoe.add(top);}
 const cut=new THREE.Mesh(new THREE.BoxGeometry(.066,.091,.0006),new THREE.MeshPhysicalMaterial({color:0xad8e39,roughness:.75}));cut.position.set(.004,0,-.046);shoe.add(cut);
 function positions(g){
  const targets=[];const center=-.36675;
  const arrange=(list,id,y,mid,width)=>{
   const step=Math.min(.072,width/Math.max(1,list.length));
   list.forEach((card,i)=>targets.push({card,target:id,pos:new THREE.Vector3(mid+(i-(list.length-1)/2)*step,y,.0007+i*.0011),angle:(i-(list.length-1)/2)*-.022}));
  };
  arrange(g.dealer.cards,'dealer',.26,center,.8);
  const n=g.hands.length,area=n>1?1.06:.8;
  g.hands.forEach((h,i)=>arrange(h.cards,h.id,.43,-.24+(i-(n-1)/2)*(area/n),n>1?area/n-.03:.8));
  return targets;
 }
 function sync(g){
  dirtyUntil=performance.now()+1800;
  game=g;casino.setBet(g.hands?.[0]?.bet||2500);const items=positions(g);const ids=new Set(items.map(i=>i.card.id));
  for(const [id,mesh]of cards){if(!ids.has(id)){removeCard(mesh);cards.delete(id);}}
  animations=animations.filter(a=>a.kind==='observed'||ids.has(a.mesh.userData.card.id));
  for(const item of items){
   let mesh=cards.get(item.card.id);
   if(!mesh){mesh=makeCard(item.card);cards.set(item.card.id,mesh);scene.add(mesh);
    if(g.mode==='practice'&&!reduce){mesh.position.copy(shoePos);mesh.rotation.set(0,Math.PI,-.12);animations.push(dealerMotion.start(mesh,item.pos,shoePos,item.angle));}
    else{mesh.position.copy(item.pos);mesh.rotation.z=item.angle;if(g.mode==='observe')fadeIn(mesh);}
   }else if(!animations.some(a=>a.mesh===mesh)){mesh.position.copy(item.pos);mesh.rotation.z=item.angle;}
  }
  for(const mesh of cards.values())mesh.visible=!cameraMode;
  cut.material.color.set(g.shoe.cut_reached?0xe1b96d:0x8e7b4d);
  cut.position.z=g.shoe.cut_reached?.014:-.018;
 }
 function pose(data){
  if(cameraMode)dirtyUntil=performance.now()+500;
  lastPose=data;if(!cameraMode&&game?.mode==='practice'){if(!animations.some(a=>a.kind==='practice'))dealerMotion.restore();return;}if(transferReplay)return;
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
  if(!active){if(game?.mode==='practice')dealerMotion.restore();else if(lastPose)applyPose(lastPose);return;}
  if(!result){observedGroup.visible=false;observationID=null;return;}
  if(transferReplay)applyPose({fresh:true,measured:result.measured||{}});else if(replayChanged&&lastPose)applyPose(lastPose);
  if(!transferReplay&&tracking){track(tracking);return;}
  if(observationID===result.scan_id)return;observationID=result.scan_id;
  if(transferReplay)navigation.sample({fresh:true,measured:result.measured||{}},true);
  const seen=result.cards||[],keep=new Set();
  const rows={top:seen.filter(c=>c.y<.34),bottom:seen.filter(c=>c.y>=.34)};
  for(const [side,list]of Object.entries(rows)){
   const occurrences={};list.sort((a,b)=>a.x-b.x).forEach((card,i)=>{
    const face=card.rank+card.suit;occurrences[face]=(occurrences[face]||0)+1;const id=side+':'+face+':'+occurrences[face];keep.add(id);
    let mesh=observedCards.get(id);if(!mesh){mesh=makeCard({...card,id});observedCards.set(id,mesh);observedGroup.add(mesh);fadeIn(mesh);}
    const line=Math.floor(i/6),n=Math.min(6,list.length-line*6),col=i%6;
    mesh.position.copy(imagePoint([card.x,card.y]));mesh.scale.setScalar(1);
    mesh.rotation.z=0;mesh.userData.observed=true;mesh.userData.cameraRow=side;
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
 function track(data){
  if(tracking?.captured_at!==data.captured_at)trackingAt=performance.now();tracking=data;
  if(!cameraMode||transferReplay)return;
  observedGroup.visible=true;const keep=new Set();
  if(data.frame_image&&photoAt!==data.captured_at){photoAt=data.captured_at;liveCardTexture.image=data.frame_image;liveCardTexture.needsUpdate=true;}
  for(const card of data.cards||[]){
   const id='track:'+card.id;keep.add(id);const face=(card.rank||'?')+(card.suit||'');
   let mesh=observedCards.get(id);
   if(mesh&&mesh.userData.face!==face&&!card.held){removeCard(mesh);observedCards.delete(id);mesh=null;}
   if(!mesh){mesh=makeCard({...card,rank:card.rank||'?',suit:card.suit||'',unknown:!card.rank,id});mesh.userData.face=face;observedCards.set(id,mesh);observedGroup.add(mesh);}
   mesh.userData.targetCorners=card.corners;
   if(!mesh.userData.imageCorners)poseFromCorners(mesh,card.corners);
   mesh.visible=data.fresh&&(card.visible||card.held);
   if(!card.held&&!card.rank&&data.frame_image){cameraFace(mesh,card.corners);mesh.children[1].material.map=liveCardTexture;}
   if(card.visible&&data.frame_image)mesh.userData.lastPhoto=data.frame_image;
   if(card.held&&mesh.children[1]?.userData.livePhoto&&mesh.userData.lastPhoto&&!mesh.userData.heldTexture){const frozen=liveCardTexture.clone();frozen.image=mesh.userData.lastPhoto;frozen.needsUpdate=true;mesh.userData.heldTexture=frozen;mesh.children[1].material.map=frozen;}
   if(card.visible&&mesh.userData.heldTexture){mesh.userData.heldTexture.dispose();delete mesh.userData.heldTexture;}
   mesh.traverse(c=>{if(!c.isMesh)return;if(!c.userData.ownedMaterial){c.material=c.material.clone();c.userData.ownedMaterial=true;}c.material.transparent=!!card.held||(!!card.provisional&&!data.frame_image);c.material.opacity=card.held?.35:((card.provisional&&!data.frame_image)?.15:1);});
   mesh.userData.observed=true;mesh.userData.tracked=true;mesh.userData.status=card.status;
  }
  for(const [id,mesh]of observedCards)if(!keep.has(id)){removeCard(mesh);observedCards.delete(id);}
  animations=animations.filter(a=>a.kind!=='observed'||a.mesh.parent);
 }
 let lastPaint=0,dirtyUntil=performance.now()+3000;const frameTimes=[],renderTimes=[];
 const invalidate=()=>{dirtyUntil=performance.now()+1400;};canvas.addEventListener('pointermove',invalidate);window.addEventListener('resize',invalidate);
 function paint(now){
  const began=performance.now();if(lastPaint&&now-lastPaint<100)frameTimes.push(now-lastPaint);if(frameTimes.length>3600)frameTimes.shift();renderer.info.reset();
  const elapsed=lastPaint?Math.min(.1,(now-lastPaint)/1000):.016;lastPaint=now;
  if(cameraMode&&!transferReplay)for(const mesh of observedCards.values()){
   const target=mesh.userData.targetCorners,current=mesh.userData.imageCorners;if(!target||!current||!mesh.visible)continue;
   const blend=reduce?1:1-Math.exp(-elapsed*32);
   const next=current.map((p,i)=>p.map((v,j)=>v+(target[i][j]-v)*blend));
   if(next.some((p,i)=>p.some((v,j)=>Math.abs(v-current[i][j])>1e-6)))poseFromCorners(mesh,next);
  }
  const w=canvas.clientWidth,h=canvas.clientHeight;if(!w||!h)return;
  const next=w+':'+h;if(size!==next){size=next;renderer.setSize(w,h,false);camera.aspect=w/h;
   camera.updateProjectionMatrix();finish.resize(w,h);}
  navigation.tick(now,camera.aspect);
  if(cameraMode&&!transferReplay&&tracking&&now-trackingAt>600)observedGroup.visible=false;
  if(cameraMode&&!transferReplay&&telemetryFresh&&performance.now()-telemetryAt>1700){telemetryFresh=false;Object.values(arms).forEach(a=>a.base.visible=false);window.dispatchEvent(new Event('pose-stale'));}
  animations=animations.filter(a=>{
   const t=Math.min(1,(now-a.start)/a.duration),ease=t*t*(3-2*t);
   if(a.kind==='observed'){for(const m of a.mesh.userData.fadeMaterials||[]){m.opacity=ease;if(t===1)m.transparent=false;}return t<1;}
   return dealerMotion.tick(a,now);
  });
  finish.render();renderTimes.push(performance.now()-began);if(renderTimes.length>3600)renderTimes.shift();
 }
 const finish=createFinish(renderer,scene,camera);
 await Promise.all([casino.ready,environmentReady]);
 renderer.info.autoReset=false;
 renderer.setAnimationLoop(now=>{if(!document.hidden&&(animations.length||cameraMode||now<dirtyUntil))paint(now);else lastPaint=0;});
 return {sync,pose,observe,track,casino,finish,environmentReady,observedGroup,navigation,deck,cards,get animations(){return animations;},get cameraMode(){return cameraMode;},arms,spec,camera,renderer,scene,dealerMotion,frameTimes,renderTimes,invalidate,get busy(){return animations.some(a=>a.kind==='practice');},dispose(){navigation.dispose();finish.dispose();casino.dispose();environmentTarget?.dispose();liveCardTexture.dispose();deck.dispose();renderer.setAnimationLoop(null);renderer.dispose();}};
}
