/* Agrégations côté navigateur : mêmes formules que analytics/kpi.py (on somme les volumes, puis on calcule le taux ;
 * dénominateur nul → null, jamais 0). S'y ajoute la complétude : les métriques qui arrivent en retard
 * (conversions, valeur, fulfillment, conversions du groupe de contrôle) sont aussi estimées à maturité grâce aux
 * courbes calculées côté Python (analytics/maturity.maturity_curves). */
'use strict';
const KPI = (() => {
  const rate = (a, b) => (b > 0 ? a / b : null);
  const PUSH_SUMS = ['gen', 'sent', 'ack', 'dlv', 'conv', 'uconv', 'val', 'fs', 'ff', 'cg', 'cgc'];
  const LATE = { conv: 'conversions', uconv: 'unique_conversions', val: 'conversion_value', fs: 'fulfillment_success', ff: 'fulfillment_failure', cgc: 'cg_conversions' };
  const IM_SUMS = ['imp', 'fs', 'ff', 'acc', 'dec', 'later', 'conv'];
  let curves = {}, refAge = 10, maturity = 3;

  function init(payload) {
    curves = payload.curves || {};
    refAge = payload.meta.maturity_reference_age || 10;
    maturity = payload.meta.maturity_days || 3;
  }

  /** Part de la valeur finale déjà connue à cet âge (1 au-delà de l'âge de référence ou sans courbe). */
  function completion(metric, age) {
    const c = curves[LATE[metric] || metric];
    if (!c || age >= c.length - 1) return 1;
    return c[Math.max(0, age)] || 1;
  }

  function emptyPush() {
    const s = { n: 0, est: {}, prov: 0, trunc: 0, lost: 0, truncMiss: 0, genMissing: 0, seedConv: 0 };
    for (const k of PUSH_SUMS) s[k] = 0;
    for (const k in LATE) s.est[k] = 0;
    return s;
  }

  /** Ajoute la ligne i de la table Push P à l'agrégat s. */
  function addPush(s, P, i) {
    const c = P.c;
    s.n++;
    for (const k of PUSH_SUMS) s[k] += c[k][i];
    const age = c.age[i], frozen = c.frozen[i];
    let provisional = false;
    for (const k in LATE) {
      const comp = completion(k, age);
      s.est[k] += comp < 1 ? c[k][i] / comp : c[k][i];
      if (k === 'conv' && comp < 0.99) provisional = true;
    }
    if (c.lost && c.lost[i]) s.lost++;              // disparu des fichiers en cours de mois
    if (provisional && frozen) {                    // n'atteindra jamais la maturité dans les données
      s.trunc++;
      s.truncMiss += c.conv[i] / completion('conv', age) - c.conv[i];
    } else if (provisional) s.prov++;               // en cours de maturation
    if (!c.gen[i] && c.sent[i] > 0) s.genMissing++; // Generated non renseigné (flows)
    if (c.seed[i]) s.seedConv += c.conv[i];
    return s;
  }

  function pushRates(s) {
    s.delivery_rate = rate(s.dlv, s.sent);
    s.ack_rate = rate(s.ack, s.sent);
    s.conv_rate = rate(s.conv, s.sent);
    s.conv_rate_est = rate(s.est.conv, s.sent);
    s.cg_conv_rate = rate(s.cgc, s.cg);
    s.cg_conv_rate_est = rate(s.est.cgc, s.cg);
    s.net_conv_rate = s.conv_rate != null && s.cg_conv_rate != null ? s.conv_rate - s.cg_conv_rate : null;
    s.net_conv_rate_est = s.conv_rate_est != null && s.cg_conv_rate_est != null ? s.conv_rate_est - s.cg_conv_rate_est : null;
    s.ff_rate = rate(s.ff, s.fs + s.ff);
    // Part encore attendue : écart entre estimé à maturité et observé (0 = définitif).
    s.pending = s.est.conv > 0 ? 1 - s.conv / s.est.conv : 0;
    // Part des conversions qui ne remonteront jamais (envois figés avant maturité) : badge « tronqué » au-delà de 1 %.
    s.truncShare = s.est.conv > 0 ? s.truncMiss / s.est.conv : 0;
    return s;
  }

  /** Agrège les lignes `idx` de P, par clé (keyFn(i) → chaîne) ou au total si keyFn est absent. */
  function push(P, idx, keyFn) {
    if (!keyFn) { const s = emptyPush(); for (const i of idx) addPush(s, P, i); return pushRates(s); }
    const m = new Map();
    for (const i of idx) {
      const k = keyFn(i);
      let s = m.get(k);
      if (!s) { s = emptyPush(); s.key = k; m.set(k, s); }
      addPush(s, P, i);
    }
    for (const s of m.values()) pushRates(s);
    return m;
  }

  function emptyIm() { const s = { n: 0 }; for (const k of IM_SUMS) s[k] = 0; return s; }
  function imRates(s) {
    s.take_rate = rate(s.fs, s.imp);
    s.failure_rate = rate(s.ff, s.fs + s.ff);
    s.attempts = s.fs + s.ff;
    return s;
  }
  function im(I, idx, keyFn) {
    const add = (s, i) => { s.n++; for (const k of IM_SUMS) s[k] += I.c[k][i]; };
    if (!keyFn) { const s = emptyIm(); for (const i of idx) add(s, i); return imRates(s); }
    const m = new Map();
    for (const i of idx) {
      const k = keyFn(i);
      let s = m.get(k);
      if (!s) { s = emptyIm(); s.key = k; m.set(k, s); }
      add(s, i);
    }
    for (const s of m.values()) imRates(s);
    return m;
  }

  /** Percentile (interpolation linéaire, comme numpy.percentile). */
  function percentile(sorted, p) {
    if (!sorted.length) return null;
    const pos = (sorted.length - 1) * p / 100, lo = Math.floor(pos), hi = Math.ceil(pos);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
  }
  const mean = (a) => { const v = a.filter((x) => x != null && isFinite(x)); return v.length ? v.reduce((x, y) => x + y, 0) / v.length : null; };

  return { init, completion, push, im, pushRates, imRates, rate, percentile, mean, LATE, get maturity() { return maturity; }, get refAge() { return refAge; } };
})();
if (typeof module !== 'undefined') module.exports = KPI; // tests de parité (node)
