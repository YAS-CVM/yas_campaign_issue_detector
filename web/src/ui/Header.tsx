import { NavLink, useLocation } from 'react-router-dom'

const TABS = [
  ['/overview', 'Overview'], ['/valeur', 'Valeur'], ['/push', 'Push'], ['/inbound', 'Inbound'], ['/risques', 'Risques'],
] as const
const TOOLS = [['/import', 'Importer'], ['/parametres', 'Paramètres']] as const

/** Hauteur fixe (64 px) : la barre de filtres collante se cale dessous sans chevauchement ni décalage. */
export const HEADER_H = 64

const pill = (isActive: boolean, underline = true) => ({
  background: isActive ? 'rgba(255,255,255,.14)' : 'transparent',
  boxShadow: isActive && underline ? 'inset 0 -2px 0 var(--yellow)' : 'none',
  color: '#fff', opacity: isActive ? 1 : 0.78,
})

/** En-tête de marque : logo, navigation des rapports, outils, export (impression PDF). */
export function Header() {
  const { search } = useLocation()   // les filtres suivent l'utilisateur d'un onglet à l'autre
  return (
    <header className="app-header no-print sticky top-0 z-30" style={{ background: 'var(--brand)', height: HEADER_H }}>
      <div className="mx-auto flex h-full max-w-[1440px] items-center gap-4 px-6">
        <NavLink to={{ pathname: '/overview', search }} className="flex shrink-0 items-center gap-3" aria-label="Yas CVM Monitor, accueil">
          {/* Dimensions explicites : le logo ne provoque pas de décalage au chargement. */}
          <img src="/yas_logo.svg" alt="" width={44} height={40} />
          <span className="h-6 w-px" style={{ background: 'rgba(255,255,255,.28)' }} aria-hidden />
          <span className="text-[15px] font-semibold tracking-tight text-white">CVM Monitor</span>
        </NavLink>

        <nav className="ml-4 flex flex-1 items-center gap-1" aria-label="Rapports">
          {TABS.map(([to, label]) => (
            <NavLink key={to} to={{ pathname: to, search }} className="flex h-10 items-center rounded-md px-3.5 text-sm font-medium transition-colors hover:bg-white/10"
              style={({ isActive }) => pill(isActive)}>{label}</NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-1">
          {TOOLS.map(([to, label]) => (
            <NavLink key={to} to={to} className="flex h-9 items-center rounded-md px-3 text-sm transition-colors hover:bg-white/10"
              style={({ isActive }) => pill(isActive, false)}>{label}</NavLink>
          ))}
          <button onClick={() => window.print()} className="ml-2 h-9 rounded-md px-4 text-sm font-semibold transition-opacity hover:opacity-90"
            style={{ background: 'var(--yellow)', color: '#00377d' }}>Exporter PDF</button>
        </div>
      </div>
    </header>
  )
}
