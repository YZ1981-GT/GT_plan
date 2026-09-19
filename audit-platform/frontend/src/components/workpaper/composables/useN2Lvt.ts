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
  /** 扣除项目金额（可手填，或由扣除明细弹窗回填合计） */
  deductItems: number
  /** 扣除明细·取得土地使用权支付金额 */
  landCost: number
  /** 扣除明细·开发成本 */
  devCost: number
  /** 扣除明细·开发费用 */
  devExpense: number
  /** 扣除明细·与转让相关税金 */
  relatedTax: number
  /** 扣除明细·财政部规定的加计扣除（加计20%，公式=(取得土地+开发成本)×20%） */
  additionalDeduction: number
  /** 扣除明细合计（公式=取得土地+开发成本+开发费用+相关税金+加计扣除） */
  deductionDetailTotal: number
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

/** 面积参考表行（辅助按面积分摊扣除项目） */
export interface N2LvtAreaRow {
  /** 项目类型（数量/收入/单价/成本） */
  key: string
  /** 可销售面积 */
  sellable: number
  /** 已售面积 */
  sold: number
  /** 未售面积（公式：可销售 - 已售） */
  unsold: number
  /** 索引 */
  indexNo: string
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

/** 面积参考表固定行（数量/收入/单价/成本） */
export const AREA_ROW_KEYS = ['数量', '收入', '单价', '成本'] as const

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

      // 扣除明细 5 子项（加计扣除自动=(取得土地+开发成本)×20%）
      const landCost = parseNum(r.landCost)
      const devCost = parseNum(r.devCost)
      const devExpense = parseNum(r.devExpense)
      const relatedTax = parseNum(r.relatedTax)
      const additionalDeduction = (landCost + devCost) * 0.20
      const deductionDetailTotal = landCost + devCost + devExpense + relatedTax + additionalDeduction

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
        landCost,
        devCost,
        devExpense,
        relatedTax,
        additionalDeduction,
        deductionDetailTotal,
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
   * 更新指定行的扣除明细（5子项）并回填 deductItems = 明细合计。
   * 加计扣除自动=(取得土地+开发成本)×20%，合计写入 deductItems（扣除项目金额）。
   */
  async function updateDeductionDetail(
    rowId: string,
    detail: { landCost: number; devCost: number; devExpense: number; relatedTax: number },
  ): Promise<void> {
    const stored = getField('10', 'lvt-rows') || []
    const raw: any[] = Array.isArray(stored) ? [...stored] : []
    const idx = raw.findIndex(r => r.id === rowId)
    if (idx < 0) return

    const landCost = parseNum(detail.landCost)
    const devCost = parseNum(detail.devCost)
    const devExpense = parseNum(detail.devExpense)
    const relatedTax = parseNum(detail.relatedTax)
    const additionalDeduction = (landCost + devCost) * 0.20
    const total = landCost + devCost + devExpense + relatedTax + additionalDeduction

    raw[idx] = {
      ...raw[idx],
      landCost,
      devCost,
      devExpense,
      relatedTax,
      // 回填扣除项目金额 = 扣除明细合计
      deductItems: total,
    }
    await saveField('10', 'lvt-rows', raw)
  }

  // ─── 面积参考表（辅助按面积分摊扣除项目，item_id N2-10-area） ──────────────

  /** 各项目测算行（公式列自动计算 + 四级累进自动匹配）之外的面积参考数据 */
  const areaRows: ComputedRef<N2LvtAreaRow[]> = computed(() => {
    const stored = getField('10', 'area')
    const rawRows: any[] = stored && Array.isArray(stored.rows) ? stored.rows : []
    return AREA_ROW_KEYS.map((key) => {
      const r = rawRows.find((x: any) => x.key === key) || {}
      const sellable = parseNum(r.sellable)
      const sold = parseNum(r.sold)
      return {
        key,
        sellable,
        sold,
        // 未售面积 = 可销售面积 - 已售面积（公式列）
        unsold: sellable - sold,
        indexNo: r.indexNo || '',
      }
    })
  })

  /**
   * 更新面积参考表某行字段（可销售面积/已售面积/索引，未售面积自动计算）
   */
  async function updateAreaRow(
    key: string,
    field: 'sellable' | 'sold' | 'indexNo',
    value: any,
  ): Promise<void> {
    const stored = getField('10', 'area')
    const rawRows: any[] = stored && Array.isArray(stored.rows) ? [...stored.rows] : []
    const idx = rawRows.findIndex((x: any) => x.key === key)
    if (idx >= 0) {
      rawRows[idx] = { ...rawRows[idx], key, [field]: value }
    } else {
      rawRows.push({ key, [field]: value })
    }
    await saveField('10', 'area', { rows: rawRows })
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
    updateDeductionDetail,
    areaRows,
    updateAreaRow,
    syncTotal,
  }
}

export default useN2Lvt
