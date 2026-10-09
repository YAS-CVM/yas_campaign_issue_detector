import { axis, Chart } from './Chart'
import { int, pct } from './format'
import type { Tokens } from './theme'

type Fmt = (v: number) => string

/** Barres horizontales classées : une série, un axe, valeur écrite au bout de la barre. */
export function BarsH({ rows, label, value, fmt = int, color, onPick, empty = 'Aucune donnée.' }: {
  rows: Record<string, any>[]; label: string; value: string; fmt?: Fmt; color?: (r: any, t: Tokens) => string | undefined
  onPick?: (r: any) => void; empty?: string
}) {
  if (!rows.length) return <div className="p-6 text-sm" style={{ color: 'var(--faint)' }}>{empty}</div>
  return (
    <Chart height={Math.max(rows.length, 10) * 30 + 36} label={`${value} par ${label}`} onClick={(e) => e.data?.row && onPick?.(e.data.row)} build={(t) => ({
      grid: { left: 180, right: 64, top: 4, bottom: 4 },
      tooltip: { formatter: (i: any) => `<b>${i.name}</b><br/>${fmt(i.value)}` },
      xAxis: { type: 'value', show: false },
      yAxis: { type: 'category', inverse: true, data: rows.map((r) => r[label]), ...axis(t), axisLine: { show: false }, splitLine: { show: false },
        axisLabel: { color: t.ink, fontSize: 12, width: 170, overflow: 'truncate' } },
      series: [{ type: 'bar', barWidth: 16, label: { show: true, position: 'right', color: t.muted, fontSize: 12, formatter: (p: any) => fmt(p.value) },
        data: rows.map((r) => ({ value: r[value], name: r[label], row: r, itemStyle: { color: color?.(r, t) ?? t.accent, borderRadius: [0, 4, 4, 0] } })) }],
    })} />
  )
}

/** Courbe simple : une série, un axe. */
export function Line({ rows, x = 'date', y, fmt = int, height = 240, name }: {
  rows: Record<string, any>[]; x?: string; y: string; fmt?: Fmt; height?: number; name: string
}) {
  return (
    <Chart height={height} label={`${name} par jour`} build={(t) => ({
      grid: { left: 56, right: 12, top: 12, bottom: 24 }, legend: { show: false },
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => fmt(v) },
      xAxis: { type: 'category', data: rows.map((r) => r[x]), ...axis(t), axisLabel: { color: t.muted, formatter: (d: string) => d.slice(5) } },
      yAxis: { type: 'value', ...axis(t), axisLabel: { color: t.muted, formatter: (v: number) => fmt(v) } },
      series: [{ name, type: 'line', data: rows.map((r) => r[y]), symbol: 'none', smooth: true, lineStyle: { width: 3, color: t.accent }, areaStyle: { color: t.accent, opacity: 0.08 } }],
    })} />
  )
}

/** Colonnes simples (une série) : volumes par jour. */
export function Columns({ rows, x = 'date', y, fmt = int, height = 240, name, color }: {
  rows: Record<string, any>[]; x?: string; y: string; fmt?: Fmt; height?: number; name: string; color?: string
}) {
  return (
    <Chart height={height} label={`${name} par jour`} build={(t) => ({
      grid: { left: 56, right: 12, top: 12, bottom: 24 }, legend: { show: false },
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => fmt(v) },
      xAxis: { type: 'category', data: rows.map((r) => r[x]), ...axis(t), axisLabel: { color: t.muted, formatter: (d: string) => d.slice(5) } },
      yAxis: { type: 'value', ...axis(t), axisLabel: { color: t.muted, formatter: (v: number) => fmt(v) } },
      series: [{ name, type: 'bar', data: rows.map((r) => r[y]), barMaxWidth: 20, itemStyle: { color: color ?? t.accent, borderRadius: [4, 4, 0, 0] } }],
    })} />
  )
}

export const fmtPct: Fmt = (v) => pct(v)
