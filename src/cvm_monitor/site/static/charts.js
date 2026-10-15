/* Graphiques SVG sans dépendance : lignes, barres (empilées), barres horizontales, sparkline, heatmap, nuage,
 * forest plot. Chaque fonction écrit un <svg> dans `el` (largeur = celle du conteneur, viewBox pour l'adaptation)
 * et gère son infobulle. Convention de complétude : à partir de `provisionalFrom` (index), les valeurs sont en
 * cours de maturation, dessinées hachurées / en pointillés. */
'use strict';
const Charts = (() => {
  // Charte : marine, bleus, jaune Yas, complétés pour distinguer 12 catégories. Orange et rouge restent réservés au défavorable.
  const PALETTE = ['#1a4fb0', '#7aa7ff', '#0a2357', '#f2c200', '#2e9d7f', '#8e5bd6', '#b9cbee', '#5b6478', '#e0a800', '#64b5a5', '#3e6cc9', '#c3a6ea'];
  const SEQ = ['#eef3fb', '#d5e1f6', '#b9cbee', '#7aa0e0', '#3e6cc9', '#1a4fb0', '#0a2357'];
  const INK = '#5b6478', LINE = '#eef1f6', FAINT = '#8a93a6';
  const colorCache = new Map();
  let nextColor = 0;
  /** Couleur stable par nom (une catégorie garde sa couleur quels que soient les filtres). */
  function colorOf(name) {
    if (!colorCache.has(name)) colorCache.set(name, PALETTE[nextColor++ % PALETTE.length]);
    return colorCache.get(name);
  }
  function seed(names) { names.forEach(colorOf); }
  /** Couleur imposée pour un nom (ex. touchpoints : couleurs de la charte). */
  function fix(name, color) { colorCache.set(name, color); }

  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const tipEl = () => document.getElementById('tip');
  function tip(html, ev) {
    const t = tipEl();
    if (!t) return;
    t.innerHTML = html;
    t.hidden = false;
    const r = t.getBoundingClientRect();
    let x = ev.clientX + 14, y = ev.clientY + 14;
    if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - 14;
    if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - 14;
    t.style.left = x + 'px';
    t.style.top = y + 'px';
  }
  function untip() { const t = tipEl(); if (t) t.hidden = true; }

  function ticks(min, max, n = 4) {
    if (!isFinite(min) || !isFinite(max)) return [0];
    if (min === max) { max = min + (Math.abs(min) || 1); }
    const span = max - min, step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= n) || 10 * mag;
    const out = [];
    for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) out.push(+v.toFixed(12));
    return out;
  }
  const width = (el) => Math.max(260, Math.round(el.clientWidth || el.parentElement?.clientWidth || 800));
  const defs = (id, color) => `<defs><pattern id="${id}" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="5" height="5" fill="${color}" opacity=".18"/><line x1="0" y1="0" x2="0" y2="5" stroke="${color}" stroke-width="2.2" opacity=".75"/></pattern></defs>`;
  let uid = 0;

  function legend(series) {
    if (series.length < 2) return '';
    return '<div class="legend">' + series.map((s) => `<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join('') + '</div>';
  }

  /** Cadre commun : axes, grille, échelle. Renvoie les fonctions d'échelle. */
  function frame(W, H, n, yMin, yMax, fmt, xlab, opt = {}) {
    const m = { l: opt.left ?? 54, r: 10, t: 10, b: 24 };
    const ys = ticks(yMin, yMax, opt.yTicks || 4);
    const lo = Math.min(yMin, ys[0]), hi = Math.max(yMax, ys[ys.length - 1]);
    const X = (i) => m.l + (n <= 1 ? (W - m.l - m.r) / 2 : (i * (W - m.l - m.r)) / (n - 1));
    const band = (W - m.l - m.r) / Math.max(n, 1);
    const XB = (i) => m.l + i * band;
    const Y = (v) => m.t + (H - m.t - m.b) * (1 - (v - lo) / (hi - lo || 1));
    let g = '<g class="grid">', prevLabel = null;
    for (const v of ys) {
      const label = fmt(v);
      if (label === prevLabel) continue; // graduations fines arrondies au même libellé (ex. 0,25 en entier)
      prevLabel = label;
      g += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${m.l - 6}" y="${Y(v) + 4}" text-anchor="end">${esc(label)}</text>`;
    }
    g += '</g>';
    if (lo < 0 && hi > 0) g += `<line class="zero" x1="${m.l}" x2="${W - m.r}" y1="${Y(0)}" y2="${Y(0)}"/>`;
    const every = Math.max(1, Math.ceil(n / Math.max(2, Math.floor((W - m.l) / 62))));
    for (let i = 0; i < n; i += every) {
      const x = opt.bars ? XB(i) + band / 2 : X(i);
      g += `<text x="${x}" y="${H - 6}" text-anchor="middle">${esc(xlab(i))}</text>`;
    }
    return { m, X, XB, band, Y, g, lo, hi };
  }

  function overlay(svg, el, n, f, W, opt, html) {
    svg.addEventListener('mousemove', (ev) => {
      const r = svg.getBoundingClientRect();
      const px = ((ev.clientX - r.left) / r.width) * W;
      const i = opt.bars ? Math.floor((px - f.m.l) / f.band) : Math.round(((px - f.m.l) / (W - f.m.l - f.m.r)) * (n - 1));
      if (i < 0 || i >= n) return untip();
      const cur = el.querySelector('.cursor');
      if (cur) {
        const x = opt.bars ? f.XB(i) + f.band / 2 : f.X(i);
        cur.setAttribute('x1', x); cur.setAttribute('x2', x); cur.style.display = '';
      }
      tip(html(i), ev);
    });
    svg.addEventListener('mouseleave', () => { untip(); const c = el.querySelector('.cursor'); if (c) c.style.display = 'none'; });
    if (opt.onClick) { svg.style.cursor = 'pointer'; svg.addEventListener('click', (ev) => {
      const r = svg.getBoundingClientRect(), px = ((ev.clientX - r.left) / r.width) * W;
      const i = opt.bars ? Math.floor((px - f.m.l) / f.band) : Math.round(((px - f.m.l) / (W - f.m.l - f.m.r)) * (n - 1));
      if (i >= 0 && i < n) opt.onClick(i);
    }); }
  }

  function tipHtml(title, rows, note) {
    return `<b>${esc(title)}</b>` + rows.map((r) => `<div class="r"><span><i style="background:${r.color}"></i>${esc(r.name)}</span><span>${esc(r.value)}</span></div>`).join('') + (note ? `<div style="margin-top:4px;opacity:.8">${note}</div>` : '');
  }

  /**
   * Courbes. opt = { x: [libellés], series: [{name, values, color?, dash?}], fmt, xfmt, height,
   *   provisionalFrom: index (valeurs en maturation ensuite), bands: [{from, to, label}], zeroBased, note(i) }
   */
  function line(el, opt) {
    const W = width(el), H = opt.height || 200, n = opt.x.length;
    const fmt = opt.fmt || String, xfmt = opt.xfmt || String;
    const series = opt.series.map((s, k) => ({ ...s, color: s.color || PALETTE[k % PALETTE.length] }));
    const vals = series.flatMap((s) => s.values.filter((v) => v != null && isFinite(v)));
    if (!n || !vals.length) { el.innerHTML = '<div class="empty">Aucune donnée sur la période</div>'; return; }
    let yMin = Math.min(...vals), yMax = Math.max(...vals);
    if (opt.zeroBased !== false) yMin = Math.min(0, yMin);
    if (yMax === yMin) yMax = yMin + 1;
    const f = frame(W, H, n, yMin, yMax, fmt, (i) => xfmt(opt.x[i]), opt);
    const id = 'h' + (++uid);
    let body = defs(id, '#c99a00') + f.g;
    for (const b of opt.bands || []) {
      const x1 = f.X(b.from) - (n > 1 ? (f.X(1) - f.X(0)) / 2 : 0), x2 = f.X(b.to) + (n > 1 ? (f.X(1) - f.X(0)) / 2 : 0);
      body += `<rect x="${Math.max(f.m.l, x1)}" y="${f.m.t}" width="${Math.max(2, Math.min(W - f.m.r, x2) - Math.max(f.m.l, x1))}" height="${H - f.m.t - f.m.b}" fill="${b.color || '#8a95a3'}" opacity=".12"/>`;
      if (b.label) body += `<text x="${Math.max(f.m.l, x1) + 4}" y="${f.m.t + 12}" style="fill:${b.color || INK};font-size:10px">${esc(b.label)}</text>`;
    }
    const pf = opt.provisionalFrom ?? n;
    if (pf < n) body += `<rect x="${f.X(Math.max(0, pf - 0.5))}" y="${f.m.t}" width="${W - f.m.r - f.X(Math.max(0, pf - 0.5))}" height="${H - f.m.t - f.m.b}" fill="url(#${id})" opacity=".35"/>`;
    for (const s of series) {
      let d = '', dp = '', pen = false, penp = false;
      s.values.forEach((v, i) => {
        if (v == null || !isFinite(v)) { pen = penp = false; return; }
        const pt = `${f.X(i).toFixed(1)},${f.Y(v).toFixed(1)}`;
        if (i < pf || i === pf - 1) { d += (pen ? 'L' : 'M') + pt; pen = true; }
        if (i >= pf - 1) { dp += (penp ? 'L' : 'M') + pt; penp = true; }
      });
      if (s.area) {
        const pts = s.values.map((v, i) => (v == null ? null : `${f.X(i).toFixed(1)},${f.Y(v).toFixed(1)}`)).filter(Boolean);
        if (pts.length) body += `<path d="M${f.X(0)},${f.Y(Math.max(f.lo, 0))}L${pts.join('L')}L${f.X(n - 1)},${f.Y(Math.max(f.lo, 0))}Z" fill="${s.color}" opacity=".1"/>`;
      }
      body += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="2.4" stroke-linejoin="round" ${s.dash ? 'stroke-dasharray="5 4"' : ''}/>`;
      if (dp) body += `<path d="${dp}" fill="none" stroke="${s.color}" stroke-width="2" stroke-dasharray="3 3" opacity=".8"/>`;
      if (n <= 45) s.values.forEach((v, i) => { if (v != null && isFinite(v)) body += `<circle cx="${f.X(i)}" cy="${f.Y(v)}" r="${i >= pf ? 2.5 : 2}" fill="${i >= pf ? '#fff' : s.color}" stroke="${s.color}" stroke-width="1.4"/>`; });
    }
    for (const mk of opt.markers || []) body += `<circle cx="${f.X(mk.i)}" cy="${f.Y(mk.v)}" r="5" fill="none" stroke="${mk.color || '#c0392b'}" stroke-width="2"/>`;
    body += `<line class="cursor" x1="0" x2="0" y1="${f.m.t}" y2="${H - f.m.b}" stroke="${FAINT}" stroke-dasharray="2 2" style="display:none"/>`;
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="height:${H}px">${body}</svg>` + legend(series);
    const svg = el.querySelector('svg');
    overlay(svg, el, n, f, W, opt, (i) => tipHtml(xfmt(opt.x[i]), series.map((s) => ({ name: s.name, color: s.color, value: s.values[i] == null ? 'n/r' : fmt(s.values[i]) })),
      (i >= pf ? '⚠ en cours de maturation' : '') + (opt.note ? opt.note(i) || '' : '')));
  }

  /** Barres verticales, empilées si plusieurs séries. opt = { x, series, fmt, xfmt, height, provisionalFrom, onClick, note(i) } */
  function bars(el, opt) {
    const W = width(el), H = opt.height || 200, n = opt.x.length;
    const fmt = opt.fmt || String, xfmt = opt.xfmt || String;
    const series = opt.series.map((s, k) => ({ ...s, color: s.color || PALETTE[k % PALETTE.length] }));
    if (!n) { el.innerHTML = '<div class="empty">Aucune donnée sur la période</div>'; return; }
    const tot = (i) => series.reduce((a, s) => a + Math.max(0, s.values[i] || 0), 0);
    const neg = (i) => series.reduce((a, s) => a + Math.min(0, s.values[i] || 0), 0);
    let yMax = 0, yMin = 0;
    for (let i = 0; i < n; i++) { yMax = Math.max(yMax, tot(i)); yMin = Math.min(yMin, neg(i)); }
    if (yMax === yMin) yMax = 1;
    const f = frame(W, H, n, yMin, yMax, fmt, (i) => xfmt(opt.x[i]), { ...opt, bars: true });
    const bw = Math.max(1, f.band * 0.72), pf = opt.provisionalFrom ?? n;
    let body = f.g;
    const ids = series.map((s) => { const id = 'h' + (++uid); body += defs(id, s.color); return id; });
    for (let i = 0; i < n; i++) {
      let up = 0, dn = 0;
      series.forEach((s, k) => {
        const v = s.values[i] || 0;
        if (!v) return;
        const y0 = v > 0 ? up : dn, y1 = y0 + v;
        if (v > 0) up = y1; else dn = y1;
        const top = f.Y(Math.max(y0, y1)), h = Math.abs(f.Y(y0) - f.Y(y1));
        const x = f.XB(i) + (f.band - bw) / 2;
        body += `<rect x="${x.toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(0.5, h).toFixed(1)}" rx="${Math.min(3, bw / 5).toFixed(1)}" fill="${i >= pf ? `url(#${ids[k]})` : s.color}" ${i >= pf ? `stroke="${s.color}" stroke-width=".8"` : ''}/>`;
      });
    }
    body += `<line class="cursor" x1="0" x2="0" y1="${f.m.t}" y2="${H - f.m.b}" stroke="${FAINT}" stroke-dasharray="2 2" style="display:none"/>`;
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="height:${H}px">${body}</svg>` + legend(series);
    overlay(el.querySelector('svg'), el, n, f, W, { ...opt, bars: true }, (i) => {
      const rows = series.filter((s) => s.values[i]).map((s) => ({ name: s.name, color: s.color, value: fmt(s.values[i]) }));
      if (series.length > 1) rows.push({ name: 'Total', color: 'transparent', value: fmt(tot(i) + neg(i)) });
      return tipHtml(xfmt(opt.x[i]), rows, (i >= pf ? '⚠ en cours de maturation' : '') + (opt.note ? opt.note(i) || '' : ''));
    });
  }

  /** Barres horizontales triées. opt = { rows: [{label, value, color?, note?}], fmt, onClick(row) } */
  function hbars(el, opt) {
    const rows = opt.rows.filter((r) => r.value != null);
    if (!rows.length) { el.innerHTML = '<div class="empty">Aucune donnée</div>'; return; }
    const max = Math.max(...rows.map((r) => Math.abs(r.value))) || 1, fmt = opt.fmt || String;
    el.innerHTML = '<div style="display:flex;flex-direction:column;gap:2px">' + rows.map((r, i) =>
      `<div class="hb" data-i="${i}" style="display:grid;grid-template-columns:minmax(140px,36%) 1fr minmax(64px,auto) ${rows.some((x) => x.note) ? 'minmax(64px,auto)' : ''};gap:12px;align-items:center;font-size:14px;padding:6px 8px;border-radius:10px;${opt.onClick ? 'cursor:pointer' : ''}${r.on ? ';background:#fff8d6' : ''}">
        <span class="ell" title="${esc(r.label)}" style="max-width:100%;font-weight:600">${esc(r.label)}</span>
        <span style="background:#f1f4f9;border-radius:6px;height:${opt.thin ? 10 : 18}px;position:relative;overflow:hidden"><span style="position:absolute;inset:0 auto 0 0;width:${(Math.abs(r.value) / max * 100).toFixed(1)}%;background:${r.color || '#0a2357'};border-radius:6px"></span></span>
        <span class="num" style="font-weight:800">${esc(fmt(r.value))}</span>${rows.some((x) => x.note) ? `<span class="num muted">${esc(r.note || '')}</span>` : ''}</div>`).join('') + '</div>';
    el.querySelectorAll('.hb').forEach((d) => { d.addEventListener('mouseenter', () => { if (!rows[+d.dataset.i].on) d.style.background = '#f7f9fc'; }); d.addEventListener('mouseleave', () => { if (!rows[+d.dataset.i].on) d.style.background = ''; }); });
    if (opt.onClick) el.querySelectorAll('.hb').forEach((d) => d.addEventListener('click', () => opt.onClick(rows[+d.dataset.i])));
  }

  /** Mini-courbe en ligne (chaîne SVG). */
  function spark(values, opt = {}) {
    const w = opt.w || 160, h = opt.h || 26, v = values.map((x) => (x == null || !isFinite(x) ? null : x));
    const ok = v.filter((x) => x != null);
    if (ok.length < 2) return '';
    const lo = Math.min(...ok), hi = Math.max(...ok), span = hi - lo || 1, n = v.length;
    const X = (i) => (i * (w - 4)) / (n - 1) + 2, Y = (x) => h - 3 - ((x - lo) / span) * (h - 6);
    const pf = opt.provisionalFrom ?? n, c = opt.color || '#1a4fb0';
    let d = '', dp = '';
    v.forEach((x, i) => {
      if (x == null) return;
      if (i <= pf - 1 || pf === n) d += (d ? 'L' : 'M') + X(i).toFixed(1) + ',' + Y(x).toFixed(1);
      if (i >= pf - 1 && pf < n) dp += (dp ? 'L' : 'M') + X(i).toFixed(1) + ',' + Y(x).toFixed(1);
    });
    const last = v.length - 1;
    const first = v.findIndex((x) => x != null), lastOk = v.length - 1 - [...v].reverse().findIndex((x) => x != null);
    const area = opt.area === false ? '' : `<path d="${d}${dp ? dp.replace(/^M[^L]*/, '') : ''}L${X(lastOk).toFixed(1)},${h}L${X(first).toFixed(1)},${h}Z" fill="${opt.color ? c : '#e6edfa'}" opacity="${opt.color ? 0.12 : 1}"/>`;
    return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:${h}px">${area}<path d="${d}" fill="none" stroke="${c}" stroke-width="1.6" vector-effect="non-scaling-stroke"/>${dp ? `<path d="${dp}" fill="none" stroke="${c}" stroke-width="1.6" stroke-dasharray="2 2"/>` : ''}${v[last] != null ? `<circle cx="${X(last)}" cy="${Y(v[last])}" r="3" fill="${opt.color || '#0a2357'}"/>` : ''}</svg>`;
  }

  /** Couleur séquentielle (0..1) ou divergente (-1..1). */
  function seqColor(t) { t = Math.max(0, Math.min(1, t)); return SEQ[Math.round(t * (SEQ.length - 1))]; }
  function divColor(t) {
    t = Math.max(-1, Math.min(1, t));
    const neg = ['#b54708', '#e07a32', '#f3b382', '#fbe1cd'], pos = ['#dde7f8', '#b9cbee', '#3e6cc9', '#0a2357'];
    if (Math.abs(t) < 0.08) return '#f3f5f9';
    return t < 0 ? neg[Math.min(3, Math.floor((1 + t) * 4))] : pos[Math.min(3, Math.floor(t * 4))];
  }

  /** Carte de chaleur HTML. opt = { rows, cols, value(r, c) → nombre|null, fmt, color(v) → css, colFmt, rowFmt, onClick(r, c), title(r, c, v) } */
  function heatmap(el, opt) {
    const { rows, cols } = opt, fmt = opt.fmt || String;
    if (!rows.length || !cols.length) { el.innerHTML = '<div class="empty">Aucune donnée</div>'; return; }
    let h = '<div style="overflow:auto"><table class="heat"><thead><tr><th></th>' + cols.map((c) => `<th>${esc((opt.colFmt || String)(c))}</th>`).join('') + '</tr></thead><tbody>';
    rows.forEach((r, ri) => {
      h += `<tr><th>${esc((opt.rowFmt || String)(r))}</th>`;
      cols.forEach((c, ci) => {
        const v = opt.value(r, c);
        const bg = v == null ? '#fff' : opt.color(v, r, c);
        const dark = v != null && /#(00377d|1f5a9c|3977b8|c0392b|d9665b)/i.test(bg);
        h += `<td data-r="${ri}" data-c="${ci}" style="background:${bg};color:${dark ? '#fff' : '#222a33'}">${v == null ? '' : esc(opt.cellText ? opt.cellText(v) : '')}</td>`;
      });
      h += '</tr>';
    });
    el.innerHTML = h + '</tbody></table></div>';
    el.querySelectorAll('td[data-r]').forEach((td) => {
      const r = rows[+td.dataset.r], c = cols[+td.dataset.c], v = opt.value(r, c);
      td.addEventListener('mousemove', (ev) => tip(opt.title ? opt.title(r, c, v) : `<b>${esc(r)} · ${esc(c)}</b><div>${v == null ? 'aucun envoi' : esc(fmt(v))}</div>`, ev));
      td.addEventListener('mouseleave', untip);
      if (opt.onClick) td.addEventListener('click', () => opt.onClick(r, c));
    });
  }

  /** Nuage de points. opt = { points: [{x, y, r?, color?, label, flag?}], xfmt, yfmt, xlog, height, onClick(p), xLabel, yLabel } */
  function scatter(el, opt) {
    const pts = opt.points.filter((p) => p.x != null && p.y != null && isFinite(p.x) && isFinite(p.y) && (!opt.xlog || p.x > 0));
    if (!pts.length) { el.innerHTML = '<div class="empty">Aucune donnée</div>'; return; }
    const W = width(el), H = opt.height || 280, m = { l: 54, r: 14, t: 10, b: 34 };
    const xv = (x) => (opt.xlog ? Math.log10(x) : x);
    const xs = pts.map((p) => xv(p.x)), ys = pts.map((p) => p.y);
    const x0 = Math.min(...xs), x1 = Math.max(...xs) || 1, y0 = Math.min(0, ...ys), y1 = Math.max(...ys) || 1;
    const X = (x) => m.l + ((xv(x) - x0) / (x1 - x0 || 1)) * (W - m.l - m.r), Y = (y) => m.t + (1 - (y - y0) / (y1 - y0 || 1)) * (H - m.t - m.b);
    let g = '';
    for (const v of ticks(y0, y1, 4)) g += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="${LINE}"/><text x="${m.l - 6}" y="${Y(v) + 4}" text-anchor="end">${esc(opt.yfmt(v))}</text>`;
    const xt = opt.xlog ? [...Array(Math.floor(x1) - Math.ceil(x0) + 1)].map((_, i) => Math.pow(10, Math.ceil(x0) + i)) : ticks(x0, x1, 5);
    for (const v of xt) g += `<text x="${X(v)}" y="${H - 18}" text-anchor="middle">${esc(opt.xfmt(v))}</text>`;
    if (opt.xLabel) g += `<text x="${W - m.r}" y="${H - 3}" text-anchor="end">${esc(opt.xLabel)}</text>`;
    if (opt.yLabel) g += `<text x="${m.l}" y="${m.t + 2}" dx="4" style="font-weight:600">${esc(opt.yLabel)}</text>`;
    pts.forEach((p, i) => { g += `<circle data-i="${i}" cx="${X(p.x).toFixed(1)}" cy="${Y(p.y).toFixed(1)}" r="${p.r || 4}" fill="${p.color || '#0b4a9c'}" fill-opacity="${p.flag ? .9 : .45}" stroke="${p.flag ? '#c0392b' : '#fff'}" stroke-width="${p.flag ? 2 : 1}"/>`; });
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" style="height:${H}px">${g}</svg>`;
    el.querySelectorAll('circle').forEach((c) => {
      const p = pts[+c.dataset.i];
      c.addEventListener('mousemove', (ev) => tip(p.tip || `<b>${esc(p.label)}</b>`, ev));
      c.addEventListener('mouseleave', untip);
      if (opt.onClick) { c.style.cursor = 'pointer'; c.addEventListener('click', () => opt.onClick(p)); }
    });
  }

  /** Forest plot : intervalle [lo, hi] et point central par ligne. opt = { rows: [{label, lo, mid, hi, color, tip}], fmt, onClick } */
  function forest(el, opt) {
    const rows = opt.rows.filter((r) => r.mid != null);
    if (!rows.length) { el.innerHTML = '<div class="empty">Aucune campagne évaluable</div>'; return; }
    const W = width(el), rh = 20, m = { l: Math.min(260, W * 0.38), r: 16, t: 8, b: 22 }, H = m.t + m.b + rows.length * rh;
    const lo = Math.min(0, ...rows.map((r) => r.lo ?? r.mid)), hi = Math.max(0, ...rows.map((r) => r.hi ?? r.mid));
    const X = (v) => m.l + ((v - lo) / (hi - lo || 1)) * (W - m.l - m.r);
    let g = `<line x1="${X(0)}" x2="${X(0)}" y1="${m.t}" y2="${H - m.b}" stroke="${FAINT}" stroke-dasharray="3 3"/>`;
    for (const v of ticks(lo, hi, 5)) g += `<text x="${X(v)}" y="${H - 6}" text-anchor="middle">${esc(opt.fmt(v))}</text>`;
    rows.forEach((r, i) => {
      const y = m.t + i * rh + rh / 2;
      g += `<g data-i="${i}" style="cursor:${opt.onClick ? 'pointer' : 'default'}"><rect x="0" y="${y - rh / 2}" width="${W}" height="${rh}" fill="transparent"/><text x="${m.l - 8}" y="${y + 4}" text-anchor="end">${esc(r.label.length > 42 ? r.label.slice(0, 40) + '…' : r.label)}</text>`;
      if (r.lo != null && r.hi != null) g += `<line x1="${X(r.lo)}" x2="${X(r.hi)}" y1="${y}" y2="${y}" stroke="${r.color}" stroke-width="2"/>`;
      g += `<circle cx="${X(r.mid)}" cy="${y}" r="4" fill="${r.color}"/></g>`;
    });
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" style="height:${H}px">${g}</svg>`;
    el.querySelectorAll('g[data-i]').forEach((gg) => {
      const r = rows[+gg.dataset.i];
      gg.addEventListener('mousemove', (ev) => tip(r.tip || esc(r.label), ev));
      gg.addEventListener('mouseleave', untip);
      if (opt.onClick) gg.addEventListener('click', () => opt.onClick(r));
    });
  }

  /** Distribution : un point par entité, repères P5 / P50 / P95 par groupe. opt = { groups: [{name, values: [{v, label, flag}], q: {p_low, p50, p_high}}], fmt } */
  function strip(el, opt) {
    const groups = opt.groups.filter((g) => g.values.length);
    if (!groups.length) { el.innerHTML = '<div class="empty">Aucune donnée</div>'; return; }
    const W = width(el), rh = 28, m = { l: 170, r: 16, t: 6, b: 22 }, H = m.t + m.b + groups.length * rh;
    const all = groups.flatMap((g) => g.values.map((p) => p.v)), lo = Math.min(0, ...all), hi = Math.max(...all) || 1;
    const X = (v) => m.l + ((v - lo) / (hi - lo || 1)) * (W - m.l - m.r);
    let s = '';
    for (const v of ticks(lo, hi, 5)) s += `<line x1="${X(v)}" x2="${X(v)}" y1="${m.t}" y2="${H - m.b}" stroke="${LINE}"/><text x="${X(v)}" y="${H - 6}" text-anchor="middle">${esc(opt.fmt(v))}</text>`;
    const pts = [];
    groups.forEach((g, gi) => {
      const y = m.t + gi * rh + rh / 2;
      s += `<text x="${m.l - 8}" y="${y + 4}" text-anchor="end">${esc(g.name)} <tspan class="faint">(${g.values.length})</tspan></text>`;
      if (g.q) {
        s += `<rect x="${X(g.q.p_low)}" y="${y - 7}" width="${Math.max(1, X(g.q.p_high) - X(g.q.p_low))}" height="14" fill="#e7eef6" rx="3"/>`;
        s += `<line x1="${X(g.q.p50)}" x2="${X(g.q.p50)}" y1="${y - 9}" y2="${y + 9}" stroke="#00377d" stroke-width="2"/>`;
      }
      g.values.forEach((p, k) => {
        const jitter = ((k * 7919) % 11 - 5) * 0.9;
        pts.push(p);
        s += `<circle data-i="${pts.length - 1}" cx="${X(p.v).toFixed(1)}" cy="${(y + jitter).toFixed(1)}" r="${p.flag ? 3.6 : 2.6}" fill="${p.flag ? '#c0392b' : '#2a78d6'}" fill-opacity="${p.flag ? .95 : .5}"/>`;
      });
    });
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" style="height:${H}px">${s}</svg>`;
    el.querySelectorAll('circle').forEach((c) => {
      const p = pts[+c.dataset.i];
      c.addEventListener('mousemove', (ev) => tip(p.tip || esc(p.label), ev));
      c.addEventListener('mouseleave', untip);
      if (opt.onClick) { c.style.cursor = 'pointer'; c.addEventListener('click', () => opt.onClick(p)); }
    });
  }

  return { line, bars, hbars, spark, heatmap, scatter, forest, strip, seqColor, divColor, colorOf, seed, fix, tip, untip, PALETTE };
})();
