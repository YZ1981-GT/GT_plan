/**
 * useH10Check — H10-4 检查表（动态行 + 合规判断 + 明细联动）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { H10_COMPLIANCE_OPTIONS } from './h10Constants'
import type { ChecklistResponse } from './useF1FormData'

export type H10ComplianceValue = 'compliant' | 'non_compliant' | 'not_applicable' | ''

export interface H10CheckRow {
  id: string
  seq: number
  detailRowId: string
  assetName: string
  approvalProcess: H10ComplianceValue
  appraisalBasis: H10ComplianceValue
  pricingReasonableness: H10ComplianceValue
  taxTreatment: H10ComplianceValue
  accountingTiming: H10ComplianceValue
  revenueRecognition: H10ComplianceValue
  expenseAllocation: H10ComplianceValue
  relatedParty: H10ComplianceValue
  auditConclusion: H10ComplianceValue
  remark: string
  voucherRef: string
}

const ITEM_ID_ROWS = 'H10-check-rows'

const CHECK_FIELDS: Array<keyof H10CheckRow> = [
  'approvalProcess',
  'appraisalBasis',
  'pricingReasonableness',
  'taxTreatment',
  'accountingTiming',
  'revenueRecognition',
  'expenseAllocation',
  'relatedParty',
  'auditConclusion',
]

function genId(): string {
  return `h10c-${Date.now().toString(36)}`
}

function normalizeRow(raw: any, seq: number): H10CheckRow {
  const base: H10CheckRow = {
    id: raw.id || raw.rowId || genId(),
    seq,
    detailRowId: raw.detailRowId ?? '',
    assetName: raw.assetName ?? '',
    approvalProcess: raw.approvalProcess ?? '',
    appraisalBasis: raw.appraisalBasis ?? '',
    pricingReasonableness: raw.pricingReasonableness ?? '',
    taxTreatment: raw.taxTreatment ?? '',
    accountingTiming: raw.accountingTiming ?? '',
    revenueRecognition: raw.revenueRecognition ?? '',
    expenseAllocation: raw.expenseAllocation ?? '',
    relatedParty: raw.relatedParty ?? '',
    auditConclusion: raw.auditConclusion ?? '',
    remark: raw.remark ?? '',
    voucherRef: raw.voucherRef ?? '',
  }
  return base
}

function parseRows(json: string | null | undefined): H10CheckRow[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    return Array.isArray(arr) ? arr.map((r, i) => normalizeRow(r, i + 1)) : []
  } catch {
    return []
  }
}

function isNonCompliant(row: H10CheckRow): boolean {
  return CHECK_FIELDS.some((f) => row[f] === 'non_compliant')
}

export function useH10Check(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<H10CheckRow[]>([])

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => { rows.value = parseRows(json) },
    { immediate: true },
  )

  watch(
    () => opts.allResponses.value.get('H10-detail-rows')?.remark,
    (json) => {
      if (!json) return
      try {
        const details = JSON.parse(json)
        if (!Array.isArray(details)) return
        const existing = new Map(rows.value.map((r) => [r.detailRowId, r]))
        const merged: H10CheckRow[] = details.map((d: any, i: number) => {
          const prev = existing.get(d.id)
          if (prev) return { ...prev, assetName: d.assetName ?? prev.assetName, seq: i + 1 }
          return normalizeRow({
            detailRowId: d.id,
            assetName: d.assetName ?? '',
          }, i + 1)
        })
        if (merged.length !== rows.value.length || merged.some((r, i) => r.id !== rows.value[i]?.id)) {
          rows.value = merged
          persist()
        }
      } catch { /* ignore */ }
    },
    { immediate: true },
  )

  function persist(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  const nonCompliantRows = computed(() => rows.value.filter(isNonCompliant))

  const nonCompliantSummary = computed(() => {
    if (!nonCompliantRows.value.length) return null
    const names = nonCompliantRows.value.map((r) => r.assetName || `行${r.seq}`).join('、')
    return `存在 ${nonCompliantRows.value.length} 项不合规检查：${names}`
  })

  const complianceOptions = H10_COMPLIANCE_OPTIONS

  function updateRow(id: string, patch: Partial<H10CheckRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? normalizeRow({ ...r, ...patch }, r.seq) : r))
    persist()
  }

  function linkToDetail(detailRowId: string): H10CheckRow | undefined {
    return rows.value.find((r) => r.detailRowId === detailRowId)
  }

  const complianceRate = computed(() => {
    if (!rows.value.length) return 1
    const ok = rows.value.filter((r) => !isNonCompliant(r)).length
    return ok / rows.value.length
  })

  function rowIsCompliant(row: H10CheckRow): boolean {
    return !isNonCompliant(row)
  }

  return {
    rows,
    nonCompliantRows,
    nonCompliantSummary,
    complianceRate,
    rowIsCompliant,
    complianceOptions,
    updateRow,
    linkToDetail,
    ITEM_ID_ROWS,
  }
}
