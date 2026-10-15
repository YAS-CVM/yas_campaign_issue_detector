/* Onglet Alertes : « Que dois-je traiter et prévenir aujourd'hui ? »
 * Santé du flux NEON-dx, état des alertes, file de traitement (acquitter / sourdine / rouvrir), tendance, catalogue. */
'use strict';
(() => {
  const { F, esc, card, section, tile } = App;
  const SEV = ['critical', 'major', 'minor', 'info'];
  const SEV_FR = { critical: 'Critique', major: 'Majeure', minor: 'Mineure', info: 'Info' };
  const STATUS_FR = { open: 'Ouverte', ack: 'Acquittée', muted: 'Sourdine', resolved: 'Résolue' };
  const SCOPE_FR = { push: 'Push', im: 'Inbound', snapshot: 'Snapshots', feed: 'Flux NEON-dx' };
  const ENTITY_FR = { broadcast: 'Broadcast', bc_name: 'BC', campaign: 'Campagne', category: 'Catégorie', im_rule: 'Règle IM', touchpoint: 'Touchpoint',
    program: 'Programme', global: 'Global', column: 'Colonne', dataset: 'Jeu de données' };
  // PM-EXE-01 → EXE ; SNP-02 → SNP ; FEED-01 → FEED
  const FAMILY = (id) => { const p = id.split('-'); return p.length >= 3 ? p[1] : p[0]; };
  const FAMILY_FR = { EXE: 'Exécution', DLV: 'Livraison', PRF: 'Performance', FUL: 'Fulfillment', IMP: 'Impressions', DQ: 'Qualité des données', SNP: 'Snapshots', FEED: 'Flux NEON-dx' };
  const ACTION = {
    EXE: "Vérifier le broadcast dans NEON-dx : statut, fenêtre de blackout, file d'envoi. Relancer ou clôturer selon le cas.",
    DLV: "Vérifier la route SMS (opérateur, SMSC) et la remontée des accusés de réception (DLR) pour ce BC.",
    PRF: 'Revoir le ciblage, l\'offre ou le message ; comparer au groupe de contrôle (onglet Analytics › Incrémentalité).',
    FUL: "Vérifier le provisioning de l'offre (échecs d'activation) avec l'équipe IT / Flytxt.",
    IMP: "Vérifier l'éligibilité et l'affichage de la règle IM (statut, rafraîchissement, ciblage).",
    DQ: 'Signaler à Flytxt (NEON-dx) : donnée manquante ou incohérente dans le Daily Dashboard. Préciser la colonne, la date et le volume.',
    SNP: 'Comparer les deux fichiers concernés ; si la révision ou la disparition est inattendue, la signaler à Flytxt (préciser les broadcasts et le fichier de dernière apparition).',
    FEED: 'Signaler à Flytxt (NEON-dx) avec la date, la colonne ou le fichier concerné. Tant que la donnée manque, les chiffres concernés sont incomplets (n/r, tronqué ou disparu dans l\'interface).',
  };
  const latest = App.snaps.length ? App.snaps[App.snaps.length - 1] : null;
  const catalog = new Map((App.D.catalog || []).map((r) => [r.id, r]));
  const readOnly = location.protocol === 'file:';

  function filtered(st) {
    const status = st.status || 'active';
    const sevSel = st.sev ? [].concat(st.sev) : null;
    const ent = st.ent;
    const q = (st.q || '').toLowerCase();
    return App.anomalies.filter((a) => {
      if (status === 'active' && !(a.status === 'open' || a.status === 'ack')) return false;
      if (status !== 'active' && status !== 'all' && a.status !== status) return false;
      if (sevSel && !sevSel.includes(a.severity)) return false;
      if (st.scope && a.scope !== st.scope) return false;
      if (st.fam && FAMILY(a.rule_id) !== st.fam) return false;
      if (st.rule && a.rule_id !== st.rule) return false;
      if (st.since === 'new' && a.first_seen_at !== latest?.snapshot_date) return false;
      if (st.since === 'resolved' && a.resolved_at !== latest?.snapshot_date) return false;
      if (ent) {
        const [type, ...k] = ent.split(':'), key = k.join(':');
        const direct = a.entity_type === type && String(a.entity_key) === key;
        const viaBroadcast = type === 'broadcast' && (a.details?.broadcast_ids || []).map(String).includes(key);
        if (!direct && !viaBroadcast) return false;
      }
      if (q && !`${a.rule_id} ${a.rule_name} ${a.entity_key} ${a.message} ${a.category || ''}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }

  function feedBlock() {
    const fh = App.feed();
    const last = fh.last;
    const shown = fh.signals.filter((x) => !x.hidden);
    const nWarn = shown.filter((s) => s.level !== 'info').length, nInfo = shown.length - nWarn;
    const nBad = shown.filter((s) => s.level === 'bad').length;
    const facts = last ? `<div class="grid tiles" style="margin-bottom:18px">
      ${tile({ label: 'Dernier fichier', value: `till ${F.dateFull(last.snapshot_date)}`, cls: fh.lag > 3 ? 't-bad' : fh.lag > 1 ? 't-warn' : '',
        sub: `<b style="color:${fh.lag > 3 ? 'var(--bad)' : fh.lag > 1 ? 'var(--warn)' : 'var(--good)'}">${fh.lag > 1 ? `reçu il y a ${fh.lag} jours` : 'à jour'}</b> · le ${F.dt(last.ingested_at)}` })}
      ${tile({ label: 'Couverture', value: `${F.date(last.date_min)} → ${F.date(last.date_max)}`, sub: `${F.int(last.push_rows)} lignes Push · ${F.int(last.im_rows)} lignes IM` })}
      ${tile({ label: 'Fichiers manquants', value: F.int(fh.missing.length), cls: fh.missing.length ? 't-warn' : '', sub: `depuis le ${F.dateFull(App.snaps[0].snapshot_date)} · ${App.snaps.length} reçus` })}
      ${tile({ label: 'Signaux', value: `${nWarn} <small>+ ${nInfo} info</small>`, sub: `${nBad} critique${nBad > 1 ? 's' : ''} · ${nWarn - nBad} à surveiller` })}
    </div>` : '';
    const feedAlerts = App.anomalies.filter((a) => (a.status === 'open' || a.status === 'ack') && /^(FEED|SNP)-/.test(a.rule_id))
      .sort((x, y) => App.SEV_RANK[y.severity] - App.SEV_RANK[x.severity] || (y.date || '').localeCompare(x.date || ''));
    const alertsHtml = feedAlerts.length ? `<h3 style="margin:0 0 10px">Alertes ouvertes sur le flux (${feedAlerts.length})</h3><div class="signals" style="margin-bottom:18px">${feedAlerts.slice(0, 8).map((a) =>
      `<div class="signal"><span><span class="sev ${a.severity}">${SEV_FR[a.severity]}</span></span><a href="#" data-open-drawer="alert:${a.id}"><span class="t">${esc(a.rule_id)} · ${esc(a.rule_name || '')}</span><span class="d">${esc(a.message)}</span></a></div>`).join('')}</div>${feedAlerts.length > 8 ? `<p class="small" style="margin:-8px 0 18px"><a href="#alertes?fam=FEED">Voir les ${feedAlerts.length} alertes du flux →</a></p>` : ''}` : '';
    const list = shown.length ? `<div class="signals">${shown.map((s) => `<div class="signal"><span>${App.levelPill(s.level)}</span><span><span class="t">${esc(s.title)}</span><span class="d">${esc(s.text)}</span></span></div>`).join('')}</div>`
      : '<div class="empty">Aucun signal : le flux NEON-dx est nominal.</div>';
    return facts + alertsHtml + `<h3 style="margin:0 0 10px">Signaux calculés sur les fichiers reçus ${App.help('Fraîcheur, fichiers manquants, lignes en baisse, remplissage des colonnes, fulfillment IM. Les signaux déjà portés par une alerte ouverte ne sont pas répétés.')}</h3>` + list;
  }

  function tiles(st) {
    const act = App.anomalies.filter((a) => a.status === 'open');
    const by = (s) => act.filter((a) => a.severity === s).length;
    const ld = latest?.snapshot_date;
    const nNew = App.anomalies.filter((a) => a.first_seen_at === ld && (a.status === 'open' || a.status === 'ack')).length;
    const nRes = App.anomalies.filter((a) => a.resolved_at === ld).length;
    const nAck = App.anomalies.filter((a) => a.status === 'ack').length, nMuted = App.anomalies.filter((a) => a.status === 'muted').length;
    const BG = { critical: ['#fbe3e3', '#9b1c1c', '#c62828'], major: ['#fdebdd', '#9a3b07', '#d9620b'], minor: ['#fff4bf', '#5c4600', '#c99a00'], info: ['#e7eefb', '#163e8c', '#3e6cc9'] };
    const sevTile = (s) => {
      const on = st.status === 'open' && [].concat(st.sev || []).join() === s && !st.since;
      const [bg, fg, dot] = BG[s];
      return `<button class="tile click ${on ? 'on' : ''}" data-set-many='${JSON.stringify(on ? { status: null, sev: null, since: null } : { status: 'open', sev: s, since: null })}' aria-pressed="${on}"
        style="background:${on ? '#0a2357' : bg};border-color:${on ? '#0a2357' : bg};color:${on ? '#fff' : fg}">
        <div class="lbl" style="color:inherit"><span style="width:10px;height:10px;border-radius:50%;background:${on ? '#fff' : dot}"></span>${SEV_FR[s]}s</div>
        <div class="val" style="font-size:34px">${F.int(by(s))}</div><div class="sub" style="color:inherit;opacity:.85;font-weight:600">${on ? '✓ filtre actif' : 'ouvertes'}</div></button>`;
    };
    const mini = (label, v, set, extra = '') => `<button class="tile click" data-set-many='${JSON.stringify(set)}' style="padding:14px 16px;gap:4px;background:#fff"><div class="lbl" style="font-size:12px;min-height:0">${label}</div><div class="val" style="font-size:22px">${F.int(v)}</div><div class="sub">${extra}</div></button>`;
    return `<div class="split">
      <div role="group" aria-label="Filtrer par sévérité" style="flex:999 1 640px;display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px">${SEV.map(sevTile).join('')}</div>
      <div style="flex:1 1 320px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px">
        ${mini('Nouvelles', nNew, { status: 'active', since: 'new', sev: null }, `fichier du ${F.date(ld)}`)}
        ${mini('Résolues', nRes, { status: 'resolved', since: 'resolved', sev: null }, `fichier du ${F.date(ld)}`)}
        ${mini('Acquittées', nAck, { status: 'ack', since: null, sev: null })}
        ${mini('En sourdine', nMuted, { status: 'muted', since: null, sev: null })}
      </div></div>`;
  }

  function filtersHtml(st) {
    const opt = (k, v, l) => `<button data-set="${k}" data-val="${v}" class="${(st[k] || '') === v ? 'on' : ''}">${l}</button>`;
    const rules = [...new Set(App.anomalies.map((a) => a.rule_id))].sort();
    const fams = [...new Set(App.anomalies.map((a) => FAMILY(a.rule_id)))].sort();
    return `<div class="fgroup"><div class="flbl">Statut</div><div class="seg">${opt('status', '', 'À traiter')}${opt('status', 'open', 'Ouvertes')}${opt('status', 'ack', 'Acquittées')}${opt('status', 'muted', 'Sourdine')}${opt('status', 'resolved', 'Résolues')}${opt('status', 'all', 'Toutes')}</div></div>
      <div class="fgroup"><div class="flbl">Sévérité</div><div class="seg">${opt('sev', '', 'Toutes')}${SEV.map((s) => opt('sev', s, SEV_FR[s])).join('')}</div></div>
      <div class="fgroup"><div class="flbl">Règles</div><select class="field" data-set="scope"><option value="">Périmètre : tous</option>${Object.entries(SCOPE_FR).map(([k, l]) => `<option value="${k}" ${st.scope === k ? 'selected' : ''}>${l}</option>`).join('')}</select>
      <select class="field" data-set="fam"><option value="">Famille : toutes</option>${fams.map((f) => `<option value="${f}" ${st.fam === f ? 'selected' : ''}>${FAMILY_FR[f] || f}</option>`).join('')}</select>
      <select class="field" data-set="rule"><option value="">Règle : toutes</option>${rules.map((r) => `<option value="${r}" ${st.rule === r ? 'selected' : ''}>${r} · ${esc(catalog.get(r)?.name || '')}</option>`).join('')}</select></div>
`;
  }

  /** Position de la valeur dans la distribution de référence (P5 / P50 / P95), à partir des détails de l'anomalie. */
  function position(a) {
    const d = a.details || {};
    if (d.p50 == null || a.value == null) return '';
    const pts = [d.p_low, d.p50, d.p_high, a.value].filter((x) => x != null);
    let lo = Math.min(...pts), hi = Math.max(...pts);
    if (hi === lo) hi = lo + 1;
    const X = (v) => ((v - lo) / (hi - lo)) * 100;
    const isRate = Math.abs(d.p50) <= 1.0001 && Math.abs(a.value) <= 1.5;
    const f = isRate ? F.pct : F.compact;
    return `<div class="pos" title="Valeur ${f(a.value)} · P${App.meta.percentiles.low} ${f(d.p_low)} · médiane ${f(d.p50)} · P${App.meta.percentiles.high} ${f(d.p_high)} (n = ${d.n ?? '?'})">
      <div class="rng" style="left:${X(d.p_low ?? d.p50)}%;width:${Math.max(1, X(d.p_high ?? d.p50) - X(d.p_low ?? d.p50))}%"></div>
      <div class="med" style="left:${X(d.p50)}%"></div><div class="val" style="left:${X(a.value)}%"></div></div>`;
  }

  const entityLabel = (a) => `<span class="faint small">${ENTITY_FR[a.entity_type] || a.entity_type}</span> ${esc(a.entity_key)}`;
  const ruleCell = (a) => `<span style="display:flex;flex-direction:column;min-width:0"><span class="small muted" style="font-weight:700">${esc(a.rule_id)}</span><span class="ell" style="max-width:230px;font-weight:600" title="${esc(a.rule_name || '')}">${esc(a.rule_name || '')}</span></span>`;
  const valueCell = (a) => (a.value == null ? '' : (Math.abs(a.value) <= 1.5 && /%|rate|ratio|Failure|Delivery|Ack|Conv/i.test(a.metric || '') ? F.pct(a.value) : F.compact(a.value)));

  function queue(el, st, list) {
    const columns = [
      { key: 'severity', label: 'Sévérité', sort: (a) => App.SEV_RANK[a.severity], csv: (a) => SEV_FR[a.severity] || a.severity, html: (a) => (a._children ? '' : `<span class="sev ${a.severity}">${SEV_FR[a.severity]}</span>`) },
      { key: 'rule_id', label: 'Règle', html: (a) => (a._children ? `<b>${esc(a._label)}</b> <span class="badge grey">${a._children.length}</span>` : ruleCell(a)), csv: (a) => `${a.rule_id} ${a.rule_name}` },
      { key: 'entity_key', label: 'Entité', html: (a) => (a._children ? '' : `<span class="ell" style="max-width:300px" title="${esc(a.entity_key)}">${entityLabel(a)}</span>`) },
      { key: 'category', label: 'Catégorie', html: (a) => esc(a.category || '') },
      { key: 'date', label: 'Date', fmt: (v, a) => (a._children ? '' : `<span class="nowrap">${F.date(v)}${a.details?.days?.length > 1 ? ` <span class="faint">(${a.details.days.length} j)</span>` : ''}</span>`) },
      { key: 'value', label: 'Valeur', num: true, html: valueCell },
      { key: 'pos', label: 'Position (P5 · médiane · P95)', export: false, sort: (a) => a.value, html: (a) => (a._children ? '' : position(a)) },
      { key: 'volume', label: 'Volume impacté', num: true, fmt: (v) => F.compact(v) },
      { key: 'first_seen_at', label: 'Depuis', fmt: (v, a) => (a._children ? '' : `${F.date(v)} <span class="faint">· ${a.occurrences}×</span>`) },
      { key: 'status', label: 'Statut', csv: (a) => STATUS_FR[a.status] || a.status, html: (a) => (a._children ? '' : `<span class="st ${a.status}">${STATUS_FR[a.status]}</span>`) },
      { key: 'last_notified_at', label: 'Notifiée', fmt: (v, a) => (a._children ? '' : v ? F.date(v) : '<span class="faint">non</span>') },
      ...(readOnly ? [] : [{ key: 'act', label: 'Action', sort: (a) => a.status, export: false, html: (a) => (a._children || !(a.status === 'open' || a.status === 'muted') ? ''
        : `<button class="btn sm" data-ack="${a.id}">${a.status === 'open' ? 'Acquitter' : 'Rouvrir'}</button>`) }]),
    ];
    let rows = list;
    if (st.group) {
      const g = new Map();
      for (const a of list) {
        const k = st.group === 'rule' ? a.rule_id : `${a.entity_type}:${a.entity_key}`;
        if (!g.has(k)) g.set(k, []);
        g.get(k).push(a);
      }
      rows = [...g.entries()].map(([k, ch]) => ({
        _key: 'g:' + k, _label: st.group === 'rule' ? `${k} · ${catalog.get(k)?.name || ''}` : `${ENTITY_FR[ch[0].entity_type] || ''} ${ch[0].entity_key}`,
        _children: ch, severity: ch.reduce((w, a) => (App.SEV_RANK[a.severity] > App.SEV_RANK[w] ? a.severity : w), 'info'),
        volume: ch.reduce((s, a) => s + (a.volume || 0), 0), rule_id: k, entity_key: ch[0].entity_key, category: '',
      }));
    }
    const groupSel = `<select class="field" data-local="group" title="Regroupement de cette liste uniquement"><option value="">Sans regroupement</option><option value="rule" ${st.group === 'rule' ? 'selected' : ''}>Grouper par règle</option><option value="entity" ${st.group === 'entity' ? 'selected' : ''}>Grouper par entité</option></select>`;
    const tools = groupSel + (readOnly ? ' <span class="small faint">Lecture seule (fichier local) : actions désactivées</span>' : '');
    el.innerHTML = '<div class="actions-bar" hidden></div><div class="q"></div>';
    const bar = el.querySelector('.actions-bar');
    el.addEventListener('click', (ev) => {
      const b = ev.target.closest('[data-ack]');
      if (!b) return;
      ev.stopPropagation();
      openAlert(+b.dataset.ack, true);
    }, true);
    const g = App.grid(el.querySelector('.q'), {
      columns, rows, sort: ['severity', 'desc'], csv: 'alertes', tools, tall: true, tree: !!st.group,
      select: !readOnly, id: (a) => a._key ?? a.id,
      searchText: (a) => `${a.rule_id} ${a.rule_name} ${a.entity_key} ${a.message} ${a.category || ''}`,
      onRow: (a) => (a._children ? null : openAlert(a.id)),
      onSelect: (ids) => {
        const real = ids.filter((x) => typeof x === 'number');
        bar.hidden = !real.length;
        bar.innerHTML = real.length ? actionsHtml(real.length) : '';
        bar.querySelectorAll('[data-act]').forEach((b) => b.addEventListener('click', () => act(real, b.dataset.act, bar, g)));
      },
    });
  }

  const actionsHtml = (n) => `<b>${n} sélectionnée(s)</b>
    <input class="field" data-by placeholder="Votre nom" value="${esc(store('cvm.by') || '')}" style="width:150px">
    <input class="field" data-note placeholder="Note (facultatif)" style="width:260px">
    <button class="btn primary" data-act="ack">Acquitter</button><button class="btn" data-act="muted">Mettre en sourdine</button><button class="btn" data-act="open">Rouvrir</button>`;

  /** Actions enregistrées mais pas encore intégrées au site affiché (régénération en cours) : réappliquées au chargement. */
  function readPending() { try { return JSON.parse(store('cvm.pending') || '{}'); } catch { return {}; } }
  function applyPending() {
    const pending = readPending(), gen = App.meta.generated_at || '';
    for (const [id, p] of Object.entries(pending)) {
      if (p.at < gen) { delete pending[id]; continue; } // le site régénéré contient déjà l'action
      const a = App.anomalies.find((x) => x.id === +id);
      if (a) { a.status = p.status; if (p.by) a.ack_by = p.by; if (p.note) a.ack_note = p.note; a.ack_at = p.at; }
    }
    store('cvm.pending', JSON.stringify(pending));
    App.indexAlerts();
  }
  applyPending();

  function store(k, v) {
    try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch { return null; }
    return v;
  }

  async function act(ids, status, scope, grid) {
    const by = scope.querySelector('[data-by]')?.value.trim() || null, note = scope.querySelector('[data-note]')?.value.trim() || null;
    if (status === 'ack' && !by) { App.toast('Indiquez votre nom pour acquitter.', true); scope.querySelector('[data-by]')?.focus(); return; }
    if (by) store('cvm.by', by);
    try {
      const r = await fetch('api/v1/anomalies', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids, status, by, note }) });
      if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
      const { at } = await r.json();
      const pending = readPending();
      for (const id of ids) pending[id] = { status, by, note, at };
      store('cvm.pending', JSON.stringify(pending));
      applyPending();
      App.indexAlerts();
      App.invalidate(); // les badges d'alerte des autres onglets doivent refléter le nouveau statut
      App.toast(`${ids.length} alerte(s) : ${STATUS_FR[status].toLowerCase()}. Tableau de bord régénéré en arrière-plan.`);
      App.closeDrawer();
      App.go('alertes'); // re-rendu sur place, sans entrée d'historique (invalidate ci-dessus)
    } catch (e) {
      App.toast(`Échec de l'enregistrement : ${e.message}`, true);
    }
  }

  function openAlert(id, focusActions) {
    const a = App.anomalies.find((x) => x.id === +id);
    if (!a) return;
    const rule = catalog.get(a.rule_id) || {};
    const d = a.details || {};
    const fam = FAMILY(a.rule_id);
    const extra = Object.entries(d).filter(([k]) => !['p_low', 'p50', 'p_normal_high', 'p_high', 'n', 'mode'].includes(k))
      .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(Array.isArray(v) ? (v.length > 12 ? v.slice(0, 12).join(', ') + ` … (${v.length})` : v.join(', ')) : typeof v === 'object' ? JSON.stringify(v) : v)}</dd>`).join('');
    const dist = d.p50 != null ? `<div><h3>Position dans la distribution</h3>${position(a)}<div class="small muted" style="margin-top:6px">Référence : ${d.mode === 'percentile' ? 'historique propre' : d.mode === 'percentile_global' ? 'toute la population' : d.mode === 'static' ? 'seuil fixe (trop peu de pairs)' : 'pairs du groupe'} · n = ${d.n ?? '?'} · P${App.meta.percentiles.low} = ${valueCell({ ...a, value: d.p_low })} · médiane = ${valueCell({ ...a, value: d.p50 })} · P${App.meta.percentiles.high} = ${valueCell({ ...a, value: d.p_high })}</div></div>` : '';
    const link = entityLink(a);
    App.drawer(`<span class="sev ${a.severity}">${SEV_FR[a.severity]}</span> <span class="st ${a.status}">${STATUS_FR[a.status]}</span><h2 style="margin-top:4px">${esc(a.rule_id)} · ${esc(a.rule_name || rule.name || '')}</h2>`,
      `<div class="callout ${a.severity === 'critical' || a.severity === 'major' ? 'bad' : 'info'}">${esc(a.message)}</div>
      <div><h3>Action recommandée</h3><p style="margin:0">${esc(ACTION[fam] || ACTION.DQ)}</p>${link ? `<p style="margin:8px 0 0">${link}</p>` : ''}</div>
      ${dist}
      <dl class="kv">
        <dt>Entité</dt><dd>${entityLabel(a)}</dd><dt>Catégorie</dt><dd>${esc(a.category || '–')}</dd>
        <dt>Date</dt><dd>${F.dateFull(a.date)}</dd><dt>Métrique</dt><dd>${esc(a.metric || '–')} : <b>${valueCell(a) || '–'}</b> (attendu ${esc(a.expected || '–')})</dd>
        <dt>Volume impacté</dt><dd>${F.int(a.volume)}</dd>
        <dt>Cycle de vie</dt><dd>vue la 1re fois au fichier du ${F.dateFull(a.first_seen_at)}, la dernière au ${F.dateFull(a.last_seen_at)} · ${a.occurrences} occurrence(s)${a.resolved_at ? ` · résolue le ${F.dateFull(a.resolved_at)}` : ''}</dd>
        <dt>Acquittement</dt><dd>${a.ack_by ? `${esc(a.ack_by)} le ${F.dt(a.ack_at)}${a.ack_note ? ` : « ${esc(a.ack_note)} »` : ''}` : '–'}</dd>
        <dt>Notification</dt><dd>${a.last_notified_at ? F.dt(a.last_notified_at) : 'jamais notifiée'}</dd>
        ${extra}
      </dl>
      <div><h3>La règle</h3><p class="small" style="margin:0 0 6px;white-space:pre-line">${esc(rule.doc || 'Voir docs/PLATEFORME.md')}</p><p class="small muted" style="margin:0">Paramètres : ${esc(JSON.stringify(rule.params || {}))}</p></div>
      ${readOnly ? '' : `<div data-acts style="display:flex;flex-wrap:wrap;gap:8px;align-items:center"><h3 style="width:100%;margin:0 0 4px">Traiter l'alerte</h3>${actionsHtml(1).replace('<b>1 sélectionnée(s)</b>', '')}</div>`}`,
      (body) => {
        body.querySelectorAll('[data-act]').forEach((b) => b.addEventListener('click', () => act([a.id], b.dataset.act, body.querySelector('[data-acts]'))));
        if (focusActions) { const f = body.querySelector('[data-acts]'); f?.scrollIntoView({ block: 'nearest' }); f?.querySelector('[data-by]')?.focus(); }
      });
  }

  /** Lien vers l'entité dans l'onglet Push ou Inbound. */
  function entityLink(a) {
    const k = encodeURIComponent(a.entity_key);
    switch (a.entity_type) {
      case 'bc_name': return `<a href="#push?p=tout" data-open-drawer="bc:${esc(a.entity_key)}">Voir le BC dans Push Campaigns →</a>`;
      case 'broadcast': return `<a href="#push?p=tout" data-open-drawer="broadcast:${esc(a.entity_key)}">Voir le broadcast dans Push Campaigns →</a>`;
      case 'campaign': return `<a href="#push?p=tout&camp=${k}">Voir la campagne dans Push Campaigns →</a>`;
      case 'category': return `<a href="#push?cat=${encodeURIComponent(a.entity_key.split(' · ')[0])}">Voir la catégorie dans Push Campaigns →</a>`;
      case 'im_rule': return `<a href="#inbound?p=tout" data-open-drawer="rule:${esc(a.entity_key)}">Voir la règle dans Inbound Marketing →</a>`;
      case 'touchpoint': return `<a href="#inbound?p=tout&tp=${encodeURIComponent(a.entity_key.split(' · ')[0])}">Voir le touchpoint dans Inbound Marketing →</a>`;
      case 'program': return `<a href="#inbound?prog=${k}">Voir le programme dans Inbound Marketing →</a>`;
      case 'column': case 'dataset': return '<a href="#analytics?sec=arrivee">Voir l\'arrivée des données (Analytics) →</a>';
      default: return '';
    }
  }

  function trend(el) {
    // Nouvelles alertes par fichier, par sévérité : mesure du bruit et des vagues.
    const files = App.snaps.map((s) => s.snapshot_date);
    const counts = Object.fromEntries(SEV.map((s) => [s, files.map(() => 0)]));
    const pos = new Map(files.map((d, i) => [d, i]));
    for (const a of App.anomalies) { const i = pos.get(a.first_seen_at); if (i != null) counts[a.severity][i]++; }
    const colors = { critical: '#c62828', major: '#d9620b', minor: '#c99a00', info: '#b9cbee' };
    Charts.bars(el.querySelector('[data-c=trend]'), { x: files, xfmt: F.date, fmt: F.int, height: 190,
      series: SEV.map((s) => ({ name: SEV_FR[s], values: counts[s], color: colors[s] })) });
    const byRule = new Map();
    for (const a of App.anomalies) if (a.status === 'open' || a.status === 'ack') byRule.set(a.rule_id, (byRule.get(a.rule_id) || 0) + 1);
    Charts.hbars(el.querySelector('[data-c=rules]'), { fmt: F.int, onClick: (r) => App.set({ rule: r.id, status: null }),
      rows: [...byRule.entries()].sort((x, y) => y[1] - x[1]).slice(0, 12).map(([id, n]) => ({ id, label: `${id} · ${catalog.get(id)?.name || ''}`, value: n })) });
  }

  function catalogGrid(el, scope) {
    App.grid(el, {
      rows: (App.D.catalog || []).filter((r) => !scope || r.scope === scope), sort: ['id', 'asc'], csv: 'regles', id: (r) => r.id,
      tools: App.localSeg('scope', [['', 'Tous'], ...Object.entries(SCOPE_FR)], scope || ''),
      columns: [
        { key: 'id', label: 'Règle', html: (r) => `<b>${esc(r.id)}</b>` }, { key: 'name', label: 'Nom' },
        { key: 'scope', label: 'Périmètre', fmt: (v) => SCOPE_FR[v] || v },
        { key: 'severity', label: 'Sévérité', csv: (r) => SEV_FR[r.severity], html: (r) => `<span class="sev ${r.severity}">${SEV_FR[r.severity]}</span>` },
        { key: 'enabled', label: 'Active', html: (r) => (r.enabled ? '<span class="badge ok">oui</span>' : '<span class="badge grey">non</span>') },
        { key: 'params', label: 'Paramètres', html: (r) => `<span class="small muted">${esc(Object.entries(r.params).map(([k, v]) => `${k}=${v}`).join(' · '))}</span>`, csv: (r) => JSON.stringify(r.params) },
        { key: 'count', label: 'Alertes (45 j)', num: true, fmt: F.int, bar: true, barMax: Math.max(1, ...(App.D.catalog || []).map((r) => r.count || 0)) },
      ],
      onRow: (r) => App.set({ rule: r.id, status: 'all' }),
    });
  }

  function notifGrid(el) {
    App.grid(el, {
      rows: App.D.notifications || [], sort: ['id', 'desc'], search: false, id: (r) => r.id, empty: 'Aucune notification envoyée',
      columns: [
        { key: 'sent_at', label: 'Envoyée le', fmt: (v) => F.dt(v) }, { key: 'channel', label: 'Canal' },
        { key: 'n_anomalies', label: 'Alertes', num: true, fmt: F.int },
        { key: 'success', label: 'Résultat', html: (r) => (r.success ? '<span class="badge ok">envoyée</span>' : `<span class="badge alert">échec</span> <span class="small muted">${esc(r.error || '')}</span>`) },
      ],
    });
  }

  function render(el, st) {
    const list = filtered(st);
    const slot = (id) => `<div data-slot="${id}"></div>`;
    const nOpen = App.anomalies.filter((a) => a.status === 'open').length;
    App.subtitle(`Que traiter et prévenir aujourd'hui ? · fichier du ${F.dateFull(latest?.snapshot_date)} · ${F.int(nOpen)} alertes ouvertes`);
    const notifs = App.D.notifications || [];
    el.innerHTML = `
      ${section('Santé du flux NEON-dx', slot('feed'), { id: 'al-feed', nav: 'Santé du flux', panel: true, sub: 'Fraîcheur, fichiers manquants, remplissage des colonnes et fulfillment IM' })}
      ${section('État des alertes', slot('state'), { id: 'al-state', nav: 'État', sub: 'Cliquer une sévérité filtre la file de traitement' })}
      ${section('File de traitement', slot('queue'), { id: 'al-queue', nav: 'File de traitement', panel: true, sub: `${F.int(list.length)} alerte(s) · triées par sévérité puis volume`, note: 'Cliquer une ligne pour le détail, cocher pour agir en lot. Les filtres de la page s\'appliquent à cette file ; le regroupement ne concerne qu\'elle.' })}
      ${section('Tendance et bruit', slot('trend'), { id: 'al-trend', nav: 'Tendance' })}
      ${section('Catalogue des règles', slot('catalog'), { id: 'al-catalog', nav: 'Catalogue', panel: true, sub: `${(App.D.catalog || []).filter((r) => r.enabled).length} règles actives · alertes levées sur 45 jours`, note: 'Cliquer une règle filtre la file de traitement.' })}
      ${notifs.length ? section(`Journal des notifications`, slot('notif'), { id: 'al-notif', nav: 'Notifications', panel: true, sub: `${notifs.length} envoi(s)` })
        : `<div class="section panel journal" id="al-notif"><div style="display:flex;gap:14px;align-items:center"><div class="ic"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0"/></svg></div>
          <div><h2 style="font-size:18px;margin:0 0 4px">Journal des notifications</h2><span class="muted">Aucune notification envoyée pour l'instant (Teams / e-mail).</span></div></div><a class="btn primary" href="settings.html#canaux">Configurer les canaux</a></div>`}`;
    const W = (id, draw) => App.widget(el.querySelector(`[data-slot=${id}]`), id, draw);
    W('feed', (w) => { w.innerHTML = feedBlock(); });
    W('state', (w) => {
      w.innerHTML = tiles(st);  // clics des tuiles : délégation [data-set-many] du socle (position conservée)
    });
    W('queue', (w, g, l) => { w.innerHTML = '<div class="card flush" data-q></div>'; queue(w.firstChild, { ...st, group: l.group }, list); });
    W('trend', (w) => {
      w.innerHTML = `<div class="grid g2">${card('Nouvelles alertes par fichier', '<div class="chart" data-c="trend"></div>', { note: 'Une vague soudaine signale souvent un problème de données plutôt que de campagnes.' })}
        ${card('Règles les plus déclenchées (actives)', '<div data-c="rules"></div>', { note: 'Cliquer une règle filtre la file de traitement (filtre de la page).' })}</div>`;
      trend(w);
    });
    W('catalog', (w, g, l) => { w.innerHTML = '<div class="card flush"></div>'; catalogGrid(w.firstChild, l.scope); });
    if (notifs.length) W('notif', (w) => { w.innerHTML = '<div class="card flush"></div>'; notifGrid(w.firstChild); });
  }

  const STATUS_CHIP = { open: 'Ouvertes', ack: 'Acquittées', muted: 'Sourdine', resolved: 'Résolues', all: 'Toutes' };
  /** Puces des filtres de la file (filtres de la page de cet onglet). */
  function chips(st) {
    const out = [];
    if (st.status) out.push({ label: `Statut : ${STATUS_CHIP[st.status] || st.status}`, patch: { status: null } });
    if (st.sev) out.push({ label: `Sévérité : ${[].concat(st.sev).map((x) => SEV_FR[x] || x).join(', ')}`, patch: { sev: null } });
    if (st.scope) out.push({ label: `Périmètre : ${SCOPE_FR[st.scope] || st.scope}`, patch: { scope: null } });
    if (st.fam) out.push({ label: `Famille : ${FAMILY_FR[st.fam] || st.fam}`, patch: { fam: null } });
    if (st.rule) out.push({ label: `Règle : ${st.rule}`, patch: { rule: null } });
    if (st.ent) out.push({ label: `Entité : ${st.ent}`, patch: { ent: null } });
    if (st.since) out.push({ label: st.since === 'new' ? 'Nouvelles au dernier fichier' : 'Résolues au dernier fichier', patch: { since: null } });
    return out;
  }

  App.drawerOpeners.alert = openAlert;
  App.tab('alertes', { title: 'Alertes', render, defaults: {}, multi: [], filters: { period: false, extraLabel: null, extra: filtersHtml, chips } });
})();
