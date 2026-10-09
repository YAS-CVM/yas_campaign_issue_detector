/** Palette catégorielle de référence, validée (bande de luminosité, CVD, vision normale) sur fond blanc. */
const SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948']
/** Séquentiel : rampe bleu Yas, du clair (peu) au marine (beaucoup). */
const SEQ = ['#e7eef6', '#c7dbef', '#9bbfe4', '#5f99d2', '#3977b8', '#1f5a9c', '#00377d']
/** Divergent : rouge (en dessous) ↔ bleu (au-dessus), milieu neutre. */
const DIV = ['#c0392b', '#e08a80', '#eceff3', '#7aa5d6', '#00377d']

export interface Tokens {
  ink: string; muted: string; faint: string; line: string; surface: string
  brand: string; yellow: string; accent: string
  good: string; warn: string; critical: string; major: string
  series: string[]; seq: string[]; div: string[]; severity: Record<string, string>
}

const base = {
  ink: '#222a33', muted: '#5b6674', faint: '#8a95a3', line: '#e1e8f0', surface: '#ffffff',
  brand: '#00377d', yellow: '#ffd100', accent: '#00377d',
  good: '#1e8e3e', warn: '#b46e00', critical: '#c0392b', major: '#ec835a',
  series: SERIES, seq: SEQ, div: DIV,
}

export const tokens = (): Tokens => ({
  ...base, severity: { critical: base.critical, major: base.major, minor: SERIES[0], info: base.faint },
})

const KNOWN = ['Informative', 'Bundle Drive Campaign', 'CVM', 'Upsell Campaign', 'Nursery Campaign',
  'DATAFRAMEWORK', 'Engagements', 'Voice Campaigns']

/** La couleur suit l'entité (catégorie), jamais son rang : stable quand les filtres changent. */
export function catColor(name: string, t: Tokens): string {
  const i = KNOWN.indexOf(name)
  if (i >= 0) return t.series[i % t.series.length]
  let h = 0
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) >>> 0
  return t.series[h % t.series.length]
}
