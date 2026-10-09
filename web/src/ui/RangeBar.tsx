import { pct } from './format'

/** Valeur positionnée entre P5 et P95 des pairs, avec repère médiane : lisible sans connaître les seuils. */
export function RangeBar({ value, p5, p50, p95, bad }: {
  value: number | null; p5: number | null; p50: number | null; p95: number | null; bad?: boolean
}) {
  if (value == null || p5 == null || p50 == null || p95 == null) return <span style={{ color: 'var(--muted)' }}>—</span>
  const hi = Math.max(p95, value, p50 * 1.2, 1e-9)
  const x = (v: number) => `${Math.min(100, Math.max(0, (v / hi) * 100))}%`
  return (
    <div className="flex items-center gap-2" title={`P5 ${pct(p5)} · médiane ${pct(p50)} · P95 ${pct(p95)}`}>
      <div className="relative h-2 w-28 rounded" style={{ background: 'var(--line)' }}>
        <div className="absolute h-2 rounded opacity-40" style={{ left: x(p5), width: `calc(${x(p95)} - ${x(p5)})`, background: 'var(--accent)' }} />
        <div className="absolute -top-0.5 h-3 w-px" style={{ left: x(p50), background: 'var(--ink)' }} />
        <div className="absolute -top-0.5 h-3 w-1.5 rounded" style={{ left: x(value), background: bad ? 'var(--critical)' : 'var(--good)' }} />
      </div>
      <span className="whitespace-nowrap text-xs tabular-nums">{pct(value)}</span>
    </div>
  )
}
