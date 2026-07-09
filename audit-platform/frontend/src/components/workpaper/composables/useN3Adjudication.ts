/**
 * useN3Adjudication — N3-1 审定表 composable
 *
 * Spec: .kiro/specs/n3-deferred-tax-liabilities/
 * Task: 3.3
 * Requirements: 2.1-2.8
 *
 * 职责：
 * - 管理24×14审定表数据（按应纳税暂时性差异项目分行）
 * - 固定行：固定资产折旧差异/公允价值变动/一次性税前扣除/长期股权投资/其他 + 期初/本期变动/期末
 * - 每行：项目|期初余额|本期贷方|本期借方|未审数|AJE|RJE|审定数
 * - 78公式（审定=未审+AJE+RJE, 负债类期末=期初+贷-借）
 * - SUMIF等价：从N3-2明细表按分类汇总
 * - TB回写触发(via useN3FormData.writebackTB)
 * - Row validation + subtotal
 * - 与N3-2明细合计交叉验证
 *
 * 科目：2901 递延所得税负债（贷方/负债类！期末=期初+贷方-借方）
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
  calcChange,
  calcChangeRate,
} from './useN3FormulaEngine'
import type { ChecklistResponse } from './useN3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 应纳税暂时性差异项目分类 */
export type N3DiffCategory =
  | '固定资产折旧差异'
  | '公允价值变动'
  | '一次性税前扣除'
  | '长期股权投资'
  | '投资性房地产'
  | '无形资产'
  | '其他'

/** 审定表单行数据 */
export interface N3AdjudicationRow {
  /** 应纳税暂时性差异项目分类 */
  category: N3DiffCategory
  /** 期初余额（贷方余额） */
  beginning: number
  /** 本期贷方发生额（确认/增加递延税负债） */
  creditAmount: number
  /** 本期借方发生额（转回/减少递延税负债） */
  debitAmount: number
  /** 期末余额（公式：期初+贷方-借方，负债类） */
  endBalance: number
  /** 未审数 */
  unadjusted: number
  /** AJE调整 */
  aje: number
  /** RJE调整 */
  rje: number
  /** 审定数（公式：未审+AJE+RJE） */
  audited: number
  /** 变动额（期末-期初） */
  change: number
  /** 变动率 */
  changeRate: number
}

/** 合计行 */
export interface N3AdjudicationTotal {
  beginning: number
  credit: number
  debit: number
  endBalance: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
  change: number
}

/** 行级校验结果 */
export interface N3AdjRowValidation {
  category: N3DiffCategory
  /** 期末余额 vs 审定数差异（应一致） */
  endVsAuditedDiff: number
  isValid: boolean
}

/** 与N3-2明细表交叉验证结果 */
export interface N3CrossValidation {
  /** 审定表合计 */
  adjudicationTotal: number
  /** 明细表合计 */
  detailTotal: number
  /** 差异 */
  diff: number
  /** 是否匹配 */
  isMatch: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 默认应纳税暂时性差异项目分类行（N3-1固定结构） */
export const DEFAULT_CATEGORIES: N3DiffCategory[] = [
  '固定资产折旧差异',
  '公允价值变动',
  '一次性税前扣除',
  '长期股权投资',
  '投资性房地产',
  '无形资产',
  '其他',
]

/** 阈值：差异容忍度 */
const MATCH_THRESHOLD = 0.01

// ─── Helpers ─────────────────────────────────────────────────────────────────

function parseNum(v: any): number {
  if (v == null) return 0
  if (typeof v === 'string') {
    try { v = JSON.parse(v) } catch { /* noop */ }
  }
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function getFieldFromResponses(
  allResponses: Map<string, ChecklistResponse>,
  sheet: string,
  field: string,
): any {
  const itemId = `N3-${sheet}-${field}`
  const resp = allResponses.get(itemId)
  if (!resp?.conclusion) return null
  try { return JSON.parse(resp.conclusion) } catch { return resp.conclusion }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseN3AdjudicationOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveField: (sheet: string, field: string, value: any) => Promise<void>
  getField: (sheet: string, field: string) => any
  writebackTB: (auditedAmount: number) => Promise<void>
}

export function useN3Adjudication(options: UseN3AdjudicationOptions) {
  const { allResponses, saveField, getField, writebackTB } = options

  // ─── 1. 从 allResponses 提取审定表行数据 ─────────────────────────────────

  /** 审定表各项目行（公式列自动计算） */
  const rows: ComputedRef<N3AdjudicationRow[]> = computed(() => {
    const stored = getFieldFromResponses(allResponses.value, '1', 'adjudication-rows')
    const raw: any[] = Array.isArray(stored) ? stored : []

    // 如果已有存储数据，使用存储数据；否则返回默认空行
    if (raw.length > 0) {
      return raw.map((r: any) => {
        const beginning = parseNum(r.beginning)
        const creditAmount = parseNum(r.creditAmount)
        const debitAmount = parseNum(r.debitAmount)
        const unadjusted = parseNum(r.unadjusted)
        const aje = parseNum(r.aje)
        const rje = parseNum(r.rje)
        const endBalance = calcLiabilityEndBalance(beginning, creditAmount, debitAmount)
        const change = calcChange(endBalance, beginning)
        return {
          category: r.category || '其他',
          beginning,
          creditAmount,
          debitAmount,
          endBalance,
          unadjusted,
          aje,
          rje,
          audited: calcAuditedAmount(unadjusted, aje, rje),
          change,
          changeRate: calcChangeRate(beginning, change),
        }
      })
    }

    // 默认空行
    return DEFAULT_CATEGORIES.map(category => ({
      category,
      beginning: 0,
      creditAmount: 0,
      debitAmount: 0,
      endBalance: 0,
      unadjusted: 0,
      aje: 0,
      rje: 0,
      audited: 0,
      change: 0,
      changeRate: 0,
    }))
  })

  // ─── 2. 合计行 ────────────────────────────────────────────────────────────

  const total: ComputedRef<N3AdjudicationTotal> = computed(() => {
    const r = rows.value
    const beginningTotal = calcSubtotal(r.map(x => x.beginning))
    const endBalanceTotal = calcSubtotal(r.map(x => x.endBalance))
    return {
      beginning: beginningTotal,
      credit: calcSubtotal(r.map(x => x.creditAmount)),
      debit: calcSubtotal(r.map(x => x.debitAmount)),
      endBalance: endBalanceTotal,
      unadjusted: calcSubtotal(r.map(x => x.unadjusted)),
      aje: calcSubtotal(r.map(x => x.aje)),
      rje: calcSubtotal(r.map(x => x.rje)),
      audited: calcSubtotal(r.map(x => x.audited)),
      change: calcChange(endBalanceTotal, beginningTotal),
    }
  })

  // ─── 3. 行级校验（期末 vs 审定数） ────────────────────────────────────────

  /** 每行期末余额应等于审定数（审定表合一逻辑） */
  const rowValidations: ComputedRef<N3AdjRowValidation[]> = computed(() => {
    return rows.value.map(row => {
      const diff = row.endBalance - row.audited
      return {
        category: row.category,
        endVsAuditedDiff: parseFloat(diff.toFixed(2)),
        isValid: Math.abs(diff) <= MATCH_THRESHOLD,
      }
    })
  })

  // ─── 4. 与N3-2明细表交叉验证 ──────────────────────────────────────────────

  /**
   * SUMIF等价：从N3-2明细表按分类汇总与审定表合计对比
   * 依赖 N3-2 的期末递延税负债合计存储在 allResponses
   */
  const crossValidation: ComputedRef<N3CrossValidation> = computed(() => {
    const adjTotal = total.value.audited
    const detailTotal = parseNum(
      getFieldFromResponses(allResponses.value, '2', 'end-dtl-total'),
    )
    const diff = adjTotal - detailTotal
    return {
      adjudicationTotal: adjTotal,
      detailTotal,
      diff: parseFloat(diff.toFixed(2)),
      isMatch: Math.abs(diff) <= MATCH_THRESHOLD,
    }
  })

  // ─── 5. 行更新 ────────────────────────────────────────────────────────────

  /**
   * 更新指定分类行的可编辑字段
   * 公式列(endBalance/audited/change/changeRate)自动由computed刷新
   */
  async function updateRow(
    category: N3DiffCategory,
    field: 'beginning' | 'creditAmount' | 'debitAmount' | 'unadjusted' | 'aje' | 'rje',
    value: number,
  ): Promise<void> {
    // 获取当前行数据并修改
    const stored = getField('1', 'adjudication-rows')
    const raw: any[] = Array.isArray(stored) ? [...stored] : DEFAULT_CATEGORIES.map(c => ({ category: c }))

    const idx = raw.findIndex(r => r.category === category)
    if (idx >= 0) {
      raw[idx] = { ...raw[idx], [field]: value }
    }

    await saveField('1', 'adjudication-rows', raw)
  }

  // ─── 6. 审定数变化 → TB回写 ───────────────────────────────────────────────

  /**
   * 触发TB回写（审定合计→trial_balance 2901期末余额）
   */
  async function triggerWriteback(): Promise<void> {
    await writebackTB(total.value.audited)
  }

  // ─── 7. 保存审定表 + 同步合计 ─────────────────────────────────────────────

  /**
   * 保存审定表数据并同步合计到独立字段
   * 供 useN3CrossSheet 和 N5 联动使用
   */
  async function saveAndSync(): Promise<void> {
    // 保存整体rows（只存可编辑字段，公式列由computed计算）
    const raw = rows.value.map(r => ({
      category: r.category,
      beginning: r.beginning,
      creditAmount: r.creditAmount,
      debitAmount: r.debitAmount,
      unadjusted: r.unadjusted,
      aje: r.aje,
      rje: r.rje,
    }))
    await saveField('1', 'adjudication-rows', raw)

    // 同步期末合计（供交叉验证+N5核对使用）
    await saveField('1', 'end-balance-total', total.value.endBalance)
    await saveField('1', 'audited-total', total.value.audited)
    await saveField('1', 'change-total', total.value.change)

    // TB回写
    await triggerWriteback()
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    total,
    rowValidations,
    crossValidation,
    updateRow,
    triggerWriteback,
    saveAndSync,
  }
}

export default useN3Adjudication
