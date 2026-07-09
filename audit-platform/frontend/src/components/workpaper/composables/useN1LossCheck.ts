/**
 * useN1LossCheck — 亏损检查表N1-5 逻辑层
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/
 * Task: 3.4
 * Requirements: 5.1-5.6
 *
 * 职责：
 * - 动态行管理（各年度亏损，可新增年度）
 * - 列结构：亏损年度/亏损金额/弥补截止年度/已弥补金额(期初)/本期弥补/未弥补金额/
 *          预计未来应纳税所得额/适用税率/可确认递延税资产/确认依据/是否届满/剩余年限
 * - 公式：未弥补亏损/可确认递延税资产/弥补期限届满判断/剩余年限
 * - 高亮：届满标红、不足标黄
 * - 合计可确认额回填 N1-4/N1-1 可弥补亏损项
 *
 * 核心引擎：
 * - calcUnrecoveredLoss / calcRecognizableAsset / isCompensationExpired / calcRemainingYears
 *   from useN1LossCompensationEngine
 *
 * 科目：1811 递延所得税资产（**借方/资产类**！期末余额=期初+借-贷）
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import {
  calcUnrecoveredLoss,
  calcRecognizableAsset,
  isCompensationExpired,
  calcRemainingYears,
} from './useN1LossCompensationEngine'
import { calcSubtotal, parseNum } from './useN1FormulaEngine'
import type { useN1FormData } from './useN1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 亏损检查表单行数据（可编辑字段） */
export interface N1LossCheckRow {
  /** 唯一行标识 */
  id: string
  /** 亏损年度 */
  lossYear: number
  /** 亏损金额 */
  lossAmount: number
  /** 最长弥补年限（一般5年，高新/科技型中小企业10年） */
  maxYears: number
  /** 已弥补金额（期初累计） */
  recoveredBegin: number
  /** 本期弥补金额 */
  currentRecovery: number
  /** 预计未来应纳税所得额 */
  futureTaxableIncome: number
  /** 适用税率（小数如0.25） */
  taxRate: number
  /** 确认依据（文本） */
  recognitionBasis: string
}

/** 亏损检查表行计算结果 */
export interface N1LossCheckComputed extends N1LossCheckRow {
  /** 弥补截止年度 = lossYear + maxYears */
  expiryYear: number
  /** 已弥补金额合计 = recoveredBegin + currentRecovery */
  totalRecovered: number
  /** 未弥补金额 = max(0, lossAmount - totalRecovered) */
  unrecoveredLoss: number
  /** 可确认递延税资产 = min(unrecovered, futureTaxableIncome) × taxRate */
  recognizableAsset: number
  /** 是否届满（true=标红不可确认） */
  isExpired: boolean
  /** 剩余弥补年限 */
  remainingYears: number
  /** 预计不足标识（futureTaxableIncome < unrecoveredLoss） */
  isInsufficient: boolean
}

/** 亏损检查表合计 */
export interface N1LossCheckTotals {
  lossAmount: number
  totalRecovered: number
  unrecoveredLoss: number
  recognizableAsset: number
}

/** 警告信息 */
export interface N1LossWarning {
  rowIndex: number
  lossYear: number
  type: 'expired' | 'insufficient'
  message: string
}

export interface UseN1LossCheckOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  formData: ReturnType<typeof useN1FormData>
  /** 当前审计年度（默认当前年份） */
  currentYear?: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'N1-5-loss'
let _nextId = 1

// ─── Composable ──────────────────────────────────────────────────────────────

export function useN1LossCheck(options: UseN1LossCheckOptions) {
  const { allResponses, formData, currentYear = new Date().getFullYear() } = options

  // ─── 1. 动态行数据（从 allResponses 恢复） ─────────────────────────────

  const rows = ref<N1LossCheckRow[]>(_loadRows())

  function _loadRows(): N1LossCheckRow[] {
    const stored = allResponses.value.get(`${ITEM_PREFIX}-rows`)
    if (stored?.conclusion) {
      try {
        const parsed = JSON.parse(stored.conclusion) as N1LossCheckRow[]
        if (Array.isArray(parsed) && parsed.length > 0) {
          _nextId = parsed.length + 1
          return parsed
        }
      } catch { /* fallback */ }
    }
    return []
  }

  // ─── 2. 计算属性：公式列自动计算 ──────────────────────────────────────────

  const computedRows: ComputedRef<N1LossCheckComputed[]> = computed(() => {
    return rows.value.map((row) => {
      const expiryYear = row.lossYear + row.maxYears
      const totalRecovered = parseNum(row.recoveredBegin) + parseNum(row.currentRecovery)
      const unrecoveredLoss = calcUnrecoveredLoss(row.lossAmount, totalRecovered)
      const isExpired = isCompensationExpired(row.lossYear, currentYear, row.maxYears)
      const recognizableAsset = isExpired
        ? 0
        : calcRecognizableAsset(unrecoveredLoss, row.futureTaxableIncome, row.taxRate)
      const remainingYears = calcRemainingYears(row.lossYear, currentYear, row.maxYears)
      const isInsufficient = !isExpired && row.futureTaxableIncome < unrecoveredLoss && unrecoveredLoss > 0

      return {
        ...row,
        expiryYear,
        totalRecovered,
        unrecoveredLoss,
        recognizableAsset,
        isExpired,
        remainingYears,
        isInsufficient,
      }
    })
  })

  // ─── 3. 合计行 ─────────────────────────────────────────────────────────

  const totals: ComputedRef<N1LossCheckTotals> = computed(() => {
    const r = computedRows.value
    return {
      lossAmount: calcSubtotal(r.map(x => x.lossAmount)),
      totalRecovered: calcSubtotal(r.map(x => x.totalRecovered)),
      unrecoveredLoss: calcSubtotal(r.map(x => x.unrecoveredLoss)),
      recognizableAsset: calcSubtotal(r.map(x => x.recognizableAsset)),
    }
  })

  // ─── 4. 警告信息 ──────────────────────────────────────────────────────

  /** 届满标红警告 */
  const expiredWarnings: ComputedRef<N1LossWarning[]> = computed(() => {
    return computedRows.value
      .map((row, i) => row.isExpired
        ? { rowIndex: i, lossYear: row.lossYear, type: 'expired' as const, message: `${row.lossYear}年度亏损已超过弥补期限(${row.maxYears}年)，不可确认递延税资产` }
        : null)
      .filter((w): w is N1LossWarning => w !== null)
  })

  /** 不足标黄警告 */
  const insufficientWarnings: ComputedRef<N1LossWarning[]> = computed(() => {
    return computedRows.value
      .map((row, i) => row.isInsufficient
        ? { rowIndex: i, lossYear: row.lossYear, type: 'insufficient' as const, message: `${row.lossYear}年度预计未来应纳税所得额不足以全额抵扣未弥补亏损` }
        : null)
      .filter((w): w is N1LossWarning => w !== null)
  })

  // ─── 5. 行操作 ─────────────────────────────────────────────────────────

  /** 新增亏损年度行 */
  function addRow(lossYear: number, maxYears: number = 5): void {
    rows.value.push({
      id: `loss-${_nextId++}`,
      lossYear,
      lossAmount: 0,
      maxYears,
      recoveredBegin: 0,
      currentRecovery: 0,
      futureTaxableIncome: 0,
      taxRate: 0.25,
      recognitionBasis: '',
    })
    _persistRows()
  }

  /** 删除亏损年度行 */
  function removeRow(index: number): void {
    if (index < 0 || index >= rows.value.length) return
    rows.value.splice(index, 1)
    _persistRows()
  }

  /** 更新行字段 */
  function updateRow(index: number, field: keyof Omit<N1LossCheckRow, 'id'>, value: any): void {
    if (index < 0 || index >= rows.value.length) return
    ;(rows.value[index] as any)[field] = value
    _persistRows()
  }

  // ─── 6. 持久化 ─────────────────────────────────────────────────────────

  function _persistRows(): void {
    formData.debouncedSave(`${ITEM_PREFIX}-rows`, {
      conclusion: JSON.stringify(rows.value),
    })
    // 同步可确认合计（供 crossSheet 读取 → N1-4可弥补亏损行）
    formData.saveField('N1-5-total-recognizable', {
      remark: String(totals.value.recognizableAsset),
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    rows: computedRows,
    addRow,
    removeRow,
    updateRow,
    totals,
    expiredWarnings,
    insufficientWarnings,
  }
}

export default useN1LossCheck
