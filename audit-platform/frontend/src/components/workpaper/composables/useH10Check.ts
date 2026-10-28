/**
 * useH10Check — H10-4 检查表（动态行 + 合规判断 + 明细联动 + 抽凭回填）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { H10_COMPLIANCE_OPTIONS } from './h10Constants'
import type { ChecklistResponse } from './useF1FormData'
import {
  legacyIdentity, useVoucherCheckFill, withRowMeta,
  type EngineFilledPayload, type FillSample, type PreparedItem, type UndoRequestPayload,
} from './shared/voucherCheckFill'

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
    return Array.isArray(arr) ? arr.map((r, i) => withRowMeta(normalizeRow(r, i + 1), r)) : []
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

/** 凭证索引「日期/凭证号」拆回两段（旧行没有 `_gt` 时按凭证号 + 日期认同一分录） */
export function splitVoucherRef(ref: string): { no: string; date: string } {
  const s = String(ref ?? '').trim()
  const i = s.indexOf('/')
  return i >= 0 ? { date: s.slice(0, i), no: s.slice(i + 1) } : { date: '', no: s }
}

/** 行上已填核对内容（替换与撤销抽凭时据此先确认）：任一合规判断，或改过备注 */
export function hasH10CheckContent(row: H10CheckRow): boolean {
  return CHECK_FIELDS.some((f) => row[f] !== '')
    || (String(row.remark ?? '').trim() !== '' && row.remark !== '抽凭标记异常')
}

/**
 * 共享回填函数的待写入项 → 检查行（spec voucher-identity-writeback-and-audit-phase 任务 12）：样本各成一行、不挂明细。
 * 原实现按顺序把第 i 个样本填进第 i 个还没挂凭证的明细行，凭证与资产对不上
 */
export function mapPreparedToH10CheckRow(item: PreparedItem): H10CheckRow {
  const s = item.sample as PreparedItem['sample'] & { abnormal?: boolean; checkResult?: string }
  return normalizeRow({
    detailRowId: '',
    assetName: sampleAssetName(s),
    voucherRef: voucherLabel(s),
    remark: s.abnormal || s.checkResult === 'ERR' ? '抽凭标记异常' : '',
  }, 0)
}

export function useH10Check(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  /** 项目（共享回填函数按它取审计阶段） */
  projectId?: Ref<string> | ComputedRef<string>
}) {
  const rows = ref<H10CheckRow[]>([])
  const detailPopulation = ref(0)
  const sampledVoucherCount = ref(0)

  // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读：共享回填函数
  const voucherFill = useVoucherCheckFill<H10CheckRow>({
    projectId: () => opts.projectId?.value,
    tables: rows,
    policy: 'join',
    mapSampleToRow: item => mapPreparedToH10CheckRow(item),
    persist: () => { persist(); syncSampleMeta() },
    hasUserContent: hasH10CheckContent,
    afterChange: (_key, list) => { list.forEach((r, i) => { r.seq = i + 1 }) },
    // 旧行（没有 `_gt`）没有金额：按凭证索引里的凭证号 + 日期认
    legacy: (r) => {
      const { no, date } = splitVoucherRef(r.voucherRef)
      return legacyIdentity({ voucherNo: no, voucherDate: date, amount: 0 })
    },
    readonly: () => opts.isReadonly.value,
  })

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => {
      rows.value = parseRows(json)
      voucherFill.markLoaded()
    },
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
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(voucherFill.guardPersist(rows.value)) })
  }

  /** 抽凭 / 挂凭导入 / 撤销之后：已挂凭证索引的行数落到抽样元数据 */
  function syncSampleMeta(): void {
    sampledVoucherCount.value = rows.value.filter((r) => !!r.voucherRef).length
    persistSampleMeta()
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
    const current = rows.value.find((r) => r.id === id)
    if (current && voucherFill.isRowLocked(current)) return
    rows.value = rows.value.map((r) => (r.id === id ? withRowMeta(normalizeRow({ ...r, ...patch }, r.seq), r) : r))
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
    onEngineFilled: (payload: EngineFilledPayload) => voucherFill.onEngineFilled(payload),
    onAttachImported: (samples: FillSample[]) => voucherFill.onAttachImported(samples),
    onUndoRequest: (payload: UndoRequestPayload) => voucherFill.onUndoRequest(payload),
    voucherRowClass: voucherFill.rowClass,
    isVoucherRowLocked: voucherFill.isRowLocked,
    voucherFillReady: voucherFill.ready,
    sampleRatio,
    sampleRatioLow,
    detailPopulation,
    sampledVoucherCount,
    H10_CHECK_MIN_SAMPLE_RATIO,
    ITEM_ID_ROWS,
  }
}
