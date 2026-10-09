import { useMemo, useState, type ReactNode } from 'react'

export interface Col<T = any> {
  key: string
  header: string
  render?: (r: T) => ReactNode
  sort?: (r: T) => number | string | null
  align?: 'right'
}

const csvCell = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`

/** Export CSV des lignes affichées (séparateur « ; », BOM pour Excel), avec le tri courant. */
function exportCsv(name: string, cols: Col[], rows: any[]) {
  const data = cols.filter((c) => c.key !== 'sel')
  const text = [data.map((c) => csvCell(c.header)).join(';'), ...rows.map((r) => data.map((c) => csvCell(r[c.key])).join(';'))].join('\n')
  const url = URL.createObjectURL(new Blob(['﻿' + text], { type: 'text/csv;charset=utf-8' }))
  const a = Object.assign(document.createElement('a'), { href: url, download: `${name}.csv` })
  a.click()
  URL.revokeObjectURL(url)
}

export function DataTable<T = any>({ rows, cols, onRow, max = 200, exportName }: {
  rows: T[]; cols: Col<T>[]; onRow?: (r: T) => void; max?: number; exportName?: string
}) {
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null)
  const [all, setAll] = useState(false)
  const data = useMemo(() => {
    const c = cols.find((c) => c.key === sort?.key)
    if (!c || !sort) return rows
    const val = c.sort ?? ((r: any) => r[c.key])
    return [...rows].sort((a, b) => {
      const x = val(a), y = val(b)
      if (x == null) return 1
      if (y == null) return -1
      return (x < y ? -1 : x > y ? 1 : 0) * sort.dir
    })
  }, [rows, cols, sort])
  const shown = all ? data : data.slice(0, max)

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr style={{ color: 'var(--muted)', background: 'var(--tint)' }}>
              {cols.map((c) => (
                <th key={c.key} scope="col" onClick={() => c.header && setSort({ key: c.key, dir: sort?.key === c.key && sort.dir === -1 ? 1 : -1 })}
                  className={`select-none whitespace-nowrap px-4 py-2 text-[11px] font-semibold uppercase tracking-wide ${c.header ? 'cursor-pointer' : ''} ${c.align === 'right' ? 'text-right' : 'text-left'}`}>
                  {c.header}{sort?.key === c.key ? (sort.dir === -1 ? ' ↓' : ' ↑') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((r: any, i) => (
              <tr key={i} onClick={() => onRow?.(r)} className={onRow ? 'cursor-pointer' : ''}
                style={{ borderTop: '1px solid var(--line)' }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--tint)')} onMouseLeave={(e) => (e.currentTarget.style.background = '')}>
                {cols.map((c) => (
                  <td key={c.key} className={`px-4 py-2.5 ${c.align === 'right' ? 'text-right tabular' : ''}`}>{c.render ? c.render(r) : (r[c.key] ?? '—')}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="no-print flex items-center justify-between px-4 py-2 text-xs" style={{ color: 'var(--muted)' }}>
        <span>{shown.length} / {data.length} lignes{data.length > max && !all && <> · <button className="underline" onClick={() => setAll(true)}>tout afficher</button></>}</span>
        {exportName && <button className="underline" onClick={() => exportCsv(exportName, cols, data)}>Exporter CSV</button>}
      </div>
    </div>
  )
}
