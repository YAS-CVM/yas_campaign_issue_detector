import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, useFilters, type Row } from '../api'
import { SeverityBadge } from '../ui/Badge'
import { Card, Grid } from '../ui/Card'
import { BarsH, Columns } from '../ui/Simple'
import { DataTable, type Col } from '../ui/DataTable'
import { Drawer, Facts } from '../ui/Drawer'
import { State } from '../ui/State'
import { SEVERITY, STATUS, int } from '../ui/format'

const ORDER = ['critical', 'major', 'minor', 'info']

export default function Risques() {
  const { params } = useFilters()
  const qc = useQueryClient()
  const [status, setStatus] = useState('open')
  const [severity, setSeverity] = useState('')
  const [text, setText] = useState('')
  const [picked, setPicked] = useState<number[]>([])
  const [open, setOpen] = useState<Row | null>(null)

  const range = new URLSearchParams()
  for (const k of ['date_from', 'date_to']) if (params.get(k)) range.set(k, params.get(k)!)
  const summary = useQuery({ queryKey: ['anomalies-summary', range.toString()], queryFn: () => get<Row>('/anomalies/summary', range) })

  const p = new URLSearchParams(range)
  if (status) p.set('status', status)
  if (severity) p.set('severity', severity)
  if (text) p.set('q', text)
  params.getAll('category').forEach((v) => p.append('category', v))
  const list = useQuery({ queryKey: ['anomalies', p.toString()], queryFn: () => get<Row[]>('/anomalies', p) })

  const update = useMutation({
    mutationFn: async (s: string) => {
      const r = await fetch('/api/v1/anomalies', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: picked, status: s, by: 'ui' }) })
      if (!r.ok) throw new Error(await r.text())
    },
    onSuccess: () => { setPicked([]); qc.invalidateQueries({ queryKey: ['anomalies'] }); qc.invalidateQueries({ queryKey: ['anomalies-summary'] }) },
  })

  const sev: Row[] = summary.data?.by_severity ?? [], byDay: Row[] = summary.data?.by_day ?? [], byRule: Row[] = summary.data?.by_rule ?? []
  const total = sev.reduce((a, r) => a + r.n, 0)
  const perDay = Object.values(byDay.reduce<Record<string, Row>>((m, r) => ((m[r.date] ??= { date: r.date, n: 0 }).n += r.n, m), {})).sort((a, b) => a.date.localeCompare(b.date))

  const cols: Col[] = [
    { key: 'sel', header: '', render: (r) => (
      <input type="checkbox" aria-label="Sélectionner" checked={picked.includes(r.id)} onClick={(e) => e.stopPropagation()}
        onChange={(e) => setPicked(e.target.checked ? [...picked, r.id] : picked.filter((i) => i !== r.id))} />) },
    { key: 'severity', header: 'Sévérité', render: (r) => <SeverityBadge value={r.severity} />, sort: (r) => ORDER.indexOf(r.severity) },
    { key: 'rule_id', header: 'Règle', render: (r) => <span className="whitespace-nowrap">{r.rule_id}</span> }, { key: 'entity_key', header: 'Entité' }, { key: 'date', header: 'Date', render: (r) => <span className="whitespace-nowrap">{r.date}</span> }, { key: 'message', header: 'Constat', render: (r) => <div className="max-w-[420px] text-[12px] leading-snug">{r.message}</div> },
    { key: 'volume', header: 'Volume', align: 'right', render: (r) => int(r.volume) },
    { key: 'status', header: 'Statut', render: (r) => STATUS[r.status] ?? r.status },
  ]

  return (
    <Grid>
      <div className="col-span-12 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {ORDER.map((k) => (
          <div key={k} className="card p-4" style={{ borderTop: `4px solid ${k === 'critical' ? 'var(--critical)' : k === 'major' ? 'var(--major)' : k === 'minor' ? '#2a78d6' : 'var(--info)'}` }}>
            <div className="text-xs" style={{ color: 'var(--muted)' }}>{SEVERITY[k].label}</div>
            <div className="mt-1 text-3xl font-semibold tabular">{int(sev.find((r) => r.severity === k)?.n ?? 0)}</div>
            <div className="mt-0.5 text-[11px]" style={{ color: 'var(--faint)' }}>sur {int(total)} anomalies ouvertes ou acquittées</div>
          </div>
        ))}
      </div>

      <Card className="col-span-12 xl:col-span-6" title="Anomalies par jour" insight="Un pic isolé est un incident ; des barres qui restent hautes jour après jour signalent un problème installé.">
        <State q={summary}><Columns rows={perDay} y="n" name="Anomalies" /></State>
      </Card>
      <Card className="col-span-12 xl:col-span-6" title="Règles les plus déclenchées" insight={byRule[0] ? `« ${byRule[0].rule_name} » (${byRule[0].rule_id}) concentre ${byRule[0].n} anomalies.` : ' '}>
        <State q={summary}><BarsH rows={byRule.map((r) => ({ ...r, label: `${r.rule_id} · ${r.rule_name}` }))} label="label" value="n" /></State>
      </Card>

      <Card className="col-span-12" title="Anomalies" flush right={
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <input placeholder="Rechercher…" aria-label="Rechercher" value={text} onChange={(e) => setText(e.target.value)} className="field px-2 py-1" />
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="field px-2 py-1" aria-label="Statut">
            <option value="">Tous statuts</option>{Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select value={severity} onChange={(e) => setSeverity(e.target.value)} className="field px-2 py-1" aria-label="Sévérité">
            <option value="">Toutes sévérités</option>{ORDER.map((k) => <option key={k} value={k}>{SEVERITY[k].label}</option>)}
          </select>
          {picked.length > 0 && (['ack', 'muted', 'open'] as const).map((s) => (
            <button key={s} onClick={() => update.mutate(s)} className="rounded-md px-2 py-1 text-xs font-semibold text-white" style={{ background: 'var(--accent)' }}>
              {s === 'ack' ? 'Acquitter' : s === 'muted' ? 'Sourdine' : 'Rouvrir'} ({picked.length})
            </button>
          ))}
        </div>}>
        <State q={list} empty="Aucune anomalie."><DataTable rows={list.data ?? []} cols={cols} onRow={setOpen} max={30} exportName="anomalies" /></State>
      </Card>

      <Drawer open={!!open} title={open?.entity_key ?? ''} onClose={() => setOpen(null)}>
        {open && (
          <>
            <p className="mb-4 text-sm">{open.message}</p>
            <Facts rows={[['Règle', `${open.rule_id} · ${open.rule_name}`], ['Sévérité', <SeverityBadge value={open.severity} />], ['Date', open.date], ['Catégorie', open.category ?? '—'],
              ['Valeur', open.value ?? '—'], ['Attendu', open.expected ?? '—'], ['Volume', int(open.volume)], ['Occurrences', open.occurrences], ['Statut', STATUS[open.status] ?? open.status], ['Vue depuis', open.first_seen_at?.slice(0, 10) ?? '—']]} />
          </>
        )}
      </Drawer>
    </Grid>
  )
}
