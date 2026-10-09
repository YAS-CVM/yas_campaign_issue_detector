/** Sélecteur segmenté (niveau de détail, regroupement, …). */
export function Pills<T extends string | number>({ items, value, onChange }: {
  items: readonly { id: T; label: string }[]; value: T; onChange: (id: T) => void
}) {
  return (
    <div className="flex rounded-lg p-0.5" style={{ border: '1px solid var(--line)', background: 'var(--surface)' }} role="group">
      {items.map((it) => (
        <button key={String(it.id)} onClick={() => onChange(it.id)} className="rounded-md px-2.5 py-1 text-xs font-medium"
          style={{ background: it.id === value ? 'var(--accent)' : 'transparent', color: it.id === value ? '#fff' : 'var(--muted)' }}>
          {it.label}
        </button>
      ))}
    </div>
  )
}
