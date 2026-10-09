import type { ReactNode } from 'react'

/** Carte de reporting : titre, constat en une phrase (la « conclusion »), visuel/contenu, actions à droite. */
export function Card({ title, insight, right, children, className = '', flush }: {
  title?: string; insight?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; flush?: boolean
}) {
  return (
    <section className={`card ${className}`}>
      {(title || right) && (
        <header className="flex items-start justify-between gap-3 px-5 pt-4">
          <div className="min-w-0">
            {title && <h2 className="text-[15px] font-semibold leading-tight">{title}</h2>}
            {insight && <p className="mt-1 text-[13px] leading-snug" style={{ color: 'var(--muted)' }}>{insight}</p>}
          </div>
          <div className="no-print shrink-0">{right}</div>
        </header>
      )}
      <div className={flush ? 'pt-2' : 'px-5 pb-4 pt-2'}>{children}</div>
    </section>
  )
}

/** Grille 12 colonnes : les cartes se placent avec `span` (col-span-*), de tailles variées. */
export function Grid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-12 gap-4">{children}</div>
}
