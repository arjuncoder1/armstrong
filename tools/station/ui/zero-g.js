// Zero-G buttons for Manifest's Torque menu (arm-cooling.js): one per arm, next to its Torque switch.
// Zero-G = weightless hand guiding: the arm carries its own weight, moves with a light push, and stays where you let go.
// Talks to /v1/arms/freedrive {arm, on} -> station tools/station/free_drive.py. Teaching's hand guidance uses it too.
(() => {
  if (window.__zeroG) return;
  window.__zeroG = true;
  const style = document.createElement('style');
  style.textContent = `#torque-menu .zg{min-width:86px;margin-left:6px;font-weight:600;border-radius:99px;padding:5px 10px;border:1px solid var(--line,#ffffff18);cursor:pointer;background:#33294a;color:#eadfff}
#torque-menu .zg.on{background:#7c4ddb;color:#fff;box-shadow:0 0 0 2px #b394ff55}`;
  document.head.append(style);
  let Z = {active: [], why: {}}, busy = false;
  const menu = () => document.getElementById('torque-menu');
  const say = (t, c) => { const m = menu() && menu().querySelector('[data-msg]'); if (m) { m.textContent = t; m.style.color = c || 'var(--muted,#a5a5a5)'; } };

  function paint() {
    const m = menu();
    if (!m) return;
    m.querySelectorAll('.tq-row').forEach(row => {
      const sw = row.querySelector('[data-toggle]');
      if (!sw) return;
      const side = sw.dataset.toggle;
      let b = row.querySelector('.zg');
      if (!b) { b = document.createElement('button'); b.className = 'zg'; b.dataset.zg = side; sw.after(b); }
      const on = (Z.active || []).includes(side);
      b.classList.toggle('on', on);
      const txt = on ? 'Zero-G ON' : 'Zero-G';
      if (b.textContent !== txt) b.textContent = txt;  // unchanged text: no mutation, so the observer does not loop
      b.title = on ? 'Back to a stiff hold where it is' : 'Weightless: it carries its own weight, move it by hand, it stays where you let go';
    });
  }

  async function load() {
    try {
      const d = await (await fetch('/v1/arms/state')).json();
      if (d && d.free_drive) Z = d.free_drive;
    } catch (e) { /* the Torque menu shows station errors */ }
    paint();
  }

  document.addEventListener('click', async e => {
    const b = e.target.closest && e.target.closest('#torque-menu .zg');
    if (!b || busy) return;
    e.preventDefault(); e.stopPropagation();
    const side = b.dataset.zg, on = !(Z.active || []).includes(side);
    busy = true; say(on ? `Zero-G ${side}: engaging, keep a hand near it…` : `Zero-G ${side}: back to hold…`);
    try {
      const r = await fetch('/v1/arms/freedrive', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({arm: side, on})});
      const d = await r.json().catch(() => ({}));
      if (d.free_drive) Z = d.free_drive;
      say(r.ok ? (on ? `${side} arm is weightless. Move it by hand; it stays where you let go.` : `${side} arm holding stiff where it is.`)
               : (d.error || 'HTTP ' + r.status), r.ok ? 'var(--green,#7bdd98)' : 'var(--red,#f49898)');
    } catch (err) { say(String(err), 'var(--red,#f49898)'); }
    busy = false; load();
  }, true);

  const hook = () => {
    const m = menu();
    if (!m) return setTimeout(hook, 500);
    new MutationObserver(paint).observe(m, {childList: true, subtree: true});
    m.addEventListener('toggle', () => { if (m.open) load(); });
    setInterval(() => { if (m.open && !busy) load(); }, 2000);
    paint();
  };
  hook();
})();
