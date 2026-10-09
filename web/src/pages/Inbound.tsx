import { useApi, useFilters, type Row } from '../api'
import { Card, Grid } from '../ui/Card'
import { DataTable, type Col } from '../ui/DataTable'
import { BarsH, Columns, fmtPct, Line } from '../ui/Simple'
import { State } from '../ui/State'
import { int, pct } from '../ui/format'

export default function Inbound() {
  const f = useFilters()
  const daily = useApi<Row[]>('/inbound/daily')
  const rules = useApi<Row[]>('/inbound/rules')
  const worst = [...(rules.data ?? [])].filter((r) => r.failure_rate != null && r.success + r.failures >= 500).sort((a, b) => b.failure_rate - a.failure_rate).slice(0, 10)

  const cols: Col[] = [
    { key: 'rule_name', header: 'Règle' }, { key: 'program', header: 'Programme' }, { key: 'touchpoint', header: 'Touchpoint' },
    { key: 'impressions', header: 'Impressions', align: 'right', render: (r) => int(r.impressions) },
    { key: 'success', header: 'Fulfillment', align: 'right', render: (r) => int(r.success) },
    { key: 'take_rate', header: 'Taux d’achat', align: 'right', render: (r) => pct(r.take_rate) },
    { key: 'failure_rate', header: 'Failure %', align: 'right', render: (r) => pct(r.failure_rate) },
  ]

  return (
    <Grid>
      <Card className="col-span-12 xl:col-span-6" title="Impressions par jour"><State q={daily}><Columns rows={daily.data ?? []} y="impressions" name="Impressions" /></State></Card>
      <Card className="col-span-12 xl:col-span-6" title="Achats réussis (fulfillment) par jour"><State q={daily}><Line rows={daily.data ?? []} y="fulfillment_success" name="Fulfillment" /></State></Card>
      <Card className="col-span-12 xl:col-span-6" title="Taux d’achat par jour"><State q={daily}><Line rows={daily.data ?? []} y="take_rate" name="Taux d’achat" fmt={fmtPct} /></State></Card>
      <Card className="col-span-12 xl:col-span-6" title="Failure % par jour"><State q={daily}><Line rows={daily.data ?? []} y="failure_rate" name="Failure %" fmt={fmtPct} /></State></Card>

      <Card className="col-span-12" title="Règles les plus en échec"
        insight={worst[0] ? `« ${worst[0].rule_name} » échoue ${pct(worst[0].failure_rate)} du temps (règles avec au moins 500 tentatives).` : ' '}>
        <State q={rules} empty="Pas assez de tentatives pour classer les règles.">
          <BarsH rows={worst} label="rule_name" value="failure_rate" fmt={fmtPct} color={(r, t) => (r.failure_rate >= 0.9 ? t.critical : t.major)} onPick={(r) => f.drill('rule', r.rule_name)} />
        </State>
      </Card>

      <Card className="col-span-12" title="Toutes les règles IM" flush>
        <State q={rules}><DataTable rows={rules.data ?? []} cols={cols} onRow={(r) => f.drill('rule', String(r.rule_name))} max={15} exportName="regles-im" /></State>
      </Card>
    </Grid>
  )
}
