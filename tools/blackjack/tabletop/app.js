import {createScene} from './scene.js';
import './top-camera.js';
import './foley.js';
const $=id=>document.getElementById(id);
let game=null,view=null,busy=false,drawing=false,bet=2500,operatorToken=null,dismissedToken=null;
const dollars=v=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:v%100?2:0}).format(v/100);
async function json(url,body){const r=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d;}
function report(message){$('error').textContent=message||'';$('error').hidden=!message;}
function cardsText(cards){return cards.map(c=>`${c.rank}${c.suit}`).join('  ');}
function render(){
 if(!game)return;
 const amount=(game.bankroll/100).toFixed(2).split('.');$('bankroll').replaceChildren(document.createTextNode('$'+Number(amount[0]).toLocaleString()));const cents=document.createElement('span');cents.textContent='.'+amount[1];$('bankroll').append(cents);
 $('details-bankroll').textContent=dollars(game.bankroll);$('details-result').textContent=game.message;
 $('remaining').textContent=game.shoe.remaining;$('round-label').textContent=game.round?'ROUND '+String(game.round).padStart(2,'0'):'ROUND —';
 $('dealer-total').textContent=game.dealer.cards.length?game.dealer.score.total+(game.dealer.score.soft?' soft':''):'—';$('dealer-accessible').textContent=cardsText(game.dealer.cards);
 const labels=game.hands.map((h,i)=>{const el=document.createElement('div');el.className='hand-label'+(i===game.active&&game.phase==='player'?' active':'');const name=document.createElement('span');name.textContent=game.hands.length>1?'HAND '+(i+1):'YOUR HAND';const total=document.createElement('strong');total.textContent=h.cards.length?h.score.total+(h.score.soft?' soft':''):'—';const detail=document.createElement('div');detail.className='accessible-cards';detail.textContent=cardsText(h.cards);const result=document.createElement('div');result.className='accessible-cards';result.textContent=dollars(h.bet)+(h.result?' · '+h.result:'');el.append(name,total,detail,result);return el;});$('player-labels').replaceChildren(...labels);
 $('empty-invitation').hidden=!!game.round;
 $('message').textContent=window.cameraViewing?(window.transferReplay?'Camera transfer snapshot · attachment schematic':'Actual card reads · live measured arms'):game.physical?.active?game.physical.message:game.message;
 const waiting=!!game.pending;const open=['betting','settled'].includes(game.phase);const locked=busy||drawing||!!game.physical?.active||window.cameraViewing===true;
 for(const action of ['hit','stand','double','split'])$(action).disabled=locked||!game.actions.includes(action);
 $('deal').hidden=false;$('deal').disabled=locked||!open||!game.actions.includes('deal')||bet>game.bankroll;
 $('deal').firstChild.textContent=game.round?'Deal again ':'Deal ';
 for(const id of ['less','more','bet'])$(id).disabled=locked||!open;
 $('chips').hidden=!open;
 for(const chip of $('chips').querySelectorAll('button')){chip.classList.toggle('selected',Number(chip.dataset.bet)*100===bet);chip.disabled=locked||!open;}
 $('details-button').firstChild.textContent=(window.cameraViewing?'Camera · '+(window.cameraReadStatus||'reading'):game.mode==='practice'?'Practice':'Observation')+' · movement off ';
 $('mode-note').textContent=window.cameraViewing?(window.transferReplay?'Capture-time arm pose · card attachment schematic':'Camera-read cards · live arm pose · no scoring'):game.mode==='practice'?'Practice animation · Movement disabled':'Physical observations · Movement disabled';
 $('running-count').textContent=game.running_count;$('true-count').textContent=game.true_count?.toFixed(1)??'—';$('cut-status').textContent=game.shoe.cut_reached?'Reached · shuffle after this round':'At '+game.shoe.cut_at+' cards remaining';
 $('mode').textContent=game.mode==='practice'?'Operator observation mode':'Return to practice';$('mode').disabled=$('shuffle').disabled=!open||locked;
 if(view)view.sync(game);
 if(game.mode==='observe'&&waiting&&(!game.physical?.enabled||game.physical.phase==='needs_operator')){
  if(operatorToken!==game.pending.id){operatorToken=game.pending.id;dismissedToken=null;$('rank').value=$('suit').value='';$('checked').checked=false;$('card-text').value='';$('operator-camera').src='/api/camera/top?t='+Date.now();}
  $('operator-reason').textContent=game.pending.reason||'Waiting for camera confirmation. Live dealing is not enabled; an operator may record an already dealt physical card.';
  if(!$('operator').open&&dismissedToken!==operatorToken)$('operator').showModal();
 }else if($('operator').open)$('operator').close();
 const gate=game.camera_gate;$('camera-prepare').disabled=locked||!gate||gate.busy||!waiting;
 $('camera-verify').disabled=locked||!gate?.baseline_ready||gate.busy;
 $('camera-gate-status').textContent=gate?.message||'Camera verification is unavailable. Operator confirmation is still available.';
 $('confirm-card').disabled=locked||!$('rank').value||!$('suit').value||!$('checked').checked;
}
async function action(name,extra={}){
 if(busy||drawing||!game||window.cameraViewing)return;busy=true;report('');render();
 try{game=await json('/api/action',{action:name,revision:game.revision,...extra});}
 catch(e){report(e.message);try{game=await json('/api/game');}catch{}}
 finally{busy=false;render();if(game?.mode==='practice'&&game.pending)drawQueue();}
}
async function drawQueue(){
 if(drawing||busy||!game?.pending||game.mode!=='practice')return;drawing=true;render();
 try{
  while(game.pending&&game.mode==='practice'){
   game=await json('/api/action',{action:'draw',revision:game.revision,token:game.pending.id});render();
   await new Promise(resolve=>setTimeout(resolve,100));
   while(view?.busy)await new Promise(resolve=>setTimeout(resolve,40));
  }
 }catch(e){report(e.message);try{game=await json('/api/game');}catch{}}
 finally{drawing=false;render();}
}
$('deal').onclick=()=>action('deal',{bet});for(const a of ['hit','stand','double','split'])$(a).onclick=()=>action(a);
function setBet(value){if(!Number.isFinite(value))return;bet=Math.min(10000,Math.max(500,Math.round(value/500)*500));$('bet').value=bet/100;render();}
$('bet').onchange=()=>setBet(Number($('bet').value)*100);$('less').onclick=()=>setBet(bet-500);$('more').onclick=()=>setBet(bet+500);
for(const chip of $('chips').querySelectorAll('button'))chip.onclick=()=>setBet(Number(chip.dataset.bet)*100);
$('details-button').onclick=()=>$('details').showModal();$('close-details').onclick=()=>$('details').close();
$('mode').onclick=()=>{if(confirm('Switch mode and start a new six-deck shoe and virtual bankroll? No arms will move.')){const mode=game.mode==='practice'?'observe':'practice';$('details').close();action('mode',{mode});}};
$('shuffle').onclick=()=>{if(confirm(game.mode==='observe'?'Confirm that you physically shuffled and cut the shoe.':'Shuffle a fresh six-deck practice shoe?'))action('shuffle',{checked:true});};
$('operator-camera').onerror=()=>{$('camera-message').textContent='Camera unavailable. Do not infer a card from this view.';$('operator-camera').hidden=true;};
$('operator-camera').onload=()=>{$('operator-camera').hidden=false;$('camera-message').textContent='Current top-camera view. Confirm only the pending physical card.';};
for(const id of ['rank','suit','checked'])$(id).onchange=()=>render();
$('card-text').oninput=()=>{const match=$('card-text').value.trim().toUpperCase().match(/^(10|[2-9AJQKT])\s*([SHDC♠♥♦♣])$/);if(match){$('rank').value=match[1]==='T'?'10':match[1];$('suit').value=({S:'♠',H:'♥',D:'♦',C:'♣'})[match[2]]||match[2];}else{$('rank').value='';$('suit').value='';}render();};
$('camera-prepare').onclick=()=>action('camera_prepare',{token:game.pending.id});
$('camera-verify').onclick=()=>action('camera_verify',{token:game.pending.id});
$('confirm-card').onclick=()=>action('confirm',{token:game.pending.id,rank:$('rank').value,suit:$('suit').value,checked:$('checked').checked});
$('close-operator').onclick=()=>{dismissedToken=operatorToken;$('operator').close();};$('operator').addEventListener('cancel',()=>{dismissedToken=operatorToken;});
$('message').onclick=()=>{if(game?.mode==='observe'&&game.pending){dismissedToken=null;render();}};
window.addEventListener('camera-view-mode',()=>{render();if(!window.cameraViewing&&game?.pending&&game.mode==='practice')drawQueue();});
window.addEventListener('pose-stale',()=>{$('pose-status').textContent='Pose stale · arm model hidden';$('pose-light').style.background='#806d51';});
async function telemetry(){
 if(!document.hidden){try{const data=await json('/api/telemetry');view?.pose(data);$('pose-status').textContent=window.transferReplay?'Camera snapshot · capture-time arm pose':data.fresh?'Measured joint pose':'Pose unavailable · arm model hidden';$('pose-light').style.background=data.fresh?'#8f9b79':'#806d51';const temps=Object.values(data.measured||{}).flatMap(m=>m.motor_temps_c||[]).filter(Number.isFinite);$('temperature').textContent=temps.length?Math.max(...temps).toFixed(0)+' °C':'Unknown';}catch{view?.pose({fresh:false});$('pose-status').textContent='Station disconnected';}}
 setTimeout(telemetry,400);
}
try{game=await json('/api/game');render();}catch(e){report(e.message);}
try{view=await createScene($('scene'));render();window.blackjackView=view;window.dispatchEvent(new Event('blackjack-scene-ready'));}catch(e){$('scene-failure').hidden=false;console.error(e);}
telemetry();if(!window.cameraViewing&&game?.pending&&game.mode==='practice')drawQueue();
setInterval(async()=>{if(!busy&&!drawing&&!document.hidden){try{const next=await json('/api/game');if(next.revision!==game?.revision){game=next;render();if(!window.cameraViewing&&game.pending&&game.mode==='practice')drawQueue();}}catch(e){report('Connection lost. '+e.message);}}},2000);
