import { useState } from 'react'
import { useApi, useFilters, type Row } from '../api'
import { Card, Grid } from '../ui/Card'
import { DataTable, type Col } from '../ui/DataTable'
import { Pills } from '../ui/Pills'
import { BarsH, Columns, fmtPct, Line } from '../ui/Simple'
import { State } from '../ui/State'
import { int, pct } from '../ui/format'

const GROUPS = [
  { id: 'category', label: 'Catégorie', dim: 'category' as const },
  { id: 'campaign_name', label: 'Campagne', dim: 'campaign' as const },
  { id: 'bc_name', label: 'BC', dim: 'bc' as const },
  { id: 'status', label: 'Statut', dim: 'status' as const },
] as const

export default function Push() {
  const f = useFilters()
  const [g, setG] = useState<(typeof GROUPS)[number]['id']>('category')
  const G = GROUPS.find((x) => x.id === g)!
  const daily = useApi<Row[]>('/push/breakdown', { group_by: 'date' })
  const rows = useApi<Row[]>('/push/breakdown', { group_by: g })
  const score = useApi<Row[]>('/campaigns/scorecard', { key: g === 'bc_name' ? 'bc_name' : 'campaign_name' })
  const key = g === 'bc_name' ? 'bc_name' : 'campaign_name'

  const top = [...(rows.data ?? [])].filter((r) => r.conv_rate != null && r.sent > 0).sort((a, b) => b.sent - a.sent).slice(0, 10)
  const net = [...(score.data ?? [])].filter((r) => r.significant && r.incremental_conversions != null)
    .sort((a, b) => b.incremental_conversions - a.incremental_conversions)
  const shown = [...net.slice(0, 5), ...net.slice(-5)].filter((r, i, a) => a.indexOf(r) === i)

  const cols: Col[] = [
    { key: G.id, header: G.label },
    { key: 'sent', header: 'Envoyés', align: 'right', render: (r) => int(r.sent) },
    { key: 'delivery_rate', header: 'Delivery %', align: 'right', render: (r) => pct(r.delivery_rate) },
    { key: 'conversions', header: 'Conv', align: 'right', render: (r) => int(r.conversions) },
    { key: 'conv_rate', header: 'Conv %', align: 'right', render: (r) => pct(r.conv_rate) },
    { key: 'net_conv_rate', header: 'Net Conv %', align: 'right', render: (r) => pct(r.net_conv_rate) },
  ]

  return (
    <Grid>
      <Card className="col-span-12 xl:col-span-6" title="Envoyés par jour"><State q={daily}><Columns rows={daily.data ?? []} y="sent" name="Envoyés" /></State></Card>
      <Card className="col-span-12 xl:col-span-6" title="Conversion % par jour"><State q={daily}><Line rows={daily.data ?? []} y="conv_rate" name="Conversion %" fmt={fmtPct} /></State></Card>
      <Card className="col-span-12 xl:col-span-6" title="Delivery % par jour"><State q={daily}><Line rows={daily.data ?? []} y="delivery_rate" name="Delivery %" fmt={fmtPct} /></State></Card>
      <Card className="col-span-12 xl:col-span-6" title="Conversions par jour"><State q={daily}><Columns rows={daily.data ?? []} y="conversions" name="Conversions" /></State></Card>

      <Card className="col-span-12 xl:col-span-6" title={`Conversion % : les 10 plus gros volumes (${G.label.toLowerCase()})`}
        right={<Pills items={GROUPS} value={g} onChange={setG} />}>
        <State q={rows}><BarsH rows={top} label={G.id} value="conv_rate" fmt={fmtPct} onPick={(r) => f.drill(G.dim, String(r[G.id]))} /></State>
      </Card>
      <Card className="col-span-12 xl:col-span-6" title="Conversions incrémentales (vs groupe de contrôle)"
        insight="Conversions apportées au-delà de ce que le groupe de contrôle aurait fait seul ; en rouge, sous le contrôle. Seuls les écarts significatifs sont affichés.">
        <State q={score} empty="Pas de groupe de contrôle exploitable.">
          <BarsH rows={shown} label={key} value="incremental_conversions" color={(r, t) => (r.incremental_conversions >= 0 ? t.accent : t.critical)} empty="Aucun écart significatif." />
        </State>
      </Card>

      <Card className="col-span-12" title={`Détail par ${G.label.toLowerCase()}`} flush>
        <State q={rows}><DataTable rows={rows.data ?? []} cols={cols} onRow={(r) => f.drill(G.dim, String(r[G.id]))} max={15} exportName="push" /></State>
      </Card>
    </Grid>
  )
}
