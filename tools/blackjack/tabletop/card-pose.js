// Measured image corners, NOT robot coordinates. The default display mapping
// preserves camera positions/perspective. No calibrated camera→arm transform
// exists at this station; this projection must never be used to move a robot.
import * as THREE from './vendor/three.module.min.js';
export function imagePoint([x,y]) { return new THREE.Vector3(-1.16675+1.6*x,.88-1.2*y,.0007); }
export function poseFromCorners(mesh,corners){
 if(!Array.isArray(corners)||corners.length!==4||corners.some(p=>p.length!==2||!p.every(Number.isFinite)))return false;
 const q=corners.map(imagePoint),center=q.reduce((p,v)=>p.add(v),new THREE.Vector3()).multiplyScalar(.25);
 mesh.position.copy(center);mesh.rotation.set(0,0,0);mesh.scale.setScalar(1);
 const {width,height}=mesh.userData.physicalSize;
 mesh.traverse(child=>{
  if(!child.isMesh)return;
  if(!child.userData.originalPositions){child.geometry=child.geometry.clone();child.userData.originalPositions=child.geometry.attributes.position.array.slice();child.userData.ownedGeometry=true;}
  const original=child.userData.originalPositions,p=child.geometry.attributes.position;
  for(let i=0;i<p.count;i++){
   // Local bottom-left→image corner3, bottom-right→2, top-right→1, top-left→0.
   // The reverse face has a 180° Y transform of its own.
   const back=Math.abs(child.rotation.y)>3;
   const u=(original[i*3]*(back?-1:1)+width/2)/width,v=(original[i*3+1]+height/2)/height;
   const point=new THREE.Vector3().addScaledVector(q[3],(1-u)*(1-v)).addScaledVector(q[2],u*(1-v)).addScaledVector(q[1],u*v).addScaledVector(q[0],(1-u)*v).sub(center);
   p.setXYZ(i,point.x*(back?-1:1),point.y,original[i*3+2]);
  }
  p.needsUpdate=true;child.geometry.computeVertexNormals();child.geometry.computeBoundingSphere();
 });
 mesh.userData.imageCorners=corners;return true;
}
