import type { ReactNode } from 'react'

/** Affiche chargement / erreur / vide, sinon le contenu. */
export function State({ q, empty, children, minH = 240 }: {
  q: { isLoading: boolean; isPending?: boolean; error: unknown; data?: any }; empty?: string; children: ReactNode; minH?: number
}) {
  // Squelette de même hauteur que le contenu attendu : rien ne bouge quand les données arrivent.
  if (q.isLoading || q.isPending) return <div className="skeleton" style={{ minHeight: minH }} aria-busy="true" />
  if (q.error) return <div className="p-6 text-sm" style={{ color: 'var(--critical)' }}>Erreur : {String((q.error as Error).message)}</div>
  if (Array.isArray(q.data) && q.data.length === 0) return <div className="p-6 text-sm" style={{ color: 'var(--faint)' }}>{empty ?? 'Aucune donnée pour ces filtres.'}</div>
  return <>{children}</>
}
