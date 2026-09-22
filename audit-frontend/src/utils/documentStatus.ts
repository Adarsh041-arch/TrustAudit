/**
 * Unified document audit status — single source of truth.
 *
 * Every place that renders a status badge, tab, or categorises a document
 * MUST call `getDocumentStatus()` to derive label, colour, and variant.
 * The authoritative field is `audit_status` (mirrors backend `decision.status`).
 */
import type { DocumentAuditResult } from '../types/audit'

export type AuditVerdict = 'PASS' | 'FAIL' | 'NEEDS_REVIEW' | 'INCOMPLETE' | 'UNSUPPORTED' | 'NOT_AUDITED'

export interface DocumentStatus {
  /** Canonical verdict derived from `audit_status`. */
  verdict: AuditVerdict
  /** Human-readable label shown in every badge. */
  label: string
  /** CSS class token for colour-coding (maps to existing v2-status classes). */
  variant: 'passed' | 'attention' | 'review' | 'incomplete' | 'unsupported'
  /** Inline colour classes for badges (background + text). */
  badgeBg: string
  /** Short description for tooltips or next-action prompts. */
  description: string
}

export const STATUS_MAP: Record<AuditVerdict, Omit<DocumentStatus, 'verdict'>> = {
  PASS: {
    label: 'Pass',
    variant: 'passed',
    badgeBg: 'bg-teal-50 text-teal-700 border border-teal-600/20 dark:bg-teal-500/15 dark:text-teal-300 dark:border-teal-500/30',
    description: 'All mandatory checks cleared.',
  },
  FAIL: {
    label: 'Fail',
    variant: 'attention',
    badgeBg: 'bg-rose-50 text-rose-700 border border-rose-600/20 dark:bg-rose-500/15 dark:text-rose-300 dark:border-rose-500/30',
    description: 'One or more mandatory checks failed.',
  },
  NEEDS_REVIEW: {
    label: 'Needs Review',
    variant: 'review',
    badgeBg: 'bg-amber-50 text-amber-700 border border-amber-600/20 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30',
    description: 'Checks passed but extraction disagreements or evidence gaps require human review.',
  },
  INCOMPLETE: {
    label: 'Incomplete',
    variant: 'incomplete',
    badgeBg: 'bg-sky-50 text-sky-700 border border-sky-600/20 dark:bg-sky-500/15 dark:text-sky-300 dark:border-sky-500/30',
    description: 'Mandatory checks could not complete — evidence or extraction is missing.',
  },
  UNSUPPORTED: {
    label: 'Unsupported',
    variant: 'unsupported',
    badgeBg: 'bg-slate-100 text-slate-600 border border-slate-300 dark:bg-slate-700/40 dark:text-slate-400 dark:border-slate-600',
    description: 'Document type is advisory (e.g. contract, letter) and does not require clearance checks.',
  },
  NOT_AUDITED: {
    label: 'Not Audited',
    variant: 'unsupported',
    badgeBg: 'bg-slate-100 text-slate-600 border border-slate-300 dark:bg-slate-700/40 dark:text-slate-400 dark:border-slate-600',
    description: 'Document has not been processed through the audit pipeline.',
  },
}

/**
 * Derive the canonical display status for a document.
 *
 * Priority: `audit_status` > `decision.status` > fallbacks.
 */
export function getDocumentStatus(doc: Partial<DocumentAuditResult> | null | undefined): DocumentStatus {
  if (!doc) {
    return { verdict: 'NOT_AUDITED', ...STATUS_MAP.NOT_AUDITED }
  }

  let raw: string | undefined = doc.audit_status ?? doc.decision?.status

  if (!raw) {
    if (doc.document_status === 'UNSUPPORTED') {
      raw = 'UNSUPPORTED'
    } else if (doc.passed === true) {
      raw = 'PASS'
    } else if (doc.failed_rules && doc.failed_rules.length > 0) {
      raw = 'FAIL'
    } else if (doc.human_review_recommended) {
      raw = 'NEEDS_REVIEW'
    } else if (doc.document_status === 'FAILED' || doc.document_status === 'INCOMPLETE') {
      raw = 'INCOMPLETE'
    } else {
      raw = 'NOT_AUDITED'
    }
  }

  const verdict = (raw in STATUS_MAP ? raw : 'NOT_AUDITED') as AuditVerdict
  return { verdict, ...STATUS_MAP[verdict] }
}

/**
 * Formatted score representation for unified score display.
 */
export interface FormattedScore {
  value: string
  colorClass: string
  label: string
  isNumeric: boolean
}

export function formatDocumentScore(doc?: Partial<DocumentAuditResult> | { score?: number | null } | null): FormattedScore {
  if (!doc) {
    return {
      value: '—',
      colorClass: 'text-slate-400',
      label: 'Not audited',
      isNumeric: false,
    }
  }

  const { verdict } = getDocumentStatus(doc as any)

  if (verdict === 'UNSUPPORTED') {
    return {
      value: 'N/A',
      colorClass: 'text-slate-500 dark:text-slate-400',
      label: 'Advisory (N/A)',
      isNumeric: false,
    }
  }

  if (verdict === 'INCOMPLETE') {
    return {
      value: 'Incomplete',
      colorClass: 'text-sky-600 dark:text-sky-400',
      label: 'Evidence incomplete',
      isNumeric: false,
    }
  }

  if (verdict === 'NOT_AUDITED') {
    return {
      value: 'Not Audited',
      colorClass: 'text-slate-400',
      label: 'Audit pending',
      isNumeric: false,
    }
  }

  const numScore = (doc as any).score
  if (typeof numScore === 'number' && !isNaN(numScore)) {
    const formatted = `${numScore.toFixed(1)}%`
    if (verdict === 'PASS') {
      return {
        value: formatted,
        colorClass: 'text-teal-600 dark:text-teal-400',
        label: 'All checks passed',
        isNumeric: true,
      }
    }
    if (verdict === 'FAIL') {
      return {
        value: formatted,
        colorClass: 'text-rose-600 dark:text-rose-400',
        label: 'Violations detected',
        isNumeric: true,
      }
    }
    // NEEDS_REVIEW
    return {
      value: formatted,
      colorClass: 'text-amber-600 dark:text-amber-400',
      label: 'Review required',
      isNumeric: true,
    }
  }

  return {
    value: '—',
    colorClass: 'text-slate-400',
    label: 'Unscored',
    isNumeric: false,
  }
}

/**
 * Dashboard-compatible bucket: maps to 3 categories used in metric cards.
 */
export type DashboardBucket = 'attention' | 'incomplete' | 'passed'

export function dashboardBucketOf(doc: DocumentAuditResult): DashboardBucket {
  const { verdict } = getDocumentStatus(doc)
  switch (verdict) {
    case 'PASS':
      return 'passed'
    case 'FAIL':
    case 'NEEDS_REVIEW':
      return 'attention'
    default:
      return 'incomplete'
  }
}
