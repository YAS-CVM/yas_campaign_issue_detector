import { Chart } from './Chart'
import { delta } from './format'

/** Chiffre phare (≥ 48 px) avec variation vs période précédente. */
export function Hero({ label, value, change, caption }: { label: string; value: string; change?: number | null; caption?: string }) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide" style={{ color: 'var(--muted)' }}>{label}</div>
      <div className="mt-1 flex items-baseline gap-3">
        <span className="text-5xl font-bold leading-none">{value}</span>
        {change != null && <Delta v={change} />}
      </div>
      {caption && <div className="mt-2 text-xs" style={{ color: 'var(--muted)' }}>{caption}</div>}
    </div>
  )
}

/** Variation avec flèche + signe (jamais la couleur seule). `invert` : une hausse est mauvaise (ex. failure %). */
export function Delta({ v, invert }: { v: number; invert?: boolean }) {
  const good = invert ? v <= 0 : v >= 0
  return (
    <span className="text-sm font-semibold tabular" style={{ color: good ? 'var(--good)' : 'var(--critical)' }}>
      {v >= 0 ? '▲' : '▼'} {delta(v).replace('+', '')}
    </span>
  )
}

/** Tuile KPI : valeur, variation, mini-courbe. */
export function Kpi({ label, value, change, invert, spark, hint }: {
  label: string; value: string; change?: number | null; invert?: boolean; spark?: number[]; hint?: string
}) {
  return (
    <div className="card relative overflow-hidden p-4">
      <div className="text-xs" style={{ color: 'var(--muted)' }}>{label}</div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="text-2xl font-semibold tabular">{value}</span>
        {change != null && <Delta v={change} invert={invert} />}
      </div>
      {hint && <div className="mt-0.5 text-[11px]" style={{ color: 'var(--faint)' }}>{hint}</div>}
      <div className="mt-2" style={{ height: 36 }}>
        {spark && spark.length > 1 && (
          <Chart height={36} label={`Tendance ${label}`} build={(t) => ({
            grid: { left: 0, right: 0, top: 2, bottom: 2 }, tooltip: { show: false }, legend: { show: false },
            xAxis: { type: 'category', show: false, data: spark.map((_, i) => i) }, yAxis: { type: 'value', show: false, scale: true },
            series: [{ type: 'line', data: spark, smooth: true, symbol: 'none', lineStyle: { width: 2, color: t.accent },
              areaStyle: { color: t.accent, opacity: 0.12 } }],
          })} />
        )}
      </div>
    </div>
  )
}
