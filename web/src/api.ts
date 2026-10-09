import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'

export type Row = Record<string, any>

/** Dimensions de filtre : clé d'URL = nom de paramètre de l'API. */
export const DIMENSIONS = [
  { key: 'category', opt: 'categories', label: 'Catégorie' },
  { key: 'campaign', opt: 'campaigns', label: 'Campagne' },
  { key: 'bc', opt: 'bcs', label: 'BC' },
  { key: 'status', opt: 'statuses', label: 'Statut' },
  { key: 'touchpoint', opt: 'touchpoints', label: 'Touchpoint' },
  { key: 'program', opt: 'programs', label: 'Programme' },
  { key: 'rule', opt: 'rules', label: 'Règle IM' },
  { key: 'offer', opt: 'offers', label: 'Offre' },
] as const

export type Dim = (typeof DIMENSIONS)[number]['key']
const SCALARS = ['date_from', 'date_to', 'include_seeding', 'mature_only'] as const

export async function get<T = any>(path: string, params?: URLSearchParams | string): Promise<T> {
  const qs = params ? `?${params.toString()}` : ''
  const r = await fetch(`/api/v1${path}${qs}`)
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json()
}

/** Filtres globaux stockés dans l'URL (partageables). */
export function useFilters() {
  const [sp, setSp] = useSearchParams()
  const params = new URLSearchParams()
  for (const d of DIMENSIONS) sp.getAll(d.key).forEach((v) => params.append(d.key, v))
  for (const k of SCALARS) if (sp.get(k)) params.set(k, sp.get(k)!)

  // Forme fonctionnelle : part de l'URL la plus récente, pas de celle du dernier rendu, donc deux modifications
  // rapprochées (période par défaut puis clic de l'utilisateur) ne s'écrasent pas.
  const update = (fn: (p: URLSearchParams) => void) =>
    setSp((prev) => { const next = new URLSearchParams(prev); fn(next); return next }, { replace: true })
  return {
    params,
    values: (k: string) => sp.getAll(k),
    scalar: (k: string) => sp.get(k) ?? '',
    setMany: (k: Dim, vals: string[]) => update((p) => { p.delete(k); vals.forEach((v) => p.append(k, v)) }),
    setScalar: (k: string, v: string) => update((p) => (v ? p.set(k, v) : p.delete(k))),
    setScalars: (kv: Record<string, string>) => update((p) => Object.entries(kv).forEach(([k, v]) => (v ? p.set(k, v) : p.delete(k)))),
    /** Drill-down : restreint une dimension à une seule valeur. */
    drill: (k: Dim, v: string) => update((p) => { p.delete(k); p.append(k, v) }),
    /** Réinitialise les filtres de dimension (la période est gérée à part). */
    clear: () => update((p) => [...DIMENSIONS.map((d) => d.key), 'include_seeding', 'mature_only'].forEach((k) => p.delete(k))),
    /** Période connue (dates dans l'URL, ou « Tout » choisi) : avant, on ne requête pas, pour éviter une double requête et un double rendu. */
    ready: sp.has('date_from') || sp.get('p') === 'all',
    active: [...DIMENSIONS.map((d) => d.key), 'include_seeding', 'mature_only'].filter((k) => sp.has(k)).length,
  }
}

/** Requête filtrée : les filtres globaux + paramètres propres à l'écran. */
export function useApi<T = any>(path: string, extra?: Record<string, string | string[]>, opts?: { always?: boolean }) {
  const { params, ready } = useFilters()
  const p = new URLSearchParams(params)
  for (const [k, v] of Object.entries(extra ?? {})) {
    p.delete(k)
    ;(Array.isArray(v) ? v : [v]).forEach((x) => p.append(k, x))
  }
  return useQuery<T>({
    queryKey: [path, p.toString()], queryFn: () => get<T>(path, p),
    enabled: ready || !!opts?.always,
    // Pas de placeholderData : afficher les données de l'ancien filtre pendant le chargement du nouveau serait faux.
    // Les squelettes (State) réservent la hauteur, donc pas de décalage non plus.
  })
}
