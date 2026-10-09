import { useState } from 'react'
import { useApi, useFilters, type Dim, type Row } from '../api'
import { Card, Grid } from '../ui/Card'
import { DataTable, type Col } from '../ui/DataTable'
import { Drawer, Facts } from '../ui/Drawer'
import { Kpi } from '../ui/Kpi'
import { Pills } from '../ui/Pills'
import { RangeBar } from '../ui/RangeBar'
import { BarsH } from '../ui/Simple'
import { State } from '../ui/State'
import { int, pct } from '../ui/format'

// Niveaux de lecture, du général au fin.
const CAMP = [
  { id: 'category', label: 'Catégorie', name: 'category', dim: 'category' as Dim },
  { id: 'campaign', label: 'Campagne', name: 'campaign_name', dim: 'campaign' as Dim },
  { id: 'bc', label: 'BC', name: 'bc_name', dim: 'bc' as Dim },
] as const
const OFFER = [
  { id: 'touchpoint', label: 'Touchpoint', name: 'touchpoint', dim: 'touchpoint' as Dim },
  { id: 'program', label: 'Programme', name: 'program', dim: 'program' as Dim },
  { id: 'rule', label: 'Règle', name: 'rule_name', dim: 'rule' as Dim },
  { id: 'offer', label: 'Offre', name: 'offer_name', dim: 'offer' as Dim },
] as const

/** Potentiel = (médiane des pairs − valeur) × volume : ce que l'entité gagnerait en rejoignant la médiane. */
const potential = (rows: Row[], rate: string, volume: string, n = 10) =>
  rows.filter((r) => r.p50 != null && r[rate] != null && r.p50 > r[rate])
    .map((r) => ({ ...r, potential: (r.p50 - r[rate]) * r[volume] }))
    .sort((a, b) => b.potential - a.potential).slice(0, n)

export default function Value() {
  const f = useFilters()
  const [ci, setCi] = useState<(typeof CAMP)[number]['id']>('bc')
  const [oi, setOi] = useState<(typeof OFFER)[number]['id']>('offer')
  const [only, setOnly] = useState(false)
  const [pick, setPick] = useState<{ kind: 'camp' | 'offer'; row: Row } | null>(null)
  const summary = useApi<Row>('/value/summary', { campaign_level: ci, offer_level: oi })
  const camp = useApi<Row[]>('/value/campaigns', { level: ci })
  const offers = useApi<Row[]>('/value/offers', { level: oi })
  const C = CAMP.find((c) => c.id === ci)!, O = OFFER.find((o) => o.id === oi)!
  const s = summary.data
  const lvl = C.id === 'bc' ? 'BC' : C.label.toLowerCase()
  const cRows = camp.data ?? [], oRows = offers.data ?? []
  const redIf = (r: Row, t: { critical: string; accent: string }) => (r.underperforming ? t.critical : t.accent)

  const campCols: Col[] = [
    { key: C.name, header: C.label }, { key: 'category', header: 'Catégorie' },
    { key: 'sent', header: 'Envoyés', align: 'right', render: (r) => int(r.sent) },
    { key: 'conv_rate', header: 'Conv % vs pairs', sort: (r) => r.conv_rate, render: (r) => <RangeBar value={r.conv_rate} p5={r.p_low} p50={r.p50} p95={r.p_high} bad={r.underperforming} /> },
    { key: 'missing', header: 'Conv. manquantes', align: 'right', render: (r) => int(r.missing) },
  ]
  const offerCols: Col[] = [
    { key: O.name, header: O.label }, { key: 'touchpoint', header: 'Touchpoint' },
    { key: 'impressions', header: 'Impressions', align: 'right', render: (r) => int(r.impressions) },
    { key: 'take_rate', header: 'Taux d’achat vs pairs', sort: (r) => r.take_rate, render: (r) => <RangeBar value={r.take_rate} p5={r.p_low} p50={r.p50} p95={r.p_high} bad={r.underperforming} /> },
    { key: 'missing_purchases', header: 'Achats manquants', align: 'right', render: (r) => int(r.missing_purchases) },
  ]
  const campTable = only ? cRows.filter((r) => r.underperforming) : cRows
  const offerTable = only ? oRows.filter((r) => r.underperforming) : oRows

  return (
    <>
      <div className="mb-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Campagnes sous-performantes" value={s ? `${s.campaigns_underperforming} / ${s.campaigns_total}` : '…'} hint="queue basse (P5) de leur catégorie" />
        <Kpi label="Conversions manquantes" value={int(s?.missing_conversions)} hint="écart à la médiane des pairs" />
        <Kpi label="Offres sous-performantes" value={s ? `${s.offers_underperforming} / ${s.offers_total}` : '…'} hint="taux d’achat sous le P5 du touchpoint" />
        <Kpi label="Achats manquants (IM)" value={int(s?.missing_purchases)} hint="écart à la médiane des pairs" />
      </div>

      <Grid>
        <Card className="col-span-12 xl:col-span-6" title="Campagnes : potentiel d’amélioration"
          insight={s ? `Conversions en plus si l’entité égalait la médiane de ses pairs (niveau ${lvl}). ${s.campaigns_underperforming ? `En rouge : les ${s.campaigns_underperforming} sous le P5.` : 'Aucune n’est sous le P5 sur cette période.'}` : ' '}
          right={<Pills items={CAMP} value={ci} onChange={setCi} />}>
          <State q={camp}>
            <BarsH rows={potential(cRows, 'conv_rate', 'sent')} label={C.name} value="potential" color={redIf} empty="Aucune entité sous la médiane de ses pairs." onPick={(r) => setPick({ kind: 'camp', row: r })} />
          </State>
        </Card>
        <Card className="col-span-12 xl:col-span-6" title="Offres : potentiel d’amélioration"
          insight={s ? `Achats en plus si l’offre égalait la médiane de son touchpoint. ${s.offers_underperforming ? `En rouge : les ${s.offers_underperforming} sous le P5.` : ''}` : ' '}
          right={<Pills items={OFFER} value={oi} onChange={setOi} />}>
          <State q={offers}>
            <BarsH rows={potential(oRows, 'take_rate', 'impressions')} label={O.name} value="potential" color={redIf} empty="Aucune offre sous la médiane de son touchpoint." onPick={(r) => setPick({ kind: 'offer', row: r })} />
          </State>
        </Card>

        <Card className="col-span-12" title={`Détail des campagnes (${lvl})`} flush right={
          <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={only} onChange={(e) => setOnly(e.target.checked)} />Sous-performants seulement</label>}>
          <State q={camp}><DataTable rows={campTable} cols={campCols} onRow={(r) => setPick({ kind: 'camp', row: r })} max={15} exportName="valeur-campagnes" /></State>
        </Card>
        <Card className="col-span-12" title={`Détail des offres (${O.label.toLowerCase()})`} flush>
          <State q={offers}><DataTable rows={offerTable} cols={offerCols} onRow={(r) => setPick({ kind: 'offer', row: r })} max={15} exportName="valeur-offres" /></State>
        </Card>
      </Grid>

      <Drawer open={!!pick} title={pick ? String(pick.row[pick.kind === 'camp' ? C.name : O.name]) : ''} onClose={() => setPick(null)}>
        {pick && (
          <>
            <Facts rows={pick.kind === 'camp' ? [
              ['Catégorie', pick.row.category ?? '—'], ['Envoyés', int(pick.row.sent)], ['Conversion %', pct(pick.row.conv_rate)],
              ['Médiane des pairs', pct(pick.row.p50)], ['P5 des pairs', pct(pick.row.p_low)], ['Pairs comparés', int(pick.row.n)],
              ['Conv. manquantes', int(pick.row.missing)], ['Net conv %', pct(pick.row.net_conv_rate)],
            ] : [
              ['Touchpoint', pick.row.touchpoint ?? '—'], ['Impressions', int(pick.row.impressions)], ['Taux d’achat', pct(pick.row.take_rate)],
              ['Médiane des pairs', pct(pick.row.p50)], ['P5 des pairs', pct(pick.row.p_low)], ['Pairs comparés', int(pick.row.n)],
              ['Achats manquants', int(pick.row.missing_purchases)], ['Taux d’acceptation', pct(pick.row.accept_rate)],
            ]} />
            <button className="mt-6 rounded-lg px-4 py-2 text-sm font-semibold text-white" style={{ background: 'var(--accent)' }}
              onClick={() => { const d = pick.kind === 'camp' ? C : O; f.drill(d.dim, String(pick.row[d.name])); setPick(null) }}>
              Filtrer sur cette entité
            </button>
          </>
        )}
      </Drawer>
    </>
  )
}
