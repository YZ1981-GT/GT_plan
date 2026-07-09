/**
 * useN2Lvt — N2-10 土地增值税测算表 composable
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 3.4
 * Requirements: 7.1-7.5
 *
 * 职责：
 * - 逐项目：转让收入|扣除项目|增值额|增值率|税率|速算扣除|应交
 * - Uses calcLandVat, calcAppreciationRate from useN2MultiTaxEngine
 * - 四级累进自动匹配(根据增值率确定税率和速算扣除系数)
 * - 动态行
 *
 * 公式：增值额=转让收入-扣除项目；增值率=增值额/扣除项目
 *       四级超率累进：≤50%→30%/0%  |  50%~100%→40%/5%  |  100%~200%→50%/15%  |  >200%→60%/35%
 *       应交=增值额×税率-扣除项目×速算扣除系数
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { calcLandVat, calcAppreciationRate } from './useN2MultiTaxEngine'
import { calcSubtotal } from './useN2FormulaEngine'
import type { ChecklistResponse } from './useN2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 四级累进税率档 */
export interface LvtBracket {
  /** 增值率上限（含） */
  maxRate: number
  /** 适用税率 */
  taxRate: number
  /** 速算扣除系数 */
  quickDeductCoef: number
  /** 档次描述 */
  label: string
}

/** 土地增值税测算行 */
export interface N2LvtRow {
  /** 行ID */
  id: string
  /** 项目名称 */
  projectName: string
  /** 转让收入 */
  transferIncome: number
  /** 扣除项目金额 */
  deductItems: number
  /** 增值额（公式：收入-扣除） */
  appreciation: number
  /** 增值率（公式：增值额/扣除项目） */
  appreciationRate: number
  /** 适用税率（自动匹配） */
  taxRate: number
  /** 速算扣除系数（自动匹配） */
  quickDeductCoef: number
  /** 应交土增税（公式：增值额×税率-扣除×系数） */
  taxAmount: number
  /** 匹配的税率档次描述 */
  bracketLabel: string
}

/** 土增税汇总 */
export interface N2LvtSummary {
  /** 转让收入合计 */
  totalTransferIncome: number
  /** 扣除项目合计 */
  totalDeductItems: number
  /** 增值额合计 */
  totalAppreciation: number
  /** 应交土增税合计 */
  totalTaxAmount: number
  /** 项目数 */
  projectCount: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 四级超率累进税率表 */
export const LVT_BRACKETS: LvtBracket[] = [
  { maxRate: 0.50, taxRate: 0.30, quickDeductCoef: 0, label: '≤50%: 30%/0%' },
  { maxRate: 1.00, taxRate: 0.40, quickDeductCoef: 0.05, label: '50%~100%: 40%/5%' },
  { maxRate: 2.00, taxRate: 0.50, quickDeductCoef: 0.15, label: '100%~200%: 50%/15%' },
  { maxRate: Infinity, taxRate: 0.60, quickDeductCoef: 0.35, label: '>200%: 60%/35%' },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function generateRowId(): string {
  return `lvt-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/**
 * 根据增值率匹配四级累进税率档次
 */
function matchBracket(appreciationRate: number): LvtBracket {
  for (const bracket of LVT_BRACKETS) {
    if (appreciationRate <= bracket.maxRate) {
      return bracket
    }
  }
  // 兜底（不应到达）
  return LVT_BRACKETS[LVT_BRACKETS.length - 1]
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseN2LvtOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveField: (sheet: string, field: string, value: any) => Promise<void>
  getField: (sheet: string, field: string) => any
}

export function useN2Lvt(options: UseN2LvtOptions) {
  const { allResponses, saveField, getField } = options

  // ─── 1. 土增税测算行数据 ──────────────────────────────────────────────────

  /** 各项目测算行（公式列自动计算 + 四级累进自动匹配） */
  const rows: ComputedRef<N2LvtRow[]> = computed(() => {
    const itemId = 'N2-10-lvt-rows'
    const resp = allResponses.value.get(itemId)
    let raw: any[] = []
    if (resp?.conclusion) {
      try { raw = JSON.parse(resp.conclusion) } catch { raw = [] }
    }

    return raw.map((r: any) => {
      const transferIncome = parseNum(r.transferIncome)
      const deductItems = parseNum(r.deductItems)

      // 增值额 = 转让收入 - 扣除项目
      const appreciation = transferIncome - deductItems
      // 增值率 = 增值额 / 扣除项目（除零保护）
      const appreciationRate = calcAppreciationRate(appreciation, deductItems)
      // 匹配税率档次
      const bracket = matchBracket(appreciationRate)
      // 应交 = 增值额 × 税率 - 扣除项目 × 速算扣除系数
      const taxAmount = calcLandVat(appreciation, bracket.taxRate, deductItems, bracket.quickDeductCoef)

      return {
        id: r.id || generateRowId(),
        projectName: r.projectName || '',
        transferIncome,
        deductItems,
        appreciation,
        appreciationRate,
        taxRate: bracket.taxRate,
        quickDeductCoef: bracket.quickDeductCoef,
        taxAmount,
        bracketLabel: bracket.label,
      }
    })
  })

  // ─── 2. 汇总 ──────────────────────────────────────────────────────────────

  const summary: ComputedRef<N2LvtSummary> = computed(() => {
    const r = rows.value
    return {
      totalTransferIncome: calcSubtotal(r.map(x => x.transferIncome)),
      totalDeductItems: calcSubtotal(r.map(x => x.deductItems)),
      totalAppreciation: calcSubtotal(r.map(x => x.appreciation)),
      totalTaxAmount: calcSubtotal(r.map(x => x.taxAmount)),
      projectCount: r.length,
    }
  })

  // ─── 3. 动态行操作 ────────────────────────────────────────────────────────

  /**
   * 新增项目行（先ElMessageBox.prompt输入项目名称）
   */
  async function addRow(projectName: string): Promise<void> {
    const stored = getField('10', 'lvt-rows') || []
    const raw: any[] = Array.isArray(stored) ? [...stored] : []

    raw.push({
      id: generateRowId(),
      projectName,
      transferIncome: 0,
      deductItems: 0,
    })

    await saveField('10', 'lvt-rows', raw)
  }

  /**
   * 删除指定行
   */
  async function removeRow(rowId: string): Promise<void> {
    const stored = getField('10', 'lvt-rows') || []
    const raw: any[] = Array.isArray(stored) ? [...stored] : []
    const filtered = raw.filter(r => r.id !== rowId)
    await saveField('10', 'lvt-rows', filtered)
  }

  /**
   * 更新指定行字段
   */
  async function updateRow(
    rowId: string,
    field: 'projectName' | 'transferIncome' | 'deductItems',
    value: any,
  ): Promise<void> {
    const stored = getField('10', 'lvt-rows') || []
    const raw: any[] = Array.isArray(stored) ? [...stored] : []
    const idx = raw.findIndex(r => r.id === rowId)
    if (idx >= 0) {
      raw[idx] = { ...raw[idx], [field]: value }
      await saveField('10', 'lvt-rows', raw)
    }
  }

  /**
   * 同步土增税合计到独立字段（供N2-1回填）
   */
  async function syncTotal(): Promise<void> {
    await saveField('10', 'lvt-total', summary.value.totalTaxAmount)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    summary,
    addRow,
    removeRow,
    updateRow,
    syncTotal,
  }
}

export default useN2Lvt
