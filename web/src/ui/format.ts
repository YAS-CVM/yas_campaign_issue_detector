export const int = (v: any) => (v == null ? '—' : Math.round(v).toLocaleString('fr-FR'))
export const pct = (v: any, d = 1) => (v == null ? '—' : `${(v * 100).toFixed(Math.abs(v) < 0.1 ? 2 : d)} %`)
export const delta = (v: any) => (v == null ? '' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)} %`)

export const SEVERITY: Record<string, { label: string; color: string }> = {
  critical: { label: 'Critique', color: 'var(--critical)' },
  major: { label: 'Majeure', color: 'var(--major)' },
  minor: { label: 'Mineure', color: 'var(--minor)' },
  info: { label: 'Info', color: 'var(--info)' },
}
export const STATUS: Record<string, string> = { open: 'Ouverte', ack: 'Acquittée', muted: 'En sourdine', resolved: 'Résolue' }
