/* Page Paramètres : seule page qui interroge le serveur (état des canaux, tests, import). */
'use strict';
(() => {
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const SEV = { critical: 'Critique', major: 'Élevée', minor: 'À surveiller', info: 'Info' };
  const local = location.protocol === 'file:';
  const status = (ok, label) => `<span class="badge ${ok ? 'ok' : 'trunc'}">${ok ? '✓ ' : ''}${esc(label)}</span>`;
  const kv = (rows) => '<dl class="kv">' + rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v ?? '–'}</dd>`).join('') + '</dl>';

  async function channels() {
    const el = document.getElementById('channels');
    if (local) { el.innerHTML = '<div class="card" style="flex:1"><span class="muted">Ouvrir le tableau de bord via le serveur (cvm-monitor dashboard) pour gérer les canaux et importer.</span></div>'; return; }
    try {
      const r = await fetch('api/v1/settings/alerts');
      if (!r.ok) throw new Error(r.status);
      const s = await r.json();
      const t = s.teams, m = s.email;
      el.innerHTML = `
        ${channel('Microsoft Teams', 'teams', t, [['Webhook', esc(t.webhook_host || '–')], ['Seuil', sev(t.min_severity)], ['Alertes par carte', esc(t.max_items)]])}
        ${channel('E-mail', 'email', m, [['Mode', esc(m.backend)], ['Serveur', esc(`${m.smtp_host || '–'}:${m.smtp_port || ''}`)], ['Expéditeur', esc(m.sender || '–')], ['Destinataires', esc((m.recipients || []).join(', ') || '–')], ['Seuil', sev(m.min_severity)]])}`;
      el.querySelectorAll('[data-test]').forEach((b) => b.addEventListener('click', () => test(b)));
    } catch (e) {
      el.innerHTML = `<div class="card" style="flex:1"><div class="callout bad">Configuration des canaux illisible (${esc(e.message)}).</div></div>`;
    }
  }

  const sev = (s) => `<span class="sev ${esc(s)}">${esc(SEV[s] || s)} et plus</span>`;
  /** Carte d'un canal : état (configuré / à compléter), paramètres, ce qui manque, bouton de test. */
  function channel(title, key, c, rows) {
    const missing = c.missing || [];
    return `<div class="card" style="flex:1 1 520px;${c.configured ? '' : 'border-color:var(--warn-line)'}"><div class="head"><div class="head-l"><h2>${title}</h2></div><div class="head-r">${status(c.configured, c.configured ? 'Configuré' : 'À compléter')}${c.enabled ? '' : ' ' + status(false, 'Désactivé')}</div></div>
      ${missing.length ? `<div class="callout" style="margin-bottom:14px;background:#fff8f1">MISSING_VAR : ${esc(missing.join(', '))}.</div>` : ''}
      ${kv(rows)}
      <div style="margin-top:16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap"><button class="btn primary" data-test="${key}" ${c.configured ? '' : 'disabled'}>Envoyer un message de test</button><span class="small" data-out="${key}" role="status"></span></div></div>`;
  }

  async function test(btn) {
    const ch = btn.dataset.test, out = document.querySelector(`[data-out=${ch}]`);
    btn.disabled = true;
    out.textContent = 'Envoi en cours…';
    try {
      const r = await fetch(`api/v1/settings/alerts/test/${ch}`, { method: 'POST' });
      if (r.status === 429) throw new Error("Un test vient d'être envoyé : patientez quelques secondes.");
      const res = await r.json();
      out.innerHTML = `${status(res.ok, res.ok ? 'envoyé' : 'échec')} ${esc(res.message)}`;
    } catch (e) {
      out.innerHTML = `${status(false, 'échec')} ${esc(e.message)}`;
    } finally { btn.disabled = false; }
  }

  async function upload(file) {
    const out = document.getElementById('import-status'), input = document.getElementById('file');
    if (local) { out.innerHTML = '<div class="callout bad">Import impossible en lecture locale.</div>'; return; }
    input.disabled = true;
    out.innerHTML = `Envoi de ${esc(file.name)}…`;
    try {
      const body = new FormData();
      body.append('file', file);
      const notify = document.getElementById('notify').checked;
      const r = await fetch(`api/v1/import?notify=${notify}`, { method: 'POST', body });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
      const { job_id } = await r.json();
      out.innerHTML = 'Traitement en cours : lecture, détection, régénération du tableau de bord…';
      for (;;) {
        await new Promise((res) => setTimeout(res, 1000));
        const s = await (await fetch(`api/v1/import/${job_id}`)).json();
        if (s.state === 'done') {
          out.innerHTML = `<div class="callout info" style="background:var(--good-bg);color:var(--good)">${esc(s.summary)}</div><p style="margin:12px 0 0"><a class="btn primary" href="index.html#alertes">Voir le tableau de bord</a></p>`;
          break;
        }
        if (s.state === 'error') throw new Error(s.error);
      }
    } catch (e) {
      out.innerHTML = `<div class="callout bad">${esc(e.message)}</div>`;
    } finally { input.disabled = false; input.value = ''; }
  }

  document.getElementById('file').addEventListener('change', (ev) => ev.target.files[0] && upload(ev.target.files[0]));
  // Glisser-déposer sur la zone d'import
  const drop = document.getElementById('drop');
  ['dragenter', 'dragover'].forEach((t) => drop.addEventListener(t, (ev) => { ev.preventDefault(); drop.classList.add('over'); }));
  ['dragleave', 'drop'].forEach((t) => drop.addEventListener(t, () => drop.classList.remove('over')));
  drop.addEventListener('drop', (ev) => { ev.preventDefault(); const f = ev.dataTransfer.files[0]; if (f) upload(f); });
  channels();
})();
