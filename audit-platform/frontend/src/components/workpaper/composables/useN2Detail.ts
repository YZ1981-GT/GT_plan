/**
 * useN2Detail — N2-2 明细表 composable
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 3.4
 * Requirements: 3.1-3.6
 *
 * 职责：
 * - 42行23列dynamic rows，各税种明细子目
 * - 区段Tab: 基础(税种/子目/计税依据/税率) | 计提缴纳(期初/计提/缴纳/期末) | 核对(申报表/差异/结论)
 * - Uses calcLiabilityEndBalance, calcDiff
 * - 动态行新增 + 统计摘要（税种数/计提合计/缴纳合计/期末合计）
 *
 * 科目：2221 应交税费（贷方/负债类！期末=期初+贷方-借方）
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { calcLiabilityEndBalance, calcDiff, calcSubtotal } from './useN2FormulaEngine'
import type { ChecklistResponse } from './useN2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 明细表单行数据 */
export interface N2DetailRow {
  /** 行ID（唯一标识） */
  id: string
  /** 税种大类 */
  taxType: string
  /** 明细子目（如"应交增值税-销项税额"） */
  subItem: string
  /** 计税依据 */
  taxBase: number
  /** 适用税率 */
  taxRate: number
  /** 期初余额 */
  beginning: number
  /** 本期计提（贷方增加） */
  accrual: number
  /** 本期缴纳（借方减少） */
  payment: number
  /** 期末余额（公式：期初+计提-缴纳，负债类） */
  endBalance: number
  /** 申报表金额 */
  declaredAmount: number
  /** 差异（公式：账面-申报表） */
  diff: number
  /** 核查结论 */
  conclusion: string
}

/** 统计摘要 */
export interface N2DetailSummary {
  /** 税种数 */
  taxTypeCount: number
  /** 计提合计 */
  accrualTotal: number
  /** 缴纳合计 */
  paymentTotal: number
  /** 期末合计 */
  endBalanceTotal: number
  /** 存在差异的行数 */
  diffRowCount: number
}

/** 区段Tab标识 */
export type N2DetailTabSection = 'basic' | 'accrual-payment' | 'reconcile'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function generateRowId(): string {
  return `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/** 源模板 N2-2 明细表默认 13 类标准税种（与 N2-1 审定表同源） */
export const N2_DEFAULT_TAX_TYPES: string[] = [
  '企业所得税',
  '增值税',
  '消费税',
  '资源税',
  '土地增值税',
  '城市维护建设税',
  '车船牌照税',
  '房产税',
  '土地使用税',
  '教育费附加',
  '矿产资源补偿费',
  '代扣代缴外国企业所得税',
  '代扣代缴个人所得税',
]

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseN2DetailOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveField: (sheet: string, field: string, value: any) => Promise<void>
  getField: (sheet: string, field: string) => any
}

export function useN2Detail(options: UseN2DetailOptions) {
  const { allResponses, saveField, getField } = options

  // ─── 1. 从 allResponses 提取明细行数据 ────────────────────────────────────

  /** 明细表全部行（公式列自动计算） */
  const rows: ComputedRef<N2DetailRow[]> = computed(() => {
    const itemId = 'N2-2-rows'
    const resp = allResponses.value.get(itemId)
    let raw: any[] = []
    if (resp?.conclusion) {
      try { raw = JSON.parse(resp.conclusion) } catch { raw = [] }
    }

    return raw.map((r: any) => {
      const beginning = parseNum(r.beginning)
      const accrual = parseNum(r.accrual)
      const payment = parseNum(r.payment)
      const declaredAmount = parseNum(r.declaredAmount)
      // 负债类期末=期初+贷方(计提)-借方(缴纳)
      const endBalance = calcLiabilityEndBalance(beginning, accrual, payment)
      // 差异=账面(期末)-申报表
      const diff = calcDiff(endBalance, declaredAmount)
      return {
        id: r.id || generateRowId(),
        taxType: r.taxType || '',
        subItem: r.subItem || '',
        taxBase: parseNum(r.taxBase),
        taxRate: parseNum(r.taxRate),
        beginning,
        accrual,
        payment,
        endBalance,
        declaredAmount,
        diff,
        conclusion: r.conclusion || '',
      }
    })
  })

  // ─── 2. 统计摘要 ──────────────────────────────────────────────────────────

  const summary: ComputedRef<N2DetailSummary> = computed(() => {
    const r = rows.value
    const uniqueTaxTypes = new Set(r.map(row => row.taxType).filter(Boolean))
    return {
      taxTypeCount: uniqueTaxTypes.size,
      accrualTotal: calcSubtotal(r.map(x => x.accrual)),
      paymentTotal: calcSubtotal(r.map(x => x.payment)),
      endBalanceTotal: calcSubtotal(r.map(x => x.endBalance)),
      diffRowCount: r.filter(x => Math.abs(x.diff) > 0.01).length,
    }
  })

  // ─── 3. 差异行标识（红色背景） ────────────────────────────────────────────

  /** 返回存在差异的行ID列表 */
  const diffRowIds: ComputedRef<Set<string>> = computed(() => {
    const ids = new Set<string>()
    for (const row of rows.value) {
      if (Math.abs(row.diff) > 0.01) {
        ids.add(row.id)
      }
    }
    return ids
  })

  // ─── 4. 动态行新增 ────────────────────────────────────────────────────────

  /**
   * 新增明细行（需先ElMessageBox.prompt输入税种/子目名称后调用）
   */
  async function addRow(taxType: string, subItem: string): Promise<void> {
    const stored = getField('2', 'rows') || []
    const raw: any[] = Array.isArray(stored) ? [...stored] : []

    raw.push({
      id: generateRowId(),
      taxType,
      subItem,
      taxBase: 0,
      taxRate: 0,
      beginning: 0,
      accrual: 0,
      payment: 0,
      declaredAmount: 0,
      conclusion: '',
    })

    await saveField('2', 'rows', raw)
  }

  /**
   * 预置源模板 N2-2 明细表 13 类标准税种（仅当前为空时生效，避免覆盖已录数据）。
   * 对齐致同 N2-2 明细表固定税种行（与 N2-1 审定表同源）。
   */
  async function seedDefaultRows(): Promise<void> {
    const stored = getField('2', 'rows') || []
    const raw: any[] = Array.isArray(stored) ? [...stored] : []
    if (raw.length > 0) return
    for (const taxType of N2_DEFAULT_TAX_TYPES) {
      raw.push({
        id: generateRowId(),
        taxType,
        subItem: '',
        taxBase: 0,
        taxRate: 0,
        beginning: 0,
        accrual: 0,
        payment: 0,
        declaredAmount: 0,
        conclusion: '',
      })
    }
    await saveField('2', 'rows', raw)
  }

  /**
   * 删除指定行
   */
  async function removeRow(rowId: string): Promise<void> {
    const stored = getField('2', 'rows') || []
    const raw: any[] = Array.isArray(stored) ? [...stored] : []
    const filtered = raw.filter(r => r.id !== rowId)
    await saveField('2', 'rows', filtered)
  }

  /**
   * 更新指定行字段
   */
  async function updateRow(
    rowId: string,
    field: keyof Omit<N2DetailRow, 'id' | 'endBalance' | 'diff'>,
    value: any,
  ): Promise<void> {
    const stored = getField('2', 'rows') || []
    const raw: any[] = Array.isArray(stored) ? [...stored] : []
    const idx = raw.findIndex(r => r.id === rowId)
    if (idx >= 0) {
      raw[idx] = { ...raw[idx], [field]: value }
      await saveField('2', 'rows', raw)
    }
  }

  // ─── 5. 保存明细表 ────────────────────────────────────────────────────────

  /**
   * 同步保存明细表期末合计（供 useN2CrossSheet 校验用）
   */
  async function syncSummary(): Promise<void> {
    await saveField('2', 'end-balance-total', summary.value.endBalanceTotal)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    summary,
    diffRowIds,
    addRow,
    seedDefaultRows,
    removeRow,
    updateRow,
    syncSummary,
  }
}

export default useN2Detail
