import * as T from './vendor/three.module.min.js';
import {EffectComposer} from './vendor/addons/postprocessing/EffectComposer.js';
import {RenderPass} from './vendor/addons/postprocessing/RenderPass.js';
import {GTAOPass} from './vendor/addons/postprocessing/GTAOPass.js';
import {UnrealBloomPass} from './vendor/addons/postprocessing/UnrealBloomPass.js';
import {OutputPass} from './vendor/addons/postprocessing/OutputPass.js';
import {ShaderPass} from './vendor/addons/postprocessing/ShaderPass.js';
import {BokehPass} from './vendor/addons/postprocessing/BokehPass.js';
export function createFinish(renderer,scene,camera){
 const target=new T.WebGLRenderTarget(1,1,{type:T.HalfFloatType,samples:4});
 const composer=new EffectComposer(renderer,target);composer.addPass(new RenderPass(scene,camera));
 const ao=new GTAOPass(scene,camera,1,1,undefined,{radius:.075,thickness:.05,distanceExponent:1,samples:8},{samples:8,radius:4});ao.blendIntensity=.48;composer.addPass(ao);
 const dof=new BokehPass(scene,camera,{focus:1.05,aperture:.000008,maxblur:.0013});composer.addPass(dof);
 const bloom=new UnrealBloomPass(new T.Vector2(1,1),.09,.25,1.8);composer.addPass(bloom);composer.addPass(new OutputPass());
 const film=new ShaderPass({uniforms:{tDiffuse:{value:null}},vertexShader:'varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',fragmentShader:`uniform sampler2D tDiffuse;varying vec2 vUv;void main(){vec3 c=texture2D(tDiffuse,vUv).rgb;vec2 p=vUv-.5;float vignette=1.-.24*dot(p,p);float grain=fract(sin(dot(gl_FragCoord.xy,vec2(12.9898,78.233)))*43758.5453)-.5;gl_FragColor=vec4(c*vignette+grain*.0022,1.);}`});composer.addPass(film);
 return {composer,ao,dof,bloom,resize(w,h){composer.setSize(w,h);ao.setSize(Math.round(w*.65),Math.round(h*.65));},render(){composer.render();},dispose(){composer.dispose();for(const p of composer.passes)p.dispose?.();}};
}
