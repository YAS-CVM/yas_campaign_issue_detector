import { useEffect, type ReactNode } from 'react'

/** Panneau latéral : détail d'une ligne sans quitter la page. Échap ou clic hors panneau pour fermer. */
export function Drawer({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    if (!open) return
    const h = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="no-print fixed inset-0 z-50 flex justify-end" style={{ background: 'rgba(0,20,50,.35)' }} onClick={onClose}>
      <aside className="h-full w-full max-w-md overflow-y-auto p-6" style={{ background: 'var(--surface)', borderLeft: '1px solid var(--line)' }}
        onClick={(e) => e.stopPropagation()} role="dialog" aria-label={title}>
        <div className="mb-4 flex items-start justify-between gap-3">
          <h3 className="text-lg font-semibold leading-snug">{title}</h3>
          <button onClick={onClose} aria-label="Fermer" className="field px-2 py-1 text-sm">✕</button>
        </div>
        {children}
      </aside>
    </div>
  )
}

export function Facts({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
      {rows.map(([k, v]) => (
        <div key={k}><dt className="text-xs" style={{ color: 'var(--muted)' }}>{k}</dt><dd className="font-semibold tabular">{v}</dd></div>
      ))}
    </dl>
  )
}
