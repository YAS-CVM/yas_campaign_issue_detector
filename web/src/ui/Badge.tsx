import { SEVERITY } from './format'

export function SeverityBadge({ value }: { value: string }) {
  const s = SEVERITY[value] ?? SEVERITY.info
  return <span className="whitespace-nowrap text-xs font-semibold" style={{ color: s.color }}>● {s.label}</span>
}
