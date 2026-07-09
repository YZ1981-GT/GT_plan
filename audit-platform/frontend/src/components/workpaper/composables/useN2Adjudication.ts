/**
 * useN2Adjudication — N2-1 审定表 composable
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 3.4
 * Requirements: 2.1-2.8
 *
 * 职责：
 * - 多税种分行数据管理（增值税/城建税/教育费附加/地方教育附加/房产税/土地使用税/印花税/所得税/其他）
 * - 每行：税种|期初|本期贷方(计提)|本期借方(缴纳)|期末|未审|AJE|RJE|审定数
 * - 85公式（审定=未审+AJE+RJE, 期末=期初+贷-借）
 * - TB回写触发(via useN2FormData.writebackTB)
 * - Row validation + subtotal
 *
 * 科目：2221 应交税费（贷方/负债类！期末=期初+贷方-借方）
 */
import { computed, watch, type ComputedRef, type Ref } from 'vue'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
} from './useN2FormulaEngine'
import type { ChecklistResponse } from './useN2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 税种枚举 */
export type N2TaxType =
  | '增值税'
  | '未交增值税'
  | '消费税'
  | '城建税'
  | '教育费附加'
  | '地方教育附加'
  | '房产税'
  | '土地使用税'
  | '印花税'
  | '所得税'
  | '其他'

/** 审定表单行数据 */
export interface N2AdjudicationRow {
  /** 税种 */
  taxType: N2TaxType
  /** 期初余额 */
  beginning: number
  /** 本期贷方发生额（计提/增加） */
  creditAmount: number
  /** 本期借方发生额（缴纳/减少） */
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
}

/** 合计行 */
export interface N2AdjudicationTotal {
  beginning: number
  credit: number
  debit: number
  endBalance: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
}

/** 行级校验结果 */
export interface N2AdjRowValidation {
  taxType: N2TaxType
  /** 期末余额 vs 审定数差异（应一致） */
  endVsAuditedDiff: number
  isValid: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 默认税种行（N2-1固定结构） */
export const DEFAULT_TAX_TYPES: N2TaxType[] = [
  '增值税',
  '未交增值税',
  '消费税',
  '城建税',
  '教育费附加',
  '地方教育附加',
  '房产税',
  '土地使用税',
  '印花税',
  '所得税',
  '其他',
]

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
  const itemId = `N2-${sheet}-${field}`
  const resp = allResponses.get(itemId)
  if (!resp?.conclusion) return null
  try { return JSON.parse(resp.conclusion) } catch { return resp.conclusion }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseN2AdjudicationOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveField: (sheet: string, field: string, value: any) => Promise<void>
  getField: (sheet: string, field: string) => any
  writebackTB: (auditedAmount: number) => Promise<void>
}

export function useN2Adjudication(options: UseN2AdjudicationOptions) {
  const { allResponses, saveField, getField, writebackTB } = options

  // ─── 1. 从 allResponses 提取审定表行数据 ─────────────────────────────────

  /** 审定表各税种行（公式列自动计算） */
  const rows: ComputedRef<N2AdjudicationRow[]> = computed(() => {
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
        return {
          taxType: r.taxType || '其他',
          beginning,
          creditAmount,
          debitAmount,
          endBalance: calcLiabilityEndBalance(beginning, creditAmount, debitAmount),
          unadjusted,
          aje,
          rje,
          audited: calcAuditedAmount(unadjusted, aje, rje),
        }
      })
    }

    // 默认空行
    return DEFAULT_TAX_TYPES.map(taxType => ({
      taxType,
      beginning: 0,
      creditAmount: 0,
      debitAmount: 0,
      endBalance: 0,
      unadjusted: 0,
      aje: 0,
      rje: 0,
      audited: 0,
    }))
  })

  // ─── 2. 合计行 ────────────────────────────────────────────────────────────

  const total: ComputedRef<N2AdjudicationTotal> = computed(() => {
    const r = rows.value
    return {
      beginning: calcSubtotal(r.map(x => x.beginning)),
      credit: calcSubtotal(r.map(x => x.creditAmount)),
      debit: calcSubtotal(r.map(x => x.debitAmount)),
      endBalance: calcSubtotal(r.map(x => x.endBalance)),
      unadjusted: calcSubtotal(r.map(x => x.unadjusted)),
      aje: calcSubtotal(r.map(x => x.aje)),
      rje: calcSubtotal(r.map(x => x.rje)),
      audited: calcSubtotal(r.map(x => x.audited)),
    }
  })

  // ─── 3. 行级校验 ──────────────────────────────────────────────────────────

  /** 每行期末余额应等于审定数（审定表合一逻辑：审定数=期末余额） */
  const rowValidations: ComputedRef<N2AdjRowValidation[]> = computed(() => {
    return rows.value.map(row => {
      const diff = row.endBalance - row.audited
      return {
        taxType: row.taxType,
        endVsAuditedDiff: parseFloat(diff.toFixed(2)),
        isValid: Math.abs(diff) <= MATCH_THRESHOLD,
      }
    })
  })

  // ─── 4. 行更新 ────────────────────────────────────────────────────────────

  /**
   * 更新指定税种行的可编辑字段
   * 公式列(endBalance/audited)自动由computed刷新
   */
  async function updateRow(
    taxType: N2TaxType,
    field: 'beginning' | 'creditAmount' | 'debitAmount' | 'unadjusted' | 'aje' | 'rje',
    value: number,
  ): Promise<void> {
    // 获取当前行数据并修改
    const stored = getField('1', 'adjudication-rows')
    const raw: any[] = Array.isArray(stored) ? [...stored] : DEFAULT_TAX_TYPES.map(t => ({ taxType: t }))

    const idx = raw.findIndex(r => r.taxType === taxType)
    if (idx >= 0) {
      raw[idx] = { ...raw[idx], [field]: value }
    }

    await saveField('1', 'adjudication-rows', raw)
  }

  // ─── 5. 审定数变化 → TB回写 ───────────────────────────────────────────────

  /**
   * 触发TB回写（审定合计→trial_balance 2221期末余额）
   */
  async function triggerWriteback(): Promise<void> {
    await writebackTB(total.value.audited)
  }

  // ─── 6. 保存审定表 + 同步各税种审定数到独立字段 ─────────────────────────────

  /**
   * 保存审定表数据并同步各税种审定数到独立item_id
   * 供 useN2CrossSheet 交叉验证使用
   */
  async function saveAndSync(): Promise<void> {
    // 保存整体rows
    const raw = rows.value.map(r => ({
      taxType: r.taxType,
      beginning: r.beginning,
      creditAmount: r.creditAmount,
      debitAmount: r.debitAmount,
      unadjusted: r.unadjusted,
      aje: r.aje,
      rje: r.rje,
    }))
    await saveField('1', 'adjudication-rows', raw)

    // 同步期末合计
    await saveField('1', 'end-balance-total', total.value.endBalance)

    // TB回写
    await triggerWriteback()
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    total,
    rowValidations,
    updateRow,
    triggerWriteback,
    saveAndSync,
  }
}

export default useN2Adjudication
