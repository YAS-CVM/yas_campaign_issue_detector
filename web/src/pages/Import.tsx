import { useState } from 'react'
import { get } from '../api'
import { Card } from '../ui/Card'

export default function Import() {
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  async function upload(file: File) {
    setBusy(true); setMsg(null)
    try {
      const body = new FormData()
      body.append('file', file)
      const r = await fetch('/api/v1/import', { method: 'POST', body })
      if (!r.ok) throw new Error((await r.json()).detail ?? r.statusText)
      const { job_id } = await r.json()
      for (;;) {
        await new Promise((res) => setTimeout(res, 1000))
        const s = await get<any>(`/import/${job_id}`)
        if (s.state === 'done') { setMsg({ ok: true, text: s.summary }); break }
        if (s.state === 'error') { setMsg({ ok: false, text: s.error }); break }
      }
    } catch (e) {
      setMsg({ ok: false, text: String((e as Error).message) })
    } finally { setBusy(false) }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <Card title="Importer un Daily Dashboard" insight="Fichier .xlsb cumulatif du mois. Un fichier déjà importé est ignoré.">
        <input type="file" accept=".xlsb,.xlsx,.xlsm" disabled={busy} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        {busy && <p className="mt-3 text-sm" style={{ color: 'var(--muted)' }}>Traitement en cours…</p>}
        {msg && <p className="mt-3 text-sm" style={{ color: msg.ok ? 'var(--good)' : 'var(--critical)' }}>{msg.text}</p>}
      </Card>
    </div>
  )
}
