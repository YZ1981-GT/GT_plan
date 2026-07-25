/**
 * useN3Detail — N3-2 明细表 composable
 *
 * Spec: .kiro/specs/n3-deferred-tax-liabilities/
 * Task: 3.3
 * Requirements: 3.1-3.6
 *
 * 职责：
 * - 管理31×14明细表数据（按应纳税暂时性差异项目明细）
 * - 每行：序号/项目/账面价值/计税基础/应纳税暂时性差异/适用税率/期初递延税负债/本期确认/本期转回/期末递延税负债/备注
 * - 14公式（应纳税差异=账面-计税基础；递延税负债=差异×税率）
 * - 动态行新增（ElMessageBox.prompt输入项目名称）+ 删除
 * - 统计摘要：差异项目数/应纳税差异合计/递延税负债合计/加权平均税率
 * - 转回项（期末=0）标记灰色
 * - 合计行与N3-1审定表交叉验证
 * - Calls useN3DeferredTaxEngine（calcTaxableTemporaryDifference, calcDeferredTaxLiabilityRounded）
 *
 * 科目：2901 递延所得税负债（贷方/负债类！）
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import {
  calcTaxableTemporaryDifference,
  calcDeferredTaxLiabilityRounded,
  calcWeightedAvgRate,
  isSpecialNonRecognitionItem,
} from './useN3DeferredTaxEngine'
import { calcSubtotal } from './useN3FormulaEngine'
import type { ChecklistResponse } from './useN3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 明细表单行数据 */
export interface N3DetailRow {
  /** 行ID（唯一标识） */
  id: string
  /** 序号 */
  index: number
  /** 应纳税暂时性差异项目名称 */
  itemName: string
  /** 所属分类（对应N3-1审定表分类，用于SUMIF汇总） */
  category: string
  /** 账面价值 */
  bookValue: number
  /** 计税基础 */
  taxBase: number
  /** 应纳税暂时性差异（公式：账面-计税基础） */
  taxableDiff: number
  /** 适用税率（小数形式，如0.25） */
  taxRate: number
  /** 期初递延所得税负债 */
  beginDtl: number
  /** 本期确认（增加） */
  recognized: number
  /** 本期转回（减少） */
  reversed: number
  /** 期末递延所得税负债（公式：应纳税差异×税率，ROUND 2位） */
  endDtl: number
  /** 备注 */
  remark: string
  /** 是否为不确认特殊项（商誉/长期股权投资拟长期持有） */
  isSpecialNonRecognition: boolean
  /** 是否已转回（期末=0） */
  isReversed: boolean
}

/** 统计摘要 */
export interface N3DetailSummary {
  /** 差异项目数 */
  itemCount: number
  /** 应纳税差异合计 */
  taxableDiffTotal: number
  /** 递延税负债合计（期末） */
  endDtlTotal: number
  /** 加权平均税率 */
  weightedAvgRate: number
  /** 已转回项目数 */
  reversedCount: number
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function parseNum(v: any): number {
  if (v == null) return 0
  if (typeof v === 'string') {
    try { v = JSON.parse(v) } catch { /* noop */ }
  }
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function generateRowId(): string {
  return `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/**
 * 源模板 N3-2 明细表默认 10 项应纳税暂时性差异项目（含类别映射，对齐致同 N3-2 A11~A20）
 * category 对应 N3-1 审定表 5 类（评估增值/公允价值变动/使用权资产/购入摊销年限大于税法规定的资产/其他）
 */
export const N3_DEFAULT_DETAIL_ITEMS: Array<{ itemName: string; category: string }> = [
  { itemName: '非同一控制企业合并资产评估增值', category: '评估增值' },
  { itemName: '使用权资产', category: '使用权资产' },
  { itemName: '交易性金融资产（公允价值与初始账面成本差异）', category: '公允价值变动' },
  { itemName: '其他权益工具投资（公允价值与初始账面成本差异）', category: '公允价值变动' },
  { itemName: '计入其他综合收益的应收款项融资公允价值变动', category: '公允价值变动' },
  { itemName: '计入其他综合收益的其他债权投资公允价值变动', category: '公允价值变动' },
  { itemName: '投资性房地产（公允价值与账面差异）', category: '公允价值变动' },
  { itemName: '交易性金融负债（公允价值与账面差异）', category: '公允价值变动' },
  { itemName: '购入摊销年限大于税法规定的资产', category: '购入摊销年限大于税法规定的资产' },
  { itemName: '除上述项目以外的其他', category: '其他' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseN3DetailOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveField: (sheet: string, field: string, value: any) => Promise<void>
  getField: (sheet: string, field: string) => any
}

export function useN3Detail(options: UseN3DetailOptions) {
  const { allResponses, saveField, getField } = options

  // ─── 1. 从 allResponses 提取明细行数据 ────────────────────────────────────

  /** 明细表全部行（公式列自动计算） */
  const rows: ComputedRef<N3DetailRow[]> = computed(() => {
    const itemId = 'N3-2-rows'
    const resp = allResponses.value.get(itemId)
    let raw: any[] = []
    if (resp?.conclusion) {
      try { raw = JSON.parse(resp.conclusion) } catch { raw = [] }
    }

    return raw.map((r: any, idx: number) => {
      const bookValue = parseNum(r.bookValue)
      const taxBase = parseNum(r.taxBase)
      const taxRate = parseNum(r.taxRate)
      const beginDtl = parseNum(r.beginDtl)
      const recognized = parseNum(r.recognized)
      const reversed = parseNum(r.reversed)

      // 核心公式：应纳税暂时性差异 = 账面价值 - 计税基础
      const taxableDiff = calcTaxableTemporaryDifference(bookValue, taxBase)
      // 核心公式：期末递延所得税负债 = 应纳税暂时性差异 × 适用税率（ROUND 2位）
      const endDtl = calcDeferredTaxLiabilityRounded(taxableDiff, taxRate)
      // 特殊项检测
      const itemName = r.itemName || ''
      const isSpecial = isSpecialNonRecognitionItem(itemName)

      return {
        id: r.id || generateRowId(),
        index: idx + 1,
        itemName,
        category: r.category || '其他',
        bookValue,
        taxBase,
        taxableDiff,
        taxRate,
        beginDtl,
        recognized,
        reversed,
        endDtl: isSpecial ? 0 : endDtl, // 特殊项不确认递延税负债
        remark: r.remark || '',
        isSpecialNonRecognition: isSpecial,
        isReversed: !isSpecial && endDtl === 0 && beginDtl > 0,
      }
    })
  })

  // ─── 2. 统计摘要 ──────────────────────────────────────────────────────────

  const summary: ComputedRef<N3DetailSummary> = computed(() => {
    const r = rows.value
    const nonSpecialRows = r.filter(x => !x.isSpecialNonRecognition)
    const taxableDiffs = nonSpecialRows.map(x => x.taxableDiff)
    const endDtls = nonSpecialRows.map(x => x.endDtl)

    return {
      itemCount: r.length,
      taxableDiffTotal: calcSubtotal(taxableDiffs),
      endDtlTotal: calcSubtotal(endDtls),
      weightedAvgRate: calcWeightedAvgRate(endDtls, taxableDiffs),
      reversedCount: r.filter(x => x.isReversed).length,
    }
  })

  // ─── 3. 转回行标识（灰色背景） ────────────────────────────────────────────

  /** 返回已转回行的ID集合（期末递延税负债=0） */
  const reversedRowIds: ComputedRef<Set<string>> = computed(() => {
    const ids = new Set<string>()
    for (const row of rows.value) {
      if (row.isReversed) {
        ids.add(row.id)
      }
    }
    return ids
  })

  /** 返回特殊项行的ID集合（不确认递延税负债） */
  const specialRowIds: ComputedRef<Set<string>> = computed(() => {
    const ids = new Set<string>()
    for (const row of rows.value) {
      if (row.isSpecialNonRecognition) {
        ids.add(row.id)
      }
    }
    return ids
  })

  // ─── 4. 动态行新增 ────────────────────────────────────────────────────────

  /**
   * 新增明细行（需先ElMessageBox.prompt输入项目名称后调用）
   *
   * @param itemName - 应纳税暂时性差异项目名称（用户输入）
   * @param category - 所属分类（对应N3-1审定表分类，用于SUMIF汇总）
   */
  async function addRow(itemName: string, category?: string): Promise<void> {
    const stored = getField('2', 'rows') || []
    const raw: any[] = Array.isArray(stored) ? [...stored] : []

    raw.push({
      id: generateRowId(),
      itemName,
      category: category || '其他',
      bookValue: 0,
      taxBase: 0,
      taxRate: 0.25, // 默认25%企业所得税率
      beginDtl: 0,
      recognized: 0,
      reversed: 0,
      remark: '',
    })

    await saveField('2', 'rows', raw)
  }

  /**
   * 预置源模板 N3-2 明细表 10 项常见应纳税暂时性差异项目（仅当前为空时生效，不覆盖已录数据）。
   * 对齐致同 N3-2 明细表默认项目清单，category 映射 N3-1 审定表 5 类。
   */
  async function seedDefaultRows(): Promise<void> {
    const stored = getField('2', 'rows') || []
    const raw: any[] = Array.isArray(stored) ? [...stored] : []
    if (raw.length > 0) return
    for (const item of N3_DEFAULT_DETAIL_ITEMS) {
      raw.push({
        id: generateRowId(),
        itemName: item.itemName,
        category: item.category,
        bookValue: 0,
        taxBase: 0,
        taxRate: 0.25,
        beginDtl: 0,
        recognized: 0,
        reversed: 0,
        remark: '',
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
    field: keyof Pick<N3DetailRow, 'itemName' | 'category' | 'bookValue' | 'taxBase' | 'taxRate' | 'beginDtl' | 'recognized' | 'reversed' | 'remark'>,
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

  // ─── 5. 同步合计（供N3-1交叉验证） ────────────────────────────────────────

  /**
   * 同步明细表期末递延税负债合计到独立字段
   * 供 useN3Adjudication crossValidation 使用
   */
  async function syncSummary(): Promise<void> {
    await saveField('2', 'end-dtl-total', summary.value.endDtlTotal)
    await saveField('2', 'taxable-diff-total', summary.value.taxableDiffTotal)
  }

  // ─── 6. 按分类汇总（SUMIF等价，供N3-1审定表使用） ─────────────────────────

  /**
   * 按分类汇总期末递延税负债（SUMIF等价）
   * 用于N3-1审定表各分类行期末余额自动填充
   */
  const categoryTotals: ComputedRef<Map<string, number>> = computed(() => {
    const map = new Map<string, number>()
    for (const row of rows.value) {
      if (row.isSpecialNonRecognition) continue
      const current = map.get(row.category) || 0
      map.set(row.category, current + row.endDtl)
    }
    return map
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    summary,
    reversedRowIds,
    specialRowIds,
    categoryTotals,
    addRow,
    seedDefaultRows,
    removeRow,
    updateRow,
    syncSummary,
  }
}

export default useN3Detail
