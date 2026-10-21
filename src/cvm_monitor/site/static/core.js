/* Socle de l'interface : données embarquées, état dans l'URL, barre de filtres, composants (tuiles, tableau, tiroir),
 * santé du flux NEON-dx. Aucune requête réseau à l'affichage : tout vient du JSON inclus dans la page. */
'use strict';
const App = (() => {
  const D = JSON.parse(document.getElementById('payload').textContent);
  KPI.init(D);
  const meta = D.meta || {};
  const snaps = D.snapshots || [];

  // ------------------------------------------------------------------ tables en colonnes
  function table(t) {
    if (!t || !t.n) return { n: 0, c: {}, d: {}, v: () => '', all: [] };
    return { n: t.n, c: t.cols, d: t.dict, v: (k, i) => t.dict[k][t.cols[k][i]], all: Array.from({ length: t.n }, (_, i) => i) };
  }
  const P = table(D.push), I = table(D.im), V = table(D.versions);
  const imRules = new Map((D.im_rules || []).map((r) => [String(r.id), r]));
  const dates = [...new Set([...(P.d.d || []), ...(I.d.d || [])])].sort();
  const minDate = dates[0], maxDate = dates[dates.length - 1];
  if (P.n) {
    Charts.seed(P.d.cat);
    // Disparu en cours de mois (perte NEON-dx) : figé alors qu'un fichier ultérieur du même mois aurait dû le contenir.
    P.c.lost = P.c.frozen.map((f, i) => (f && lostMidMonth(P.d.d[P.c.d[i]], P.c.snap[i]) ? 1 : 0));
  }

  // ------------------------------------------------------------------ formats (fr-FR)
  const nf0 = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 });
  const nf2 = new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const F = {
    int: (v) => (v == null || !isFinite(v) ? '–' : nf0.format(v)),
    compact: (v) => {
      if (v == null || !isFinite(v)) return '–';
      const a = Math.abs(v);
      if (a >= 1e9) return nf1.format(v / 1e9) + ' Md';
      if (a >= 1e6) return nf1.format(v / 1e6) + ' M';
      if (a >= 1e4) return nf1.format(v / 1e3) + ' k';
      return nf0.format(v);
    },
    pct: (v) => (v == null || !isFinite(v) ? '–' : (Math.abs(v) < 0.1 ? nf2 : nf1).format(v * 100) + ' %'),
    pct1: (v) => (v == null || !isFinite(v) ? '–' : nf1.format(v * 100) + ' %'),
    pts: (v) => (v == null || !isFinite(v) ? '–' : (v > 0 ? '+' : '') + nf2.format(v * 100) + ' pt'),
    signedPct: (v) => (v == null || !isFinite(v) ? '–' : (v > 0 ? '+' : '') + nf1.format(v * 100) + ' %'),
    money: (v) => (v == null || !isFinite(v) ? '–' : F.compact(v) + ' F'),
    date: (s) => (s ? `${s.slice(8, 10)}/${s.slice(5, 7)}` : '–'),
    dateFull: (s) => (s ? `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}` : '–'),
    dt: (s) => (s ? `${s.slice(8, 10)}/${s.slice(5, 7)} ${s.slice(11, 16)}` : '–'),
    day: (s) => (s ? ['Dimanche', 'Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi'][new Date(s + 'T00:00:00Z').getUTCDay()] + ' ' + F.date(s) : '–'),
    dayLong: (s) => (s ? ['Dimanche', 'Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi'][new Date(s + 'T00:00:00Z').getUTCDay()] + ' ' + F.date(s) : '–'),
  };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const addDays = (s, n) => { const d = new Date(s + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
  const daysBetween = (a, b) => Math.round((new Date(b + 'T00:00:00Z') - new Date(a + 'T00:00:00Z')) / 864e5);
  const range = (a, b) => { const out = []; for (let d = a; d <= b; d = addDays(d, 1)) out.push(d); return out; };
  const isTest = (cat) => (meta.test_categories || []).includes(cat);
  const isTechnical = (bc) => (meta.technical_bc_patterns || []).some((p) => (bc || '').toLowerCase().includes(p.toLowerCase()));

  // ------------------------------------------------------------------ période
  const PRESETS = { '7j': '7 j', '30j': '30 j', mois: 'Mois', tout: 'Tout' };
  function period(st) {
    if (st.p === 'custom' && st.from && st.to) return [st.from, st.to];
    const end = maxDate;
    switch (st.p || '30j') {
      case '7j': return [addDays(end, -6), end];
      case 'mois': return [end.slice(0, 8) + '01', end];
      case 'tout': return [minDate, end];
      default: return [addDays(end, -29), end];
    }
  }
  /** Mesure de la période : dates du jeu de données comprises entre les bornes. */
  const periodDates = (st) => { const [a, b] = period(st); return range(a, b); };

  // ------------------------------------------------------------------ filtrage
  /** Lignes de T dont la date est dans [from, to] et dont chaque dimension filtrée a une valeur retenue. */
  function rows(T, st, dims, opt = {}) {
    if (!T.n) return [];
    const [a, b] = opt.period === false ? [minDate, maxDate] : (opt.range || period(st));
    const dd = T.d.d, dc = T.c.d;
    const okDate = dd.map((x) => x >= a && x <= b);
    const tests = [];
    for (const dim of dims) {
      if (dim.key === opt.except) continue;
      const sel = st[dim.key];
      if (!sel || !sel.length) continue;
      const set = new Set(sel), codes = T.c[dim.dim], dict = T.d[dim.dim];
      const ok = dict.map((x) => set.has(x));
      tests.push((i) => ok[codes[i]]);
    }
    const extra = opt.where;
    const out = [];
    for (let i = 0; i < T.n; i++) {
      if (!okDate[dc[i]]) continue;
      let pass = true;
      for (const t of tests) if (!t(i)) { pass = false; break; }
      if (pass && (!extra || extra(i))) out.push(i);
    }
    return out;
  }

  // ------------------------------------------------------------------ anomalies indexées par entité
  const anomalies = D.anomalies || [];
  const ACTIVE = new Set(['open', 'ack']);
  const alertIndex = new Map();
  function indexAlerts() {
    alertIndex.clear();
    for (const a of anomalies) {
      if (!ACTIVE.has(a.status)) continue;
      const keys = [`${a.entity_type}:${a.entity_key}`];
      for (const id of a.details?.broadcast_ids || []) keys.push(`broadcast:${id}`);
      if (a.entity_type === 'im_rule' && a.details?.rule_id) keys.push(`im_rule:${a.details.rule_id}`);
      for (const k of keys) { if (!alertIndex.has(k)) alertIndex.set(k, []); alertIndex.get(k).push(a); }
    }
  }
  indexAlerts();
  const SEV_RANK = { info: 0, minor: 1, major: 2, critical: 3 };
  const alertsFor = (type, key) => alertIndex.get(`${type}:${key}`) || [];
  function alertBadge(type, key) {
    const list = alertsFor(type, key);
    if (!list.length) return '';
    const worst = list.reduce((w, a) => (SEV_RANK[a.severity] > SEV_RANK[w] ? a.severity : w), 'info');
    return `<a class="badge alert" href="#alertes?ent=${encodeURIComponent(type + ':' + key)}" title="${list.length} alerte(s) active(s)" onclick="event.stopPropagation()"><span class="sev ${worst}"></span>${list.length}</a>`;
  }

  // ------------------------------------------------------------------ santé du flux NEON-dx
  /** Un broadcast vu pour la dernière fois au fichier `snapIdx` a-t-il disparu alors qu'un fichier ultérieur
   *  du même mois aurait dû le contenir ? (sinon : simple fin de mois, le fichier suivant couvre un autre mois) */
  function lostMidMonth(date, snapIdx) {
    const m = date.slice(0, 7);
    for (let k = snapIdx + 1; k < snaps.length; k++) if (snaps[k].snapshot_date.slice(0, 7) === m) return true;
    return false;
  }
  function feedHealth() {
    const sig = [];
    if (!snaps.length) return { level: 'bad', signals: [{ level: 'bad', title: 'Aucun fichier reçu', text: 'Importer un Daily Dashboard NEON-dx.' }] };
    const last = snaps[snaps.length - 1], today = (meta.generated_at || '').slice(0, 10);
    const lag = today ? daysBetween(last.snapshot_date, today) : 0;
    // 1. Fraîcheur : le fichier « till J » arrive normalement le lendemain.
    if (lag > 1) sig.push({ level: lag > 3 ? 'bad' : 'warn', kind: 'fraicheur', title: `Dernier fichier reçu il y a ${lag} jours`,
      text: `Fichier « till ${F.dateFull(last.snapshot_date)} ». Le suivant (till ${F.dateFull(addDays(last.snapshot_date, 1))}) est attendu.` });
    // 2. Fichiers manquants (calendrier : un fichier par jour attendu).
    const have = new Set(snaps.map((s) => s.snapshot_date));
    const missing = range(snaps[0].snapshot_date, last.snapshot_date).filter((d) => !have.has(d));
    const recent = missing.filter((d) => d >= addDays(last.snapshot_date, -14));
    if (recent.length) sig.push({ level: 'warn', kind: 'fichiers', title: `${recent.length} fichier(s) manquant(s) sur 14 jours`,
      text: recent.map(F.date).join(', ') + '. Un fichier manquant en fin de mois fait perdre définitivement la maturité des derniers envois.', days: missing });
    // 3. Lignes en baisse d'un fichier au suivant dans le même mois (fichier tronqué ?).
    for (let k = 1; k < snaps.length; k++) {
      const a = snaps[k - 1], b = snaps[k];
      if (a.snapshot_date.slice(0, 7) !== b.snapshot_date.slice(0, 7)) continue;
      for (const [col, lbl] of [['push_rows', 'Push'], ['im_rows', 'IM']]) {
        if (b[col] < a[col] * 0.97) sig.push({ level: k === snaps.length - 1 ? 'bad' : 'info', kind: 'lignes', date: b.snapshot_date,
          title: `${lbl} : ${F.int(a[col] - b[col])} lignes de moins le ${F.date(b.snapshot_date)}`,
          text: `Le fichier du ${F.dateFull(b.snapshot_date)} contient ${F.int(b[col])} lignes ${lbl} contre ${F.int(a[col])} la veille, dans le même mois : des données ont disparu.` });
      }
    }
    // 4. Broadcasts absents des fichiers suivants : disparition en cours de mois (perte NEON-dx) ou
    //    fin de mois (le fichier ne couvre que le mois en cours). Dans les deux cas, ils restent dans l'historique.
    const tr = new Map(), gone = new Map();
    for (let i = 0; i < P.n; i++) {
      if (!P.c.frozen[i] || !P.c.sent[i]) continue;   // mêmes critères que FEED-04 / SNP-02
      const d = P.v('d', i), last = snaps[P.c.snap[i]];
      const comp = KPI.completion('conv', P.c.age[i]);
      if (lostMidMonth(d, P.c.snap[i])) {
        const s = gone.get(last.snapshot_date) || { n: 0, sent: 0, conv: 0, est: 0, from: d, to: d };
        s.n++; s.sent += P.c.sent[i]; s.conv += P.c.conv[i]; s.est += P.c.conv[i] / comp;
        if (d < s.from) s.from = d;
        if (d > s.to) s.to = d;
        gone.set(last.snapshot_date, s);
      } else if (comp < 0.99) {
        const m = d.slice(0, 7), s = tr.get(m) || { n: 0, conv: 0, est: 0 };
        s.n++; s.conv += P.c.conv[i]; s.est += P.c.conv[i] / comp;
        tr.set(m, s);
      }
    }
    for (const [lastSeen, s] of gone) sig.push({ level: 'bad', kind: 'disparus', date: lastSeen,
      title: `${F.int(s.n)} broadcasts disparus des fichiers après le ${F.date(lastSeen)}`,
      text: `Envois du ${F.date(s.from)} au ${F.date(s.to)} (${F.compact(s.sent)} envoyés) présents dans le fichier du ${F.dateFull(lastSeen)} puis absents de tous les fichiers suivants du même mois. Leurs dernières valeurs connues sont conservées ; ≈ ${F.int(s.est - s.conv)} conversions n'ont jamais été remontées. À signaler à Flytxt.` });
    for (const [m, s] of tr) sig.push({ level: 'warn', kind: 'troncature', month: m,
      title: `${F.int(s.n)} envois de fin ${m} jamais observés matures`,
      text: `Le fichier NEON-dx ne couvre que le mois en cours : ces envois de fin de mois ont disparu avant J+${KPI.maturity}. Conversions observées ${F.int(s.conv)}, estimées à maturité ≈ ${F.int(s.est)} (≈ ${F.int(s.est - s.conv)} manquantes). Prévention : demander à Flytxt d'inclure les 7 derniers jours du mois précédent.` });
    // 5. Remplissage des colonnes : dernier fichier vs fichiers précédents.
    const fill = D.fill || {};
    const colsDead = [];
    for (const [sheet, cols] of Object.entries(fill)) {
      for (const [col, vals] of Object.entries(cols)) {
        const n = vals.length, cur = vals[n - 1];
        const prev = vals.slice(Math.max(0, n - 8), n - 1).filter((x) => x != null);
        if (cur == null) continue;
        if (!prev.length) continue;
        const med = KPI.percentile([...prev].sort((x, y) => x - y), 50);
        const label = `${sheet === 'push' ? 'Push' : 'IM'} · ${col}`;
        if (Math.max(cur, ...prev) === 0) { colsDead.push(label); continue; }
        if (med === 0 && cur > 0) sig.push({ level: 'info', kind: 'remplissage', title: `${label} : commence à être alimentée`, text: `Remplie à ${F.pct1(cur)} dans le dernier fichier, vide auparavant.` });
        else if (med > 0.05 && cur === 0) sig.push({ level: 'bad', kind: 'remplissage', title: `${label} : n'est plus alimentée`, text: `Vide dans le dernier fichier, remplie à ${F.pct1(med)} habituellement.` });
        else if (med > 0.05 && cur < med * 0.6) sig.push({ level: 'warn', kind: 'remplissage', title: `${label} : remplissage en baisse`, text: `${F.pct1(cur)} dans le dernier fichier contre ${F.pct1(med)} habituellement.` });
      }
    }
    if (colsDead.length) sig.push({ level: 'info', kind: 'remplissage', title: `${colsDead.length} colonne(s) jamais alimentée(s) par NEON-dx`, text: colsDead.join(', ') + '. Surveillées : un signal apparaîtra dès qu\'elles se remplissent.' });
    // 6. IM : jours avec impressions mais aucun fulfillment remonté.
    if (I.n) {
      const byDay = KPI.im(I, I.all, (i) => I.v('d', i));
      const dead = [...byDay.values()].filter((s) => s.imp > 0 && s.attempts === 0).map((s) => s.key).sort();
      if (dead.length) sig.push({ level: dead.includes(maxDate) ? 'bad' : 'info', kind: 'im_fulfillment', title: `Fulfillment IM non alimenté ${dead.length} jour(s)`,
        text: `Impressions présentes mais aucun succès ni échec : ${dead.length > 8 ? `du ${F.date(dead[0])} au ${F.date(dead[dead.length - 1])}` : dead.map(F.date).join(', ')}.`, days: dead });
      const recent7 = rows(I, {}, [], { range: [addDays(maxDate, -6), maxDate] });
      for (const s of KPI.im(I, recent7, (i) => I.v('tp', i)).values())
        if (s.imp > 0 && s.attempts === 0) sig.push({ level: 'warn', kind: 'im_touchpoint', title: `${s.key} : aucun fulfillment remonté (7 j)`, text: `${F.int(s.imp)} impressions sans succès ni échec sur 7 jours.` });
    }
    // Alertes ouvertes des règles FEED / SNP : elles comptent dans le niveau de santé.
    for (const a of anomalies) {
      if (a.status !== 'open' || !/^(FEED|SNP)-/.test(a.rule_id) || !(a.severity === 'critical' || a.severity === 'major')) continue;
      if (sig.some((x) => x.alert === a.id)) continue;
      sig.push({ level: a.severity === 'critical' ? 'bad' : 'warn', kind: 'alerte', alert: a.id, title: `${a.rule_id} · ${a.rule_name}`, text: a.message, hidden: true });
    }
    // Signal déjà porté par une alerte ouverte de la règle correspondante : il compte dans le niveau, sans doublon.
    const RULE_OF = { disparus: 'SNP-02', troncature: 'FEED-04', im_fulfillment: 'FEED-03', fichiers: 'FEED-01' };
    const openRules = new Set(anomalies.filter((a) => a.status === 'open' || a.status === 'ack').map((a) => a.rule_id));
    for (const x of sig) if (RULE_OF[x.kind] && openRules.has(RULE_OF[x.kind])) x.hidden = true;
    const rank = { ok: -1, info: 0, warn: 1, bad: 2 };
    sig.sort((a, b) => rank[b.level] - rank[a.level]);
    const level = sig.reduce((w, s) => (rank[s.level] > rank[w] ? s.level : w), 'ok');
    return { level: level === 'info' ? 'ok' : level, signals: sig, last, lag, missing };
  }
  let feedCache = null;
  const feed = () => (feedCache ||= feedHealth());

  // ------------------------------------------------------------------ état et routage
  // Un état par onglet, rangé dans l'URL. Deux natures de clés :
  //  - filtres GLOBAUX (« cat », « p »…) : barre « Filtres de la page », s'appliquent à toutes les cartes ;
  //  - réglages LOCAUX (« heat.m », « cats.cat »…) : « idCarte.clé », ne concernent que la carte idCarte.
  const tabs = new Map();
  const state = {};
  const scrollPos = {};          // position de défilement mémorisée par onglet
  let current = null;
  const isLocal = (k) => k.includes('.');
  function parseHash() {
    const h = location.hash.slice(1);
    const [id, qs] = h.split('?');
    const st = {};
    for (const [k, v] of new URLSearchParams(qs || '')) st[k] = !isLocal(k) && (v.includes('|') || (tabs.get(id)?.multi || []).includes(k)) ? v.split('|').filter(Boolean) : v;
    return { id: tabs.has(id) ? id : 'alertes', st, explicit: !!qs };
  }
  function hashOf(id, st) {
    const qs = Object.entries(st).filter(([, v]) => v != null && v !== '' && !(Array.isArray(v) && !v.length))
      .map(([k, v]) => `${k}=${encodeURIComponent(Array.isArray(v) ? v.join('|') : v)}`).join('&');
    return '#' + id + (qs ? '?' + qs : '');
  }
  const globalOf = (st) => Object.fromEntries(Object.entries(st || {}).filter(([k]) => !isLocal(k)));
  const globalKey = (st) => JSON.stringify(globalOf(st));

  /** Filtre GLOBAL : toute la page est recalculée, à la même position (Retour annule). */
  function set(patch, opt = {}) {
    const st = { ...state[current], ...patch };
    for (const k of Object.keys(patch)) if (patch[k] == null) delete st[k];
    state[current] = st;
    history.pushState(null, '', hashOf(current, st));
    render({ force: true, ...opt });
  }
  /** Changement d'onglet : la position de l'onglet quitté est mémorisée, celle de l'onglet ouvert restaurée. */
  function go(id, st, opt = {}) {
    if (current && current !== id) scrollPos[current] = window.scrollY;
    const changedTab = current !== id;
    current = id;
    if (st) state[id] = st;
    state[id] ||= { ...(tabs.get(id).defaults || {}) };
    const h = hashOf(id, state[id]);
    if (opt.push && location.hash !== h) history.pushState(null, '', h);
    else history.replaceState(null, '', h);
    render({ restoreScroll: changedTab ? (scrollPos[id] || 0) : undefined });
  }
  /** Retour / Suivant du navigateur, ou lien interne #onglet?… : on applique l'URL. */
  function fromUrl() {
    const { id, st, explicit } = parseHash();
    if (!explicit) return go(id, null);
    if (id === current && globalKey(st) === globalKey(state[id])) {
      // seuls des réglages locaux diffèrent : on ne redessine que les cartes concernées
      const before = state[id];
      state[id] = st;
      for (const w of widgets.values()) if (localKey(before, w.id) !== localKey(st, w.id)) drawWidget(w.id, true);
      return;
    }
    go(id, st);
  }

  // ------------------------------------------------------------------ cartes (widgets) et réglages locaux
  const widgets = new Map();     // cartes de l'onglet courant : id → { id, el, draw, pending }
  const localKey = (st, id) => JSON.stringify(Object.entries(st || {}).filter(([k]) => k.startsWith(id + '.')).sort());
  function localOf(id) {
    const out = {}, pre = id + '.';
    for (const [k, v] of Object.entries(state[current] || {})) if (k.startsWith(pre)) out[k.slice(pre.length)] = v;
    return out;
  }
  /** Enregistre et dessine une carte : draw(el, filtresGlobaux, réglagesLocaux). Une carte d'une section
   *  repliée n'est dessinée qu'à son ouverture. */
  const lastHeight = {};          // hauteur de chaque carte au rendu précédent : place réservée (pas de saut)
  let deferQueue = [], deferring = false;
  function widget(el, id, draw) {
    if (!el) return;
    el.dataset.w = id;
    const w = { id, el, draw, pending: false };
    widgets.set(id, w);
    if (lastHeight[id]) el.style.minHeight = lastHeight[id] + 'px';
    if (el.closest('.section.collapsed')) { w.pending = true; return; }
    // Carte sous la zone visible : dessinée juste après l'affichage (images suivantes), dans sa place réservée.
    if (deferring && el.getBoundingClientRect().top > window.innerHeight + 200) { deferQueue.push(id); return; }
    drawWidget(id);
  }
  function flushDeferred() {
    if (!deferQueue.length) return;
    const t0 = performance.now();
    while (deferQueue.length && performance.now() - t0 < 12) drawWidget(deferQueue.shift());
    if (deferQueue.length) requestAnimationFrame(flushDeferred);
  }
  function drawWidget(id, keepHeight) {
    const w = widgets.get(id);
    if (!w || !w.el.isConnected) return;
    if (w.el.closest('.section.collapsed')) { w.pending = true; return; }
    w.pending = false;
    const y = window.scrollY;
    if (keepHeight) w.el.style.minHeight = w.el.offsetHeight + 'px';
    const t0 = performance.now();
    Charts.untip();   // la bulle d'un graphique remplacé ne doit pas rester affichée
    // Tableau en plein écran dans cette carte : on le rétablit après le redessin (réglage local cliqué en plein écran).
    const fullIdx = fullEl && w.el.contains(fullEl) ? [...w.el.querySelectorAll('.grid-host')].indexOf(fullEl) : -1;
    try {
      w.draw(w.el, globalOf(state[current]), localOf(id));
      (window.__widgetMs ||= {})[id] = Math.round((performance.now() - t0) * 10) / 10;
    } catch (e) {
      console.error(e);
      w.el.innerHTML = `<div class="callout bad">Erreur d'affichage : ${esc(e.message)}</div>`;
    }
    if (fullIdx >= 0) { fullEl = null; document.documentElement.classList.remove('has-full'); const g = w.el.querySelectorAll('.grid-host')[fullIdx]; if (g) enterFull(g); }
    if (keepHeight) window.scrollTo(0, y);   // min-height conservé : la carte peut grandir, jamais rétrécir sous le curseur
    else w.el.style.minHeight = '';
  }
  /** Réglage LOCAL : seule la carte `id` est redessinée ; l'URL est mise à jour sans entrée d'historique. */
  function setLocal(id, patch) {
    const st = { ...state[current] };
    for (const [k, v] of Object.entries(patch)) { if (v == null || v === '') delete st[`${id}.${k}`]; else st[`${id}.${k}`] = v; }
    state[current] = st;
    history.replaceState(null, '', hashOf(current, st));
    const t0 = performance.now();
    drawWidget(id, true);
    window.__lastRenderMs = performance.now() - t0;
  }
  /** Badge « filtre local » (jaune) : cliquer le retire. */
  const localBadge = (label, key) => `<button class="local-badge" data-local="${key}" data-val="" title="Filtre de cette carte uniquement : cliquer pour le retirer">↳ ${esc(label)} <span aria-hidden="true">×</span></button>`;
  /** Navigation du Jour J (réglage local) : jour précédent, suivant, dernier jour disponible. Boutons à position fixe. */
  function dayNav(dates, day, last) {
    const k = dates.indexOf(day), prev = dates[k - 1], next = dates[k + 1];
    const v = (d) => (d === last ? '' : d);
    return `<div class="daynav"><button class="iconbtn" data-local="day" data-val="${prev ? v(prev) : ''}" ${prev ? '' : 'disabled'} aria-label="Jour précédent" title="${prev ? F.day(prev) : ''}">‹</button>
      <button class="iconbtn" data-local="day" data-val="${next ? v(next) : ''}" ${next ? '' : 'disabled'} aria-label="Jour suivant" title="${next ? F.day(next) : ''}">›</button>
      <button class="btn" data-local="day" data-val="" ${day === last ? 'disabled' : ''} style="min-height:44px">Dernier jour</button></div>`;
  }
  /** Bascule locale compacte. options = [[valeur, libellé]] */
  const localSeg = (key, options, cur) => `<div class="seg sm" title="Réglage de cette carte uniquement">${options.map(([v, l]) => `<button data-local="${key}" data-val="${v}" class="${String(cur) === String(v) ? 'on' : ''}">${l}</button>`).join('')}</div>`;

  // Titre de page : sur-titre, titre et sous-titre (résumé chiffré fourni par l'onglet via App.subtitle).
  const subtitles = {};
  function renderHead(tab) {
    document.getElementById('ph-eyebrow').textContent = tab.eyebrow || 'Customer Value Management';
    document.getElementById('ph-h1').textContent = tab.title;
    document.getElementById('ph-sub').innerHTML = subtitles[current] || '';
  }
  function subtitle(html) {
    subtitles[current] = html;
    document.getElementById('ph-sub').innerHTML = html;
  }

  // Onglet déjà dessiné avec les mêmes filtres globaux : on se contente de l'afficher (changement d'onglet instantané).
  const rendered = {};
  const invalidate = () => { for (const k of Object.keys(rendered)) delete rendered[k]; };
  function render(opt = {}) {
    const t0 = performance.now();
    if (fullEl && !document.getElementById('tab-' + current)?.contains(fullEl)) exitFull();
    const tab = tabs.get(current);
    document.querySelectorAll('#tabs a').forEach((a) => a.classList.toggle('active', a.dataset.tab === current));
    document.querySelectorAll('main > .tab').forEach((s) => { s.hidden = s.id !== 'tab-' + current; });
    if (!opt.keepFilters) renderFilters(tab, state[current]);
    const el = document.getElementById('tab-' + current);
    const key = globalKey(state[current]);
    if (!opt.force && rendered[current] === key) {
      renderHead(tab);
      renderNav(el);
      if (opt.restoreScroll != null) window.scrollTo(0, opt.restoreScroll);
      window.__lastRenderMs = performance.now() - t0;
      document.title = `${tab.title} · Yas CVM Monitor`;
      return;
    }
    rendered[current] = key;
    exitFull();
    // On fige la hauteur pendant le rendu : sinon la page se vide un instant et le navigateur remonte en haut.
    const y = opt.restoreScroll != null ? opt.restoreScroll : window.scrollY;
    el.style.minHeight = el.offsetHeight + 'px';
    for (const w of widgets.values()) if (w.el.isConnected && w.el.offsetHeight) lastHeight[w.id] = w.el.offsetHeight;
    widgets.clear();
    deferQueue = [];
    deferring = true;
    try {
      subtitles[current] = '';
      renderHead(tab);
      tab.render(el, state[current]);
      decorateSections(el);
    } catch (e) {
      console.error(e);
      el.innerHTML = `<div class="callout bad">Erreur d'affichage : ${esc(e.message)}</div>`;
    } finally {
      deferring = false;
    }
    renderNav(el);
    window.scrollTo(0, y);
    requestAnimationFrame(flushDeferred);
    requestAnimationFrame(() => { el.style.minHeight = ''; window.scrollTo(0, Math.min(y, document.documentElement.scrollHeight)); });
    const ms = performance.now() - t0;
    document.title = `${tab.title} · Yas CVM Monitor`;
    if (window.CVM_DEBUG) console.log(`[cvm] ${current} rendu en ${ms.toFixed(1)} ms`);
    window.__lastRenderMs = ms;
  }

  // ------------------------------------------------------------------ sections repliables et sommaire
  const COLLAPSE_KEY = 'cvm.collapsed';
  function collapsedSet() { try { return new Set(JSON.parse(localStorage.getItem(COLLAPSE_KEY) || '[]')); } catch { return new Set(); } }
  function saveCollapsed(set) { try { localStorage.setItem(COLLAPSE_KEY, JSON.stringify([...set])); } catch { /* stockage indisponible */ } }
  /** Applique l'état replié mémorisé aux sections de l'onglet (avant le dessin des cartes : elles attendent l'ouverture). */
  function decorateSections(root) {
    const closed = collapsedSet();
    root.querySelectorAll('.section[id]').forEach((s) => s.classList.toggle('collapsed', closed.has(`${current}:${s.id}`)));
  }
  function toggleSection(sec, open) {
    const closed = collapsedSet(), key = `${current}:${sec.id}`;
    const willOpen = open ?? sec.classList.contains('collapsed');
    sec.classList.toggle('collapsed', !willOpen);
    sec.querySelector('.sec-toggle')?.setAttribute('aria-expanded', String(willOpen));
    if (willOpen) closed.delete(key); else closed.add(key);
    saveCollapsed(closed);
    if (willOpen) for (const w of widgets.values()) if (w.pending && sec.contains(w.el)) drawWidget(w.id);
  }
  let navObserver = null;
  function renderNav(root) {
    const nav = document.getElementById('secnav');
    if (!nav) return;
    const secs = [...root.querySelectorAll('.section[data-nav]')];
    nav.innerHTML = secs.length ? `<span class="secnav-lbl">Aller à</span>${secs.map((s) => `<a href="#" data-jump="${s.id}">${esc(s.dataset.nav)}</a>`).join('')}<span class="spacer"></span><button class="link small" data-expand-all>Tout déplier</button>` : '';
    nav.hidden = !secs.length;
    navObserver?.disconnect();
    // Lectures de mise en page (hauteur de la barre collante) à l'image suivante : elles ne bloquent pas le rendu.
    requestAnimationFrame(() => observeSections(nav, secs));
  }
  function observeSections(nav, secs) {
    syncSticky();
    if (!secs.length || !('IntersectionObserver' in window)) return;
    const visible = new Map();
    navObserver = new IntersectionObserver((entries) => {
      for (const e of entries) visible.set(e.target.id, e.isIntersecting);
      const first = secs.find((s) => visible.get(s.id));
      nav.querySelectorAll('a').forEach((a) => a.classList.toggle('on', !!first && a.dataset.jump === first.id));
    }, { rootMargin: `-${stickyHeight() + 4}px 0px -55% 0px` });
    secs.forEach((s) => navObserver.observe(s));
  }
  // Hauteur couverte en haut d'écran : en-tête (toujours visible) + barre des filtres actifs et du sommaire.
  const stickyHeight = () => (document.querySelector('.app-header')?.offsetHeight || 0) + (document.getElementById('stickybar')?.offsetHeight || 0);
  function syncSticky() { document.documentElement.style.setProperty('--sticky', stickyHeight() + 'px'); }

  // ------------------------------------------------------------------ barre de filtres
  function renderFilters(tab, st) {
    const bar = document.querySelector('#filterbar .bar');
    const spec = tab.filters || {};
    let h = '';
    const group = (label, html) => (html ? `<div class="fgroup"><div class="flbl">${label}</div>${html}</div>` : '');
    if (spec.period !== false) {
      const p = st.p || '30j';
      const [a, b] = period(st);
      h += group('Période', '<div class="seg seg-4">' + Object.entries(PRESETS).map(([k, l]) => `<button data-set="p" data-val="${k}" class="${p === k ? 'on' : ''}">${l}</button>`).join('') + '</div>'
        + `<div class="dates"><label><span>Du</span><input type="date" class="field" data-period="from" value="${a}" min="${minDate}" max="${maxDate}"></label><label><span>Au</span><input type="date" class="field" data-period="to" value="${b}" min="${minDate}" max="${maxDate}"></label></div>`);
    }
    let dims = '';
    for (const dim of spec.dims || []) {
      const T = dim.T === 'I' ? I : P;
      const idx = rows(T, st, spec.dims, { except: dim.key });
      const counts = new Map();
      for (const i of idx) { const v = T.v(dim.dim, i); counts.set(v, (counts.get(v) || 0) + 1); }
      const sel = st[dim.key] || [];
      for (const v of sel) if (!counts.has(v)) counts.set(v, 0);
      dims += multiSelect(dim, [...counts.entries()].sort((x, y) => x[0].localeCompare(y[0])), sel);
    }
    h += group('Dimensions', dims);
    h += !spec.extra ? '' : spec.extraLabel === null ? spec.extra(st) : group(spec.extraLabel || 'Options', spec.extra(st));
    bar.innerHTML = h;
    // Puces des filtres globaux actifs : visibles en permanence, retirables une à une.
    lastChips = chipsOf(tab, st);
    const chips = document.getElementById('chips');
    // Ligne toujours présente (hauteur fixe) : son apparition décalerait toute la page.
    chips.innerHTML = lastChips.length
      ? `<span class="chips-lbl">Filtres de la page</span>${lastChips.map((c, i) => `<button class="chip-f" data-chip="${i}" title="Retirer ce filtre">${esc(c.label)} <span aria-hidden="true">×</span></button>`).join('')}<button class="link small" data-chip="all">Tout effacer</button>`
      : `<span class="chips-lbl idle">Aucun filtre</span><span class="muted small">${esc(spec.idle || (spec.period !== false ? 'période par défaut (30 j), toutes les dimensions' : 'valeurs par défaut'))}</span>`;
    chips.hidden = false;
    document.getElementById('stickybar').classList.toggle('has-filters', lastChips.length > 0);
  }
  let lastChips = [];
  function chipsOf(tab, st) {
    const out = [], spec = tab.filters || {}, def = tab.defaults || {};
    if (spec.period !== false && (st.p || '30j') !== (def.p || '30j')) {
      const [a, b] = period(st);
      out.push({ label: `Période : ${st.p === 'custom' ? `${F.date(a)} → ${F.date(b)}` : PRESETS[st.p] || st.p}`, patch: { p: def.p || null, from: null, to: null } });
    }
    for (const d of spec.dims || []) {
      const sel = st[d.key] || [];
      if (sel.length) out.push({ label: `${d.label} : ${sel.length > 2 ? `${sel.slice(0, 2).join(', ')} +${sel.length - 2}` : sel.join(', ')}`, patch: { [d.key]: null } });
    }
    for (const c of spec.chips ? spec.chips(st) : []) out.push(c);
    return out;
  }
  function multiSelect(dim, options, sel) {
    const on = sel.length > 0;
    const label = `${dim.label}<em>${on ? (sel.length === 1 ? esc(sel[0]).slice(0, 40) : `${sel.length} sélections`) : dim.all || 'Tous'}</em>`;
    const full = on ? `${dim.label} : ${sel.join(', ')}` : dim.label;
    return `<div class="ms" data-dim="${dim.key}"><button class="${on ? 'on' : ''}" data-open title="${esc(full)}"><span class="ms-lbl">${label}</span><span class="ms-caret" aria-hidden="true">▾</span></button><div class="pop" hidden>
      <input class="field" placeholder="Rechercher…" data-search>
      <div class="opts">${options.map(([v, n]) => `<label><input type="checkbox" value="${esc(v)}" ${sel.includes(v) ? 'checked' : ''}> <span class="ell">${esc(v || '(vide)')}</span> <span class="faint small" style="margin-left:auto">${n}</span></label>`).join('')}</div>
      <div class="acts"><button class="link" data-none>Tout désélectionner</button><button class="btn primary" data-apply>Appliquer</button></div></div></div>`;
  }
  function bindFilterbar() {
    const bar = document.querySelector('#filterbar .bar');
    bar.addEventListener('click', (ev) => {
      const t = ev.target;
      const ms = t.closest('.ms');
      if (t.closest('[data-open]') && ms) {
        const pop = ms.querySelector('.pop'), was = !pop.hidden;
        closePops();
        pop.hidden = was;
        if (!was) pop.querySelector('[data-search]').focus();
        return;
      }
      if (t.closest('[data-none]') && ms) { ms.querySelectorAll('.opts input').forEach((c) => (c.checked = false)); return; }
      if (t.closest('[data-apply]') && ms) {
        const vals = [...ms.querySelectorAll('.opts input:checked')].map((c) => c.value);
        closePops();
        set({ [ms.dataset.dim]: vals.length ? vals : null });
        return;
      }
    });
    document.getElementById('chips').addEventListener('click', (ev) => {
      const c = ev.target.closest('[data-chip]');
      if (!c) return;
      if (c.dataset.chip === 'top') { window.scrollTo({ top: 0, behavior: 'smooth' }); return; }
      if (c.dataset.chip === 'all') set(Object.assign({}, ...lastChips.map((x) => x.patch)));
      else set(lastChips[+c.dataset.chip].patch);
    });
    document.getElementById('secnav').addEventListener('click', (ev) => {
      const a = ev.target.closest('[data-jump]');
      if (a) {
        ev.preventDefault();
        const sec = document.getElementById(a.dataset.jump);
        if (sec?.classList.contains('collapsed')) toggleSection(sec, true);
        sec?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
      if (ev.target.closest('[data-expand-all]')) document.querySelectorAll(`#tab-${current} .section.collapsed`).forEach((sec) => toggleSection(sec, true));
    });
    bar.addEventListener('input', (ev) => {
      if (ev.target.matches('[data-search]')) {
        const q = ev.target.value.toLowerCase();
        ev.target.closest('.pop').querySelectorAll('.opts label').forEach((l) => { l.hidden = !l.textContent.toLowerCase().includes(q); });
      }
    });
    bar.addEventListener('change', (ev) => {
      const t = ev.target;
      if (t.dataset.period) {
        const st = state[current], [a, b] = period(st);
        const from = t.dataset.period === 'from' ? t.value : a, to = t.dataset.period === 'to' ? t.value : b;
        if (from && to && from <= to) set({ p: 'custom', from, to });
      }
    });
    document.addEventListener('click', (ev) => { if (!ev.target.closest('.ms')) closePops(); });
  }
  const closePops = () => document.querySelectorAll('.ms .pop').forEach((p) => (p.hidden = true));

  /** Repère de l'élément cliqué : après le redessin, on retrouve son équivalent et on compense tout décalage. */
  function anchorOf(el) {
    const attr = el.dataset.local != null ? 'data-local' : el.dataset.set != null ? 'data-set' : el.dataset.setMany != null ? 'data-set-many' : null;
    if (!attr) return null;
    return { w: el.closest('[data-w]')?.dataset.w, attr, key: el.getAttribute(attr), text: el.textContent.trim().slice(0, 40), top: el.getBoundingClientRect().top };
  }
  function restoreAnchor(a) {
    if (!a) return;
    const root = (a.w && document.querySelector(`#tab-${current} [data-w="${a.w}"]`)) || document;
    const cands = [...root.querySelectorAll(`[${a.attr}]`)].filter((c) => c.getAttribute(a.attr) === a.key || a.attr === 'data-set-many');
    const el = cands.find((c) => c.textContent.trim().slice(0, 40) === a.text && c.offsetParent !== null);
    if (!el) return;
    const dy = el.getBoundingClientRect().top - a.top;
    if (Math.abs(dy) > 0.5) window.scrollBy(0, dy);
  }
  function anchored(el, fn) {
    const a = anchorOf(el);
    fn();
    restoreAnchor(a);
    requestAnimationFrame(() => restoreAnchor(a));  // après les cartes différées
  }

  /** Délégation globale : data-set="clé" data-val="valeur" (bouton) ou data-set sur un select / input. */
  function bindActions() {
    document.addEventListener('click', (ev) => {
      const loc = ev.target.closest('[data-local]');
      if (loc && loc.tagName !== 'SELECT' && loc.tagName !== 'INPUT') {
        ev.preventDefault();
        ev.stopPropagation();
        const w = loc.closest('[data-w]');
        if (w) anchored(loc, () => setLocal(w.dataset.w, { [loc.dataset.local]: loc.dataset.val }));
        return;
      }
      const goTab = ev.target.closest('[data-go]');
      if (goTab) { ev.preventDefault(); go(goTab.dataset.go, null, { push: true }); return; }
      const many = ev.target.closest('[data-set-many]');
      if (many) { ev.preventDefault(); anchored(many, () => set(JSON.parse(many.dataset.setMany))); return; }
      const tg = ev.target.closest('.section > .head .sec-toggle, .section > .head .sec-title');
      if (tg) { toggleSection(tg.closest('.section')); return; }
      const t = ev.target.closest('[data-set]');
      if (t && t.tagName !== 'SELECT' && t.tagName !== 'INPUT') {
        ev.preventDefault();
        const k = t.dataset.set, v = t.dataset.val;
        const cur = state[current]?.[k];
        anchored(t, () => {
          if (t.dataset.toggle != null) set({ [k]: cur === v ? null : v });
          else if (t.dataset.multi != null) set({ [k]: [v] });
          else set({ [k]: v === '' ? null : v });
        });
        return;
      }
      const o = ev.target.closest('[data-open-drawer]');
      if (o) { ev.preventDefault(); openDrawer(o.dataset.openDrawer); }
    });
    document.addEventListener('change', (ev) => {
      const t = ev.target;
      if (t.dataset.local && (t.tagName === 'SELECT' || t.tagName === 'INPUT')) {
        const w = t.closest('[data-w]');
        if (w) anchored(t, () => setLocal(w.dataset.w, { [t.dataset.local]: t.value || null }));
        return;
      }
      if (t.dataset.set && (t.tagName === 'SELECT' || t.tagName === 'INPUT')) {
        const v = t.type === 'checkbox' ? (t.checked ? '1' : null) : (t.value || null);
        anchored(t, () => set({ [t.dataset.set]: v }));
      }
    });
  }

  // ------------------------------------------------------------------ tiroir
  const drawerOpeners = {};
  function openDrawer(spec) {
    const [type, ...rest] = spec.split(':');
    const key = rest.join(':');
    const fn = drawerOpeners[type];
    if (fn) fn(key);
  }
  function drawer(titleHtml, bodyHtml, after) {
    document.getElementById('drawer-title').innerHTML = titleHtml;
    const body = document.getElementById('drawer-body');
    body.innerHTML = bodyHtml;
    document.getElementById('drawer').hidden = false;
    document.getElementById('drawer-bg').hidden = false;
    body.scrollTop = 0;
    if (after) requestAnimationFrame(() => after(body));
  }
  function closeDrawer() { document.getElementById('drawer').hidden = true; document.getElementById('drawer-bg').hidden = true; Charts.untip(); }

  // ------------------------------------------------------------------ composants
  /** Pastille d'écart : bleu = favorable, orange = défavorable (inverse : une hausse est défavorable). */
  function deltaPill(dl) {
    if (!dl || dl.v == null || !isFinite(dl.v)) return '';
    const v = dl.v, flat = Math.abs(v) < (dl.kind === 'pts' ? 0.0005 : 0.005);
    const dir = flat ? 'flat' : v > 0 ? 'up' : 'down';
    return `<span class="delta ${dir} ${dl.inverse ? 'inv' : ''}" title="${esc(dl.title || '')}">${flat ? '■' : v > 0 ? '▲' : '▼'} ${dl.kind === 'pts' ? F.pts(v) : F.signedPct(v)}</span>`;
  }
  /** Tuile KPI. o = { label, value (texte formaté), prov, nr, sub, delta: {v, kind: 'pct'|'pts', inverse, ref}, spark, click, hint, badge, cls, attrs } */
  function tile(o) {
    const d = deltaPill(o.delta);
    const ref = d ? `<span>${esc(o.delta.ref || 'vs moy. 7 j')}</span>` : '';
    const val = o.nr ? '<span class="nr">n/r</span>' : `<span class="${o.prov ? 'prov' : ''}" title="${esc(o.provTitle || '')}">${o.value}</span>`;
    const tag = o.attrs ? 'button' : 'div';
    return `<${tag} class="tile ${o.click || o.attrs ? 'click' : ''} ${o.cls || ''}" ${o.click ? `data-open-drawer="${esc(o.click)}"` : ''} ${o.attrs || ''}>
      <div class="lbl">${o.dot ? `<span class="d" style="width:10px;height:10px;border-radius:50%;background:${o.dot}"></span>` : ''}${esc(o.label)}${help(o.hint && esc(o.hint))}${o.badge || ''}</div><div class="val">${val}</div>
      ${d || o.dlSlot ? `<div class="dl">${d}${ref}</div>` : ''}${o.sub != null ? `<div class="sub">${o.sub}</div>` : ''}${o.extra || ''}${o.spark ? `<div class="spark">${o.spark}</div>` : ''}</${tag}>`;
  }
  /** Pastille de statut NEON-dx (broadcast ou règle IM), couleur par famille de statut. */
  const ST_CLS = { Delivering: 's-blue', Active: 's-blue', Paused: 's-yel', Targeting: 's-yel', 'Render Scheduled': 's-yel', 'Blackout Pause': '',
    'Blackout Expired': 's-orange', 'Delivery Stalled': 's-red', Aborted: 's-red', Completed: '', Inactive: 'muted' };
  const ST_DOT = { 's-blue': '#1a4fb0', 's-yel': '#c99a00', 's-orange': '#d9620b', 's-red': '#c62828', '': '#7a849a', muted: '#a3abbb' };
  const stCls = (s) => ST_CLS[s] ?? 's-orange';
  const stDot = (s) => ST_DOT[stCls(s)];
  const stPill = (s) => `<span class="st ${stCls(s)}">${esc(s || '–')}</span>`;
  /** Niveau d'un signal du flux (bad / warn / info) en pastille de sévérité. */
  const levelPill = (l) => (l === 'bad' ? '<span class="sev critical">Critique</span>' : l === 'warn' ? '<span class="sev major">À surveiller</span>' : '<span class="sev info">Info</span>');
  /** Icône « ? » cerclée : le texte d'aide (HTML) s'affiche au survol ou au focus clavier. */
  const help = (html) => (html ? `<span class="help" tabindex="0" role="img" aria-label="Aide"><span aria-hidden="true">?</span><span class="help-body" hidden>${html}</span></span>` : '');
  /** Carte. opt = { note (aide), right (réglages locaux), local: [badges de filtre local], flush, id } */
  function card(title, body, opt = {}) {
    const pad = opt.flush ? 'style="padding:12px 16px 0"' : '';
    const local = (opt.local || []).filter(Boolean).join('');
    const head = title || opt.note || opt.right || local
      ? `<div class="head" ${pad}><div class="head-l">${title ? `<h2>${title}</h2>` : ''}${help(opt.note)}${local}</div>${opt.right ? `<div class="head-r">${opt.right}</div>` : ''}</div>` : '';
    const legendHtml = opt.legend ? `<div class="legend" style="margin:-6px 0 12px">${opt.legend.map(([c, l, line]) => `<span><i style="background:${c};${line ? 'height:3px;width:16px;vertical-align:3px' : ''}"></i>${esc(l)}</span>`).join('')}</div>` : '';
    if (legendHtml) body = legendHtml + body;
    return `<div class="card ${opt.flush ? 'flush' : ''}" ${opt.id ? `id="${opt.id}"` : ''}>${head}${body}</div>`;
  }
  /** Section repliable (si `id`) ; `nav` = libellé court dans le sommaire ; `panel` = fond blanc (le contenu est une seule carte) ;
   *  `sub` = résumé chiffré affiché à côté du titre ; `note` = aide (icône « ? »). */
  function section(title, body, opt = {}) {
    const closed = opt.id && collapsedSet().has(`${current}:${opt.id}`);
    return `<div class="section ${opt.panel ? 'panel' : ''} ${closed ? 'collapsed' : ''}" ${opt.id ? `id="${opt.id}"` : ''} ${opt.nav ? `data-nav="${esc(opt.nav)}"` : ''}>
      <div class="head">${opt.id ? `<button class="sec-toggle" aria-expanded="${!closed}" title="Replier / déplier la section">▾</button>` : ''}<h2 class="${opt.id ? 'sec-title' : ''}">${title}</h2>${help(opt.note)}${opt.sub ? `<span class="sec-sub">${opt.sub}</span>` : ''}${opt.right ? `<span class="spacer"></span>${opt.right}` : ''}</div>
      <div class="sec-body">${body}</div></div>`;
  }

  /**
   * Tableau triable, avec recherche, export Excel (.xlsx), arborescence et sélection.
   * opt = { columns: [{key, label, num, fmt(v,row), html(row), sort(row), csv(row), title}], rows, sort: [key, dir],
   *   search: true, csv: 'nom', onRow(row), rowClass(row), limit, tools: html, total: row, select: bool, onSelect(ids), id(row), tall }
   * Lignes arborescentes : row._children (tableau) ; dépliage au clic sur ▸.
   */
  function grid(el, opt) {
    const st = { sort: opt.sort || null, q: '', open: new Set(opt.open || []), sel: new Set(), limit: opt.limit || 300 };
    const cols = opt.columns;
    const idOf = opt.id || ((r) => r._key ?? r.id);
    const sv = (c, r) => (c.sort ? c.sort(r) : r[c.key]);
    function sorted(list) {
      if (!st.sort) return list;
      const [k, dir] = st.sort, c = cols.find((x) => x.key === k) || { key: k };
      const m = dir === 'asc' ? 1 : -1;
      return [...list].sort((a, b) => {
        const x = sv(c, a), y = sv(c, b);
        if (x == null && y == null) return 0;
        if (x == null) return 1;
        if (y == null) return -1;
        return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'fr')) * m;
      });
    }
    function flat(list, lvl, out) {
      for (const r of sorted(list)) {
        out.push([r, lvl]);
        if (r._children && st.open.has(idOf(r))) flat(r._children, lvl + 1, out);
      }
      return out;
    }
    function matches(r) {
      if (!st.q) return true;
      const q = st.q.toLowerCase();
      const hay = (opt.searchText ? opt.searchText(r) : cols.map((c) => r[c.key]).join(' ')).toLowerCase();
      return hay.includes(q) || (r._children || []).some(matches);
    }
    // Colonnes `bar` : mini-barre proportionnelle au maximum de la colonne (lignes de premier niveau).
    const maxOf = {};
    for (const c of cols) if (c.bar) maxOf[c.key] = c.barMax || Math.max(1e-12, ...opt.rows.map((r) => Math.abs(+(c.sort ? c.sort(r) : r[c.key]) || 0)));
    function cell(c, r) {
      const txt = c.html ? c.html(r) : c.fmt ? c.fmt(r[c.key], r) : esc(r[c.key] ?? '');
      if (!c.bar || r === opt.total) return txt;
      const v = Math.abs(+(c.sort ? c.sort(r) : r[c.key]) || 0);
      const color = typeof c.bar === 'function' ? c.bar(r) : '';
      return `<div class="cb"><i><b style="width:${Math.min(100, (v / maxOf[c.key]) * 100).toFixed(1)}%;${color ? `background:${color}` : ''}"></b></i><span>${txt}</span></div>`;
    }
    function draw() {
      const list = flat(opt.rows.filter(matches), 0, []);
      const shown = list.slice(0, st.limit);
      let h = '<table class="t"><thead><tr>';
      if (opt.select) h += `<th style="width:28px"><input type="checkbox" data-all></th>`;
      for (const c of cols) h += `<th data-k="${c.key}" class="${c.num ? 'num' : ''} ${st.sort?.[0] === c.key ? 'sorted ' + st.sort[1] : ''}" title="${esc(c.title || '')}" ${c.bar ? 'style="min-width:170px"' : ''}>${esc(c.label)}</th>`;
      h += '</tr></thead><tbody>';
      if (!shown.length) h += `<tr><td colspan="${cols.length + (opt.select ? 1 : 0)}" class="empty">${opt.empty || 'Aucune ligne'}</td></tr>`;
      shown.forEach(([r, lvl], n) => {
        const id = idOf(r);
        const cls = [opt.onRow ? 'click' : '', lvl ? 'lvl' + Math.min(lvl, 2) : '', st.sel.has(id) ? 'sel' : '', opt.rowClass ? opt.rowClass(r) : ''].join(' ');
        h += `<tr class="${cls}" data-n="${n}">`;
        if (opt.select) h += `<td><input type="checkbox" data-id="${esc(id)}" ${st.sel.has(id) ? 'checked' : ''}></td>`;
        cols.forEach((c, ci) => {
          const tw = ci === 0 && r._children ? `<span class="tw" data-tw="${esc(id)}">${st.open.has(id) ? '▾' : '▸'}</span>` : (ci === 0 && opt.tree ? '<span class="tw"></span>' : '');
          h += `<td class="${c.num ? 'num' : ''}">${tw}${cell(c, r)}</td>`;
        });
        h += '</tr>';
      });
      if (opt.total && shown.length) h += '<tr class="tot">' + (opt.select ? '<td></td>' : '') + cols.map((c, ci) => `<td class="${c.num ? 'num' : ''}">${ci === 0 ? 'Total' : (opt.total[c.key] != null || c.html ? cell(c, opt.total) : '')}</td>`).join('') + '</tr>';
      h += '</tbody></table>';
      if (list.length > st.limit) h += `<div class="empty"><button class="btn" data-more>Afficher ${Math.min(list.length - st.limit, 300)} lignes de plus (${list.length - st.limit} restantes)</button></div>`;
      body.innerHTML = h;
      count.textContent = `${F.int(opt.rows.filter(matches).length)} ligne(s)`;
      body._shown = shown;
    }
    el.classList.add('grid-host');
    el.innerHTML = `<div class="full-head"><b class="full-title"></b><span class="small muted">Esc</span><button class="x" data-full-exit aria-label="Quitter le plein écran" title="Quitter le plein écran (Échap)">×</button></div>
      <div class="tbl-tools">${opt.search !== false ? '<input class="field" placeholder="Rechercher…" data-q>' : ''}<span class="small muted count" data-count></span><span class="spacer"></span>${opt.tools || ''}${opt.csv ? `<button class="btn" data-csv title="Télécharger ce tableau (filtres et tri appliqués) au format Excel">${DL_ICON}Export Excel</button>` : ''}<button class="btn icon" data-full title="Plein écran (Esc)" aria-label="Plein écran">${FULL_ICON}</button></div><div class="tbl-wrap ${opt.tall ? 'tall' : ''}"></div>`;
    const body = el.querySelector('.tbl-wrap'), count = el.querySelector('[data-count]');
    el.querySelector('[data-full]').addEventListener('click', () => (fullEl === el ? exitFull() : enterFull(el)));
    el.querySelector('[data-full-exit]').addEventListener('click', exitFull);
    el.querySelector('[data-q]')?.addEventListener('input', (ev) => { st.q = ev.target.value; draw(); });
    el.querySelector('[data-csv]')?.addEventListener('click', () => csv(opt.csv, cols, flat(opt.rows.filter(matches), 0, []).map(([r]) => r)));
    body.addEventListener('click', (ev) => {
      const th = ev.target.closest('th[data-k]');
      if (th) { const k = th.dataset.k; st.sort = st.sort?.[0] === k ? [k, st.sort[1] === 'desc' ? 'asc' : 'desc'] : [k, cols.find((c) => c.key === k)?.num ? 'desc' : 'asc']; draw(); return; }
      if (ev.target.closest('[data-more]')) { st.limit += 300; draw(); return; }
      const tw = ev.target.closest('[data-tw]');
      if (tw) { const id = findId(tw.dataset.tw); if (st.open.has(id)) st.open.delete(id); else st.open.add(id); draw(); ev.stopPropagation(); return; }
      if (ev.target.matches('[data-all]')) { const on = ev.target.checked; st.sel = on ? new Set(body._shown.map(([r]) => idOf(r))) : new Set(); draw(); opt.onSelect?.([...st.sel]); return; }
      if (ev.target.matches('[data-id]')) { const id = findId(ev.target.dataset.id); if (ev.target.checked) st.sel.add(id); else st.sel.delete(id); draw(); opt.onSelect?.([...st.sel]); return; }
      const tr = ev.target.closest('tr[data-n]');
      if (tr && opt.onRow && !ev.target.closest('a')) opt.onRow(body._shown[+tr.dataset.n][0]);
    });
    function findId(s) { for (const [r] of body._shown || []) { const id = idOf(r); if (String(id) === s) return id; } for (const r of opt.rows) { const id = idOf(r); if (String(id) === s) return id; } return s; }
    draw();
    return { redraw: draw, clearSelection: () => { st.sel.clear(); draw(); opt.onSelect?.([]); }, get selection() { return [...st.sel]; } };
  }

  const FULL_ICON = '<svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/></svg>';
  /** Plein écran d'un tableau : il occupe toute la fenêtre (vue large), la page dessous ne bouge pas. Échap ou × pour quitter. */
  let fullEl = null;
  function enterFull(el) {
    exitFull();
    const t = el.closest('.card')?.querySelector(':scope > .head h2')?.textContent.trim() || el.closest('.section')?.querySelector(':scope > .head h2')?.textContent.trim() || 'Tableau';
    el.querySelector('.full-title').textContent = t;
    el.classList.add('full');
    document.documentElement.classList.add('has-full');
    fullEl = el;
    el.querySelector('[data-full-exit]').focus();
  }
  function exitFull() {
    if (!fullEl) return;
    fullEl.classList.remove('full');
    document.documentElement.classList.remove('has-full');
    const btn = fullEl.querySelector('[data-full]');
    fullEl = null;
    btn?.focus({ preventScroll: true });
  }
  const DL_ICON = '<svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/></svg>';
  /** Export Excel du tableau tel qu'affiché (filtres, recherche et tri appliqués). Valeur d'une cellule : `csv(r)` si la
   *  colonne le définit, sinon la valeur brute ; les taux restent des fractions, affichées en % dans Excel. */
  const PCT_COL = /(^|_)(rate|uplift|ci_low|ci_high|comp|share|fill)$|%/i;
  function exportXlsx(name, cols, list) {
    const out = cols.filter((c) => c.export !== false);
    const columns = out.map((c) => ({ label: c.label, kind: c.xkind || (PCT_COL.test(c.key) || /%/.test(c.label) ? 'pct' : undefined) }));
    const rows = list.map((r) => out.map((c) => {
      const v = c.csv ? c.csv(r) : r[c.key];
      return v != null && typeof v === 'object' ? JSON.stringify(v) : v;
    }));
    Xlsx.download(`${name}_${maxDate}`, name, columns, rows);
  }
  const csv = exportXlsx;  // compatibilité : ancien nom

  function toast(msg, bad) {
    const t = document.createElement('div');
    t.className = 'toast' + (bad ? ' bad' : '');
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), bad ? 6000 : 3000);
  }

  /** Série journalière alignée sur `days` à partir d'une Map date → agrégat. */
  const series = (days, map, fn) => days.map((d) => { const s = map.get(d); return s ? fn(s) : null; });
  /** Index du premier jour encore en maturation (âge < âge de référence) : hachures à partir de là. */
  function provisionalFrom(days) {
    const ref = KPI.refAge, lastSnap = snaps.length ? snaps[snaps.length - 1].snapshot_date : maxDate;
    const curve = D.curves?.conversions || [];
    const k = days.findIndex((d) => { const age = daysBetween(d, lastSnap); return age < ref && (curve[age] ?? 1) < 0.99; });
    return k < 0 ? days.length : k;
  }

  /** Comparaison au même jour de semaine (4 semaines précédentes) et à la moyenne des 7 jours précédents. */
  function refs(byDay, day, fn) {
    const prev7 = range(addDays(day, -7), addDays(day, -1)).map((d) => byDay.get(d)).filter(Boolean).map(fn);
    const sameWd = [7, 14, 21, 28].map((k) => byDay.get(addDays(day, -k))).filter(Boolean).map(fn);
    return { avg7: KPI.mean(prev7), wd: KPI.mean(sameWd) };
  }

  /** Infobulles des icônes d'aide (survol souris et focus clavier), via la même bulle que les graphiques. */
  function bindHelp() {
    const show = (h, ev) => Charts.tip(h.querySelector('.help-body').innerHTML, ev);
    document.addEventListener('mouseover', (ev) => { const h = ev.target.closest('.help'); if (h) show(h, ev); });
    document.addEventListener('mousemove', (ev) => { const h = ev.target.closest('.help'); if (h) show(h, ev); });
    document.addEventListener('mouseout', (ev) => { const h = ev.target.closest('.help'); if (h && !h.contains(ev.relatedTarget)) Charts.untip(); });
    document.addEventListener('focusin', (ev) => {
      const h = ev.target.closest?.('.help');
      if (!h) return;
      const r = h.getBoundingClientRect();
      show(h, { clientX: r.right, clientY: r.bottom });
    });
    document.addEventListener('focusout', (ev) => { if (ev.target.closest?.('.help')) Charts.untip(); });
  }

  function start() {
    document.getElementById('drawer-x').addEventListener('click', closeDrawer);
    document.getElementById('drawer-bg').addEventListener('click', closeDrawer);
    // Échap : ferme d'abord le tiroir ou une liste ouverte, sinon quitte le plein écran d'un tableau.
    document.addEventListener('keydown', (ev) => {
      if (ev.key !== 'Escape') return;
      const busy = !document.getElementById('drawer').hidden || [...document.querySelectorAll('.ms .pop')].some((p) => !p.hidden);
      if (busy) { closeDrawer(); closePops(); } else exitFull();
    });
    bindFilterbar();
    bindActions();
    bindHelp();
    // En-tête : compteur d'alertes et pastille de santé du flux.
    const crit = anomalies.filter((a) => a.status === 'open' && (a.severity === 'critical' || a.severity === 'major')).length;
    const cnt = document.getElementById('alert-count');
    if (crit) { cnt.hidden = false; cnt.textContent = crit; cnt.title = `${crit} alerte(s) critique(s) ou majeure(s) ouverte(s)`; }
    const pill = document.getElementById('feed-pill');
    const fh = feed();
    pill.querySelector('.dot').className = 'dot ' + fh.level;
    pill.title = fh.signals.filter((s) => s.level !== 'info').map((s) => '• ' + s.title).join('\n') || 'Flux NEON-dx nominal';
    const toFeed = (ev) => {
      ev.preventDefault();
      if (current !== 'alertes') go('alertes', null, { push: true });
      requestAnimationFrame(() => { const s = document.getElementById('al-q-feed') || document.querySelector('[id^="al-q-"]') || document.getElementById('al-state'); if (s?.classList.contains('collapsed')) toggleSection(s, true); s?.scrollIntoView({ block: 'start' }); });
    };
    pill.addEventListener('click', toFeed);
    document.querySelector('[data-feed]')?.addEventListener('click', toFeed);
    window.addEventListener('popstate', fromUrl);       // Retour / Suivant : annule ou rejoue un filtre global ou un onglet
    window.addEventListener('hashchange', fromUrl);     // liens internes #onglet?…
    window.addEventListener('resize', debounce(() => { invalidate(); render({ keepFilters: true, force: true }); }, 200));
    if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
    const { id, st, explicit } = parseHash();
    go(id, explicit ? st : null);
  }
  function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
  window.addEventListener('DOMContentLoaded', start);

  return {
    D, meta, snaps, P, I, V, imRules, dates, minDate, maxDate, F, esc, addDays, daysBetween, range, isTest, isTechnical,
    period, periodDates, rows, anomalies, alertsFor, alertBadge, indexAlerts, feed, SEV_RANK,
    tab: (id, def) => tabs.set(id, def), set, go, invalidate, widget, setLocal, localBadge, localSeg, dayNav, toggleSection, state: (id) => state[id || current], get current() { return current; },
    drawer, closeDrawer, drawerOpeners, openDrawer, tile, card, section, help, grid, csv, toast, series, provisionalFrom, refs, PRESETS,
    subtitle, deltaPill, stPill, stDot, levelPill, DL_ICON,
  };
})();
