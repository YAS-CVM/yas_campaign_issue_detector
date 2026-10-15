/* Onglet Push Campaigns : « Que se passe-t-il sur nos envois : partent-ils, arrivent-ils, convertissent-ils ? »
 * Instant t (jour J, dernier fichier) puis période. Chaque conversion porte son état de complétude. */
'use strict';
(() => {
  const { P, V, F, esc, card, section, tile } = App;
  const DIMS = [
    { key: 'cat', label: 'Catégorie', T: 'P', dim: 'cat', all: 'Toutes' },
    { key: 'camp', label: 'Campagne', T: 'P', dim: 'camp', all: 'Toutes' },
    { key: 'bc', label: 'BC', T: 'P', dim: 'bc' },
    { key: 'st', label: 'Statut', T: 'P', dim: 'st' },
  ];
  const SEED_FR = { '': 'Tout', no: 'Hors seeding', only: 'Seeding seul' };
  const lastSnapIdx = App.snaps.length - 1;
  const pDates = P.d.d || [];
  const lastPushDate = pDates[pDates.length - 1];

  const seedWhere = (st) => (st.seed === 'no' ? (i) => !P.c.seed[i] : st.seed === 'only' ? (i) => !!P.c.seed[i] : null);
  const rowsFor = (st, opt = {}) => App.rows(P, st, DIMS, { where: seedWhere(st), ...opt });
  const organic = (idx) => idx.filter((i) => !P.c.seed[i]);
  const seeded = (idx) => idx.filter((i) => P.c.seed[i]);

  /** Conversions avec complétude : définitif, en maturation (estimé), tronqué (n'atteindra jamais la maturité). */
  function convHtml(s, fmt = F.int) {
    if (!s || !s.n) return '–';
    if (s.truncShare > 0.01) return `<span class="prov" title="Observé ${F.int(s.conv)} · estimé à maturité ≈ ${F.int(s.est.conv)}. ${s.trunc} envoi(s) absents des fichiers suivants avant maturité.">${fmt(s.conv)}</span> <span class="badge trunc" title="Fin de mois : ces envois ne seront plus jamais mis à jour">tronqué</span>`;
    if (s.pending > 0.01) return `<span class="prov" title="Observé ${F.int(s.conv)} · estimé à maturité ≈ ${F.int(s.est.conv)}">${fmt(s.conv)}</span>`;
    return fmt(s.conv);
  }
  const rateHtml = (v, est, pending) => (v == null ? '<span class="nr">n/r</span>' : pending > 0.01 ? `<span class="prov" title="Observé ${F.pct(v)} · estimé à maturité ≈ ${F.pct(est)}">${F.pct(v)}</span>` : F.pct(v));
  const genHtml = (s) => (s.genMissing === s.n && s.sent > 0 ? '<span class="nr" title="Generated non renseigné par NEON-dx (flows)">n/r</span>' : F.int(s.gen) + (s.genMissing ? ` <span class="faint small" title="${s.genMissing} broadcast(s) sans Generated">(${s.genMissing} n/r)</span>` : ''));
  const catTag = (c) => (App.isTest(c) ? ' <span class="badge test">test</span>' : '') + ((App.meta.non_conversion_categories || []).includes(c) ? ' <span class="badge grey" title="Catégorie sans objectif de conversion">sans obj. conv.</span>' : '');
  const bcTags = (bc, s) => (App.isTechnical(bc) ? ' <span class="badge grey" title="BC technique (technical_bc_patterns)">technique</span>' : '') + (s && s.sent > 0 && s.dlv === 0 ? ' <span class="badge trunc" title="Delivered = 0 : accusés de réception non remontés">sans DLR</span>' : '');

  // ------------------------------------------------------------------ instant t
  function dayBlock(st, day) {
    const all = rowsFor(st, { period: false });
    const byDay = KPI.push(P, all, (i) => P.v('d', i));
    const orgDay = KPI.push(P, organic(all), (i) => P.v('d', i));
    const s = byDay.get(day) || KPI.pushRates({ n: 0, est: {} });
    const o = orgDay.get(day);
    const seedS = KPI.push(P, seeded(all.filter((i) => P.v('d', i) === day)));
    const last30 = App.range(App.addDays(day, -29), day);
    const pf = App.provisionalFrom(last30);
    const ref = (fn, map = byDay) => App.refs(map, day, fn);
    const delta = (cur, r, kind, inverse) => ({ v: cur == null || r.avg7 == null ? null : kind === 'pts' ? cur - r.avg7 : r.avg7 ? cur / r.avg7 - 1 : null, kind, inverse,
      title: r.wd != null ? `Même jour de semaine (moy. 4 sem.) : ${kind === 'pts' ? F.pct(r.wd) : F.int(r.wd)}` : '' });
    const sp = (fn, map = byDay, prov) => Charts.spark(App.series(last30, map, fn), { provisionalFrom: prov ? pf : last30.length });
    const wdRef = (cur, r, kind) => (r.wd == null || cur == null ? '' : `même jour sem. ${kind === 'pts' ? F.pts(cur - r.wd) : F.signedPct(r.wd ? cur / r.wd - 1 : null)}`);
    const sentR = ref((x) => x.sent), ackR = ref((x) => x.ack_rate), dlvR = ref((x) => x.delivery_rate), convR = ref((x) => x.est.conv);
    const crR = ref((x) => x.conv_rate_est, orgDay), netR = ref((x) => x.net_conv_rate_est, orgDay), ffR = ref((x) => x.ff_rate);
    const prov = s.pending > 0.01;
    const tiles = [
      tile({ label: 'Envoyés (Sent)', value: F.int(s.sent), delta: delta(s.sent, sentR), sub: wdRef(s.sent, sentR) + (s.genMissing ? ` · Generated n/r sur ${s.genMissing}` : ''), spark: sp((x) => x.sent) }),
      tile({ label: 'Acknowledged %', value: F.pct(s.ack_rate), delta: delta(s.ack_rate, ackR, 'pts'), sub: wdRef(s.ack_rate, ackR, 'pts'), spark: sp((x) => x.ack_rate), hint: 'Acknowledged ÷ Sent : accusé de l\'opérateur' }),
      tile({ label: 'Delivery %', value: F.pct(s.delivery_rate), delta: delta(s.delivery_rate, dlvR, 'pts'), sub: wdRef(s.delivery_rate, dlvR, 'pts'), spark: sp((x) => x.delivery_rate), hint: 'Delivered ÷ Sent. Delivered dépend de la remontée des accusés de réception (DLR) : à lire en relatif.' }),
      tile({ label: 'Conversions', value: F.int(s.conv), prov, provTitle: `Estimé à maturité ≈ ${F.int(s.est.conv)}`, delta: delta(s.est.conv, convR), sub: prov ? `≈ ${F.int(s.est.conv)} attendues à maturité` : 'définitif', spark: sp((x) => x.conv, byDay, true),
        badge: s.truncShare > 0.01 ? '<span class="badge trunc">tronqué</span>' : prov ? '<span class="badge prov">en maturation</span>' : '' }),
      tile({ label: 'Conv % hors seeding', value: F.pct(o?.conv_rate), prov: o && o.pending > 0.01, provTitle: `Estimé à maturité ≈ ${F.pct(o?.conv_rate_est)}`, delta: delta(o?.conv_rate_est, crR, 'pts'), sub: o && o.pending > 0.01 ? `≈ ${F.pct(o.conv_rate_est)} à maturité` : '', spark: sp((x) => x.conv_rate, orgDay, true), hint: 'Conversions ÷ Sent, broadcasts hors seeding' }),
      tile({ label: 'Net Conv % (vs CG)', value: F.pts(o?.net_conv_rate), prov: o && o.pending > 0.01, delta: delta(o?.net_conv_rate_est, netR, 'pts'), sub: `CG conv ${F.pct(o?.cg_conv_rate)}`, spark: sp((x) => x.net_conv_rate, orgDay, true), hint: 'Conv % TG − Conv % groupe de contrôle, hors seeding' }),
      tile({ label: 'Fulfillment Failure %', value: F.pct(s.ff_rate), nr: s.fs + s.ff === 0, delta: delta(s.ff_rate, ffR, 'pts', true), sub: `${F.int(s.ff)} échecs / ${F.int(s.fs + s.ff)}`, spark: sp((x) => x.ff_rate) }),
      tile({ label: 'Conversions seeding', value: F.int(seedS.conv), sub: seedS.n ? `${seedS.n} broadcast(s) · ${F.int(seedS.sent)} envoyés` : 'aucun broadcast seeding', badge: '<span class="badge seed">seeding</span>', hint: 'Bonus crédités directement : comptés à part pour ne pas fausser Conv %' }),
    ];
    return { html: `<div class="grid tiles">${tiles.join('')}</div>`, byDay };
  }

  /** Broadcasts du dernier fichier qui ne sont pas « Completed », et transitions de statut depuis le fichier précédent. */
  function execution(st) {
    const cur = App.rows(P, st, DIMS, { period: false, where: (i) => !P.c.frozen[i] });
    const counts = new Map();
    for (const i of cur) counts.set(P.v('st', i), (counts.get(P.v('st', i)) || 0) + 1);
    const known = ['Completed', 'Delivering', 'Paused', 'Aborted', 'Delivery Stalled', 'Blackout Pause', 'Blackout Expired', 'Targeting', 'Render Scheduled'];
    const chips = (on) => [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([s, n]) =>
      `<button class="pill ${on === s ? 'on' : ''}" data-local="st" data-val="${on === s ? '' : esc(s)}" title="Filtrer cette carte sur ce statut"><span class="d" style="background:${App.stDot(s)}"></span>${esc(s)}${known.includes(s) ? '' : ' (nouveau)'}<span class="n">${F.int(n)}</span></button>`).join('');
    const open = (on) => cur.filter((i) => (on ? P.v('st', i) === on : P.v('st', i) !== 'Completed')).map((i) => brow(i));
    // Transitions : version au dernier fichier dont le statut diffère de la version précédente.
    const ids = new Set(cur.map((i) => P.c.id[i]));
    const trans = [];
    for (let k = 1; k < V.n; k++) {
      if (V.c.snap[k] !== lastSnapIdx || V.c.id[k] !== V.c.id[k - 1] || !ids.has(V.c.id[k])) continue;
      const a = V.v('st', k - 1), b = V.v('st', k);
      if (a !== b) trans.push({ id: V.c.id[k], from: a, to: b, since: App.snaps[V.c.snap[k - 1]]?.snapshot_date });
    }
    const pos = new Map(cur.map((i) => [P.c.id[i], i]));
    return {
      chips, open, total: cur.length, trans: trans.map((t) => ({ ...t, ...brow(pos.get(t.id)) })),
      newCount: (() => { let n = 0; for (let k = 0; k < V.n; k++) if (V.c.snap[k] === lastSnapIdx && (k === 0 || V.c.id[k - 1] !== V.c.id[k])) n++; return n; })(),
    };
  }
  const brow = (i) => ({ _key: P.c.id[i], id: P.c.id[i], i, date: P.v('d', i), name: P.c.name[i], bc: P.v('bc', i), camp: P.v('camp', i), cat: P.v('cat', i), status: P.v('st', i),
    gen: P.c.gen[i], sent: P.c.sent[i], ack: P.c.ack[i], dlv: P.c.dlv[i], conv: P.c.conv[i], age: P.c.age[i], seed: P.c.seed[i], frozen: P.c.frozen[i],
    dlv_rate: KPI.rate(P.c.dlv[i], P.c.sent[i]), conv_rate: KPI.rate(P.c.conv[i], P.c.sent[i]), comp: KPI.completion('conv', P.c.age[i]) });

  function bcState(r) {
    if (P.c.lost[r.i]) return '<span class="badge alert" title="Disparu des fichiers NEON-dx suivants du même mois : dernières valeurs connues">disparu</span>';
    if (r.comp >= 0.99) return '';
    return r.frozen ? '<span class="badge trunc" title="Absent des fichiers suivants avant maturité">tronqué</span>' : `<span class="badge prov" title="Complétude estimée des conversions : ${F.pct1(r.comp)}">J+${r.age}</span>`;
  }

  // ------------------------------------------------------------------ période
  function funnel(s) {
    const stages = [
      ['Generated', s.genMissing === s.n ? null : s.gen, s.genMissing ? `non renseigné pour ${F.int(s.genMissing)} broadcast(s) (flows)` : ''],
      ['Sent', s.sent], ['Acknowledged', s.ack], ['Delivered', s.dlv, 'dépend de la remontée des DLR'],
      ['Conversions', s.conv, s.pending > 0.01 ? `≈ ${F.int(s.est.conv)} attendues à maturité` : ''],
      ['Fulfillment Success', s.fs, s.ff ? `${F.int(s.ff)} échecs (${F.pct(s.ff_rate)})` : ''],
    ];
    const top = Math.max(s.gen || 0, s.sent, 1);
    let prev = null;
    return '<ol class="funnel">' + stages.map(([l, v, note]) => {
      const pct = v != null && prev ? F.pct(KPI.rate(v, prev)) : '';
      const out = `<li><div class="row"><b>${l}</b><span class="num" style="display:flex;gap:8px;align-items:baseline"><strong>${v == null ? '<span class="nr">n/r</span>' : F.int(v)}</strong><span class="small muted" style="min-width:52px">${pct}</span></span></div>
        <div class="track"><div class="fill" style="width:${v == null ? 0 : Math.max(1.2, (v / top) * 100)}%;${l === 'Conversions' || l === 'Fulfillment Success' ? 'background:#0a2357' : ''}"></div></div>${note ? `<span class="fnote">${esc(note)}</span>` : ''}</li>`;
      if (v != null) prev = v;
      return out;
    }).join('') + '</ol>';
  }

  function categoryRows(idx) {
    const by = KPI.push(P, idx, (i) => P.v('cat', i));
    const bcs = new Map();
    for (const i of idx) { const c = P.v('cat', i); if (!bcs.has(c)) bcs.set(c, new Set()); bcs.get(c).add(P.c.bc[i]); }
    return [...by.values()].map((s) => ({ ...s, _key: s.key, cat: s.key, nbc: bcs.get(s.key).size, est_conv: s.est.conv }));
  }

  function explorer(idx) {
    // Arbre Campagne → BC → Broadcast, agrégats « on somme puis on calcule le taux ».
    const camps = new Map();
    for (const i of idx) {
      const c = P.v('camp', i), b = P.v('bc', i);
      if (!camps.has(c)) camps.set(c, new Map());
      const m = camps.get(c);
      if (!m.has(b)) m.set(b, []);
      m.get(b).push(i);
    }
    const node = (key, label, ids, extra) => { const s = KPI.push(P, ids); return { _key: key, label, ...s, est_conv: s.est.conv, ...extra }; };
    return [...camps.entries()].map(([c, bcs]) => {
      const all = [...bcs.values()].flat();
      return node('c:' + c, c, all, {
        type: 'campaign', cat: P.v('cat', all[0]), nbc: bcs.size,
        _children: [...bcs.entries()].map(([b, ids]) => node('b:' + b, b, ids, {
          type: 'bc', cat: P.v('cat', ids[0]),
          _children: ids.map((i) => ({ ...node('x:' + P.c.id[i], `${P.c.id[i]} · ${F.date(P.v('d', i))}`, [i], { type: 'broadcast', id: P.c.id[i], status: P.v('st', i), cat: P.v('cat', i) }) })),
        })),
      });
    });
  }

  const metricCols = (opt = {}) => [
    { key: 'n', label: 'Broadcasts', num: true, fmt: F.int },
    { key: 'gen', label: 'Generated', num: true, html: genHtml, csv: (r) => r.gen },
    { key: 'sent', label: 'Sent', num: true, fmt: F.int, bar: opt.bar },
    { key: 'ack_rate', label: 'Ack %', num: true, fmt: F.pct },
    { key: 'delivery_rate', label: 'Delivery %', num: true, fmt: F.pct },
    { key: 'conv', label: 'Conversions', num: true, html: (r) => convHtml(r), csv: (r) => r.conv },
    { key: 'est_conv', label: 'Estimé à maturité', num: true, fmt: (v, r) => (r.pending > 0.01 ? `<span class="muted">≈ ${F.int(v)}</span>` : F.int(v)), csv: (r) => Math.round(r.est_conv), title: 'Conversions attendues une fois toutes les conversions remontées (courbe de maturité)' },
    { key: 'conv_rate', label: 'Conv %', num: true, html: (r) => rateHtml(r.conv_rate, r.conv_rate_est, r.pending), csv: (r) => r.conv_rate },
    { key: 'cg_conv_rate', label: 'CG Conv %', num: true, fmt: (v, r) => (r.cg ? F.pct(v) : '<span class="nr" title="Pas de groupe de contrôle">CG = 0</span>') },
    { key: 'net_conv_rate', label: 'Net Conv %', num: true, fmt: F.pts },
    { key: 'val', label: 'Valeur conv.', num: true, fmt: (v, r) => (r.conv > 0 && !v ? '<span class="nr" title="Valeur non renseignée par NEON-dx">n/r</span>' : F.money(v)) },
    { key: 'seedConv', label: 'dont seeding', num: true, fmt: (v) => (v ? `<span class="badge seed">${F.compact(v)}</span>` : '') },
    { key: 'ff_rate', label: 'Fulf. Failure %', num: true, fmt: (v, r) => (r.fs + r.ff ? F.pct(v) : '<span class="nr">–</span>') },
  ];

  const HEAT_METRICS = { dlv: ['Delivery %', (s) => s.delivery_rate], ack: ['Ack %', (s) => s.ack_rate], conv: ['Conv %', (s) => s.conv_rate], sent: ['Envoyés', (s) => s.sent] };
  /** Carte de chaleur. Sans filtre local : catégories × jours ; filtre local `cat` : BC de cette catégorie × jours. */
  function heat(el, idx, days, l) {
    const metric = HEAT_METRICS[l.m] ? l.m : 'dlv';
    const M = HEAT_METRICS[metric];
    const sub = l.cat ? idx.filter((i) => P.v('cat', i) === l.cat) : idx;
    const rowOf = (i) => (l.cat ? P.v('bc', i) : P.v('cat', i));
    const cells = KPI.push(P, sub, (i) => rowOf(i) + '|' + P.v('d', i));
    const totals = KPI.push(P, sub, rowOf);
    const rows = [...totals.values()].sort((a, b) => b.sent - a.sent).map((x) => x.key).slice(0, l.cat ? 40 : 99);
    const med = new Map();
    for (const r of rows) {
      const v = days.map((d) => cells.get(r + '|' + d)).filter((x) => x && x.sent > 0).map(M[1]).filter((x) => x != null).sort((a, b) => a - b);
      med.set(r, KPI.percentile(v, 50));
    }
    const maxSent = Math.max(1, ...[...cells.values()].map((x) => x.sent));
    el.innerHTML = card(l.cat ? 'BC × jour' : 'Catégories × jour', '<div data-c="heat"></div>', {
      note: `Couleur : écart à la médiane de la ligne sur la période (rouge = en dessous, bleu = au-dessus). ${l.cat ? 'Les 40 BC les plus envoyés. Cliquer une case ouvre le BC.' : 'Cliquer une case pour voir les BC de la catégorie (dans cette carte uniquement).'}`,
      local: [l.cat && App.localBadge(`BC de ${l.cat}`, 'cat')],
      right: App.localSeg('m', Object.entries(HEAT_METRICS).map(([k, [lbl]]) => [k, lbl]), metric),
    });
    Charts.heatmap(el.querySelector('[data-c=heat]'), {
      rows, cols: days, colFmt: F.date, rowFmt: (r) => (r.length > 38 ? r.slice(0, 36) + '…' : r),
      value: (r, d) => { const x = cells.get(r + '|' + d); return x && x.sent > 0 ? M[1](x) : null; },
      color: (v, r) => (metric === 'sent' ? Charts.seqColor(Math.sqrt(v / maxSent)) : Charts.divColor(med.get(r) ? (v - med.get(r)) / Math.max(0.05, med.get(r)) : 0)),
      title: (r, d, v) => { const x = cells.get(r + '|' + d); return `<b>${esc(r)} · ${F.day(d)}</b>${x ? `<div>${M[0]} : ${metric === 'sent' ? F.int(v) : F.pct(v)}</div>${metric === 'sent' ? '' : `<div>Médiane de la ligne : ${F.pct(med.get(r))}</div>`}<div>${F.int(x.sent)} envoyés · ${x.n} broadcast(s)</div>` : '<div>aucun envoi</div>'}`; },
      onClick: (r) => (l.cat ? openBc(r) : App.setLocal('heat', { cat: r })),
    });
  }

  function render(el, st) {
    if (!P.n) { el.innerHTML = '<div class="empty">Aucune donnée Push. Importer un fichier depuis les paramètres.</div>'; return; }
    const idx = rowsFor(st);
    const days = App.periodDates(st).filter((d) => d <= lastPushDate);
    const tot = KPI.push(P, idx);
    const ex = execution(st);
    const slot = (id) => `<div data-slot="${id}"></div>`;
    const nCats = new Set(idx.map((i) => P.v('cat', i))).size;
    App.subtitle(`Envois, livraison et conversions · ${F.int(tot.n)} broadcasts sur ${days.length} jours · ${nCats} catégorie${nCats > 1 ? 's' : ''}`);
    const orgTot = KPI.push(P, organic(idx));
    el.innerHTML = `
      ${section('Jour J', slot('instant'), { id: 'push-instant', nav: 'Jour J', panel: true,
        note: 'Écarts vs moyenne des 7 jours précédents ; « même jour sem. » : vs le même jour des 4 semaines précédentes. Conversions en italique : en cours de maturation. Le Jour J ne concerne que cette section.' })}
      ${section('Exécution au dernier fichier', `${slot('exec')}${slot('trans')}`, { id: 'push-exec', nav: 'Exécution', panel: true,
        note: 'Broadcasts du dernier fichier qui ne sont pas « Completed ». Cliquer un statut filtre ce tableau uniquement.',
        sub: `Fichier du ${F.date(App.snaps[lastSnapIdx]?.snapshot_date)} · ${F.int(ex.total)} broadcasts · ${F.int(ex.open().length)} non « Completed » · ${F.int(ex.newCount)} nouveaux · ${ex.trans.length ? `${ex.trans.length} transition(s) de statut` : 'aucune transition de statut'}` })}
      ${section(`Période · ${F.date(days[0])} → ${F.dateFull(days[days.length - 1])}`, `<div class="split"><div class="narrow">${slot('funnel')}</div><div class="wide">${slot('sent')}</div></div><div class="grid g2" style="margin-top:14px">${['rates', 'conv', 'net', 'seed'].map(slot).join('')}</div>`,
        { id: 'push-period', nav: 'Période', sub: `${F.int(tot.sent)} envoyés · Ack ${F.pct1(tot.ack_rate)} · Delivery ${F.pct1(tot.delivery_rate)} · Conv % ${F.pct(orgTot.conv_rate)} · Net ${F.pts(orgTot.net_conv_rate)}` })}
      ${section('Catégories × jour', slot('heat'), { id: 'push-heat', nav: 'Heatmap', panel: true })}
      ${section('Par catégorie', slot('cats'), { id: 'push-cats', nav: 'Par catégorie', panel: true })}
      ${section('Top des BC', slot('top'), { id: 'push-top', nav: 'Top BC', panel: true,
        note: 'Classement des BC (une programmation de message ou d\'offre) sur la période et les filtres de la page, tous types inclus : commercial, informatif, seeding. <b>Volume</b> : Sent cumulé. <b>Base par envoi</b> : Sent moyen d\'un broadcast (clients touchés à chaque envoi ; NEON-dx ne fournit pas d\'identifiant client, les clients distincts sur plusieurs envois ne sont pas comptables). <b>Fréquence</b> : nombre de jours d\'envoi sur la période.' })}
      ${section('Campagnes', slot('tree'), { id: 'push-tree', nav: 'Campagnes', panel: true, sub: 'Campagne → BC → Broadcast' })}`;
    const W = (id, draw) => App.widget(el.querySelector(`[data-slot=${id}]`), id, draw);

    // Instant t : Jour J local à la section
    W('instant', (w, g, l) => {
      const day = l.day && pDates.includes(l.day) ? l.day : lastPushDate;
      const db = dayBlock(st, day);
      w.innerHTML = card(`<span style="font-size:15px;font-weight:700;color:var(--ink-2)">${F.dayLong(day)}</span>`, db.html, {
        local: [day !== lastPushDate ? App.localBadge(`Jour J : ${F.date(day)}`, 'day') : '<span class="badge yel">Dernier rapport disponible</span>'],
        right: App.dayNav(pDates, day, lastPushDate) });
    });

    // Exécution : pastille de statut = filtre local de la carte
    const bcols = [
      { key: 'status', label: 'Statut', html: (r) => App.stPill(r.status) },
      { key: 'date', label: 'Envoi', fmt: (v, r) => `${F.date(v)} <span class="small muted">J+${r.age}</span>` },
      { key: 'bc', label: 'BC', html: (r) => `<span class="ell" title="${esc(r.bc)}">${esc(r.bc)}</span> ${App.alertBadge('broadcast', r.id)}` },
      { key: 'gen', label: 'Generated', num: true, fmt: (v, r) => (v ? F.int(v) : '<span class="nr">n/r</span>') },
      { key: 'sent', label: 'Sent', num: true, fmt: F.int },
    ];
    W('exec', (w, g, l) => {
      const rows = ex.open(l.st);
      w.innerHTML = `<div class="pills" role="group" aria-label="Filtrer par statut">${ex.chips(l.st) || '<span class="faint">aucun</span>'}</div><div data-g="open"></div>`;
      App.grid(w.querySelector('[data-g=open]'), { rows, columns: bcols, sort: ['gen', 'desc'], search: false, limit: 50, onRow: (r) => openBroadcast(r.id), empty: l.st ? 'Aucun broadcast dans ce statut' : 'Tous les broadcasts sont « Completed »' });
    });
    if (ex.trans.length) W('trans', (w) => {
      w.innerHTML = `<div style="margin-top:18px">${card('Transitions de statut depuis le fichier précédent', '<div data-g="trans"></div>', { note: 'Ex. Blackout Pause → Blackout Expired : la fenêtre a expiré, le volume ciblé n\'est jamais parti.' })}</div>`;
      App.grid(w.querySelector('[data-g=trans]'), { rows: ex.trans, search: false, limit: 50, onRow: (r) => openBroadcast(r.id), empty: 'Aucun changement de statut',
        columns: [{ key: 'from', label: 'Avant', html: (r) => App.stPill(r.from) }, { key: 'to', label: 'Maintenant', html: (r) => App.stPill(r.to) }, ...bcols.slice(1)] });
    });

    // Période
    const byDay = KPI.push(P, idx, (i) => P.v('d', i));
    const org = KPI.push(P, organic(idx), (i) => P.v('d', i));
    const seedDay = KPI.push(P, seeded(idx), (i) => P.v('d', i));
    const pf = App.provisionalFrom(days);
    const truncBands = [];
    days.forEach((d, k) => { const s = byDay.get(d); if (s && s.trunc > s.n / 2) { const b = truncBands[truncBands.length - 1]; if (b && b.to === k - 1) b.to = k; else truncBands.push({ from: k, to: k, color: '#d9620b', label: 'tronqué' }); } });
    const cats = [...new Set(idx.map((i) => P.v('cat', i)))].sort();
    const byCatDay = KPI.push(P, idx, (i) => P.v('cat', i) + '|' + P.v('d', i));
    const chartCard = (id, title, opt, drawChart) => W(id, (w, g, l) => { w.innerHTML = card(title, '<div class="chart"></div>', typeof opt === 'function' ? opt(l) : opt); drawChart(w.querySelector('.chart'), l); });

    W('funnel', (w) => { w.innerHTML = card('Entonnoir', funnel(tot), { note: `${F.int(tot.n)} broadcasts. Chaque étape : volume et part de l'étape précédente.` }); });
    chartCard('sent', 'Envoyés par catégorie', (l) => ({ note: l.day ? 'Répartition du jour par catégorie. Retirer le filtre local pour revenir à la série.' : 'Cliquer une barre pour voir la répartition du jour (dans cette carte uniquement).',
      local: [l.day && App.localBadge(F.day(l.day), 'day')] }), (c, l) => {
      if (l.day) {
        const dayCat = [...KPI.push(P, idx.filter((i) => P.v('d', i) === l.day), (i) => P.v('cat', i)).values()].sort((a, b) => b.sent - a.sent);
        Charts.hbars(c, { fmt: F.compact, rows: dayCat.map((x) => ({ label: x.key, value: x.sent, color: Charts.colorOf(x.key), note: `${x.n} bc` })) });
        return;
      }
      Charts.bars(c, { x: days, xfmt: F.date, fmt: F.compact, height: 260, onClick: (k) => App.setLocal('sent', { day: days[k] }),
        series: cats.map((cat) => ({ name: cat, color: Charts.colorOf(cat), values: days.map((d) => byCatDay.get(cat + '|' + d)?.sent || 0) })) });
    });
    chartCard('rates', 'Acknowledged % et Delivery %', { note: 'Delivery % dépend des accusés de réception (DLR) : comparer à son propre historique plutôt qu\'à un seuil absolu.' }, (c) =>
      Charts.line(c, { x: days, xfmt: F.date, fmt: F.pct1, zeroBased: false, series: [
        { name: 'Ack %', values: App.series(days, byDay, (s) => s.ack_rate), color: '#0a2357' },
        { name: 'Delivery %', values: App.series(days, byDay, (s) => s.delivery_rate), color: '#d9620b' }] }));
    chartCard('conv', 'Conv % hors seeding : observé et estimé à maturité', { note: 'Zone hachurée : conversions encore en train d\'arriver. Bande orange : jours tronqués (fin de mois).' }, (c) =>
      Charts.line(c, { x: days, xfmt: F.date, fmt: F.pct, provisionalFrom: pf, bands: truncBands, series: [
        { name: 'Observé', values: App.series(days, org, (s) => s.conv_rate), color: '#1a4fb0' },
        { name: 'Estimé à maturité', values: App.series(days, org, (s) => (s.pending > 0.005 ? s.conv_rate_est : null)), color: '#d9620b', dash: true }] }));
    chartCard('net', 'Net Conv % (TG − CG), hors seeding', {}, (c) =>
      Charts.line(c, { x: days, xfmt: F.date, fmt: F.pts, provisionalFrom: pf, zeroBased: false, series: [{ name: 'Net Conv %', values: App.series(days, org, (s) => s.net_conv_rate), color: '#0a2357' }] }));
    chartCard('seed', 'Conversions seeding et hors seeding', {}, (c) =>
      Charts.bars(c, { x: days, xfmt: F.date, fmt: F.compact, provisionalFrom: pf, series: [
        { name: 'Hors seeding', values: days.map((d) => org.get(d)?.conv || 0), color: '#1a4fb0' },
        { name: 'Seeding', values: days.map((d) => seedDay.get(d)?.conv || 0), color: '#f2c200' }] }));

    W('heat', (w, g, l) => heat(w, idx, days, l));

    // Par catégorie : un clic descend localement vers les campagnes de la catégorie
    W('cats', (w, g, l) => {
      const sub = l.cat ? idx.filter((i) => P.v('cat', i) === l.cat) : idx;
      const crumb = l.cat ? `<button data-local="cat" data-val="">Toutes les catégories</button> › <b>${esc(l.cat)}</b>` : '<b>Toutes les catégories</b> <span class="faint">· cliquer une ligne pour voir ses campagnes</span>';
      w.innerHTML = card(`<span class="crumb">${crumb}</span>`, '<div data-g="cats"></div>', {
        flush: true, note: l.cat ? 'Campagnes de la catégorie (filtre de cette carte uniquement). Cliquer une campagne ouvre son détail.' : 'Cliquer une catégorie pour voir ses campagnes (dans cette carte uniquement).',
        local: [l.cat && App.localBadge(l.cat, 'cat')] });
      const rows = l.cat
        ? [...KPI.push(P, sub, (i) => P.v('camp', i)).values()].map((x) => ({ ...x, _key: x.key, cat: x.key, nbc: new Set(sub.filter((i) => P.v('camp', i) === x.key).map((i) => P.c.bc[i])).size, est_conv: x.est.conv }))
        : categoryRows(idx);
      const subTot = KPI.push(P, sub);
      App.grid(w.querySelector('[data-g=cats]'), {
        rows, sort: ['sent', 'desc'], csv: l.cat ? `push_campagnes_${l.cat}` : 'push_categories', search: !!l.cat, total: { ...subTot, est_conv: subTot.est.conv },
        columns: [{ key: 'cat', label: l.cat ? 'Campagne' : 'Catégorie', html: (r) => (r.cat ? `<b>${esc(r.cat)}</b>${l.cat ? '' : catTag(r.cat)} ${App.alertBadge(l.cat ? 'campaign' : 'category', r.cat)}` : '') }, { key: 'nbc', label: 'BC', num: true, fmt: F.int }, ...metricCols({ bar: true })],
        onRow: (r) => (l.cat ? openCampaign(r.cat) : App.setLocal('cats', { cat: r.cat })),
      });
    });

    // Top des BC : volume, base par envoi, fréquence (réglages locaux : classement, BC techniques)
    const TOP_RANK = { vol: ['Volume', 'sent'], base: ['Base par envoi', 'avg'], freq: ['Fréquence', 'freqScore'] };   // fréquence départagée par le volume
    W('top', (w, g, l) => {
      const rank = TOP_RANK[l.rank] ? l.rank : 'vol', withTech = l.tech === '1';
      const by = new Map();
      // Tous les broadcasts sont comptés, y compris ceux sans envoi (Sent = 0 : bloqués, expirés, flows « Delivering ») :
      // ils restent visibles (colonne Generated). Fréquence et base par envoi ne retiennent que les envois effectifs.
      const tech = { bcs: new Set(), n: 0, gen: 0, sent: 0, sent0: 0, st: new Map() };
      for (const i of idx) {
        const bc = P.v('bc', i);
        if (App.isTechnical(bc)) {
          tech.bcs.add(bc); tech.n++; tech.gen += P.c.gen[i] || 0; tech.sent += P.c.sent[i]; if (!P.c.sent[i]) tech.sent0++;
          tech.st.set(P.v('st', i), (tech.st.get(P.v('st', i)) || 0) + 1);
          if (!withTech) continue;
        }
        let r = by.get(bc);
        if (!r) by.set(bc, (r = { _key: bc, bc, cat: P.v('cat', i), camp: P.v('camp', i), n: 0, nSent: 0, days: new Set(), sent: 0, gen: 0, max: 0, conv: 0, seed: 0 }));
        r.n++; r.gen += P.c.gen[i] || 0; r.conv += P.c.conv[i]; if (P.c.seed[i]) r.seed++;
        if (P.c.sent[i]) { r.nSent++; r.days.add(P.v('d', i)); r.sent += P.c.sent[i]; r.max = Math.max(r.max, P.c.sent[i]); }
      }
      const tot = [...by.values()].reduce((a, r) => a + r.sent, 0) || 1;
      const rows = [...by.values()].map((r) => ({ ...r, days: r.days.size, avg: r.nSent ? r.sent / r.nSent : 0, share: r.sent / tot, perWeek: (r.days.size / days.length) * 7, conv_rate: KPI.rate(r.conv, r.sent), freqScore: r.days.size * 1e12 + r.sent }));
      const mk = TOP_RANK[rank][1];
      [...rows].sort((a, b) => b[mk] - a[mk]).forEach((r, k, arr) => { r.rk = k && arr[k - 1][mk] === r[mk] ? arr[k - 1].rk : k + 1; });
      const stTxt = [...tech.st.entries()].sort((a, b) => b[1] - a[1]).map(([k, v]) => `${v} ${esc(k)}`).join(', ');
      const techLine = !tech.n ? '<div class="callout info" style="margin-bottom:12px">Aucun BC technique sur la période et les filtres de la page.</div>'
        : `<div class="callout ${tech.sent0 ? '' : 'info'}" style="margin-bottom:12px"><b>${tech.bcs.size} BC technique${tech.bcs.size > 1 ? 's' : ''}</b> (${esc((App.meta.technical_bc_patterns || []).join(', '))}) sur la période : ${F.int(tech.n)} broadcasts, ${F.compact(tech.gen)} générés, <b>${F.compact(tech.sent)} envoyés</b> (${stTxt}).${tech.sent0 ? ` ${F.int(tech.sent0)} broadcast(s) avec Sent = 0 : générés mais non envoyés ou non remontés par NEON-dx.` : ''} ${withTech ? 'Inclus dans le classement.' : 'Exclus du classement : cliquer « Avec » pour les afficher.'}</div>`;
      w.innerHTML = card(`Classement par <span style="color:var(--blue)">${TOP_RANK[rank][0].toLowerCase()}</span>`, '<div data-g="top"></div>', {
        flush: true,
        right: `${App.localSeg('rank', Object.entries(TOP_RANK).map(([k, [lbl]]) => [k, lbl]), rank)}${App.localSeg('tech', [['', 'Sans BC techniques'], ['1', 'Avec']], withTech ? '1' : '')}`,
        note: 'BC techniques : BC dont le nom contient un motif de technical_bc_patterns (config.yaml), ex. « Dummy BC » qui déclenchent des flows.' });
      w.querySelector('[data-g=top]').insertAdjacentHTML('beforebegin', techLine);
      App.grid(w.querySelector('[data-g=top]'), {
        rows, sort: [TOP_RANK[rank][1], 'desc'], csv: `push_top_bc_${rank}`, limit: 50, onRow: (r) => openBc(r.bc), searchText: (r) => `${r.bc} ${r.camp} ${r.cat}`,
        columns: [
          { key: 'rk', label: '#', num: true, sort: (r) => -r.rk, fmt: (v) => `<span class="muted">${v}</span>`, csv: (r) => r.rk },
          { key: 'bc', label: 'BC', html: (r) => `<span class="ell" title="${esc(r.bc)}" style="max-width:340px;font-weight:600">${esc(r.bc)}</span>${bcTags(r.bc)}${r.seed ? ' <span class="badge seed">seeding</span>' : ''} ${App.alertBadge('bc_name', r.bc)}` },
          { key: 'cat', label: 'Catégorie', html: (r) => `<span class="small">${esc(r.cat)}</span>` },
          { key: 'camp', label: 'Campagne', html: (r) => `<span class="small muted ell" style="max-width:200px" title="${esc(r.camp)}">${esc(r.camp)}</span>` },
          { key: 'sent', label: 'Sent total', num: true, fmt: F.int, bar: rank === 'vol' ? true : undefined },
          { key: 'share', label: 'Part du volume', num: true, fmt: F.pct1 },
          { key: 'avg', label: 'Sent moyen / envoi', num: true, fmt: F.int, bar: rank === 'base' ? true : undefined },
          { key: 'max', label: 'Sent max', num: true, fmt: F.int },
          { key: 'gen', label: 'Generated', num: true, fmt: (v, r) => (v ? F.int(v) : '<span class="nr">n/r</span>'), csv: (r) => r.gen },
          { key: 'n', label: 'Broadcasts', num: true, fmt: (v, r) => (r.nSent < v ? `${F.int(v)} <span class="badge trunc" title="${v - r.nSent} broadcast(s) avec Sent = 0">${F.int(v - r.nSent)} sans envoi</span>` : F.int(v)), csv: (r) => r.n },
          { key: 'days', label: "Jours d'envoi", num: true, fmt: (v) => `${F.int(v)} / ${days.length}`, csv: (r) => r.days, bar: rank === 'freq' ? true : undefined, barMax: days.length },
          { key: 'perWeek', label: 'Jours / semaine', num: true, fmt: (v) => v.toFixed(1).replace('.', ',') },
          { key: 'conv_rate', label: 'Conv %', num: true, fmt: F.pct },
        ] });
    });

    W('tree', (w) => {
      w.innerHTML = '<div class="card flush" data-g="tree"></div>';  // panneau : la section porte le fond
      App.grid(w.querySelector('[data-g=tree]'), {
        rows: explorer(idx), sort: ['sent', 'desc'], csv: 'push_explorateur', tall: true, tree: true,
        searchText: (r) => r.label + ' ' + (r._children || []).map((c) => c.label + ' ' + (c._children || []).map((x) => x.label).join(' ')).join(' '),
        columns: [
          { key: 'label', label: 'Campagne / BC / Broadcast', html: (r) => `<span class="ell" title="${esc(r.label)}">${r.type === 'broadcast' ? `${App.stPill(r.status)} ` : ''}${esc(r.label)}</span>${r.type === 'campaign' ? catTag(r.cat) + ` <span class="faint small">${esc(r.cat)}</span>` : ''}${r.type === 'bc' ? bcTags(r.label, r) : ''} ${App.alertBadge(r.type === 'bc' ? 'bc_name' : r.type, r.type === 'broadcast' ? r.id : r.label)}` },
          ...metricCols({ bar: true }),
        ],
        onRow: (r) => (r.type === 'bc' ? openBc(r.label) : r.type === 'broadcast' ? openBroadcast(r.id) : openCampaign(r.label)),
      });
    });
  }

  // ------------------------------------------------------------------ tiroirs
  function entityDrawer(title, subtitle, ids, alerts, extraHtml = '', after) {
    const s = KPI.push(P, ids);
    const byDay = KPI.push(P, ids, (i) => P.v('d', i));
    const ds = [...byDay.keys()].sort();
    const days = ds.length ? App.range(ds[0], ds[ds.length - 1]) : [];
    const rows = ids.map(brow);
    App.drawer(`<div class="small muted">${subtitle}</div><h2>${esc(title)}</h2>`,
      `<div class="grid tiles">
        ${tile({ label: 'Sent', value: F.int(s.sent), sub: `${s.n} broadcast(s)` })}
        ${tile({ label: 'Ack % · Delivery %', value: `${F.pct1(s.ack_rate)} · ${F.pct1(s.delivery_rate)}` })}
        ${tile({ label: 'Conversions', value: F.int(s.conv), prov: s.pending > 0.01, sub: s.pending > 0.01 ? `≈ ${F.int(s.est.conv)} à maturité` : 'définitif', badge: s.truncShare > 0.01 ? '<span class="badge trunc">tronqué</span>' : '' })}
        ${tile({ label: 'Conv % · Net', value: F.pct(s.conv_rate), sub: `Net ${F.pts(s.net_conv_rate)} · CG ${s.cg ? F.pct(s.cg_conv_rate) : 'aucun'}` })}
      </div>
      ${extraHtml}
      ${alerts.length ? `<div><h3>Alertes actives (${alerts.length})</h3><ul class="plain">${alerts.map((a) => `<li><a href="#" data-open-drawer="alert:${a.id}"><span class="sev ${a.severity}"></span> <b>${esc(a.rule_id)}</b> ${esc(a.rule_name)}</a><div class="small muted">${esc(a.message)}</div></li>`).join('')}</ul></div>` : ''}
      <div><h3>Envoyés par jour</h3><div class="chart" data-c="d1"></div></div>
      <div><h3>Broadcasts</h3><div data-g="b"></div></div>`,
      (body) => {
        Charts.bars(body.querySelector('[data-c=d1]'), { x: days, xfmt: F.date, fmt: F.compact, height: 150, provisionalFrom: App.provisionalFrom(days),
          series: [{ name: 'Sent', values: App.series(days, byDay, (x) => x.sent), color: '#b9cbee' }] });
        App.grid(body.querySelector('[data-g=b]'), { rows, search: rows.length > 15, limit: 100, sort: ['date', 'desc'], onRow: (r) => openBroadcast(r.id),
          columns: [
            { key: 'date', label: 'Envoi', fmt: (v, r) => `${F.date(v)} ${bcState(r)}` }, { key: 'id', label: 'ID' },
            { key: 'status', label: 'Statut', html: (r) => `${App.stPill(r.status)}${r.seed ? ' <span class="badge seed">seeding</span>' : ''}` },
            { key: 'sent', label: 'Sent', num: true, fmt: F.int }, { key: 'dlv_rate', label: 'Delivery %', num: true, fmt: F.pct },
            { key: 'conv', label: 'Conv', num: true, fmt: F.int }, { key: 'conv_rate', label: 'Conv %', num: true, fmt: F.pct },
          ] });
        after?.(body);
      });
  }

  function openBc(name) {
    const ids = P.all.filter((i) => P.v('bc', i) === name);
    if (!ids.length) return App.toast(`BC introuvable : ${name}`, true);
    const sc = (App.D.analytics?.periods?.tout?.scorecard_bc || []).find((r) => r.bc_name === name);
    const uplift = sc ? `<div><h3>Incrémentalité (envois matures, hors seeding)</h3><p style="margin:0">Uplift <b>${F.pts(sc.uplift)}</b> [IC 95 % ${F.pts(sc.ci_low)} ; ${F.pts(sc.ci_high)}] · p = ${sc.p_value == null ? '–' : sc.p_value.toFixed(3)} · <b>${esc(sc.verdict)}</b> · ≈ ${F.int(sc.incremental_conversions)} conversions incrémentales</p></div>` : '';
    entityDrawer(name, `BC · ${esc(P.v('camp', ids[0]))} · ${esc(P.v('cat', ids[0]))}${bcTags(name, KPI.push(P, ids))}`, ids, App.alertsFor('bc_name', name), uplift);
  }
  function openCampaign(name) {
    const ids = P.all.filter((i) => P.v('camp', i) === name);
    if (!ids.length) return;
    entityDrawer(name, `Campagne · ${esc(P.v('cat', ids[0]))}`, ids, App.alertsFor('campaign', name));
  }
  function openBroadcast(id) {
    id = +id;
    const i = P.all.find((k) => P.c.id[k] === id);
    if (i == null) return App.toast(`Broadcast ${id} absent de l'historique`, true);
    const r = brow(i);
    const vers = [];
    for (let k = 0; k < V.n; k++) if (V.c.id[k] === id) vers.push({ _key: k, snap: App.snaps[V.c.snap[k]]?.snapshot_date, age: V.c.age[k], st: V.v('st', k), conv: V.c.conv[k], cgc: V.c.cgc[k], fs: V.c.fs[k], val: V.c.val[k] });
    const est = r.comp < 1 ? r.conv / r.comp : r.conv;
    const state = P.c.lost[i] ? `<span class="badge alert">disparu</span> absent des fichiers NEON-dx suivants depuis le ${F.date(App.snaps[P.c.snap[i]].snapshot_date)} (vu à J+${r.age}) : valeurs figées, ≈ ${F.int(est - r.conv)} conversions jamais remontées` : r.comp >= 0.99 ? '<span class="badge ok">définitif</span>' : r.frozen ? `<span class="badge trunc">tronqué</span> absent des fichiers suivants à J+${r.age} : ≈ ${F.int(est - r.conv)} conversions ne seront jamais remontées` : `<span class="badge prov">en maturation</span> J+${r.age}, complétude ≈ ${F.pct1(r.comp)}, attendu ≈ ${F.int(est)}`;
    App.drawer(`<div class="small muted">Broadcast ${id} · ${esc(r.cat)}</div><h2>${esc(r.name || r.bc)}</h2>`,
      `<dl class="kv"><dt>BC</dt><dd><a href="#" data-open-drawer="bc:${esc(r.bc)}">${esc(r.bc)}</a></dd><dt>Campagne</dt><dd>${esc(r.camp)}</dd>
        <dt>Envoi</dt><dd>${F.day(r.date)}${P.c.hour[i] >= 0 ? ` vers ${P.c.hour[i]} h` : ''}</dd><dt>Statut</dt><dd>${App.stPill(r.status)}${r.seed ? ' <span class="badge seed">seeding</span>' : ''}</dd>
        <dt>Generated · Sent</dt><dd>${r.gen ? F.int(r.gen) : '<span class="nr">n/r</span>'} · ${F.int(r.sent)}</dd>
        <dt>Ack · Delivered</dt><dd>${F.int(r.ack)} (${F.pct(KPI.rate(r.ack, r.sent))}) · ${F.int(r.dlv)} (${F.pct(r.dlv_rate)})</dd>
        <dt>Conversions</dt><dd><b>${F.int(r.conv)}</b> (${F.pct(r.conv_rate)}) ${state}</dd>
        <dt>Groupe de contrôle</dt><dd>${P.c.cg[i] ? `${F.int(P.c.cgc[i])} / ${F.int(P.c.cg[i])} (${F.pct(KPI.rate(P.c.cgc[i], P.c.cg[i]))})` : '<span class="nr">aucun (CG = 0)</span>'}</dd>
        <dt>Fulfillment</dt><dd>${F.int(P.c.fs[i])} succès · ${F.int(P.c.ff[i])} échecs</dd><dt>Valeur</dt><dd>${P.c.val[i] ? F.money(P.c.val[i]) : r.conv ? '<span class="nr">n/r</span>' : '–'}</dd></dl>
      ${App.alertsFor('broadcast', id).map((a) => `<div class="callout"><a href="#" data-open-drawer="alert:${a.id}"><b>${esc(a.rule_id)}</b></a> ${esc(a.message)}</div>`).join('')}
      <div><h3>Ce que savait chaque fichier ${App.help('Une ligne par changement observé (conversions, statut…). Pointillés : courbe de maturité attendue.')}</h3><div class="chart" data-c="v"></div><div data-g="v"></div></div>`,
      (body) => {
        if (!vers.some((v) => v.conv > 0)) body.querySelector('[data-c=v]').innerHTML = '<p class="small muted" style="margin:0">Aucune conversion remontée à ce jour.</p>';
        else {
          const ages = App.range('2000-01-01', App.addDays('2000-01-01', Math.max(r.age, KPI.refAge))).map((_, k) => k);
          const byAge = new Map(vers.map((v) => [v.age, v.conv]));
          let last = null;
          const obs = ages.map((a) => (byAge.has(a) ? (last = byAge.get(a)) : a <= r.age && last != null ? last : null));
          Charts.line(body.querySelector('[data-c=v]'), { x: ages, xfmt: (a) => 'J+' + a, fmt: F.int, height: 160, series: [
            { name: 'Conversions connues', values: obs, color: '#1a4fb0' },
            { name: 'Attendu (courbe)', values: ages.map((a) => Math.round(est * KPI.completion('conv', a))), color: '#d9620b', dash: true }] });
        }
        App.grid(body.querySelector('[data-g=v]'), { rows: vers, search: false, sort: ['age', 'asc'], columns: [
          { key: 'snap', label: 'Fichier', fmt: F.date }, { key: 'age', label: 'Âge', fmt: (v) => 'J+' + v },
          { key: 'st', label: 'Statut', html: (v) => App.stPill(v.st) },
          { key: 'conv', label: 'Conv', num: true, fmt: F.int }, { key: 'cgc', label: 'CG conv', num: true, fmt: F.int },
          { key: 'fs', label: 'Fulf. OK', num: true, fmt: F.int }, { key: 'val', label: 'Valeur', num: true, fmt: F.money }] });
      });
  }

  App.drawerOpeners.bc = openBc;
  App.drawerOpeners.broadcast = openBroadcast;
  App.drawerOpeners.campaign = openCampaign;
  App.tab('push', {
    title: 'Push Campaigns', render, defaults: { p: '30j' }, multi: ['cat', 'camp', 'bc', 'st'],
    filters: { dims: DIMS, extraLabel: 'Seeding', chips: (st) => (st.seed ? [{ label: `Seeding : ${SEED_FR[st.seed]}`, patch: { seed: null } }] : []), extra: (st) => `<div class="seg">${Object.entries(SEED_FR).map(([k, l]) => `<button data-set="seed" data-val="${k}" class="${(st.seed || '') === k ? 'on' : ''}">${l}</button>`).join('')}</div>` },
  });
})();
