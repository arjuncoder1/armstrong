// "Torque" menu for Manifest's live UI, next to CV Teleop / View in .bottom-tools: per-arm torque on/off (rest,
// free drive), both on/off, and which arm Manifest uses. Same <details class="popover"> pattern as the View menu.
// Talks to Manifest's /v1/arms/* routes (patch_manifest_arm_pane.py) -> station add-on tools/station/arm_rest.py.
// MakerArms have no brakes and no gravity compensation: an arm with torque off goes LIMP.
(() => {
  if (window.__armTorqueMenu) return;
  window.__armTorqueMenu = true;
  const tools = document.querySelector('.bottom-tools');
  if (!tools) return;
  const css = `
#torque-menu .popover-content{min-width:290px;padding:12px}
#torque-menu .tq-row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:6px 0;border-bottom:1px solid var(--line,#ffffff18)}
#torque-menu .tq-arm{text-transform:capitalize;font-weight:600}
#torque-menu .tq-temp{font-variant-numeric:tabular-nums;color:var(--muted,#a5a5a5);font-size:12px}
#torque-menu .tq-sw{min-width:92px;font-weight:600;border-radius:99px;padding:5px 10px;border:1px solid var(--line,#ffffff18);cursor:pointer}
#torque-menu .tq-sw.on{background:#2f6b45;color:#e9fff0}#torque-menu .tq-sw.off{background:#2c3a55;color:#dfe8ff}
#torque-menu .tq-sw.lock{background:#5a4a24;color:#ffeccc}
#torque-menu .tq-line{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:8px;font-size:12px;color:var(--muted,#a5a5a5)}
#torque-menu .tq-line button{border-radius:99px;padding:4px 10px;border:1px solid var(--line,#ffffff18);cursor:pointer}
#torque-menu .tq-line button.cur{outline:2px solid var(--green,#7bdd98)}
#torque-menu label{display:flex;gap:6px;align-items:flex-start;font-size:11px;color:var(--muted,#a5a5a5);margin-top:8px}
#torque-menu .tq-msg{min-height:15px;font-size:11px;margin-top:6px}
#torque-menu .tq-note{font-size:11px;color:var(--amber,#e3b47c);margin:2px 0 4px}
#torque-menu summary .tq-dot{display:none;width:7px;height:7px;border-radius:50%;background:var(--amber,#e3b47c);margin-left:6px;vertical-align:middle}
#torque-menu.tq-alert summary .tq-dot{display:inline-block}`;
  const style = document.createElement('style');
  style.textContent = css;
  document.head.append(style);
  const menu = document.createElement('details');
  menu.id = 'torque-menu';
  menu.className = 'popover';
  menu.innerHTML = `<summary class="small-button" title="Turn arm motors off to cool them, or free drive by hand">⏻ &nbsp;Torque<span class="tq-dot"></span></summary>
    <div class="popover-content"><div data-arms></div>
    <div class="tq-line" data-both></div><div class="tq-line" data-use></div>
    <label><input type="checkbox" data-ok> The arm I turn off is supported, or I'm holding it: no brakes, it drops.</label>
    <div class="tq-msg" data-msg></div></div>`;
  tools.append(menu);
  const q = sel => menu.querySelector(sel);
  const say = (t, c) => { q('[data-msg]').textContent = t; q('[data-msg]').style.color = c || 'var(--muted,#a5a5a5)'; };
  let S = null, busy = false;

  async function post(kind, body, needsOk) {
    if (busy) return;
    if (needsOk && !q('[data-ok]').checked) { say('Tick the box first: the arm goes limp.', 'var(--red,#f49898)'); return; }
    busy = true; say('Working…');
    try {
      const r = await fetch('/v1/arms/' + kind, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      const d = await r.json().catch(() => ({}));
      say(r.ok ? 'Done.' : (d.error || 'HTTP ' + r.status), r.ok ? 'var(--green,#7bdd98)' : 'var(--red,#f49898)');
    } catch (e) { say(String(e), 'var(--red,#f49898)'); }
    busy = false; load();
  }

  function render() {
    if (!S || S.error) { q('[data-arms]').textContent = 'Station unavailable: ' + ((S && S.error) || 'no data'); return; }
    const R = S.arm_rest || {}, resting = R.resting || [], locked = R.locked || [];
    const auto = R.auto || {}, notes = auto.notices || {}, autoOff = auto.rested || [];
    menu.classList.toggle('tq-alert', Object.keys(notes).length > 0 || autoOff.length > 0);
    menu.querySelector('summary').title = Object.values(notes).join('\n') || (autoOff.length ? `Auto-rested: ${autoOff.join(', ')} (torque off at rest pose)` : 'Turn arm motors off to cool them, or free drive by hand');
    q('[data-arms]').innerHTML = ['left', 'right'].map(side => {
      const off = resting.includes(side), lk = locked.includes(side), t = S.temps[side] || [];
      const max = t.length ? Math.max(...t) : '–';
      const cls = off ? 'off' : lk ? 'lock' : 'on', text = off ? (autoOff.includes(side) ? 'OFF · auto' : 'Torque OFF') : lk ? 'ON · locked' : 'Torque ON';
      return `<div class="tq-row"><span><span class="tq-arm">${side}</span> <span class="tq-temp">${max}°C max</span></span>
        <button class="tq-sw ${cls}" data-toggle="${side}" data-off="${off}" title="${off ? 'Turn torque on: holds where it is' : 'Turn torque off: the arm goes limp (rest / free drive)'}">${text}</button></div>`
        + (notes[side] ? `<div class="tq-note">⚠ ${notes[side]}</div>` : '')
        + (autoOff.includes(side) ? `<div class="tq-note" style="color:var(--muted,#a5a5a5)">Auto-rested at its rest pose after ${Math.round((auto.idle_s || 60))} s idle; an action wakes it.</div>` : '');
    }).join('');
    q('[data-both]').innerHTML = `Both: <button data-act="rest">off</button><button data-act="wake">on</button>`;
    if (!('locked' in R)) { q('[data-use]').innerHTML = ''; return; }  // station without Lock mode yet
    const cur = locked.length === 0 ? 'both' : locked.length === 1 ? (locked[0] === 'left' ? 'right' : 'left') : '';
    q('[data-use]').innerHTML = 'Manifest uses: ' + ['left', 'right', 'both']
      .map(a => `<button data-use="${a}" class="${cur === a ? 'cur' : ''}">${a}</button>`).join('');
  }

  menu.addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.toggle) {
      const side = b.dataset.toggle;
      if (b.dataset.off === 'true') post('wake', {arm: side});
      else post('rest', {arm: side, confirm_supported: true}, true);
    } else if (b.dataset.act === 'rest') post('rest', {arm: 'both', confirm_supported: true}, true);
    else if (b.dataset.act === 'wake') post('wake', {arm: 'both'});
    else if (b.dataset.use) post('use', {arm: b.dataset.use});
  });

  async function load() {
    try { const r = await fetch('/v1/arms/state'); S = await r.json(); if (!r.ok && !S.error) S = {error: 'HTTP ' + r.status}; }
    catch (e) { S = {error: String(e)}; }
    render();
  }
  menu.addEventListener('toggle', () => { if (menu.open) load(); });
  setInterval(() => { if (menu.open && !busy) load(); }, 2000);  // fast while open
  setInterval(() => { if (!menu.open && !busy) load(); }, 10000);  // slow while closed: keeps the notice dot current
  load();
})();
