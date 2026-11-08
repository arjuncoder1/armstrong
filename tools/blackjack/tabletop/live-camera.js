// Show physical evidence while recognition runs. A wrist view is not ownership.
const base=`${location.protocol}//${location.hostname}:8204`;
const panel=document.createElement('aside');panel.className='live-evidence';panel.setAttribute('aria-label','Live physical camera evidence');
panel.innerHTML='<button class="live-overhead" aria-label="Expand live overhead camera"><img alt="Live overhead camera"><span>Live table</span></button><div class="live-wrists" hidden><figure><img data-side="left" alt="Left wrist camera"><figcaption>Left camera</figcaption></figure><figure><img data-side="right" alt="Right wrist camera"><figcaption>Right camera</figcaption></figure></div>';
document.body.append(panel);panel.hidden=true;
const photo=panel.querySelector('.live-overhead img'),wrists=panel.querySelector('.live-wrists');
const dialog=document.createElement('dialog');dialog.className='live-camera-dialog';dialog.innerHTML='<div class="dialog-head"><span class="micro">LIVE PHYSICAL TABLE</span><button aria-label="Close live camera">×</button></div><img alt="Live overhead camera enlarged"><p>Camera pixels, not a generated card face. Unknown objects never update a hand total.</p>';document.body.append(dialog);
panel.querySelector('button').onclick=()=>dialog.showModal();dialog.querySelector('button').onclick=()=>dialog.close();
let activeUntil=0,lastFrame=0,enabled=false;
const toggle=document.createElement('button');toggle.className='outline';toggle.textContent='Show live camera';document.getElementById('details').append(toggle);
toggle.onclick=()=>{enabled=!enabled;toggle.textContent=enabled?'Hide live camera':'Show live camera';panel.hidden=!enabled||!window.cameraViewing;};
window.addEventListener('camera-view-mode',()=>{panel.hidden=!enabled||!window.cameraViewing;});
window.addEventListener('camera-tracking-frame',({detail:d})=>{if(d.frame_image){photo.src=d.frame_image.src;if(dialog.open)dialog.querySelector('img').src=d.frame_image.src;lastFrame=performance.now();}panel.classList.toggle('stale',!d.fresh);});
window.addEventListener('measured-arm-motion',()=>{activeUntil=performance.now()+3500;});
const busy={left:false,right:false};
setInterval(()=>{if(document.hidden||!enabled||!window.cameraViewing)return;panel.classList.toggle('stale',performance.now()-lastFrame>600);const active=performance.now()<activeUntil;wrists.hidden=!active;if(!active)return;
 for(const image of wrists.querySelectorAll('img')){const side=image.dataset.side;if(busy[side])continue;busy[side]=true;image.onload=image.onerror=()=>{busy[side]=false;};image.src=base+'/live-image?camera='+side+'&t='+Date.now();}
},200);
