import { Navigate, Route, Routes } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { get, type Row } from './api'
import { FilterBar, PrintHeader } from './ui/FilterBar'
import { Header } from './ui/Header'
import Import from './pages/Import'
import Inbound from './pages/Inbound'
import Overview from './pages/Overview'
import Push from './pages/Push'
import Risques from './pages/Risques'
import Settings from './pages/Settings'
import Value from './pages/Value'

const REPORTS = [
  ['/overview', 'Overview', <Overview />], ['/valeur', 'Valeur', <Value />], ['/push', 'Push', <Push />],
  ['/inbound', 'Inbound', <Inbound />], ['/risques', 'Risques', <Risques />],
] as const

export default function App() {
  const snaps = useQuery({ queryKey: ['snapshots'], queryFn: () => get<Row[]>('/snapshots') })
  const last = snaps.data?.at(-1)

  return (
    <>
      <Header />
      <Routes>
        <Route path="/" element={<Navigate to="/overview" replace />} />
        {REPORTS.map(([path, title, page]) => (
          <Route key={path} path={path} element={
            <>
              <FilterBar />
              <main className="mx-auto max-w-[1440px] px-6 py-5">
                <PrintHeader title={title} />
                <div className="mb-4 flex min-h-[32px] items-baseline justify-between">
                  <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
                  {last && <span className="text-xs" style={{ color: 'var(--faint)' }}>Données au {last.date_max} · {last.file_name}</span>}
                </div>
                {page}
              </main>
            </>} />
        ))}
        <Route path="/parametres" element={<main className="mx-auto max-w-[1440px] px-6 py-5"><Settings /></main>} />
        <Route path="/import" element={<main className="mx-auto max-w-[1440px] px-6 py-5"><Import /></main>} />
      </Routes>
    </>
  )
}
