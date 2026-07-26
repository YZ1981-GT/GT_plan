/**
 * useH10Check — H10-4 检查表（动态行 + 合规判断 + 明细联动 + 抽凭回填）
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
const ITEM_ID_SAMPLE_META = 'H10-4-check-sample-meta'

/** 建议最低抽查比例（相对 H10-2 明细行数）。可由 project_context.h10_check_sample_ratio 覆盖（B15 联动） */
export const H10_CHECK_MIN_SAMPLE_RATIO = 0.2

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
  return `h10c-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

function normalizeRow(raw: any, seq: number): H10CheckRow {
  return {
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

function voucherLabel(s: any): string {
  const no = s?.voucherNo || s?.voucher_no || ''
  const date = s?.date || s?.voucherDate || ''
  if (no && date) return `${date}/${no}`
  return String(no || date || '')
}

function sampleAssetName(s: any): string {
  return String(
    s?.summary || s?.assetName || s?.businessContent || s?.accountName || '抽凭样本',
  ).slice(0, 80)
}

export function useH10Check(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<H10CheckRow[]>([])
  const detailPopulation = ref(0)
  const sampledVoucherCount = ref(0)

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => { rows.value = parseRows(json) },
    { immediate: true },
  )

  watch(
    () => opts.allResponses.value.get(ITEM_ID_SAMPLE_META)?.remark,
    (json) => {
      if (!json) return
      try {
        const meta = JSON.parse(json)
        if (typeof meta?.sampledVoucherCount === 'number') {
          sampledVoucherCount.value = meta.sampledVoucherCount
        }
      } catch { /* ignore */ }
    },
    { immediate: true },
  )

  watch(
    () => opts.allResponses.value.get('H10-detail-rows')?.remark,
    (json) => {
      if (!json) {
        detailPopulation.value = 0
        return
      }
      try {
        const details = JSON.parse(json)
        if (!Array.isArray(details)) return
        detailPopulation.value = details.length
        const existing = new Map(
          rows.value.filter((r) => r.detailRowId).map((r) => [r.detailRowId, r]),
        )
        const merged: H10CheckRow[] = details.map((d: any, i: number) => {
          const prev = existing.get(d.id)
          if (prev) return { ...prev, assetName: d.assetName ?? prev.assetName, seq: i + 1 }
          return normalizeRow({
            detailRowId: d.id,
            assetName: d.assetName ?? '',
          }, i + 1)
        })
        // 保留无明细挂接的抽凭追加行
        const orphans = rows.value.filter((r) => !r.detailRowId)
        const next = [
          ...merged,
          ...orphans.map((r, i) => ({ ...r, seq: merged.length + i + 1 })),
        ]
        if (next.length !== rows.value.length || next.some((r, i) => r.id !== rows.value[i]?.id)) {
          rows.value = next
          persist()
        }
      } catch { /* ignore */ }
    },
    { immediate: true },
  )

  function persist(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  function persistSampleMeta(): void {
    opts.debouncedSave(ITEM_ID_SAMPLE_META, {
      remark: JSON.stringify({ sampledVoucherCount: sampledVoucherCount.value }),
    })
  }

  const nonCompliantRows = computed(() => rows.value.filter(isNonCompliant))

  const nonCompliantSummary = computed(() => {
    if (!nonCompliantRows.value.length) return null
    const names = nonCompliantRows.value.map((r) => r.assetName || `行${r.seq}`).join('、')
    return `存在 ${nonCompliantRows.value.length} 项不合规检查：${names}`
  })

  const complianceOptions = H10_COMPLIANCE_OPTIONS

  /** 已挂凭证索引的检查行 / 明细总体 */
  const sampleRatio = computed(() => {
    const pop = detailPopulation.value
    if (pop <= 0) return sampledVoucherCount.value > 0 ? 1 : 0
    const withVoucher = rows.value.filter((r) => !!r.voucherRef).length
    const n = Math.max(withVoucher, sampledVoucherCount.value)
    return Math.min(1, n / pop)
  })

  const sampleRatioLow = computed(() =>
    detailPopulation.value > 0 && sampleRatio.value + 1e-9 < H10_CHECK_MIN_SAMPLE_RATIO,
  )

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

  /**
   * 抽凭引擎回填：优先按凭证号更新已有空凭证行，否则追加检查行。
   * @returns 写入行数
   */
  function fillFromSampledVouchers(samples: any[]): number {
    if (opts.isReadonly.value || !Array.isArray(samples) || !samples.length) return 0
    let n = 0
    const next = [...rows.value]
    for (const s of samples) {
      const vref = voucherLabel(s)
      const name = sampleAssetName(s)
      const emptyIdx = next.findIndex((r) => !r.voucherRef)
      if (emptyIdx >= 0) {
        const prev = next[emptyIdx]
        next[emptyIdx] = normalizeRow({
          ...prev,
          assetName: prev.assetName || name,
          voucherRef: vref || prev.voucherRef,
          remark: prev.remark || (s.abnormal || s.checkResult === 'ERR' ? '抽凭标记异常' : ''),
        }, prev.seq)
      } else {
        next.push(normalizeRow({
          detailRowId: '',
          assetName: name,
          voucherRef: vref,
          remark: s.abnormal || s.checkResult === 'ERR' ? '抽凭标记异常' : '',
        }, next.length + 1))
      }
      n++
    }
    rows.value = next.map((r, i) => ({ ...r, seq: i + 1 }))
    sampledVoucherCount.value = rows.value.filter((r) => !!r.voucherRef).length
    persist()
    persistSampleMeta()
    return n
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
    fillFromSampledVouchers,
    sampleRatio,
    sampleRatioLow,
    detailPopulation,
    sampledVoucherCount,
    H10_CHECK_MIN_SAMPLE_RATIO,
    ITEM_ID_ROWS,
  }
}
