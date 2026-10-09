import { useEffect } from 'react'
import { DIMENSIONS, useApi, useFilters } from '../api'
import { HEADER_H } from './Header'

const day = (d: Date) => d.toISOString().slice(0, 10)
const shift = (iso: string, days: number) => { const d = new Date(iso + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + days); return day(d) }

const PRESETS = [['7 j', 7], ['30 j', 30], ['90 j', 90]] as const

/**
 * Barre de filtres fixe, toujours visible sous l'en-tête : période, puis les 8 dimensions en listes déroulantes
 * (en cascade : chaque liste ne propose que les valeurs compatibles avec les autres filtres).
 * Les 8 listes sont toujours rendues (désactivées si vide) : la hauteur de la barre ne change jamais.
 */
export function FilterBar() {
  const f = useFilters()
  const opts = useApi<Record<string, string[]>>('/filters/options', undefined, { always: true })
  const o = opts.data ?? {}
  const [lo, hi] = o.date_range ?? []
  const from = f.scalar('date_from'), to = f.scalar('date_to')

  // Période par défaut : 30 derniers jours de données (sauf choix explicite « Tout »).
  useEffect(() => {
    if (hi && !from && !to && f.scalar('p') !== 'all') f.setScalars({ date_from: shift(hi, -29) < lo ? lo : shift(hi, -29), date_to: hi })
  }, [hi]) // eslint-disable-line react-hooks/exhaustive-deps

  const start = (n: number) => (shift(hi, -(n - 1)) < lo ? lo : shift(hi, -(n - 1)))
  const preset = (n: number) => f.setScalars({ date_from: start(n), date_to: hi, p: '' })
  const isPreset = (n: number) => !!hi && to === hi && from === start(n)
  const seg = (on: boolean) => ({ background: on ? 'var(--accent)' : 'transparent', color: on ? '#fff' : 'var(--muted)' })

  return (
    <div className="no-print sticky z-20 border-b" style={{ top: HEADER_H, background: 'var(--surface)', borderColor: 'var(--line)', boxShadow: '0 1px 0 rgba(0,55,125,.04)' }}>
      <div className="mx-auto max-w-[1440px] px-6 py-2.5">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex rounded-lg p-0.5" style={{ border: '1px solid var(--line)', background: 'var(--bg)' }} role="group" aria-label="Période">
            {PRESETS.map(([l, n]) => <button key={l} onClick={() => preset(n)} className="h-7 rounded-md px-3 text-xs font-medium" style={seg(isPreset(n))}>{l}</button>)}
            <button onClick={() => f.setScalars({ date_from: '', date_to: '', p: 'all' })} className="h-7 rounded-md px-3 text-xs font-medium" style={seg(!from && !to)}>Tout</button>
          </div>
          {(['date_from', 'date_to'] as const).map((k) => (
            <input key={k} type="date" min={lo} max={hi} value={f.scalar(k)} aria-label={k === 'date_from' ? 'Du' : 'Au'}
              onChange={(e) => f.setScalar(k, e.target.value)} className="field h-8 px-2 text-xs" />
          ))}
          <div className="ml-auto flex items-center gap-4">
            <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={f.scalar('mature_only') === 'true'} onChange={(e) => f.setScalar('mature_only', e.target.checked ? 'true' : '')} />Envois matures</label>
            <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={f.scalar('include_seeding') === 'true'} onChange={(e) => f.setScalar('include_seeding', e.target.checked ? 'true' : '')} />Seeding</label>
            <button onClick={f.clear} disabled={f.active === 0} className="h-8 rounded-md px-3 text-xs font-medium disabled:opacity-40"
              style={{ border: '1px solid var(--line)', color: 'var(--accent)' }}>
              Réinitialiser{f.active > 0 ? ` (${f.active})` : ''}
            </button>
          </div>
        </div>

        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-8">
          {DIMENSIONS.map((d) => {
            const choices = o[d.opt] ?? []
            const selected = f.values(d.key)[0] ?? ''
            return (
              <select key={d.key} value={selected} aria-label={d.label} disabled={!choices.length && !selected}
                onChange={(e) => f.setMany(d.key, e.target.value ? [e.target.value] : [])}
                className="field h-8 w-full min-w-0 truncate px-2 text-xs disabled:opacity-50"
                style={selected ? { borderColor: 'var(--accent)', background: 'var(--tint)', color: 'var(--accent)', fontWeight: 600 } : undefined}>
                <option value="">{d.label} : tous</option>
                {[...new Set([...(selected ? [selected] : []), ...choices])].map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            )
          })}
        </div>
      </div>
    </div>
  )
}

/** Rappel des filtres appliqués, visible uniquement à l'impression. */
export function PrintHeader({ title }: { title: string }) {
  const f = useFilters()
  const dims = DIMENSIONS.flatMap((d) => f.values(d.key).map((v) => `${d.label} : ${v}`))
  return (
    <div className="print-only mb-4 border-b pb-2 text-sm">
      <div className="text-lg font-bold">Yas CVM Monitor — {title}</div>
      <div>Période : {f.scalar('date_from') || 'début'} → {f.scalar('date_to') || 'fin'}{dims.length ? ' · ' + dims.join(' · ') : ''}</div>
    </div>
  )
}
