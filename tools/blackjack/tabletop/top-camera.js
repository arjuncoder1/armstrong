// Actual overhead observations, kept separate from anonymous dealt-card events.
const base=`${location.protocol}//${location.hostname}:8204`;
const button=document.createElement('button');button.className='camera-readout';button.textContent='Overhead · reading cards…';button.setAttribute('aria-label','Show actual cards read by overhead camera');
document.getElementById('details').append(button);
const readReason=document.createElement('div');readReason.className='camera-read-reason';readReason.setAttribute('role','status');document.getElementById('details').append(readReason);
const dialog=document.createElement('dialog');dialog.className='camera-scan';
dialog.innerHTML='<div class="dialog-head"><span class="micro">ACTUAL OVERHEAD VIEW</span><button aria-label="Close camera view">×</button></div><h2>Overhead card reads.</h2><div class="scan-photo"><img alt="The exact overhead frame used to read these cards"><div class="scan-markers"></div></div><div class="scan-cards"></div><p class="scan-status"></p><p class="muted">These are camera suggestions: small or occluded ranks can be misread. Hand totals update only after the matching deal is verified, or you inspect and confirm its card.</p><button class="outline scan-again">Read overhead again</button>';
document.body.append(dialog);
let result=null,polling=false,nextScan=0;
window.cameraViewing=true;window.transferReplay=false;
window.cameraReadStatus='reading';document.body.classList.add('camera-mode');

const sourceToggle=document.createElement('button');sourceToggle.className='camera-source-toggle';sourceToggle.textContent='Practice table →';document.getElementById('details').append(sourceToggle);
const transferButton=document.createElement('button');transferButton.className='transfer-replay';transferButton.hidden=true;document.getElementById('details').append(transferButton);
transferButton.onclick=()=>{window.transferReplay=!window.transferReplay;updateView();};
function updateView(){if(!['left','right','both'].includes(result?.transfer?.holder))window.transferReplay=false;window.blackjackView?.observe(result,window.cameraViewing,window.transferReplay);transferButton.hidden=!window.cameraViewing||!['left','right','both'].includes(result?.transfer?.holder);transferButton.textContent=window.transferReplay?'Return to live arm pose →':'View '+(result?.transfer?.holder==='both'?'shared-grip':result?.transfer?.holder+'-held')+' snapshot →';document.body.classList.toggle('camera-mode',window.cameraViewing);sourceToggle.textContent=window.cameraViewing?'Practice table →':'Actual camera cards →';window.dispatchEvent(new Event('camera-view-mode'));}
sourceToggle.onclick=()=>{window.cameraViewing=!window.cameraViewing;window.transferReplay=false;updateView();if(window.cameraViewing)scan();};
const status=dialog.querySelector('.scan-status'),photo=dialog.querySelector('img'),chips=dialog.querySelector('.scan-cards'),markers=dialog.querySelector('.scan-markers');
button.onclick=()=>{dialog.showModal();if(!result||Date.now()/1000-result.captured_at>20)scan();};
dialog.querySelector('.dialog-head button').onclick=()=>dialog.close();
dialog.querySelector('.scan-again').onclick=()=>scan();
function show(data){
 if(data.error){window.cameraReadStatus='read unavailable';button.textContent='Overhead · card read unavailable';status.textContent=data.error;readReason.textContent=data.error;photo.hidden=true;chips.replaceChildren();markers.replaceChildren();result=null;updateView();return;}
 if(data.result){
  const r=data.result,age=Math.max(0,Math.floor(Date.now()/1000-r.captured_at));
  window.cameraReadStatus=age>30?'old read · '+age+'s':r.uncertain&&!r.cards.length?'card unreadable':data.active?'reading':r.cards.length+' card'+(r.cards.length===1?'':'s');
  readReason.textContent=r.uncertain&&!r.cards.length?r.reason:'';
  button.textContent='Overhead · '+(r.cards.map(c=>c.rank+c.suit).join('  ')||'no readable cards')+(data.active?' · reading…':` · ${age}s ago`);
  if(result?.scan_id!==r.scan_id){
   result=r;photo.src=base+'/image?id='+encodeURIComponent(r.scan_id);photo.hidden=false;chips.replaceChildren();markers.replaceChildren();
   r.cards.forEach((c,i)=>{const chip=document.createElement('button');chip.className='outline';chip.textContent=c.rank+' '+c.suit;chip.title=c.evidence;
    chip.onclick=()=>{if(Date.now()/1000-r.captured_at>30){status.textContent='That photograph is old. Read the overhead camera again first.';return;}const operator=document.getElementById('operator');if(operator?.open){document.getElementById('rank').value=c.rank;document.getElementById('suit').value=c.suit;document.getElementById('checked').checked=false;document.getElementById('rank').dispatchEvent(new Event('change'));dialog.close();}};
    chips.append(chip);const label=document.createElement('span');label.textContent=c.rank+c.suit;label.style.left=(c.x*100)+'%';label.style.top=(c.y*100)+'%';markers.append(label);});
  }
  updateView();
  const t=r.transfer||{};const transferText=['left','right','both'].includes(t.holder)?` Card held by ${t.holder.toUpperCase()}${t.rank?' · '+t.rank+(t.suit||''):' · face unreadable'}.`:(t.holder==='none'?' No held card observed.':' Transfer ownership unknown.');
  status.textContent=`${transferText} Top-camera photograph, ${age}s ago. ${r.uncertain?'Some cards are uncertain. ':''}${r.reason}`;
}else if(data.active){window.cameraReadStatus='reading';updateView();button.textContent='Overhead · reading actual cards…';status.textContent='Reading a fresh overhead photograph. No arms are being commanded.';readReason.textContent='Reading the overhead camera…';}
}
async function poll(){if(polling)return;polling=true;try{const response=await fetch(base+'/state');if(!response.ok)throw Error('Reader unavailable');const data=await response.json();show(data);}catch{window.cameraReadStatus='reader offline';window.dispatchEvent(new Event('camera-view-mode'));button.textContent='Overhead · reader offline';status.textContent='The overhead reader is unavailable; no card was guessed.';}finally{polling=false;}}
async function scan(){if(Date.now()<nextScan)return;nextScan=Date.now()+10000;try{const response=await fetch(base+'/scan',{method:'POST'});if(!response.ok)throw Error('Reader unavailable');show(await response.json());}catch{button.textContent='Overhead · reader offline';status.textContent='The overhead reader is unavailable; no card was guessed.';}}
window.addEventListener('blackjack-scene-ready',updateView);
scan();setInterval(()=>{if(!document.hidden)poll();},2500);
setInterval(()=>{if(!document.hidden&&(window.cameraViewing||dialog.open||document.getElementById('operator')?.open))scan();},10000);
