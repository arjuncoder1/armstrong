import {RoundedBoxGeometry} from './vendor/addons/geometries/RoundedBoxGeometry.js';
// Display-only furniture. Arm base transforms are owned by the measured rig.
export function createCasinoSet(T,scene,options={}){
 const group=new T.Group();group.name='casino-table';scene.add(group);
 const geometries=new Set(),materials=new Set(),textures=new Set(),center=-.36675;
 const geo=g=>(geometries.add(g),g),mat=p=>{const m=new T.MeshPhysicalMaterial(p);materials.add(m);return m;};
 const felt=mat({color:0x125044,roughness:.92,sheen:1,sheenColor:new T.Color(0x488b70),sheenRoughness:.72});
 const leather=mat({color:0x10100f,roughness:.48,clearcoat:.14,clearcoatRoughness:.5});
 const wood=mat({color:0x251810,roughness:.23,clearcoat:.65,clearcoatRoughness:.18});
 const metal=mat({color:0x656764,metalness:.85,roughness:.42});
 const dark=mat({color:0x181c1e,metalness:.65,roughness:.48});
 const black=mat({color:0x080a0b,roughness:.7});
 const gold=mat({color:0xbaa779,metalness:.66,roughness:.43});
 function mesh(g,m,pos,parent=group){const o=new T.Mesh(g,m);if(pos)o.position.set(...pos);o.castShadow=o.receiveShadow=true;parent.add(o);return o;}
 function box(w,d,h,m,pos,r=.006,parent=group){return mesh(geo(new RoundedBoxGeometry(w,d,h,2,Math.min(r,w/4,d/4,h/4))),m,pos,parent);}
 const path=new T.Shape();path.moveTo(-.96,0);path.bezierCurveTo(-1.03,.45,-.87,1.04,0,1.04);path.bezierCurveTo(.87,1.04,1.03,.45,.96,0);path.bezierCurveTo(.83,-.16,.46,-.10,.30,-.08);path.bezierCurveTo(.10,-.035,-.10,-.035,-.30,-.08);path.bezierCurveTo(-.46,-.10,-.83,-.16,-.96,0);
 const slab=mesh(geo(new T.ExtrudeGeometry(path,{depth:.065,bevelEnabled:true,bevelSegments:3,steps:1,bevelSize:.014,bevelThickness:.012,curveSegments:48})),wood,[center,0,-.091]);
 const feltGeo=geo(new T.ShapeGeometry(path,64));
 const feltMesh=mesh(feltGeo,felt,[center,0,.00015]);feltMesh.scale.set(.925,.925,1);feltMesh.castShadow=false;
 // Shape UVs are meters, so the photographed nap has a consistent scale.
 const assetBase=new URL('./vendor/casino/',import.meta.url),assetErrors=[];
 async function maps(target,prefix,repeat,normal){
  const loader=new T.TextureLoader();await Promise.all(['diff','nor_gl','rough'].map(async(s,i)=>{try{const t=await loader.loadAsync(new URL(prefix+'_'+s+'_1k.jpg',assetBase).href);textures.add(t);t.wrapS=t.wrapT=T.RepeatWrapping;t.repeat.set(repeat,repeat);t.anisotropy=8;t.colorSpace=i===0?T.SRGBColorSpace:T.NoColorSpace;target[['map','normalMap','roughnessMap'][i]]=t;target.needsUpdate=true;}catch(e){assetErrors.push(e.message);}}));target.normalScale.setScalar(normal);
 }
 const ready=Promise.all([maps(felt,'polar_fleece',7,.18),maps(leather,'leather_white',8,.24)]);
 const boundary=path.getPoints(160).map(p=>new T.Vector3(p.x+center,p.y,.011));
 const curve=new T.CatmullRomCurve3(boundary,true,'centripetal');
 const rail=mesh(geo(new T.TubeGeometry(curve,240,.043,12,true)),leather);rail.scale.z=.78;
 // Two rows of actual thread dashes following the inner edge of the leather.
 const stitchPoints=[];
 for(let i=0;i<480;i++){for(const offset of [.020,.028]){const a=curve.getPoint(i/480),b=curve.getPoint((i+.48)/480);for(const p of [a,b]){p.x=center+(p.x-center)*.979;p.y*=.979;p.z=.043-offset*.08;}stitchPoints.push(a,b);}}
 const thread=new T.LineBasicMaterial({color:0x756b54,transparent:true,opacity:.55});materials.add(thread);group.add(new T.LineSegments(geo(new T.BufferGeometry().setFromPoints(stitchPoints)),thread));
 const inner=curve.clone();inner.points=boundary.map(p=>new T.Vector3(center+(p.x-center)*.943,p.y*.943,-.001));mesh(geo(new T.TubeGeometry(inner,180,.002,6,true)),gold);
 // Foil print is a thin physical surface; raised ink is 0.06 mm.
 const print=document.createElement('canvas');print.width=2048;print.height=1024;const c=print.getContext('2d');
 c.fillStyle='#bca77b';c.textAlign='center';c.font='500 39px Georgia';c.letterSpacing='5px';c.fillText('BLACKJACK PAYS 3 TO 2',1024,330);c.font='22px Georgia';c.letterSpacing='3px';c.fillText('DEALER MUST STAND ON ALL 17s',1024,390);
 c.strokeStyle='#baa679';c.lineWidth=2;c.beginPath();c.moveTo(665,280);c.lineTo(1383,280);c.stroke();c.beginPath();c.moveTo(810,428);c.lineTo(1238,428);c.stroke();
 for(const x of [340,680,1024,1368,1708]){c.beginPath();c.ellipse(x,790,84,94,0,0,Math.PI*2);c.stroke();}
 const printTexture=new T.CanvasTexture(print);textures.add(printTexture);printTexture.colorSpace=T.SRGBColorSpace;printTexture.anisotropy=8;
 const ink=mat({map:printTexture,transparent:true,alphaTest:.05,roughness:.5,metalness:.45,depthWrite:false,bumpMap:printTexture,bumpScale:.00006});
 const markings=mesh(geo(new T.PlaneGeometry(1.65,.72)),ink,[center,.64,.00055]);markings.rotation.z=Math.PI;markings.castShadow=false;
 // Mounted industrial crossmember. The two nominal rig base centers stay exact.
 box(1.0,.16,.068,dark,[center,-.025,-.034]);
 for(const x of [0,-.7335]){box(.145,.145,.026,metal,[x,0,-.013]);for(const dx of [-.055,.055])for(const dy of [-.055,.055]){const g=geo(new T.CylinderGeometry(.004,.004,.003,12));g.rotateX(Math.PI/2);mesh(g,black,[x+dx,dy,.001]);}}
 box(.38,.13,.16,dark,[center,-.105,.060],.015);box(.345,.006,.115,metal,[center,-.036,.060],.006);
 for(let i=0;i<17;i++)box(.002,.002,.048,black,[center-.14+i*.017,-.031,.054],.0004);
 box(.072,.004,.014,black,[center,-.030,.103],.002);
 for(const x of [center-.38,center+.38])box(.12,.18,.70,dark,[x,.0,-.42],.012);
 // Chip tray, with clay chips (39 mm) drawn as instances, not toy cylinders.
 box(.34,.17,.028,black,[center,.115,.014],.009);
 const chipGeom=geo(new T.CylinderGeometry(.0195,.0195,.0033,40));chipGeom.rotateX(Math.PI/2);
 function chipMaterial(colour,value){
  const a=document.createElement('canvas');a.width=a.height=256;const x=a.getContext('2d');x.fillStyle=colour;x.fillRect(0,0,256,256);
  for(let i=0;i<8;i++){x.save();x.translate(128,128);x.rotate(i*Math.PI/4);x.fillStyle='#d9d2b6';x.fillRect(-9,-128,18,36);x.restore();}
  x.fillStyle='#dfd8be';x.beginPath();x.arc(128,128,83,0,Math.PI*2);x.fill();x.strokeStyle='#94866c';x.lineWidth=2;x.beginPath();x.arc(128,128,75,0,Math.PI*2);x.stroke();x.fillStyle='#24251f';x.font='20px Georgia';x.textAlign='center';x.fillText('ARMSTRONG',128,104);x.font='bold 43px Georgia';x.fillText(value,128,153);x.font='13px Georgia';x.fillText('CASINO',128,178);
  let s=123;for(let i=0;i<600;i++){s=(s*1664525+1013904223)>>>0;x.fillStyle='#0000000d';x.fillRect(s%256,(s>>>8)%256,2,1);}
  const t=new T.CanvasTexture(a);t.colorSpace=T.SRGBColorSpace;t.anisotropy=8;textures.add(t);return [mat({color:colour,roughness:.86}),mat({map:t,roughness:.72}),mat({map:t,roughness:.72})];
 }
 const chipSets=[['#c2bdaa','1'],['#8e2827','5'],['#28664d','25'],['#202324','100']];
 const helper=new T.Object3D();const betChips=[];
 chipSets.forEach(([color,value],j)=>{
  const mats=chipMaterial(color,value),n=18,stack=new T.InstancedMesh(chipGeom,mats,n);stack.castShadow=stack.receiveShadow=true;
  for(let i=0;i<n;i++){helper.position.set(center-.12+j*.08,.11,.027+i*.0034);helper.rotation.set(0,0,i*.31);helper.updateMatrix();stack.setMatrixAt(i,helper.matrix);}group.add(stack);
  if(j===2){const bet=new T.InstancedMesh(chipGeom,mats,4);bet.castShadow=bet.receiveShadow=true;for(let i=0;i<4;i++){helper.position.set(center,.74,.002+i*.0034);helper.rotation.set(0,0,i*.13);helper.updateMatrix();bet.setMatrixAt(i,helper.matrix);}group.add(bet);betChips.push(bet);}
 });
 // Smoked shoe sides expose the six-deck stack. The scene owns visible cards.
 const shoe=new T.Group();shoe.position.set(-.88,.25,0);group.add(shoe);
 const acrylic=mat({color:0x202b29,roughness:.20,metalness:.1,transparent:true,opacity:.55,clearcoat:1,depthWrite:false});
 box(.079,.185,.006,black,[0,-.035,.003],.002,shoe);
 for(const x of [-.039,.039])box(.004,.185,.105,acrylic,[x,-.035,.056],.001,shoe);
 box(.078,.004,.105,acrylic,[0,-.125,.056],.001,shoe);box(.067,.017,.09,black,[0,-.10,.050],.003,shoe);
 // A warm pendant, visible only at the top of the seated field of view.
 const hood=mesh(geo(new T.CylinderGeometry(.13,.22,.055,64,1,true)),mat({color:0x1c1a16,metalness:.7,roughness:.35}),[center,.42,1.08]);hood.rotation.x=Math.PI/2;
 const bulb=mesh(geo(new T.CircleGeometry(.19,48)),mat({color:0xffdfac,emissive:0xffc27a,emissiveIntensity:3}),[center,.42,1.051]);bulb.rotation.x=Math.PI;
 return {group,ready,assetErrors,environmentURL:new URL('studio_small_09_1k.hdr',assetBase).href,setBet(cents){for(const b of betChips)b.count=Math.max(1,Math.min(4,Math.ceil(cents/2500)));},dispose(){group.removeFromParent();geometries.forEach(g=>g.dispose());materials.forEach(m=>m.dispose());textures.forEach(t=>t.dispose());}};
}
