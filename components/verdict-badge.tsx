import { verdictLabels, verdictTone, type Verdict } from '@/lib/types'

export function VerdictBadge({ verdict }: { verdict?: string | null }) {
  const value = (verdict && verdict in verdictLabels ? verdict : 'INCONCLUSIVE') as Verdict
  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${verdictTone[value]}`}>{verdictLabels[value]}</span>
}
