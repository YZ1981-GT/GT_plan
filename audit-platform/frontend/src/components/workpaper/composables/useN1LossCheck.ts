/**
 * useN1LossCheck — N1-5 可用以后年度税前利润弥补的亏损检查表（重建，源模板对齐）
 *
 * Spec: .kiro/specs/n1-loss-check-source-alignment/
 * Task: 2.1
 * Requirements: 1.2, 1.3, 2.1, 2.2, 3.1, 3.4, 3.5, 5.1
 *
 * 数据模型按源模板「可抵扣亏损到期年度」列示：
 * - 行：按到期年度（expiryYear）列示
 * - 列：上期不确认/本期数(账面/审计调整/审定)/确认/不确认/依据/是否充足/来源三选/索引
 *
 * 派生规则（全部 computed，不落库）：
 * - auditedAmount = bookAmount + auditAdjustment
 * - isExpired = expiryYear < auditYear（auditYear 由 options 传入，禁用 new Date()）
 * - effectiveRecognized = isExpired ? 0 : recognizedAmount
 * - unrecognizedAmount = max(0, auditedAmount - effectiveRecognized)
 * - recognizableAsset = effectiveRecognized * taxRate
 * - splitMismatch = |effectiveRecognized + unrecognizedAmount - auditedAmount| > 0.01
 * - basisMissing = unrecognizedAmount > 0 && basis 为空
 * - sufficiencyConflict = sufficient === 'no' && effectiveRecognized > 0
 *
 * 持久化键：
 * - N1-5-rows（conclusion）: N1LossRow[] JSON
 * - N1-5-lead-rows（conclusion）: Record<N1LossLeadKey, N1LossLeadRow>
 * - N1-5-total-recognizable（remark）: 可确认递延税资产合计字符串（Cross_Keys，语义不变）
 *
 * 异步 hydrate：watch(allResponses, immediate) + 一次性 guard（_hydratedOnce）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { useN1FormData } from './useN1FormData'
import { migrateLegacyLossRows, computeLegacyInfo } from './n1LossMigration'

// ─── Types ───────────────────────────────────────────────────────────────────

export type N1LossSufficiency = 'yes' | 'no' | ''

export interface N1LossRow {
  id: string
  /** 可抵扣亏损到期年度（源模板行标识） */
  expiryYear: number
  /** 亏损发生年度（可选，仅参考/迁移回溯） */
  lossYear?: number | null
  /** 上期不确认递延所得税资产的可弥补亏损 */
  priorUnrecognized: number
  /** 本期数 - 账面金额 */
  bookAmount: number
  /** 本期数 - 审计调整 */
  auditAdjustment: number
  /** 确认递延所得税资产的可弥补亏损（唯一录入侧） */
  recognizedAmount: number
  /** 适用税率（小数如 0.25） */
  taxRate: number
  /** 依据（不确认>0 时必填提示） */
  basis: string
  /** 到期前是否有足够的应纳税所得额 */
  sufficient: N1LossSufficiency
  sourceOperating: boolean
  sourceTemporaryDiff: boolean
  sourceOther: boolean
  /** 检查底稿索引 */
  indexRef: string
  /** 备注 */
  remark?: string
}

export interface N1LossComputedRow extends N1LossRow {
  /** 本期审定金额 = bookAmount + auditAdjustment */
  auditedAmount: number
  /** 有效确认额：届满行恒 0 */
  effectiveRecognized: number
  /** 不确认金额 = max(0, auditedAmount - effectiveRecognized) */
  unrecognizedAmount: number
  /** 可确认递延所得税资产 = effectiveRecognized * taxRate */
  recognizableAsset: number
  /** expiryYear < auditYear */
  isExpired: boolean
  /** max(0, expiryYear - auditYear) */
  remainingYears: number
  /** sufficient==='no' 且仍有确认额 → 提示 */
  sufficiencyConflict: boolean
  /** unrecognizedAmount > 0 且 basis 为空 */
  basisMissing: boolean
  /** |effectiveRecognized + unrecognizedAmount - auditedAmount| > 0.01 */
  splitMismatch: boolean
}

export type N1LossLeadKey = 'retainedEarnings' | 'deductibleLoss'

export interface N1LossLeadRow {
  label: string
  priorUnrecognized: number
  bookAmount: number
  auditAdjustment: number
  remark?: string
}

export interface N1LossLeadComputed extends N1LossLeadRow {
  auditedAmount: number
}

export interface N1LossTotals {
  priorUnrecognized: number
  bookAmount: number
  auditAdjustment: number
  auditedAmount: number
  recognized: number
  unrecognized: number
  recognizableAsset: number
}

export interface N1LossWarning {
  rowIndex: number
  type: 'expired' | 'splitMismatch' | 'basisMissing' | 'sufficiencyConflict'
  message: string
}

export type EditableLossField = keyof Omit<N1LossRow, 'id'>
export type EditableLeadField = keyof Omit<N1LossLeadRow, 'label'>

// ─── Options ─────────────────────────────────────────────────────────────────

export interface UseN1LossCheckOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  formData: ReturnType<typeof useN1FormData>
  /** 审计年度（Req 2.1：禁止用 new Date().getFullYear()） */
  auditYear: Ref<number>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'N1-5-rows'
const LEAD_ROWS_KEY = 'N1-5-lead-rows'
const TOTAL_RECOGNIZABLE_KEY = 'N1-5-total-recognizable'
/** Legacy key (read-only for migration, never written) */
const LEGACY_LOSS_ROWS_KEY = 'N1-5-loss-rows'

const DEFAULT_LEAD_ROWS: Record<N1LossLeadKey, N1LossLeadRow> = {
  retainedEarnings: { label: '期末未分配利润', priorUnrecognized: 0, bookAmount: 0, auditAdjustment: 0 },
  deductibleLoss: { label: '其中：可抵扣亏损', priorUnrecognized: 0, bookAmount: 0, auditAdjustment: 0 },
}

let _idSeq = 0

function _genId(): string {
  return `loss-${++_idSeq}`
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _parseJsonSafe<T>(raw: any, field: 'conclusion' | 'remark' = 'conclusion'): T | null {
  const str = typeof raw === 'string' ? raw : raw?.[field]
  if (!str || typeof str !== 'string') return null
  try {
    return JSON.parse(str) as T
  } catch {
    return null
  }
}

function _round2(n: number): number {
  return Math.round(n * 100) / 100
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useN1LossCheck(options: UseN1LossCheckOptions) {
  const { allResponses, formData, auditYear } = options

  // ─── State ───────────────────────────────────────────────────────────────

  const _rawRows = ref<N1LossRow[]>([])
  const _leadRows = ref<Record<N1LossLeadKey, N1LossLeadRow>>({ ...DEFAULT_LEAD_ROWS })

  // ─── Hydrate (one-time guard) ──────────────────────────────────────────────

  let _hydratedOnce = false

  function _hydrate(): void {
    if (_hydratedOnce) return
    const map = allResponses.value
    if (!map || map.size === 0) return

    // Hydrate rows
    const rowsEntry = map.get(ROWS_KEY)
    if (rowsEntry) {
      const parsed = _parseJsonSafe<N1LossRow[]>(rowsEntry)
      if (Array.isArray(parsed) && parsed.length > 0) {
        _rawRows.value = parsed
        // Sync id sequence
        const maxNum = parsed.reduce((max, r) => {
          const m = r.id?.match(/^loss-(\d+)$/)
          return m ? Math.max(max, Number(m[1])) : max
        }, 0)
        if (maxNum > _idSeq) _idSeq = maxNum
        _hydratedOnce = true
      }
    }

    // Hydrate lead rows
    const leadEntry = map.get(LEAD_ROWS_KEY)
    if (leadEntry) {
      const parsed = _parseJsonSafe<Record<N1LossLeadKey, N1LossLeadRow>>(leadEntry)
      if (parsed && typeof parsed === 'object') {
        _leadRows.value = {
          retainedEarnings: parsed.retainedEarnings ?? DEFAULT_LEAD_ROWS.retainedEarnings,
          deductibleLoss: parsed.deductibleLoss ?? DEFAULT_LEAD_ROWS.deductibleLoss,
        }
      }
    }

    if (rowsEntry || leadEntry) _hydratedOnce = true
  }

  watch(allResponses, _hydrate, { immediate: true })

  // ─── Computed: rows with derived fields ──────────────────────────────────

  const rows: ComputedRef<N1LossComputedRow[]> = computed(() => {
    const year = auditYear.value
    return _rawRows.value.map((row) => {
      const auditedAmount = _round2(row.bookAmount + row.auditAdjustment)
      const isExpired = row.expiryYear < year
      const effectiveRecognized = isExpired ? 0 : row.recognizedAmount
      const unrecognizedAmount = Math.max(0, _round2(auditedAmount - effectiveRecognized))
      const recognizableAsset = _round2(effectiveRecognized * row.taxRate)
      const remainingYears = Math.max(0, row.expiryYear - year)
      const sufficiencyConflict = row.sufficient === 'no' && effectiveRecognized > 0
      const basisMissing = unrecognizedAmount > 0 && !row.basis?.trim()
      const splitMismatch = Math.abs(effectiveRecognized + unrecognizedAmount - auditedAmount) > 0.01

      return {
        ...row,
        auditedAmount,
        effectiveRecognized,
        unrecognizedAmount,
        recognizableAsset,
        isExpired,
        remainingYears,
        sufficiencyConflict,
        basisMissing,
        splitMismatch,
      }
    })
  })

  // ─── Computed: lead rows ───────────────────────────────────────────────────

  const leadRows: ComputedRef<N1LossLeadComputed[]> = computed(() => {
    const keys: N1LossLeadKey[] = ['retainedEarnings', 'deductibleLoss']
    return keys.map((key) => {
      const r = _leadRows.value[key]
      return {
        ...r,
        auditedAmount: _round2(r.bookAmount + r.auditAdjustment),
      }
    })
  })

  // ─── Computed: totals ──────────────────────────────────────────────────────

  const totals: ComputedRef<N1LossTotals> = computed(() => {
    const r = rows.value
    return {
      priorUnrecognized: _round2(r.reduce((s, x) => s + x.priorUnrecognized, 0)),
      bookAmount: _round2(r.reduce((s, x) => s + x.bookAmount, 0)),
      auditAdjustment: _round2(r.reduce((s, x) => s + x.auditAdjustment, 0)),
      auditedAmount: _round2(r.reduce((s, x) => s + x.auditedAmount, 0)),
      recognized: _round2(r.reduce((s, x) => s + x.effectiveRecognized, 0)),
      unrecognized: _round2(r.reduce((s, x) => s + x.unrecognizedAmount, 0)),
      recognizableAsset: _round2(r.reduce((s, x) => s + x.recognizableAsset, 0)),
    }
  })

  // ─── Computed: warnings ────────────────────────────────────────────────────

  const warnings: ComputedRef<N1LossWarning[]> = computed(() => {
    const result: N1LossWarning[] = []
    rows.value.forEach((row, i) => {
      if (row.isExpired) {
        result.push({ rowIndex: i, type: 'expired', message: `到期年度${row.expiryYear}：弥补期限已届满，不产生可确认递延所得税资产` })
      }
      if (row.splitMismatch) {
        result.push({ rowIndex: i, type: 'splitMismatch', message: `到期年度${row.expiryYear}：确认 + 不确认 ≠ 本期审定金额` })
      }
      if (row.basisMissing) {
        result.push({ rowIndex: i, type: 'basisMissing', message: `到期年度${row.expiryYear}：存在不确认金额但依据为空` })
      }
      if (row.sufficiencyConflict) {
        result.push({ rowIndex: i, type: 'sufficiencyConflict', message: `到期年度${row.expiryYear}：判断应纳税所得额不足但仍有确认金额` })
      }
    })
    return result
  })

  // ─── Legacy info (Req 6.1) — delegates to pure function ─────────────────────

  const legacyInfo: ComputedRef<{ count: number; canImport: boolean }> = computed(() => {
    const entry = allResponses.value.get(LEGACY_LOSS_ROWS_KEY)
    return computeLegacyInfo(_rawRows.value.length, entry)
  })

  // ─── Row operations ────────────────────────────────────────────────────────

  function addRow(expiryYear: number): void {
    _rawRows.value.push({
      id: _genId(),
      expiryYear,
      lossYear: null,
      priorUnrecognized: 0,
      bookAmount: 0,
      auditAdjustment: 0,
      recognizedAmount: 0,
      taxRate: 0.25,
      basis: '',
      sufficient: '',
      sourceOperating: false,
      sourceTemporaryDiff: false,
      sourceOther: false,
      indexRef: '',
    })
    _persist()
  }

  function removeRow(index: number): void {
    if (index < 0 || index >= _rawRows.value.length) return
    _rawRows.value.splice(index, 1)
    _persist()
  }

  function updateRow(index: number, field: EditableLossField, value: unknown): void {
    if (index < 0 || index >= _rawRows.value.length) return
    ;(_rawRows.value[index] as any)[field] = value
    _persist()
  }

  function updateLead(key: N1LossLeadKey, field: EditableLeadField, value: unknown): void {
    ;(_leadRows.value[key] as any)[field] = value
    _persistLeadRows()
  }

  // ─── Migration (Req 6.1-6.4) — delegates to pure function ───────────────────

  function importFromLegacy(): number {
    const entry = allResponses.value.get(LEGACY_LOSS_ROWS_KEY)
    if (!entry) return 0
    const legacy = _parseJsonSafe<any[]>(entry)
    if (!Array.isArray(legacy) || legacy.length === 0) return 0

    const result = migrateLegacyLossRows(legacy, auditYear.value, _rawRows.value)
    if (result.added > 0) {
      _rawRows.value = result.rows
      // Sync id sequence to max of migrated rows
      const maxNum = result.rows.reduce((max, r) => {
        const m = r.id?.match(/^loss-(\d+)$/)
        return m ? Math.max(max, Number(m[1])) : max
      }, _idSeq)
      if (maxNum > _idSeq) _idSeq = maxNum
      _persist()
    }
    return result.added
  }

  // ─── Persistence ───────────────────────────────────────────────────────────

  function _persist(): void {
    // Save rows (conclusion field)
    formData.debouncedSave(ROWS_KEY, {
      conclusion: JSON.stringify(_rawRows.value),
    })
    // Save total recognizable (remark field, Cross_Keys, semantic unchanged)
    formData.saveField(TOTAL_RECOGNIZABLE_KEY, {
      remark: String(totals.value.recognizableAsset),
    })
  }

  function _persistLeadRows(): void {
    formData.debouncedSave(LEAD_ROWS_KEY, {
      conclusion: JSON.stringify(_leadRows.value),
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    leadRows,
    totals,
    warnings,
    legacyInfo,
    addRow,
    removeRow,
    updateRow,
    updateLead,
    importFromLegacy,
  }
}

export default useN1LossCheck
