import { useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, type Row } from '../api'
import { Card, Grid } from '../ui/Card'
import { State } from '../ui/State'

type Channel = 'teams' | 'email'
interface TestResult { ok: boolean; message: string; at: string }

const SEV: Record<string, string> = { critical: 'Critique', major: 'Majeure', minor: 'Mineure', info: 'Info' }

function Status({ ok, label }: { ok: boolean; label: string }) {
  // Icône + libellé : l'état ne repose jamais sur la couleur seule.
  return <span className="whitespace-nowrap text-xs font-semibold" style={{ color: ok ? 'var(--good)' : 'var(--critical)' }}>{ok ? '✓' : '✕'} {label}</span>
}

function Facts({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[150px_1fr] gap-x-4 gap-y-2 text-sm">
      {rows.map(([k, v]) => (
        <div key={k} className="contents"><dt style={{ color: 'var(--muted)' }}>{k}</dt><dd className="min-w-0 break-words font-medium">{v ?? '—'}</dd></div>
      ))}
    </dl>
  )
}

function TestButton({ channel, disabled }: { channel: Channel; disabled: boolean }) {
  const [last, setLast] = useState<TestResult | null>(null)
  const qc = useQueryClient()
  const run = useMutation({
    mutationFn: async () => {
      const r = await fetch(`/api/v1/settings/alerts/test/${channel}`, { method: 'POST' })
      if (r.status === 429) throw new Error('Un test vient d’être envoyé : patientez quelques secondes.')
      if (!r.ok) throw new Error(`Erreur ${r.status}`)
      return (await r.json()) as TestResult
    },
    onSuccess: (res) => { setLast(res); qc.invalidateQueries({ queryKey: ['alerts-status'] }) },
    onError: (e: Error) => setLast({ ok: false, message: e.message, at: new Date().toISOString() }),
  })

  return (
    <div>
      <button onClick={() => run.mutate()} disabled={disabled || run.isPending}
        className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" style={{ background: 'var(--accent)' }}>
        {run.isPending ? 'Envoi en cours…' : 'Envoyer un message de test'}
      </button>
      {disabled && <p className="mt-2 text-xs" style={{ color: 'var(--muted)' }}>Configurez d’abord les variables manquantes.</p>}
      {/* Zone de résultat à hauteur réservée : le résultat n'agrandit pas la carte. */}
      <div className="mt-3 min-h-[44px] text-sm" role="status" aria-live="polite">
        {last && (
          <div className="rounded-lg p-3" style={{ background: 'var(--tint)', border: `1px solid ${last.ok ? 'var(--good)' : 'var(--critical)'}` }}>
            <Status ok={last.ok} label={last.ok ? 'Envoyé' : 'Échec'} />
            <span className="ml-2" style={{ color: 'var(--muted)' }}>{last.at.slice(11, 19)}</span>
            <div className="mt-1 break-words">{last.message}</div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Settings() {
  const q = useQuery({ queryKey: ['alerts-status'], queryFn: () => get<Row>('/settings/alerts') })
  const t = q.data?.teams, m = q.data?.email

  return (
    <div className="mx-auto max-w-[1100px]">
      <div className="mb-4 min-h-[32px]"><h1 className="text-2xl font-bold tracking-tight">Paramètres</h1></div>
      <State q={q} minH={420}>
        <Grid>
          <Card className="col-span-12 lg:col-span-6" title="Alertes Microsoft Teams"
            insight=""
            right={t && <Status ok={t.configured} label={t.configured ? 'Configuré' : 'Non configuré'} />}>
            <Facts rows={[
              ['Alertes activées', t?.enabled ? 'Oui' : 'Non'],
              ['Sévérité minimale', SEV[t?.min_severity] ?? t?.min_severity],
              ['Anomalies par message', t?.max_items],
              ['Webhook', t?.webhook_host ? `${t.webhook_host} (clé masquée)` : 'Non défini'],
              ['Lien du rapport', q.data?.dashboard_url],
            ]} />
            {t && t.missing.length > 0 && <p className="mt-3 text-xs" style={{ color: 'var(--critical)' }}>MISSING VAR : {t.missing.join(', ')}</p>}
            <div className="mt-5"><TestButton channel="teams" disabled={!t?.configured} /></div>
          </Card>

          <Card className="col-span-12 lg:col-span-6" title="Alertes e-mail"
            insight=""
            right={m && <Status ok={m.configured} label={m.configured ? 'Configuré' : 'Non configuré'} />}>
            <Facts rows={[
              ['Alertes activées', m?.enabled ? 'Oui' : 'Non'],
              ['Sévérité minimale', SEV[m?.min_severity] ?? m?.min_severity],
              ['Envoi', m?.backend === 'outlook' ? 'Outlook local' : `SMTP ${m?.smtp_host ?? '—'}${m?.smtp_port ? `:${m.smtp_port}` : ''}`],
              ['Expéditeur', m?.sender],
              ['Destinataires', m?.recipients?.length ? m.recipients.join(', ') : 'Aucun'],
            ]} />
            {m && m.missing.length > 0 && <p className="mt-3 text-xs" style={{ color: 'var(--critical)' }}>MISSING VAR : {m.missing.join(', ')}</p>}
            <div className="mt-5"><TestButton channel="email" disabled={!m?.configured} /></div>
          </Card>
        </Grid>
        <p className="mt-4 text-xs" style={{ color: 'var(--faint)' }}>
          Les secrets (URL du webhook, mot de passe SMTP) restent dans <code>config/.env</code> et ne sont jamais affichés ici. Les seuils se règlent dans <code>config/config.yaml</code>.
        </p>
      </State>
    </div>
  )
}
