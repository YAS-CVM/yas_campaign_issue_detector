/* Onglet Analytics : « Qu'est-ce que ça rapporte, où agir, et dans quelle mesure se fier aux chiffres ? »
 * Les statistiques (uplift et z-test, percentiles des pairs) sont pré-calculées en Python par période type ;
 * les tendances, distributions et matrices d'arrivée sont calculées ici à partir des faits embarqués. */
'use strict';
(() => {
  const { P, I, F, esc, card, section, tile } = App;
  const A = App.D.analytics || { presets: {}, periods: {} };
  const DIMS = [{ key: 'cat', label: 'Catégorie', T: 'P', dim: 'cat', all: 'Toutes' }];
  const VERDICT_COLOR = { 'Net Conversion +': '#1a4fb0', 'Net Conversion −': '#d9620b', 'Non significatif': '#8a93a6', 'CG = 0': '#c99a00', 'CG Conv < 30': '#c99a00' };
  const noConv = (c) => (App.meta.non_conversion_categories || []).includes(c);
  const preset = (st) => (A.periods[st.p] ? st.p : '30j');
  const catOk = (st) => { const s = st.cat && st.cat.length ? new Set(st.cat) : null; return (c) => !s || s.has(c); };

  // ------------------------------------------------------------------ 0. quand envoyer, quoi pousser
  function timing(el, st) {
    const T = A.periods[preset(st)]?.timing, TR = A.bc_trends || {};
    if (!T || !T.weekday?.length) { el.innerHTML = '<div class="empty">Pas assez d\'envois matures sur la période</div>'; return; }
    const val = (r) => (r.reliable && r.index != null ? r.index : 0);
    const tip = (r) => `<br>Conv % ${F.pct(r.conv_rate)} · Sent ${F.compact(r.sent)} · ${F.int(r.broadcasts)} broadcasts${r.reliable ? '' : '<br>⚠ échantillon trop faible pour comparer'}`;
    const bw = T.best_weekday, bh = T.best_hour;
    const best = (b, what) => (b ? tile({ label: `Meilleur ${what}`, value: esc(b.label), sub: `${b.index >= 1 ? '+' : ''}${F.int((b.index - 1) * 100)} % vs la norme des BC · Conv % ${F.pct(b.conv_rate)}`, hint: 'Indice = conversions observées ÷ conversions attendues au Conv % moyen des mêmes BC (BC envoyés sur plusieurs créneaux seulement).' }) : tile({ label: `Meilleur ${what}`, value: '–', sub: 'Pas assez de BC envoyés sur plusieurs créneaux' }));
    el.innerHTML = `<div class="grid tiles">${best(bw, 'jour d\'envoi')}${best(bh, 'heure d\'envoi')}</div>
      <div class="grid g2" style="margin-top:18px">
        ${card("Jour d'envoi : indice de conversion", '<div class="chart" data-c="bw"></div>', { note: 'Conversions ÷ conversions attendues au Conv % habituel des mêmes BC (1,00 = norme). Envois matures, hors seeding et catégories sans objectif de conversion. Barre vide = échantillon trop faible.' })}
        ${card("Heure d'envoi : indice de conversion", '<div class="chart" data-c="bh"></div>', { note: `Heures du blackout SMS exclues (${T.blackout?.length ? `${Math.min(...T.blackout.filter((h) => h >= 12))} h → ${Math.max(...T.blackout.filter((h) => h < 12)) + 1} h` : '19 h → 7 h'}, envoi réglementairement interdit). Minuit pile = flows déclenchés, non comparés.` })}
      </div>
      <div class="grid g2" style="margin-top:18px">
        <div class="card flush" data-g="slots"></div>
        <div class="card flush" data-g="dec"></div>
      </div>
      <div class="card flush" style="margin-top:18px" data-g="top"></div>`;
    Charts.bars(el.querySelector('[data-c=bw]'), { x: T.weekday.map((r) => r.label), fmt: (v) => v.toFixed(2), height: 170, series: [{ name: 'Indice', values: T.weekday.map(val), color: '#1a4fb0' }], note: (k) => tip(T.weekday[k]) });
    Charts.bars(el.querySelector('[data-c=bh]'), { x: T.hour.map((r) => r.label), fmt: (v) => v.toFixed(2), height: 170, series: [{ name: 'Indice', values: T.hour.map(val), color: '#3e6cc9' }], note: (k) => tip(T.hour[k]) });
    App.grid(el.querySelector('[data-g=slots]'), { rows: (T.slots || []).map((r, k) => ({ ...r, _key: k })), search: false, sort: ['index', 'desc'], csv: 'meilleurs_creneaux', columns: [
      { key: 'label', label: 'Meilleurs créneaux (jour × heure)' }, { key: 'index', label: 'Indice', num: true, fmt: (v) => v.toFixed(2) },
      { key: 'conv_rate', label: 'Conv %', num: true, fmt: F.pct }, { key: 'sent', label: 'Sent', num: true, fmt: F.compact }, { key: 'broadcasts', label: 'Broadcasts', num: true, fmt: F.int }] });
    App.grid(el.querySelector('[data-g=dec]'), { rows: (TR.declining || []).map((r, k) => ({ ...r, _key: k })), search: false, sort: ['lost_conversions', 'desc'], csv: 'bc_en_declin',
      onRow: (r) => App.openDrawer('bc:' + r.bc_name), columns: [
        { key: 'bc_name', label: `BC en déclin (${TR.window?.recent_days || 7} j vs ${TR.window?.base_days || 28} j précédents)`, html: (r) => `<span class="ell" title="${esc(r.bc_name)}">${esc(r.bc_name)}</span>` },
        { key: 'conv_rate_base', label: 'Conv % avant', num: true, fmt: F.pct }, { key: 'conv_rate', label: 'Conv % récent', num: true, fmt: F.pct },
        { key: 'rel_change', label: 'Évolution', num: true, fmt: (v) => `<b style="color:var(--warn)">${F.signedPct(v)}</b>` },
        { key: 'lost_conversions', label: 'Conv. perdues', num: true, fmt: F.int }, { key: 'lost_value', label: 'Valeur perdue', num: true, fmt: F.money }] });
    App.grid(el.querySelector('[data-g=top]'), { rows: (TR.top || []).map((r, k) => ({ ...r, _key: k })), search: false, sort: ['conversions', 'desc'], csv: 'meilleurs_bc',
      onRow: (r) => App.openDrawer('bc:' + r.bc_name), columns: [
        { key: 'bc_name', label: 'Meilleurs BC (conversions sur la fenêtre)', html: (r) => `<span class="ell" title="${esc(r.bc_name)}">${esc(r.bc_name)}</span>` },
        { key: 'category', label: 'Catégorie', html: (r) => `<span class="small">${esc(r.category)}</span>` },
        { key: 'sent', label: 'Sent', num: true, fmt: F.compact }, { key: 'conversions', label: 'Conv', num: true, fmt: F.int }, { key: 'conv_rate', label: 'Conv %', num: true, fmt: F.pct }] });
  }

  // ------------------------------------------------------------------ 1. incrémentalité
  function incrementality(el, st) {
    const lvl = st.lvl === 'bc' ? 'bc' : 'campaign';
    const ok = catOk(st);
    let rows = (A.periods[preset(st)]?.[`scorecard_${lvl}`] || []).filter((r) => ok(r.category)).map((r, k) => ({ ...r, _key: k, name: lvl === 'bc' ? r.bc_name : r.campaign_name }));
    const counts = {};
    for (const r of rows) counts[r.verdict] = (counts[r.verdict] || 0) + 1;
    const sig = rows.filter((r) => r.significant && r.uplift != null);
    const incr = sig.reduce((s, r) => s + (r.incremental_conversions || 0), 0);
    if (st.vd) rows = rows.filter((r) => r.verdict === st.vd);
    const verdicts = ['Net Conversion +', 'Net Conversion −', 'Non significatif', 'CG Conv < 30', 'CG = 0'];
    el.innerHTML = `<div class="split"><div style="flex:1 1 260px;display:flex">${tile({ label: 'Conversions incrémentales significatives', value: F.int(incr), cls: 'hero', sub: `Somme de uplift × Sent · ${sig.length} ${lvl === 'bc' ? 'BC' : 'campagnes'} significatives`, hint: 'Somme de uplift × Sent pour les entités dont l\'écart TG − CG est significatif (p < 0,05)' }).replace('class="tile', 'style="flex:1" class="tile')}</div>
        <div role="group" aria-label="Filtrer par verdict" style="flex:999 1 560px;display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px">
        ${verdicts.map((v) => tile({ label: v, dot: VERDICT_COLOR[v], value: F.int(counts[v] || 0), cls: st.vd === v ? 'on' : '', sub: st.vd === v ? '✓ filtre actif' : '', attrs: `data-local="vd" data-val="${st.vd === v ? '' : v}" aria-pressed="${st.vd === v}"` })).join('')}
      </div></div>
      <div class="grid g2" style="margin-top:18px">
        ${card('Uplift et intervalle de confiance à 95 %', '<div data-c="forest"></div>', { local: [st.vd && App.localBadge(`Verdict : ${st.vd}`, 'vd')], note: 'Les 40 plus gros volumes évaluables. À droite de 0 : la campagne fait mieux que le groupe de contrôle. Envois matures, hors seeding.' })}
        <div class="card flush" data-g="sc"></div>
      </div>`;
    const ev = rows.filter((r) => r.uplift != null).sort((a, b) => b.sent - a.sent).slice(0, 40).sort((a, b) => b.uplift - a.uplift);
    Charts.forest(el.querySelector('[data-c=forest]'), { fmt: F.pts, rows: ev.map((r) => ({ label: r.name, lo: r.ci_low, mid: r.uplift, hi: r.ci_high, color: VERDICT_COLOR[r.verdict] || '#8a93a6', r,
      tip: `<b>${esc(r.name)}</b><div>${esc(r.category)}</div><div>Uplift ${F.pts(r.uplift)} [${F.pts(r.ci_low)} ; ${F.pts(r.ci_high)}]</div><div>p = ${r.p_value?.toFixed(3) ?? '–'} · ${esc(r.verdict)}</div><div>TG ${F.pct(r.conv_rate)} · CG ${F.pct(r.cg_conv_rate)} · Sent ${F.compact(r.sent)}</div>` })),
      onClick: (x) => (lvl === 'bc' ? App.openDrawer('bc:' + x.r.bc_name) : App.openDrawer('campaign:' + x.r.campaign_name)) });
    App.grid(el.querySelector('[data-g=sc]'), { rows, sort: ['incremental_conversions', 'desc'], csv: `uplift_${lvl}`,
      tools: `<div class="seg sm" title="Réglage de cette section uniquement"><button data-local="lvl" data-val="campaign" class="${lvl === 'campaign' ? 'on' : ''}">Campagnes</button><button data-local="lvl" data-val="bc" class="${lvl === 'bc' ? 'on' : ''}">BC</button></div>`,
      onRow: (r) => (lvl === 'bc' ? App.openDrawer('bc:' + r.bc_name) : App.openDrawer('campaign:' + r.campaign_name)),
      columns: [
        { key: 'name', label: lvl === 'bc' ? 'BC' : 'Campagne', html: (r) => `<span class="ell" title="${esc(r.name)}">${esc(r.name)}</span>${noConv(r.category) ? ' <span class="badge grey" title="Catégorie sans objectif de conversion">sans obj. conv.</span>' : ''}` },
        { key: 'category', label: 'Catégorie', html: (r) => `<span class="small">${esc(r.category)}</span>` },
        { key: 'sent', label: 'Sent', num: true, fmt: F.compact },
        { key: 'conv_rate', label: 'TG Conv %', num: true, fmt: F.pct }, { key: 'cg_conv_rate', label: 'CG Conv %', num: true, fmt: (v, r) => (r.cg_size ? F.pct(v) : '<span class="nr">CG = 0</span>') },
        { key: 'uplift', label: 'Uplift', num: true, fmt: (v) => `<b style="color:${v > 0 ? 'var(--good)' : v < 0 ? 'var(--warn)' : 'inherit'}">${F.pts(v)}</b>` }, { key: 'p_value', label: 'p', num: true, xkind: 'num', fmt: (v) => (v == null ? '–' : v < 0.001 ? '< 0,001' : v.toFixed(3)) },
        { key: 'incremental_conversions', label: 'Conv. incr.', num: true, fmt: F.int },
        { key: 'verdict', label: 'Verdict', html: (r) => `<span class="badge ${r.verdict === 'Net Conversion +' ? 'ok' : r.verdict === 'Net Conversion −' ? 'trunc' : r.verdict === 'Non significatif' ? 'grey' : 'yel'}">${esc(r.verdict)}</span>` },
      ] });
  }

  // ------------------------------------------------------------------ 2. potentiel
  function potential(el, st) {
    const per = A.periods[preset(st)] || {}, lvl = st.lvl === 'bc' ? 'bc' : 'campaign', ok = catOk(st);
    const camp = (per[`value_${lvl}`] || []).filter((r) => ok(r.category)).map((r, k) => ({ ...r, _key: k, name: lvl === 'bc' ? r.bc_name : r.campaign_name }));
    const off = (per.value_offer || []).map((r, k) => ({ ...r, _key: k }));
    const bc = (per.value_bc || []).filter((r) => ok(r.category));
    const sum = per.summary || {};
    const under = camp.filter((r) => r.underperforming);
    el.innerHTML = `<div class="grid tiles">
        ${tile({ label: 'Manque à gagner estimé', value: F.money(under.reduce((s, r) => s + (r.missing_value || 0), 0)), sub: `${F.int(under.reduce((s, r) => s + (r.missing || 0), 0))} conversions manquantes`, hint: 'Conversions manquantes pour rejoindre la médiane des pairs de la catégorie × valeur unitaire. Seulement pour les entités sous le P5.' })}
        ${tile({ label: `${lvl === 'bc' ? 'BC' : 'Campagnes'} sous-performantes`, value: `${under.length} <small>/ ${camp.length}</small>`, sub: 'Conv % sous le P5 des pairs', extra: `<div class="meter"><span style="width:${camp.length ? (under.length / camp.length * 100).toFixed(1) : 0}%;background:#d9620b"></span></div>` })}
        ${tile({ label: 'Achats IM manquants', value: F.int(sum.missing_purchases), sub: `${sum.offers_underperforming ?? 0} offre(s) sous le P5 de leur touchpoint` })}
      </div>
      <div class="grid g2" style="margin-top:14px">
        ${card('Conv % selon le volume envoyé (BC)', '<div data-c="scatter"></div>', { note: 'Un point par BC (envois matures, hors seeding et catégories sans objectif de conversion). Contour rouge : sous le P5 de sa catégorie.' })}
        <div class="card flush" data-g="camp"></div>
      </div>
      <div class="card flush" style="margin-top:14px" data-g="off"></div>`;
    Charts.scatter(el.querySelector('[data-c=scatter]'), { xlog: true, xfmt: F.compact, yfmt: F.pct1, xLabel: 'Sent', yLabel: 'Conv %',
      points: bc.map((r) => ({ x: r.sent, y: r.conv_rate, color: Charts.colorOf(r.category), flag: r.underperforming, bc: r.bc_name,
        tip: `<b>${esc(r.bc_name)}</b><div>${esc(r.category)}</div><div>Conv ${F.pct(r.conv_rate)} · médiane des pairs ${F.pct(r.p50)} · P5 ${F.pct(r.p_low)}</div><div>Sent ${F.int(r.sent)}</div>` })),
      onClick: (p) => App.openDrawer('bc:' + p.bc) });
    App.grid(el.querySelector('[data-g=camp]'), { rows: camp, sort: ['missing_value', 'desc'], csv: `potentiel_${lvl}`,
      tools: `<div class="seg sm" title="Réglage de cette section uniquement"><button data-local="lvl" data-val="campaign" class="${lvl === 'campaign' ? 'on' : ''}">Campagnes</button><button data-local="lvl" data-val="bc" class="${lvl === 'bc' ? 'on' : ''}">BC</button></div>`,
      onRow: (r) => App.openDrawer((lvl === 'bc' ? 'bc:' : 'campaign:') + r.name),
      columns: [
        { key: 'name', label: lvl === 'bc' ? 'BC' : 'Campagne', html: (r) => `<span class="ell" title="${esc(r.name)}">${esc(r.name)}</span>${r.underperforming ? ' <span class="badge trunc">sous P5</span>' : ''}` },
        { key: 'sent', label: 'Sent', num: true, fmt: F.compact }, { key: 'conv_rate', label: 'Conv %', num: true, fmt: F.pct },
        { key: 'p50', label: 'Médiane pairs', num: true, fmt: F.pct }, { key: 'missing', label: 'Conv. manquantes', num: true, fmt: F.int, bar: () => '#d9620b' },
        { key: 'missing_value', label: 'Manque à gagner', num: true, fmt: F.money } ] });
    App.grid(el.querySelector('[data-g=off]'), { rows: off, sort: ['missing_purchases', 'desc'], csv: 'potentiel_offres',
      columns: [
        { key: 'offer_name', label: 'Offre IM', html: (r) => `<span class="ell" title="${esc(r.offer_name)}">${esc(r.offer_name)}</span>${r.underperforming ? ' <span class="badge trunc">sous P5</span>' : ''}` },
        { key: 'touchpoint', label: 'TP' }, { key: 'impressions', label: 'Impressions', num: true, fmt: F.compact },
        { key: 'take_rate', label: "Taux d'achat", num: true, fmt: F.pct }, { key: 'p50', label: 'Médiane pairs', num: true, fmt: F.pct },
        { key: 'missing_purchases', label: 'Achats manquants', num: true, fmt: F.int, bar: () => '#d9620b' } ] });
  }

  // ------------------------------------------------------------------ 3. benchmarks
  function benchmarks(el, st) {
    const metric = st.bm || 'conv';
    const M = { conv: ['Conv %', (s) => s.conv_rate, 'low'], dlv: ['Delivery %', (s) => s.delivery_rate, 'low'], ack: ['Ack %', (s) => s.ack_rate, 'low'], ff: ['Fulfillment Failure %', (s) => (s.fs + s.ff >= 10 ? s.ff_rate : null), 'high'] }[metric];
    const pc = App.meta.percentiles;
    const ok = catOk(st);
    const idx = App.rows(P, st, [], { range: A.presets[preset(st)], where: (i) => ok(P.v('cat', i)) && !P.c.seed[i] && !App.isTechnical(P.v('bc', i)) && (metric !== 'conv' || (P.c.age[i] >= KPI.maturity && !noConv(P.v('cat', i)))) });
    const byBc = KPI.push(P, idx, (i) => P.v('cat', i) + '|' + P.v('bc', i));
    const groups = new Map();
    for (const s of byBc.values()) {
      if (s.sent < 1000) continue;
      const v = M[1](s);
      if (v == null) continue;
      const [cat, bc] = s.key.split('|');
      if (!groups.has(cat)) groups.set(cat, []);
      groups.get(cat).push({ v, bc, label: bc, s });
    }
    const out = [...groups.entries()].map(([name, values]) => {
      const sorted = values.map((p) => p.v).sort((a, b) => a - b);
      const q = { p_low: KPI.percentile(sorted, pc.low), p50: KPI.percentile(sorted, pc.median), p_high: KPI.percentile(sorted, pc.high) };
      for (const p of values) {
        p.flag = values.length >= pc.min_peers && (M[2] === 'low' ? p.v <= q.p_low : p.v >= q.p_high);
        p.tip = `<b>${esc(p.bc)}</b><div>${M[0]} ${F.pct(p.v)} · Sent ${F.compact(p.s.sent)}</div><div>${esc(name)} : P${pc.low} ${F.pct(q.p_low)} · médiane ${F.pct(q.p50)} · P${pc.high} ${F.pct(q.p_high)}</div>${values.length < pc.min_peers ? `<div>⚠ moins de ${pc.min_peers} pairs : les règles utilisent la population entière</div>` : ''}`;
      }
      return { name, values, q };
    }).sort((a, b) => b.values.length - a.values.length);
    el.innerHTML = card(`Distribution de ${M[0]} par BC, par catégorie`, '<div data-c="strip"></div>', {
      right: `<div class="seg sm" title="Réglage de cette section uniquement">${[['conv', 'Conv %'], ['dlv', 'Delivery %'], ['ack', 'Ack %'], ['ff', 'Fulf. Failure %']].map(([k, l]) => `<button data-local="bm" data-val="${k}" class="${metric === k ? 'on' : ''}">${l}</button>`).join('')}</div>`,
      note: `Un point par BC (≥ 1 000 envoyés, hors seeding et BC techniques${metric === 'conv' ? ', envois matures' : ''}). Bande : P${pc.low} → P${pc.high}, trait : médiane. En rouge : ${M[2] === 'low' ? `sous le P${pc.low}` : `au-dessus du P${pc.high}`}, c'est la zone où les règles percentiles alertent (avec les garde-fous d'écart minimal et de volume).` });
    Charts.strip(el.querySelector('[data-c=strip]'), { groups: out, fmt: F.pct1, onClick: (p) => App.openDrawer('bc:' + p.bc) });
  }

  // ------------------------------------------------------------------ 4. tendances
  function trends(el, st) {
    const [a, b] = A.presets[preset(st)] || App.period(st);
    const len = App.daysBetween(a, b) + 1;
    const pa = App.addDays(a, -len), pb = App.addDays(a, -1);
    const ok = catOk(st);
    const where = (i) => ok(P.v('cat', i));
    const cur = KPI.push(P, App.rows(P, st, [], { range: [a, b], where })), prev = KPI.push(P, App.rows(P, st, [], { range: [pa, pb], where }));
    const curO = KPI.push(P, App.rows(P, st, [], { range: [a, b], where: (i) => where(i) && !P.c.seed[i] })), prevO = KPI.push(P, App.rows(P, st, [], { range: [pa, pb], where: (i) => where(i) && !P.c.seed[i] }));
    const ci = KPI.im(I, App.rows(I, st, [], { range: [a, b] })), pi = KPI.im(I, App.rows(I, st, [], { range: [pa, pb] }));
    const lines = [
      ['Push · Sent', cur.sent, prev.sent, F.int], ['Push · Ack %', cur.ack_rate, prev.ack_rate, F.pct, 'pts'], ['Push · Delivery %', cur.delivery_rate, prev.delivery_rate, F.pct, 'pts'],
      ['Push · Conversions (estimées à maturité)', cur.est.conv, prev.est.conv, F.int], ['Push · Conv % hors seeding (estimé)', curO.conv_rate_est, prevO.conv_rate_est, F.pct, 'pts'],
      ['Push · Net Conv % hors seeding (estimé)', curO.net_conv_rate_est, prevO.net_conv_rate_est, F.pts, 'pts'], ['Push · Conversions seeding', cur.seedConv, prev.seedConv, F.int],
      ['Push · Valeur des conversions (estimée)', cur.est.val, prev.est.val, F.money],
      ['IM · Impressions', ci.imp, pi.imp, F.int], ['IM · Achats', ci.fs, pi.fs, F.int], ["IM · Taux d'achat", ci.take_rate, pi.take_rate, F.pct, 'pts'], ['IM · Failure %', ci.failure_rate, pi.failure_rate, F.pct, 'pts', true],
    ];
    const group = (title, pre) => `<table class="t"><thead><tr><th>${title}</th><th class="num">Actuelle</th><th class="num">Précédente</th><th class="num">Évolution</th></tr></thead><tbody>${lines.filter(([l]) => l.startsWith(pre)).map(([l, c, p, f, kind, inv]) => {
      const d = c == null || p == null ? null : kind === 'pts' ? c - p : p ? c / p - 1 : null;
      const cls = d == null || Math.abs(d) < 1e-4 ? 'flat' : (d > 0) !== !!inv ? 'up' : 'down';
      return `<tr><td style="font-weight:600">${l.slice(pre.length)}</td><td class="num" style="font-weight:700">${f(c)}</td><td class="num muted">${f(p)}</td><td class="num"><span class="delta ${cls}">${d == null ? '–' : kind === 'pts' ? F.pts(d) : F.signedPct(d)}</span></td></tr>`;
    }).join('')}</tbody></table>`;
    el.innerHTML = `${card(`${F.date(a)} → ${F.date(b)} comparé au ${F.date(pa)} → ${F.date(pb)}`, `<div class="grid g2" style="gap:0 28px"><div class="tbl-wrap">${group('Push', 'Push · ')}</div><div class="tbl-wrap">${group('Inbound', 'IM · ')}</div></div>
        <p class="small muted" style="margin:12px 0 0">Bleu : évolution favorable · orange : défavorable. Une hausse du Failure % est défavorable. Conversions comparées estimées à maturité, pour ne pas pénaliser la période la plus récente.</p>`)}
      <div class="grid g2" style="margin-top:18px">${card('Mix des envois par catégorie (par semaine)', '<div class="chart" data-c="mix"></div>')}
      ${card('Profil par jour de semaine', '<div class="chart" data-c="wd"></div>', { note: 'Moyenne par jour sur la période. Une baisse d\'activité se juge vs le même jour de semaine.' })}
      ${card("Profil par heure d'envoi", '<div class="chart" data-c="hour"></div>', { note: 'Heure programmée (Scheduled Date). Minuit : flows déclenchés automatiquement.' })}</div>`;
    // Mix hebdomadaire (part de Sent par catégorie)
    const idx = App.rows(P, st, [], { range: [a, b], where });
    const week = (d) => { const dt = new Date(d + 'T00:00:00Z'), wd = (dt.getUTCDay() + 6) % 7; return App.addDays(d, -wd); };
    const weeks = [...new Set(idx.map((i) => week(P.v('d', i))))].sort();
    const cats = [...new Set(idx.map((i) => P.v('cat', i)))].sort();
    const wk = KPI.push(P, idx, (i) => week(P.v('d', i)) + '|' + P.v('cat', i)), wkT = KPI.push(P, idx, (i) => week(P.v('d', i)));
    Charts.bars(el.querySelector('[data-c=mix]'), { x: weeks, xfmt: (w) => 'sem. ' + F.date(w), fmt: F.pct1, series: cats.map((c) => ({ name: c, color: Charts.colorOf(c), values: weeks.map((w) => (wk.get(w + '|' + c)?.sent || 0) / (wkT.get(w)?.sent || 1)) })) });
    const WD = ['lun.', 'mar.', 'mer.', 'jeu.', 'ven.', 'sam.', 'dim.'];
    const byDay = KPI.push(P, idx, (i) => P.v('d', i)), byDayO = KPI.push(P, idx.filter((i) => !P.c.seed[i]), (i) => P.v('d', i));
    const wdv = WD.map(() => []), wdc = WD.map(() => []);
    for (const [d, s] of byDay) { const k = (new Date(d + 'T00:00:00Z').getUTCDay() + 6) % 7; wdv[k].push(s.sent); const o = byDayO.get(d); if (o) wdc[k].push(o.conv_rate_est); }
    Charts.bars(el.querySelector('[data-c=wd]'), { x: WD, fmt: F.compact, height: 170, series: [{ name: 'Sent moyen', values: wdv.map(KPI.mean), color: '#b9cbee' }],
      note: (k) => `<br>Conv % hors seeding (estimé) : ${F.pct(KPI.mean(wdc[k]))}` });
    const hours = [...Array(24).keys()];
    const byH = KPI.push(P, idx.filter((i) => P.c.hour[i] >= 0), (i) => String(P.c.hour[i]));
    Charts.bars(el.querySelector('[data-c=hour]'), { x: hours, xfmt: (h) => h + ' h', fmt: F.int, height: 170, series: [{ name: 'Broadcasts', values: hours.map((h) => byH.get(String(h))?.n || 0), color: '#1a4fb0' }],
      note: (h) => { const s = byH.get(String(h)); return s ? `<br>Sent ${F.compact(s.sent)} · Conv % ${F.pct(s.conv_rate)}` : ''; } });
  }

  // ------------------------------------------------------------------ 5. maturité
  function maturity(el) {
    const curves = App.D.curves || {};
    const names = { conversions: 'Conversions', conversion_value: 'Valeur', fulfillment_success: 'Fulfillment Success', cg_conversions: 'CG Conversions', fulfillment_failure: 'Fulfillment Failure' };
    const ages = [...Array(KPI.refAge + 1).keys()];
    const lastSnap = App.snaps[App.snaps.length - 1]?.snapshot_date;
    // Nowcast des jours récents (tous envois, toutes catégories)
    const recent = App.range(App.addDays(lastSnap, -KPI.refAge), lastSnap).filter((d) => (P.d.d || []).includes(d));
    const byDay = KPI.push(P, P.all.filter((i) => P.v('d', i) >= recent[0]), (i) => P.v('d', i));
    const now = recent.map((d) => { const s = byDay.get(d); return s ? { _key: d, d, age: App.daysBetween(d, lastSnap), conv: s.conv, est: s.est.conv, comp: s.est.conv ? s.conv / s.est.conv : 1, val: s.val, estVal: s.est.val, trunc: s.trunc, n: s.n } : null; }).filter(Boolean).reverse();
    // Envois tronqués par jour d'envoi
    const tr = new Map();
    for (let i = 0; i < P.n; i++) {
      if (!P.c.frozen[i]) continue;
      const comp = KPI.completion('conv', P.c.age[i]);
      if (comp >= 0.99) continue;
      const d = P.v('d', i), lost = P.c.lost[i], key = d + (lost ? '|lost' : '');
      const s = tr.get(key) || { _key: key, d, lost, n: 0, conv: 0, est: 0, age: P.c.age[i], seen: App.snaps[P.c.snap[i]].snapshot_date, cats: new Set() };
      s.n++; s.conv += P.c.conv[i]; s.est += P.c.conv[i] / comp; s.cats.add(P.v('cat', i));
      tr.set(key, s);
    }
    const trunc = [...tr.values()];
    el.innerHTML = `<div class="grid g2">
      ${card('Courbes de maturité, métrique par métrique', '<div class="chart" data-c="curves"></div>', { note: `Part de la valeur finale (mesurée à J+${KPI.refAge}) déjà présente selon l'âge de l'envoi. Les métriques à 100 % dès J0 (Sent, Ack, Delivered, CG size) ne sont pas tracées. Règles de conversion appliquées à partir de J+${KPI.maturity}.` })}
      ${card('Nowcast : conversions observées et attendues par jour d\'envoi', '<div data-g="now"></div>', { flush: true })}
      </div>
      ${trunc.length ? `<div style="margin-top:14px">${card(`Envois tronqués (${F.int(trunc.reduce((s, x) => s + x.n, 0))} broadcasts)`, '<div data-g="trunc"></div>', { flush: true, note: 'Envois absents des fichiers suivants avant d\'être matures. <b>Fin de mois</b> : le Daily Dashboard ne couvre que le mois en cours (prévention : demander à Flytxt d\'inclure la fin du mois précédent). <b>Disparu</b> : le broadcast a quitté les fichiers en cours de mois, perte côté NEON-dx à signaler.' })}</div>` : ''}`;
    Charts.line(el.querySelector('[data-c=curves]'), { x: ages, xfmt: (a) => 'J+' + a, fmt: F.pct1, zeroBased: true,
      series: Object.keys(names).filter((k) => curves[k]).map((k) => ({ name: names[k], values: curves[k] })) });
    App.grid(el.querySelector('[data-g=now]'), { rows: now, search: false, sort: ['d', 'desc'], columns: [
      { key: 'd', label: "Jour d'envoi", fmt: F.day }, { key: 'age', label: 'Âge', fmt: (v) => 'J+' + v },
      { key: 'conv', label: 'Observées', num: true, fmt: F.int }, { key: 'comp', label: 'Complétude', num: true, fmt: F.pct1, bar: (r) => (r.trunc ? '#d9620b' : r.comp < 0.99 ? '#c99a00' : '#3e6cc9'), barMax: 1 },
      { key: 'est', label: 'Attendues', num: true, fmt: (v) => '≈ ' + F.int(v) }, { key: 'estVal', label: 'Valeur attendue', num: true, fmt: F.money },
      { key: 'trunc', label: 'État', html: (r) => (r.trunc ? '<span class="badge trunc">tronqué</span>' : r.comp < 0.99 ? '<span class="badge prov">en maturation</span>' : '<span class="badge ok">définitif</span>') }] });
    if (trunc.length) App.grid(el.querySelector('[data-g=trunc]'), { rows: trunc, search: false, sort: ['d', 'desc'], csv: 'envois_tronques', columns: [
      { key: 'd', label: "Jour d'envoi", fmt: F.day },
      { key: 'lost', label: 'Cause', html: (r) => (r.lost ? `<span class="badge alert">disparu</span> <span class="small muted">après le fichier du ${F.date(r.seen)}</span>` : '<span class="badge trunc">fin de mois</span>'), csv: (r) => (r.lost ? 'disparu' : 'fin de mois') },
      { key: 'age', label: 'Dernier âge vu', fmt: (v) => 'J+' + v }, { key: 'n', label: 'Broadcasts', num: true, fmt: F.int },
      { key: 'conv', label: 'Conv. observées', num: true, fmt: F.int }, { key: 'est', label: 'Estimées à maturité', num: true, fmt: (v) => '≈ ' + F.int(v) },
      { key: 'miss', label: 'Jamais remontées', num: true, sort: (r) => r.est - r.conv, html: (r) => '≈ ' + F.int(r.est - r.conv) },
      { key: 'cats', label: 'Catégories', html: (r) => `<span class="small muted">${esc([...r.cats].join(', '))}</span>` }] });
  }

  // ------------------------------------------------------------------ 6. arrivée des données
  function arrival(el) {
    const snaps = App.snaps;
    if (!snaps.length) { el.innerHTML = '<div class="empty">Aucun fichier</div>'; return; }
    const fh = App.feed();
    const have = new Map(snaps.map((s) => [s.snapshot_date, s]));
    const cal = App.range(snaps[0].snapshot_date, snaps[snaps.length - 1].snapshot_date);
    const calHtml = '<div style="display:flex;flex-wrap:wrap;gap:3px">' + cal.map((d) => `<span title="${F.day(d)} : ${have.has(d) ? 'reçu (' + esc(have.get(d).file_name) + ')' : 'aucun fichier'}" style="width:22px;height:22px;border-radius:4px;display:inline-flex;align-items:center;justify-content:center;font-size:10px;background:${have.has(d) ? '#0a2357' : '#fbe3e3'};color:${have.has(d) ? '#fff' : '#c62828'}">${d.slice(8)}</span>`).join('') + '</div>';
    const rows = snaps.map((s, k) => ({ ...s, _key: s.id, dPush: k && snaps[k - 1].snapshot_date.slice(0, 7) === s.snapshot_date.slice(0, 7) ? s.push_rows - snaps[k - 1].push_rows : null,
      dIm: k && snaps[k - 1].snapshot_date.slice(0, 7) === s.snapshot_date.slice(0, 7) ? s.im_rows - snaps[k - 1].im_rows : null,
      snp: App.anomalies.filter((a) => a.rule_id.startsWith('SNP') && a.first_seen_at === s.snapshot_date).length }));
    el.innerHTML = `<div class="grid g2">
        ${card('Calendrier des fichiers reçus', calHtml + `<p class="small muted" style="margin:8px 0 0">${snaps.length} fichiers reçus, ${fh.missing.length} jour(s) sans fichier. Chaque fichier couvre du 1er du mois au jour indiqué.</p>`)}
        ${card('Signaux sur le flux', fh.signals.some((x) => !x.hidden) ? `<div class="signals">${fh.signals.filter((x) => !x.hidden).map((s) => `<div class="signal"><span>${App.levelPill(s.level)}</span><span><span class="t">${esc(s.title)}</span><span class="d">${esc(s.text)}</span></span></div>`).join('')}</div>` : '<div class="empty">Aucun signal</div>')}
      </div>
      <!--<div style="margin-top:14px">${card('Remplissage des colonnes, fichier par fichier', '<div data-c="fill"></div>', { note: 'Part des lignes où la colonne est renseignée (non vide, non nulle). Une colonne vide aujourd\'hui peut se remplir à J+x : elle reste suivie.', right: '<span class="small muted">Push puis IM</span>' })}</div>-->
      <!--<div style="margin-top:14px">${card("Jour d'envoi × fichier : à quel âge chaque jour a été vu", '<div data-c="age"></div>', { note: `Couleur : complétude estimée des conversions à cet âge (clair = jeune, foncé = mature). Les colonnes manquantes sont les jours sans fichier ; une ligne qui s'arrête avant J+${KPI.maturity} est tronquée.` })}</div>-->
      <div class="card flush" style="margin-top:14px" data-g="snaps"></div>`;
    // Matrice de remplissage
    const fill = App.D.fill || {};
    const fRows = [...Object.keys(fill.push || {}).map((c) => 'push|' + c), ...Object.keys(fill.im || {}).map((c) => 'im|' + c)];
    const sDates = snaps.map((s) => s.snapshot_date);
    Charts.heatmap(el.querySelector('[data-c=fill]'), { rows: fRows, cols: sDates.map((_, k) => k), colFmt: (k) => F.date(sDates[k]), rowFmt: (r) => (r.startsWith('push') ? 'Push · ' : 'IM · ') + r.split('|')[1],
      value: (r, k) => { const [s, c] = r.split('|'); return fill[s]?.[c]?.[k] ?? null; },
      color: (v) => (v === 0 ? '#fbe3e3' : Charts.seqColor(0.15 + v * 0.85)), cellText: (v) => (v === 0 ? '0' : ''),
      title: (r, k, v) => `<b>${esc(r.replace('|', ' · '))}</b><div>Fichier du ${F.date(sDates[k])} : ${v == null ? '–' : F.pct1(v)} des lignes renseignées</div>` });
    // Matrice âge
    const lastDays = App.range(App.addDays(App.maxDate, -44), App.maxDate);
    Charts.heatmap(el.querySelector('[data-c=age]'), { rows: lastDays.slice().reverse(), cols: sDates.filter((d) => d >= lastDays[0]), rowFmt: F.day, colFmt: F.date,
      value: (d, s) => { const sn = have.get(s); return sn && d >= sn.date_min && d <= sn.date_max ? App.daysBetween(d, s) : null; },
      color: (age) => Charts.seqColor(KPI.completion('conv', age)), cellText: (age) => (age <= 9 ? String(age) : ''),
      title: (d, s, age) => `<b>Envois du ${F.day(d)}</b><div>${age == null ? `absents du fichier du ${F.date(s)}` : `vus à J+${age} dans le fichier du ${F.date(s)} · complétude ≈ ${F.pct1(KPI.completion('conv', age))}`}</div>` });
    App.grid(el.querySelector('[data-g=snaps]'), { rows, sort: ['snapshot_date', 'desc'], search: false, csv: 'fichiers', columns: [
      { key: 'snapshot_date', label: 'Fichier (till)', fmt: F.day }, { key: 'file_name', label: 'Nom', html: (r) => `<span class="small muted">${esc(r.file_name)}</span>` },
      { key: 'ingested_at', label: 'Importé le', fmt: F.dt }, { key: 'date_min', label: 'Couverture', fmt: (v, r) => `${F.date(r.date_min)} → ${F.date(r.date_max)}` },
      { key: 'push_rows', label: 'Lignes Push', num: true, fmt: (v, r) => `${F.int(v)}${r.dPush != null ? ` <span class="delta ${r.dPush < 0 ? 'down' : 'flat'}">${r.dPush > 0 ? '+' : ''}${F.int(r.dPush)}</span>` : ''}` },
      { key: 'im_rows', label: 'Lignes IM', num: true, fmt: (v, r) => `${F.int(v)}${r.dIm != null ? ` <span class="delta ${r.dIm < 0 ? 'down' : 'flat'}">${r.dIm > 0 ? '+' : ''}${F.int(r.dIm)}</span>` : ''}` },
      { key: 'snp', label: 'Révisions / disparitions', num: true, fmt: (v) => (v ? `<span class="badge trunc">${v}</span>` : '') }] });
  }

  function render(el, st) {
    const p = preset(st), [a, b] = A.presets[p] || ['', ''];
    const slot = (id) => `<div data-slot="${id}"></div>`;
    App.subtitle(`Incrémentalité, potentiel, tendances et maturité · période ${App.PRESETS[p]} : ${F.date(a)} → ${F.dateFull(b)}`);
    el.innerHTML = `
      ${section("Quand envoyer, quoi pousser", slot('timing'), { id: 'creneaux', nav: 'Quand envoyer', sub: "Meilleurs jours et heures d'envoi (hors blackout SMS 19h-7h), BC en déclin et meilleurs BC" })}
      ${section('Incrémentalité : TG vs CG', slot('incr'), { id: 'incrementalite', nav: 'Incrémentalité', panel: true, sub: 'Test z de deux proportions sur les envois matures, hors seeding · significatif si p < 0,05', note: 'Niveau (campagnes / BC) et verdict ne concernent que cette section.' })}
      ${section("Potentiel d'amélioration", slot('pot'), { id: 'potentiel', nav: 'Potentiel', sub: 'Entités sous le P5 de leurs pairs et manque à gagner pour rejoindre la médiane' })}
      ${section('Benchmarks', slot('bench'), { id: 'benchmarks', nav: 'Benchmarks', panel: true })}
      ${section('Tendances · Periode-over-Periode', slot('trends'), { id: 'tendances', nav: 'Tendances' })}
      ${section('Maturité des métriques', slot('maturity'), { id: 'maturite', nav: 'Maturité' })}`;

      // ${section('Arrivée des données (flux NEON-dx)', slot('arrival'), { id: 'arrivee', nav: 'Arrivée des données' })}
    const W = (id, draw) => App.widget(el.querySelector(`[data-slot=${id}]`), id, draw);
    // Réglages locaux (niveau, verdict, métrique) fusionnés aux filtres globaux pour chaque section.
    W('timing', (w) => timing(w, st));
    W('incr', (w, g, l) => incrementality(w, { ...st, lvl: l.lvl, vd: l.vd }));
    W('pot', (w, g, l) => potential(w, { ...st, lvl: l.lvl }));
    W('bench', (w, g, l) => benchmarks(w, { ...st, bm: l.bm }));
    W('trends', (w) => trends(w, st));
    W('maturity', (w) => maturity(w));
    W('arrival', (w) => arrival(w));
    if (st.sec) requestAnimationFrame(() => document.getElementById(st.sec)?.scrollIntoView({ block: 'start' }));
  }

  App.tab('analytics', {
    title: 'Analytics', render, defaults: { p: '30j' }, multi: ['cat'],
    filters: { period: false, dims: DIMS, extraLabel: 'Période', chips: (st) => (preset(st) !== '30j' ? [{ label: `Période : ${App.PRESETS[preset(st)]}`, patch: { p: null } }] : []), extra: (st) => `<div class="seg seg-4">${Object.entries(App.PRESETS).map(([k, l]) => `<button data-set="p" data-val="${k}" class="${preset(st) === k ? 'on' : ''}">${l}</button>`).join('')}</div><p class="small muted" style="margin:6px 0 0">Statistiques pré-calculées par période type.</p>` },
  });
})();
