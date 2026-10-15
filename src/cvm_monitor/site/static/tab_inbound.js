/* Onglet Inbound Marketing : « Les offres présentées sont-elles achetées, les achats aboutissent-ils,
 * et les données IM sont-elles à jour ? » */
'use strict';
(() => {
  const { I, F, esc, card, section, tile } = App;
  const DIMS = [
    { key: 'tp', label: 'Touchpoint', T: 'I', dim: 'tp' },
    { key: 'prog', label: 'Programme', T: 'I', dim: 'prog' },
    { key: 'offer', label: 'Offre', T: 'I', dim: 'offer', all: 'Toutes' },
    { key: 'rst', label: 'Statut règle', T: 'I', dim: 'rst' },
  ];
  Charts.fix('tp:USSD', '#7aa0e0');
  Charts.fix('tp:YAS APP', '#0a2357');
  const iDates = I.d.d || [];
  const lastImDate = iDates[iDates.length - 1];
  const latestSnap = App.snaps.length ? App.snaps[App.snaps.length - 1].snapshot_date : null;
  const STALE_H = 48;
  const ruleName = (id) => App.imRules.get(String(id))?.name || `Règle ${id}`;

  /** Heures écoulées entre le dernier rafraîchissement d'une règle et le lendemain du fichier (≈ 06 h GMT). */
  function refreshLag(r) {
    if (!r?.last_refresh || !latestSnap) return null;
    const ref = new Date(App.addDays(latestSnap, 1) + 'T06:00:00Z'), lr = new Date(r.last_refresh.replace(' ', 'T') + 'Z');
    return isNaN(lr) ? null : (ref - lr) / 36e5;
  }
  const isStale = (r) => r && r.status === 'Active' && r.snapshot_date === latestSnap && (refreshLag(r) ?? 0) > STALE_H;
  const ago = (h) => (h == null ? '–' : h < 48 ? `${Math.round(h)} h` : `${Math.round(h / 24)} j`);

  const deadDays = (() => {
    const by = KPI.im(I, I.all, (i) => I.v('d', i));
    return new Set([...by.values()].filter((s) => s.imp > 0 && s.attempts === 0).map((s) => s.key));
  })();
  function bandsFor(days) {
    const out = [];
    days.forEach((d, k) => { if (!deadDays.has(d)) return; const b = out[out.length - 1]; if (b && b.to === k - 1) b.to = k; else out.push({ from: k, to: k, color: '#8a93a6', label: 'fulfillment non alimenté' }); });
    return out;
  }
  const rateOrNr = (s, key) => (s.attempts === 0 && s.imp > 0 ? '<span class="nr" title="Aucun succès ni échec remonté par NEON-dx">n/r</span>' : F.pct(s[key]));

  function dayTiles(st, day) {
    const all = App.rows(I, st, DIMS, { period: false });
    const byDay = KPI.im(I, all, (i) => I.v('d', i));
    const s = byDay.get(day) || KPI.imRates({ imp: 0, fs: 0, ff: 0 });
    const last30 = App.range(App.addDays(day, -29), day);
    const sp = (fn) => Charts.spark(App.series(last30, byDay, fn));
    const dl = (fn, kind, inverse) => { const r = App.refs(byDay, day, fn), v = fn(s); return { v: v == null || r.avg7 == null ? null : kind === 'pts' ? v - r.avg7 : r.avg7 ? v / r.avg7 - 1 : null, kind, inverse }; };
    const dayRows = all.filter((i) => I.v('d', i) === day);
    const activeRules = new Set(dayRows.filter((i) => I.c.imp[i] > 0).map((i) => I.v('rule', i)));
    const rules = [...App.imRules.values()];
    const stale = rules.filter(isStale);
    const lastRefresh = rules.map((r) => r.last_refresh).filter(Boolean).sort().pop();
    const dead = s.imp > 0 && s.attempts === 0;
    const known = App.imRules.size;
    return `<div class="grid tiles">
      ${tile({ label: 'Impressions', value: F.int(s.imp), delta: dl((x) => x.imp), spark: sp((x) => x.imp) })}
      ${tile({ label: 'Achats réussis', value: F.int(s.fs), nr: dead, delta: dead ? null : dl((x) => x.fs), sub: dead ? 'fulfillment non remonté' : '', spark: sp((x) => x.fs) })}
      ${tile({ label: "Taux d'achat", value: F.pct(s.take_rate), nr: dead, delta: dead ? null : dl((x) => x.take_rate, 'pts'), hint: 'Fulfillment Success ÷ Impressions', spark: sp((x) => x.take_rate) })}
      ${tile({ label: 'Fulfillment Failures %', value: F.pct(s.failure_rate), nr: s.attempts === 0, delta: dl((x) => x.failure_rate, 'pts', true), sub: `${F.int(s.ff)} échecs / ${F.int(s.attempts)} tentatives`, spark: sp((x) => x.failure_rate) })}
      ${tile({ label: 'Règles actives ce jour', value: `${F.int(activeRules.size)} <small>/ ${F.int(known)} connues</small>`, hint: `Règles avec au moins une impression ce jour. Fraîcheur : règles Active non rafraîchies depuis plus de ${STALE_H} h.`,
        extra: `<div class="meter"><span style="width:${known ? (activeRules.size / known * 100).toFixed(1) : 0}%"></span></div>
          <div class="kvline"><span>Refresh > ${STALE_H} h</span><strong style="${stale.length ? 'color:var(--warn)' : ''}">${stale.length ? `${stale.length} en retard` : 'à jour'}</strong></div>
          <div class="kvline"><span>Dernier refresh</span><strong>${F.dt(lastRefresh)}</strong></div>` })}
    </div>`;
  }

  function touchpoints(idx) {
    const by = KPI.im(I, idx, (i) => I.v('tp', i)), all = KPI.im(I, idx);
    return [...by.values()].sort((a, b) => b.imp - a.imp).map((s, k) => {
      const dead = s.imp > 0 && s.attempts === 0;
      const share = `<span class="badge ${k ? 'grey' : 'ok'}">${F.pct1(all.imp ? s.imp / all.imp : null)} des impressions</span>`;
      const fr = s.attempts && s.failure_rate >= 0.3 ? 'color:var(--warn)' : '';
      return `<div class="card tpcard">${`<div class="head"><div class="head-l"><h2>${esc(s.key)}</h2>${App.alertBadge('touchpoint', s.key)}</div><div class="head-r">${share}</div></div>`}
        <div class="stats"><div><span>Impressions</span><b>${F.int(s.imp)}</b></div><div><span>Achats réussis</span><b>${dead ? '<span class="nr">n/r</span>' : F.int(s.fs)}</b></div>
        ${dead ? '' : `<div><span>Taux d'achat</span><b>${rateOrNr(s, 'take_rate')}</b></div><div><span>Failure %</span><b style="${fr}">${rateOrNr(s, 'failure_rate')}</b></div>`}</div>
        ${dead ? '<div class="callout info" style="margin-top:14px">Aucun fulfillment remonté : taux d\'achat et Failure % non renseignés (pas 0 %).</div>' : ''}</div>`;
    }).join('');
  }

  /** « À surveiller » : constats chiffrés sur la période, chacun avec son accès direct. */
  function watchList(idx, rr) {
    const out = [];
    const ic = { warn: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>',
      cart: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.7 13.4a2 2 0 0 0 2 1.6h9.7a2 2 0 0 0 2-1.6L23 6H6"/><path d="m3 3 18 18"/></svg>',
      phone: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="2" width="14" height="20" rx="2"/><path d="M12 18h.01"/></svg>',
      db: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5"/><path d="M3 12c0 1.7 4 3 9 3s9-1.3 9-3"/></svg>',
      clock: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>' };
    const fail = rr.filter(PREF.fail[1]).sort((a, b) => b.ff - a.ff);
    if (fail.length) out.push({ kind: 'warn', ic: ic.warn, big: `${fail.length} règle${fail.length > 1 ? 's' : ''}`, text: `avec un Failure % ≥ 50 % (≥ 100 tentatives). Pire cas : ${esc(fail[0].name)} : ${F.int(fail[0].ff)} échecs.`, go: 'fail', goLbl: 'Voir les règles en échec →' });
    const noach = rr.filter(PREF.noach[1]).sort((a, b) => b.imp - a.imp);
    if (noach.length) out.push({ kind: 'warn', ic: ic.cart, big: `${noach.length} règle${noach.length > 1 ? 's' : ''} sans achat`, text: `malgré ≥ 1 000 impressions, dont ${esc(noach[0].name)} (${F.int(noach[0].imp)} impressions).`, go: 'noach', goLbl: 'Voir les règles →' });
    const stale = rr.filter(PREF.stale[1]);
    if (stale.length) out.push({ kind: 'warn', ic: ic.clock, big: `${stale.length} règle${stale.length > 1 ? 's' : ''} non rafraîchie${stale.length > 1 ? 's' : ''}`, text: `Active mais sans refresh depuis plus de ${STALE_H} h au dernier fichier : leurs chiffres peuvent être en retard.`, go: 'stale', goLbl: 'Voir les règles →' });
    for (const t of KPI.im(I, idx, (i) => I.v('tp', i)).values())
      if (t.imp > 0 && t.attempts === 0) out.push({ kind: 'info', ic: ic.phone, big: `${esc(t.key)} · taux inconnu`, text: `${F.int(t.imp)} impressions sans fulfillment remonté sur la période. Le taux d'achat n'est pas 0 % : il est non renseigné.` });
    const sums = KPI.im(I, I.all);
    const empty = [['acc', 'Accepted'], ['dec', 'Declined'], ['later', 'May be Later'], ['conv', 'Conversions IM']].filter(([k]) => sums[k] === 0).map(([, l]) => l);
    if (empty.length) out.push({ kind: 'info', ic: ic.db, big: `${empty.length} colonne${empty.length > 1 ? 's' : ''} vide${empty.length > 1 ? 's' : ''}`, text: `${empty.map((x) => `« ${x} »`).join(', ')} ne ${empty.length > 1 ? 'sont' : 'est'} jamais alimentée${empty.length > 1 ? 's' : ''} dans NEON-dx : affichée${empty.length > 1 ? 's' : ''} n/r, jamais 0. Surveillée${empty.length > 1 ? 's' : ''} : un signal apparaîtra dès qu'elle${empty.length > 1 ? 's' : ''} se remplira.` });
    if (!out.length) return '<div class="watch"><div><div class="ic">✓</div><div class="tx"><div class="big">Rien à signaler</div><p>Aucune règle en échec, sans achat ou en retard sur la période.</p></div></div></div>';
    return `<div class="watch">${out.map((w) => `<div class="${w.kind === 'warn' ? 'w-warn' : ''}"><div class="ic">${w.ic}</div><div class="tx"><div class="big">${w.big}</div><p>${w.text}</p>${w.go ? `<button class="go" data-watch="${w.go}">${w.goLbl}</button>` : ''}</div></div>`).join('')}</div>`;
  }

  function ruleRows(idx) {
    const by = KPI.im(I, idx, (i) => I.v('rule', i));
    const days = new Map(), offers = new Map(), daily = new Map();
    for (const i of idx) {
      const r = I.v('rule', i), d = I.v('d', i);
      if (!days.has(r)) { days.set(r, new Set()); offers.set(r, new Set()); }
      if (I.c.imp[i] > 0) days.get(r).add(d);
      offers.get(r).add(I.v('offer', i));
      daily.set(r + '|' + d, (daily.get(r + '|' + d) || 0) + I.c.imp[i]);
    }
    const last14 = App.range(App.addDays(lastImDate, -13), lastImDate);
    const firstOfMonth = (latestSnap || '').slice(0, 8) + '01';
    return [...by.values()].map((s) => {
      const m = App.imRules.get(s.key) || {};
      const lag = refreshLag(m);
      return { ...s, _key: s.key, id: s.key, name: m.name || s.key, program: m.program, touchpoint: m.touchpoint, status: m.status, last_refresh: m.last_refresh, lag,
        stale: isStale(m), days: days.get(s.key).size, offers: offers.get(s.key).size, first_date: m.first_date, last_seen: m.snapshot_date,
        isNew: m.first_date >= App.addDays(lastImDate, -6) && m.first_date > firstOfMonth, gone: m.snapshot_date && m.snapshot_date < latestSnap,
        spark: last14.map((d) => daily.get(s.key + '|' + d) ?? null) };
    });
  }
  const PREF = {
    '': ['Toutes', () => true],
    fail: ['En échec (Failure % ≥ 50 %)', (r) => r.attempts >= 100 && r.failure_rate >= 0.5],
    noach: ['Sans achat (≥ 1 000 impressions)', (r) => r.imp >= 1000 && r.fs === 0],
    stale: ['Non rafraîchies (> 48 h)', (r) => r.stale],
    inactive: ['Completed / Inactive avec impressions', (r) => r.status && r.status !== 'Active' && r.imp > 0],
    newgone: ['Nouvelles ou disparues', (r) => r.isNew || r.gone],
  };

  function render(el, st) {
    if (!I.n) { el.innerHTML = '<div class="empty">Aucune donnée Inbound.</div>'; return; }
    const idx = App.rows(I, st, DIMS);
    const days = App.periodDates(st).filter((d) => d <= lastImDate);
    const tot = KPI.im(I, idx);
    const rr = ruleRows(idx);
    const slot = (id) => `<div data-slot="${id}"></div>`;
    const tpList = [...new Set(idx.map((i) => I.v('tp', i)))].sort();
    const nProg = new Set(idx.map((i) => I.v('prog', i))).size;
    App.subtitle(`Offres poussées sur ${esc(tpList.join(' et ') || '–')} via les règles IM NEON-dx · ${F.int(rr.length)} règles · ${nProg} programme${nProg > 1 ? 's' : ''}`);
    el.innerHTML = `
      ${section('Jour J', slot('instant'), { id: 'im-instant', nav: 'Jour J', panel: true, note: 'Écarts vs moyenne des 7 jours précédents. Le Jour J ne concerne que cette section.' })}
      ${section('À surveiller', `<div data-watch-root>${watchList(idx, rr)}</div>`, { id: 'im-watch', nav: 'À surveiller', note: 'Constats chiffrés sur la période et les filtres de la page. Un lien ouvre directement les règles concernées.' })}
      ${section(`Période · ${F.date(days[0])} → ${F.dateFull(days[days.length - 1])}`, `<div class="split"><div class="wide">${slot('imp')}</div><div class="narrow">${touchpoints(idx)}</div></div><div class="grid g3" style="margin-top:14px">${['fs', 'take', 'fail'].map(slot).join('')}</div>`,
        { id: 'im-period', nav: 'Période', sub: `${F.int(tot.imp)} impressions · ${F.int(tot.fs)} achats · taux ${F.pct(tot.take_rate)} · failure ${F.pct1(tot.failure_rate)}` })}
      ${section('Programmes', slot('progs'), { id: 'im-progs', nav: 'Programmes', panel: true })}
      ${section('Règles IM', slot('rules'), { id: 'im-rules', nav: 'Règles IM', panel: true })}
      ${section('Offres', slot('offers'), { id: 'im-offers', nav: 'Offres', panel: true })}`;
    // Liens « Voir les règles… » : préfiltre de la carte Règles IM puis défilement jusqu'à elle.
    el.querySelector('[data-watch-root]').addEventListener('click', (ev) => {
      const b = ev.target.closest('[data-watch]');
      if (!b) return;
      const sec = document.getElementById('im-rules');
      if (sec.classList.contains('collapsed')) App.toggleSection(sec, true);
      App.setLocal('rules', { rf: b.dataset.watch });
      sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    const W = (id, draw) => App.widget(el.querySelector(`[data-slot=${id}]`), id, draw);

    // Instant t : Jour J local à la section
    W('instant', (w, g, l) => {
      const day = l.day && iDates.includes(l.day) ? l.day : lastImDate;
      w.innerHTML = card(`<span style="font-size:15px;font-weight:700;color:var(--ink-2)">${F.dayLong(day)}</span>`, dayTiles(st, day), {
        local: [day !== lastImDate ? App.localBadge(`Jour J : ${F.date(day)}`, 'day') : '<span class="badge yel">Dernier rapport disponible</span>'],
        right: App.dayNav(iDates, day, lastImDate) });
    });

    const bands = bandsFor(days);
    const tps = [...new Set(idx.map((i) => I.v('tp', i)))].sort();
    const progs = [...new Set(idx.map((i) => I.v('prog', i)))].sort();
    const byTpDay = KPI.im(I, idx, (i) => I.v('tp', i) + '|' + I.v('d', i));
    const byProgDay = KPI.im(I, idx, (i) => I.v('prog', i) + '|' + I.v('d', i));
    const byDay = KPI.im(I, idx, (i) => I.v('d', i));
    const chartCard = (id, title, opt, drawChart) => W(id, (w, g, l) => { w.innerHTML = card(title, '<div class="chart"></div>', typeof opt === 'function' ? opt(l) : opt); drawChart(w.querySelector('.chart'), l); });

    chartCard('imp', 'Impressions par jour et par canal', (l) => ({ note: l.day ? 'Répartition du jour par programme. Retirer le filtre pour revenir à la série.' : 'Cliquer une barre pour voir la répartition du jour par programme.',
      local: [l.day && App.localBadge(F.day(l.day), 'day')] }), (c, l) => {
      if (l.day) {
        const rows = [...KPI.im(I, idx.filter((i) => I.v('d', i) === l.day), (i) => I.v('prog', i)).values()].sort((a, b) => b.imp - a.imp);
        Charts.hbars(c, { fmt: F.compact, rows: rows.map((x) => ({ label: x.key, value: x.imp, color: Charts.colorOf('prog:' + x.key), note: x.attempts ? `${F.pct(x.take_rate)} d'achat` : 'fulfillment n/r' })) });
        return;
      }
      Charts.bars(c, { x: days, xfmt: F.date, fmt: F.compact, height: 260, onClick: (k) => App.setLocal('imp', { day: days[k] }), series: tps.map((t) => ({ name: t, color: Charts.colorOf('tp:' + t), values: days.map((d) => byTpDay.get(t + '|' + d)?.imp || 0) })) });
    });
    chartCard('fs', 'Achats réussis par programme', { note: 'Bandes grises : impressions présentes mais aucun fulfillment remonté (donnée NEON-dx manquante, pas zéro achat).' }, (c) =>
      Charts.bars(c, { x: days, xfmt: F.date, fmt: F.compact, note: (k) => (deadDays.has(days[k]) ? '<br>⚠ fulfillment non alimenté ce jour' : ''), series: progs.map((p) => ({ name: p, color: Charts.colorOf('prog:' + p), values: days.map((d) => byProgDay.get(p + '|' + d)?.fs || 0) })) }));
    chartCard('take', "Taux d'achat par touchpoint", {}, (c) =>
      Charts.line(c, { x: days, xfmt: F.date, fmt: F.pct, bands, series: tps.map((t) => ({ name: t, color: Charts.colorOf('tp:' + t), values: days.map((d) => { const s = byTpDay.get(t + '|' + d); return s && s.attempts > 0 ? s.take_rate : null; }) })) }));
    chartCard('fail', 'Fulfillment Failures %', {}, (c) =>
      Charts.line(c, { x: days, xfmt: F.date, fmt: F.pct1, bands, series: [{ name: 'Failure %', values: days.map((d) => { const s = byDay.get(d); return s && s.attempts > 0 ? s.failure_rate : null; }), color: '#d9620b' }] }));

    const frColor = (r) => (r.failure_rate >= 0.5 ? '#d9620b' : r.failure_rate >= 0.3 ? '#f0a35e' : '#3e6cc9');
    const imCols = [
      { key: 'imp', label: 'Impressions', num: true, fmt: F.int, bar: true },
      { key: 'fs', label: 'Achats', num: true, fmt: (v, r) => (r.attempts === 0 && r.imp > 0 ? '<span class="nr">n/r</span>' : F.int(v)) },
      { key: 'take_rate', label: "Taux d'achat", num: true, html: (r) => rateOrNr(r, 'take_rate'), csv: (r) => r.take_rate },
      { key: 'ff', label: 'Échecs', num: true, fmt: F.int },
      { key: 'failure_rate', label: 'Failure %', num: true, html: (r) => rateOrNr(r, 'failure_rate'), csv: (r) => r.failure_rate, bar: frColor, barMax: 1, sort: (r) => (r.attempts ? r.failure_rate : null) },
    ];
    const ruleCols = [
      { key: 'name', label: 'Règle', html: (r) => `<span class="ell" title="${esc(r.name)}">${esc(r.name)}</span> <span class="faint small">#${esc(r.id)}</span>${r.isNew ? ' <span class="badge ok">nouvelle</span>' : ''}${r.gone ? ' <span class="badge grey">absente du dernier fichier</span>' : ''} ${App.alertBadge('im_rule', r.id)}` },
      { key: 'program', label: 'Programme', html: (r) => `<span class="small">${esc(r.program || '')}</span>` }, { key: 'touchpoint', label: 'TP', html: (r) => `<span class="tp ${r.touchpoint === 'USSD' ? '' : 'alt'}">${esc(r.touchpoint || '')}</span>` },
      { key: 'status', label: 'Statut', html: (r) => App.stPill(r.status) },
      ...imCols,
      { key: 'days', label: 'Jours actifs', num: true, fmt: F.int },
      { key: 'lag', label: 'Dernier refresh', num: true, html: (r) => `<span class="${r.stale ? 'badge trunc' : 'small muted'}" title="${esc(r.last_refresh || '')} GMT">${ago(r.lag)}</span>`, csv: (r) => r.last_refresh },
      { key: 'spark', label: 'Impressions 14 j', sort: (r) => r.imp, html: (r) => `<div style="width:110px">${Charts.spark(r.spark, { w: 110, h: 20 })}</div>`, export: false },
    ];

    // Programmes : un clic descend localement vers les règles du programme
    W('progs', (w, g, l) => {
      const [lp, ltp] = (l.prog || '').split('|');
      const crumb = l.prog ? `<button data-local="prog" data-val="">Tous les programmes</button> › <b>${esc(lp)}</b> (${esc(ltp)})` : '<b>Tous les programmes</b> <span class="faint">· cliquer une ligne pour voir ses règles</span>';
      w.innerHTML = card(`<span class="crumb">${crumb}</span>`, '<div data-g="prog"></div>', {
        flush: true, note: l.prog ? 'Règles du programme (filtre de cette carte uniquement). Cliquer une règle ouvre son détail.' : 'Cliquer un programme pour voir ses règles (dans cette carte uniquement).',
        local: [l.prog && App.localBadge(`${lp} · ${ltp}`, 'prog')] });
      if (l.prog) {
        const sub = rr.filter((r) => r.program === lp && r.touchpoint === ltp);
        App.grid(w.querySelector('[data-g=prog]'), { rows: sub, sort: ['imp', 'desc'], csv: `im_regles_${lp}`, onRow: (r) => openRule(r.id), searchText: (r) => `${r.id} ${r.name}`, columns: ruleCols.filter((c) => c.key !== 'program') });
        return;
      }
      const progRows = [...KPI.im(I, idx, (i) => I.v('prog', i) + '|' + I.v('tp', i)).values()].map((x) => {
        const [program, tp] = x.key.split('|');
        const rules = new Set(idx.filter((i) => I.v('prog', i) === program && I.v('tp', i) === tp).map((i) => I.v('rule', i)));
        return { ...x, _key: x.key, program, tp, rules: rules.size };
      });
      App.grid(w.querySelector('[data-g=prog]'), { rows: progRows, sort: ['imp', 'desc'], search: false, csv: 'im_programmes', total: { ...tot, rules: App.imRules.size },
        columns: [{ key: 'program', label: 'Programme', html: (r) => (r.program ? `<b>${esc(r.program)}</b> ${App.alertBadge('program', r.program)}` : '') }, { key: 'tp', label: 'TP', html: (r) => (r.tp ? `<span class="tp ${r.tp === 'USSD' ? '' : 'alt'}">${esc(r.tp)}</span>` : '') }, { key: 'rules', label: 'Règles', num: true, fmt: F.int }, ...imCols],
        onRow: (r) => App.setLocal('progs', { prog: `${r.program}|${r.tp}` }) });
    });

    // Règles IM : préfiltre local
    W('rules', (w, g, l) => {
      const pref = PREF[l.rf || ''] ? l.rf || '' : '';
      w.innerHTML = `<div class="pills" role="group" aria-label="Préfiltre des règles">${Object.entries(PREF).map(([k, [lbl]]) => `<button class="pill ${pref === k ? 'on' : ''}" data-local="rf" data-val="${k}" title="Préfiltre de ce tableau uniquement">${lbl}<span class="n">${F.int(rr.filter(PREF[k][1]).length)}</span></button>`).join('')}</div><div class="card flush"><div data-g="rules"></div></div>`;
      App.grid(w.querySelector('[data-g=rules]'), { rows: rr.filter(PREF[pref][1]), sort: ['imp', 'desc'], csv: 'im_regles', tall: true, onRow: (r) => openRule(r.id),
        searchText: (r) => `${r.id} ${r.name} ${r.program} ${r.touchpoint}`, columns: ruleCols });
    });

    // Offres : un clic sur une barre filtre localement la table de la même carte
    const offers = [...KPI.im(I, idx, (i) => I.v('offer', i) + '|' + I.v('tp', i)).values()].map((x) => {
      const [offer, tp] = x.key.split('|');
      const sub = idx.filter((i) => I.v('offer', i) === offer && I.v('tp', i) === tp);
      return { ...x, _key: x.key, offer, tp, product: sub.length ? I.v('prod', sub[0]) : '', rules: new Set(sub.map((i) => I.v('rule', i))).size };
    });
    W('offers', (w, g, l) => {
      const hb = (o) => /hidden ?bonus/i.test(o.offer);
      w.innerHTML = `<div class="grid g2">${card('Top 12 des offres par achats', '<div data-c="offers"></div>', { note: `${F.int(offers.length)} offres sur la période. Les Hidden Bonus (cadeaux) convertissent très fort et sont signalés à part. Cliquer une offre filtre le tableau voisin (dans cette section uniquement).`,
          legend: [['#0a2357', 'Offre payante'], ['#f2c200', 'Hidden Bonus']] })}
        ${card('', '<div data-g="offers"></div>', { flush: true, local: [l.offer && App.localBadge(l.offer.replace('|', ' · '), 'offer')] })}</div>`;
      Charts.hbars(w.querySelector('[data-c=offers]'), { fmt: F.int, rows: [...offers].sort((a, b) => b.fs - a.fs).slice(0, 12).map((o) => ({ key: o._key, label: o.offer, value: o.fs, note: F.pct(o.take_rate), color: hb(o) ? '#f2c200' : '#0a2357', on: l.offer === o._key })),
        onClick: (r) => App.setLocal('offers', { offer: l.offer === r.key ? null : r.key }) });
      App.grid(w.querySelector('[data-g=offers]'), { rows: l.offer ? offers.filter((o) => o._key === l.offer) : offers, sort: ['fs', 'desc'], csv: 'im_offres',
        columns: [{ key: 'offer', label: 'Offre', html: (r) => `<span class="ell" title="${esc(r.offer)}" style="max-width:240px">${esc(r.offer)}</span>` }, { key: 'tp', label: 'TP', html: (r) => `<span class="tp ${r.tp === 'USSD' ? '' : 'alt'}">${esc(r.tp)}</span>` }, { key: 'rules', label: 'Règles', num: true }, ...imCols.filter((c) => c.key !== 'ff')] });
    });
  }

  function openRule(id) {
    id = String(id);
    const m = App.imRules.get(id) || { id, name: id };
    const idx = I.all.filter((i) => I.v('rule', i) === id);
    const byDay = KPI.im(I, idx, (i) => I.v('d', i));
    const ds = [...byDay.keys()].sort();
    const days = ds.length ? App.range(ds[0], ds[ds.length - 1]) : [];
    const offers = [...KPI.im(I, idx, (i) => I.v('offer', i)).values()].map((s) => ({ ...s, _key: s.key, offer: s.key }));
    const s = KPI.im(I, idx), lag = refreshLag(m);
    App.drawer(`<div class="small muted">Règle IM #${esc(id)} · ${esc(m.program || '')} · ${esc(m.touchpoint || '')}</div><h2>${esc(m.name)}</h2>`,
      `<div class="grid tiles">${tile({ label: 'Impressions', value: F.int(s.imp) })}${tile({ label: 'Achats', value: s.attempts ? F.int(s.fs) : '', nr: !s.attempts && s.imp > 0 })}
        ${tile({ label: "Taux d'achat", value: F.pct(s.take_rate), nr: !s.attempts && s.imp > 0 })}${tile({ label: 'Failure %', value: F.pct(s.failure_rate), nr: !s.attempts })}</div>
      ${App.alertsFor('im_rule', id).map((a) => `<div class="callout bad"><a href="#" data-open-drawer="alert:${a.id}"><b>${esc(a.rule_id)}</b></a> ${esc(a.message)}</div>`).join('')}
      <dl class="kv"><dt>Statut règle / programme</dt><dd>${esc(m.status || '–')} / ${esc(m.program_status || '–')}</dd>
        <dt>Créée</dt><dd>${esc(m.created_by || '–')} · ${F.dt(m.created_at)}</dd><dt>Modifiée</dt><dd>${esc(m.modified_by || '–')} · ${F.dt(m.modified_at)}</dd>
        <dt>Approuvée</dt><dd>${m.approved_by ? `${esc(m.approved_by)} · ${F.dt(m.approved_at)}` : '<span class="nr">non renseigné par NEON-dx</span>'}</dd>
        <dt>Dernier refresh</dt><dd>${F.dt(m.last_refresh)} GMT <span class="${isStale(m) ? 'badge trunc' : 'faint'}">il y a ${ago(lag)}</span></dd><dt>Prochain refresh</dt><dd>${F.dt(m.next_refresh)} GMT</dd>
        <dt>Présente</dt><dd>du ${F.dateFull(m.first_date)} au ${F.dateFull(m.last_date)} (dernier fichier : ${F.dateFull(m.snapshot_date)})</dd></dl>
      <div><h3>Par jour</h3><div class="chart" data-c="r1"></div></div><div><h3>Offres de la règle</h3><div data-g="o"></div></div>`,
      (body) => {
        Charts.line(body.querySelector('[data-c=r1]'), { x: days, xfmt: F.date, fmt: F.compact, height: 160, bands: bandsFor(days), series: [
          { name: 'Impressions', values: App.series(days, byDay, (x) => x.imp), color: '#b9cbee', area: true },
          { name: 'Achats', values: App.series(days, byDay, (x) => (x.attempts ? x.fs : null)), color: '#d9620b' }] });
        App.grid(body.querySelector('[data-g=o]'), { rows: offers, search: false, sort: ['imp', 'desc'], columns: [
          { key: 'offer', label: 'Offre' }, { key: 'imp', label: 'Impressions', num: true, fmt: F.int }, { key: 'fs', label: 'Achats', num: true, fmt: F.int },
          { key: 'take_rate', label: 'Taux', num: true, html: (r) => rateOrNr(r, 'take_rate') }, { key: 'failure_rate', label: 'Failure %', num: true, html: (r) => rateOrNr(r, 'failure_rate') }] });
      });
  }

  App.drawerOpeners.rule = openRule;
  App.tab('inbound', { title: 'Inbound Marketing', render, defaults: { p: '30j' }, multi: ['tp', 'prog', 'offer', 'rst'], filters: { dims: DIMS } });
})();
