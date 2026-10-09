import { useApi, useFilters, type Row } from '../api'
import { Card, Grid } from '../ui/Card'
import { Hero, Kpi } from '../ui/Kpi'
import { BarsH, Columns, fmtPct, Line } from '../ui/Simple'
import { State } from '../ui/State'
import { int, pct } from '../ui/format'

const ratio = (a: number, b: number) => (b > 0 ? a / b : null)
const change = (cur: number | null, prev: number | null) => (cur != null && prev ? (cur - prev) / prev : null)

/** Entonnoir Push en barres : largeur réellement proportionnelle (une conversion minuscule reste minuscule, donc étiquetée). */
function Funnel({ totals }: { totals: Row }) {
  const stages = [['Générés', totals.generated], ['Envoyés', totals.sent], ['Délivrés', totals.delivered], ['Conversions', totals.conversions]] as const
  const top = Math.max(totals.generated, totals.sent, 1)
  return (
    <ol className="space-y-3">
      {stages.map(([label, v], i) => {
        const prev = i ? stages[i - 1][1] : null
        return (
          <li key={label}>
            <div className="mb-1 flex items-baseline justify-between text-sm">
              <span className="font-medium">{label}</span>
              <span className="tabular"><b>{int(v)}</b>{prev ? <span style={{ color: 'var(--muted)' }}> · {pct(ratio(v, prev))} de l’étape précédente</span> : null}</span>
            </div>
            <div className="h-3 rounded-full" style={{ background: 'var(--tint)' }}>
              <div className="h-3 rounded-full" style={{ width: `${Math.max(0.8, (v / top) * 100)}%`, background: i === 3 ? 'var(--yellow)' : 'var(--accent)', opacity: i === 3 ? 1 : 1 - i * 0.18 }} />
            </div>
          </li>
        )
      })}
    </ol>
  )
}

export default function Overview() {
  const f = useFilters()
  const ov = useApi<Row>('/overview')
  const camp = useApi<Row[]>('/value/campaigns', { level: 'campaign', only_underperforming: 'true' })
  const summary = useApi<Row>('/value/summary', { campaign_level: 'campaign' })

  const o = ov.data, t = o?.totals, p = o?.previous
  const pd: Row[] = o?.push_daily ?? [], idl: Row[] = o?.im_daily ?? []
  const convRate = t ? ratio(t.conversions, t.sent) : null, prevConvRate = p ? ratio(p.conversions, p.sent) : null
  const s = summary.data
  const worst = [...(camp.data ?? [])].filter((r) => r.missing >= 1).sort((a, b) => b.missing - a.missing).slice(0, 8)

  return (
    <State q={ov} minH={900}>
      <Grid>
        <Card className="col-span-12 lg:col-span-5">
          <Hero label="Conversions Push" value={int(t?.conversions)} change={p ? change(t.conversions, p.conversions) : null}
            caption={p ? `vs ${int(p.conversions)} sur la période précédente (${p.from} → ${p.to})` : 'Choisissez une période pour comparer'} />
          <div className="mt-5"><Funnel totals={t ?? {}} /></div>
        </Card>

        <div className="col-span-12 grid grid-cols-2 gap-4 lg:col-span-7 xl:grid-cols-3">
          <Kpi label="Push envoyés" value={int(t?.sent)} change={p ? change(t.sent, p.sent) : null} spark={pd.map((r) => r.sent)} />
          <Kpi label="Delivery %" value={pct(t && ratio(t.delivered, t.sent))} change={p ? change(ratio(t.delivered, t.sent), ratio(p.delivered, p.sent)) : null} spark={pd.map((r) => r.delivery_rate)} />
          <Kpi label="Conversion %" value={pct(convRate)} change={change(convRate, prevConvRate)} spark={pd.map((r) => r.conv_rate)} />
          <Kpi label="Impressions IM" value={int(t?.impressions)} change={p ? change(t.impressions, p.impressions) : null} spark={idl.map((r) => r.impressions)} />
          <Kpi label="Fulfillment IM" value={int(t?.fulfillment_success)} change={p ? change(t.fulfillment_success, p.fulfillment_success) : null} spark={idl.map((r) => r.fulfillment_success)} />
          <Kpi label="Failure % IM" invert value={pct(t && ratio(t.fulfillment_failures, t.fulfillment_success + t.fulfillment_failures))}
            change={p ? change(ratio(t.fulfillment_failures, t.fulfillment_success + t.fulfillment_failures), ratio(p.fulfillment_failures, p.fulfillment_success + p.fulfillment_failures)) : null}
            spark={idl.map((r) => r.failure_rate)} />
        </div>

        <Card className="col-span-12 xl:col-span-6" title="Conversions Push par jour"><Columns rows={pd} y="conversions" name="Conversions" /></Card>
        <Card className="col-span-12 xl:col-span-6" title="Conversion % par jour"><Line rows={pd} y="conv_rate" name="Conversion %" fmt={fmtPct} /></Card>

        <Card className="col-span-12" title="Campagnes à regarder en priorité"
          insight={s ? (s.campaigns_underperforming
            ? `${s.campaigns_underperforming} campagnes sur ${s.campaigns_total} convertissent sous le P5 de leur catégorie : ≈ ${int(s.missing_conversions)} conversions manquantes.`
            : 'Aucune campagne sous le P5 de sa catégorie sur cette période.') : ' '}>
          <State q={camp} empty="Aucune campagne sous-performante pour ces filtres.">
            <BarsH rows={worst} label="campaign_name" value="missing" color={(_r, tk) => tk.critical} onPick={(r) => f.drill('campaign', r.campaign_name)} />
          </State>
        </Card>
      </Grid>
    </State>
  )
}
