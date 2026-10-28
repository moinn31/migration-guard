import type { components } from '@/lib/api/generated/schema'

export type Verdict = 'VERIFIED_BY_CHECKS' | 'NEEDS_REVIEW' | 'UNSAFE' | 'INCONCLUSIVE'
export type RiskCategory = 'LOW' | 'MEDIUM' | 'HIGH'
export type Run = components['schemas']['RunOut'] & { verdict?: Verdict | null }
export type Project = components['schemas']['ProjectOut']
export type Finding = components['schemas']['FindingOut']
export type Report = components['schemas']['ReportOut']

export const verdictLabels: Record<Verdict, string> = {
  VERIFIED_BY_CHECKS: 'Verified by checks',
  NEEDS_REVIEW: 'Needs review',
  UNSAFE: 'Unsafe',
  INCONCLUSIVE: 'Inconclusive',
}

export const verdictTone: Record<Verdict, string> = {
  VERIFIED_BY_CHECKS: 'border-emerald-300/30 bg-emerald-300/10 text-emerald-200',
  NEEDS_REVIEW: 'border-amber-300/30 bg-amber-300/10 text-amber-200',
  UNSAFE: 'border-red-300/30 bg-red-300/10 text-red-200',
  INCONCLUSIVE: 'border-slate-300/30 bg-slate-300/10 text-slate-200',
}
