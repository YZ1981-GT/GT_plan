/**
 * useN5TaxAdjustment — N5-5 纳税调整明细表 composable
 *
 * Spec: .kiro/specs/n5-income-tax-expense/
 * Task: 3.4
 * Requirements: 4.1-4.7
 *
 * 职责：
 * - 管理N5-5数据（107行调整项），按5大类分组：收入类/扣除类/资产类/特殊事项/其他
 * - Uses calcNetAdjustment from useN5TaxAdjustmentEngine
 * - Uses calcSubtotal from useN5FormulaEngine
 * - 计算各类小计+调增合计/调减合计/净额
 * - 调整净额回填N5-4（纳税调增/调减合计）
 * - 研发费用加计扣除行联动N5-6-1
 * - 支持动态行新增 + 导入导出
 *
 * 科目：6801 所得税费用（损益类，纳税调整为税法vs会计差异）
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { calcNetAdjustment } from './useN5TaxAdjustmentEngine'
import { calcSubtotal, parseNum } from './useN5FormulaEngine'
import type { ChecklistResponse } from './useN5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 纳税调整分类枚举 */
export type TaxAdjustmentCategory = '收入类' | '扣除类' | '资产类' | '特殊事项' | '其他'

/** 纳税调整明细行 */
export interface N5TaxAdjustmentRow {
  /** 行序号 */
  index: number
  /** 项目编码（对应纳税申报表行号） */
  code: string
  /** 项目名称 */
  label: string
  /** 分类 */
  category: TaxAdjustmentCategory
  /** 账面金额 */
  bookAmount: number
  /** 税收金额 */
  taxAmount: number
  /** 调增金额（账面>税收时） */
  addBack: number
  /** 调减金额（税收>账面时） */
  deduct: number
  /** 依据/备注 */
  basis: string
  /** 是否固定行（不可删除） */
  isFixed: boolean
  /** 联动来源（如 'N5-6-1'） */
  linkedSource?: string
}

/** 分类小计 */
export interface N5TaxAdjustmentCategorySummary {
  category: TaxAdjustmentCategory
  addBackSubtotal: number
  deductSubtotal: number
  rowCount: number
}

/** 全表汇总 */
export interface N5TaxAdjustmentTotals {
  /** 调增合计 */
  addBackTotal: number
  /** 调减合计 */
  deductTotal: number
  /** 净额 = 调增 - 调减 */
  netAdjustment: number
  /** 各类小计 */
  categorySubtotals: N5TaxAdjustmentCategorySummary[]
  /** 总行数 */
  totalRows: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const CATEGORIES: TaxAdjustmentCategory[] = ['收入类', '扣除类', '资产类', '特殊事项', '其他']

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseN5TaxAdjustmentOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveField: (sheet: string, field: string, value: any) => Promise<void>
  getField: (sheet: string, field: string) => any
}

export function useN5TaxAdjustment(options: UseN5TaxAdjustmentOptions) {
  const { allResponses, saveField, getField } = options

  // ─── 1. 调整项数据行 ──────────────────────────────────────────────────────

  const rows: ComputedRef<N5TaxAdjustmentRow[]> = computed(() => {
    const itemId = 'N5-5-adjustment-rows'
    const resp = allResponses.value.get(itemId)
    let raw: any[] = []
    if (resp?.conclusion) {
      try { raw = JSON.parse(resp.conclusion) } catch { raw = [] }
    }

    if (raw.length === 0) return _getDefaultRows()

    return raw.map((r: any, i: number) => ({
      index: i + 1,
      code: r.code || '',
      label: r.label || `项目${i + 1}`,
      category: (CATEGORIES.includes(r.category) ? r.category : '其他') as TaxAdjustmentCategory,
      bookAmount: parseNum(r.bookAmount),
      taxAmount: parseNum(r.taxAmount),
      addBack: parseNum(r.addBack),
      deduct: parseNum(r.deduct),
      basis: r.basis || '',
      isFixed: r.isFixed !== false,
      linkedSource: r.linkedSource || undefined,
    }))
  })

  // ─── 2. 按分类分组 ────────────────────────────────────────────────────────

  const groupedByCategory: ComputedRef<Record<TaxAdjustmentCategory, N5TaxAdjustmentRow[]>> = computed(() => {
    const groups: Record<TaxAdjustmentCategory, N5TaxAdjustmentRow[]> = {
      '收入类': [],
      '扣除类': [],
      '资产类': [],
      '特殊事项': [],
      '其他': [],
    }
    for (const row of rows.value) {
      groups[row.category].push(row)
    }
    return groups
  })

  // ─── 3. 各类小计 ──────────────────────────────────────────────────────────

  const categorySubtotals: ComputedRef<N5TaxAdjustmentCategorySummary[]> = computed(() => {
    return CATEGORIES.map(category => {
      const catRows = groupedByCategory.value[category]
      return {
        category,
        addBackSubtotal: calcSubtotal(catRows.map(r => r.addBack)),
        deductSubtotal: calcSubtotal(catRows.map(r => r.deduct)),
        rowCount: catRows.length,
      }
    })
  })

  // ─── 4. 调增/调减合计 + 净额 ─────────────────────────────────────────────

  const addBackTotal: ComputedRef<number> = computed(() => {
    return calcSubtotal(rows.value.map(r => r.addBack))
  })

  const deductTotal: ComputedRef<number> = computed(() => {
    return calcSubtotal(rows.value.map(r => r.deduct))
  })

  const netAdjustment: ComputedRef<number> = computed(() => {
    return calcNetAdjustment(
      rows.value.map(r => r.addBack),
      rows.value.map(r => r.deduct),
    )
  })

  // ─── 5. 汇总 ─────────────────────────────────────────────────────────────

  const totals: ComputedRef<N5TaxAdjustmentTotals> = computed(() => ({
    addBackTotal: addBackTotal.value,
    deductTotal: deductTotal.value,
    netAdjustment: netAdjustment.value,
    categorySubtotals: categorySubtotals.value,
    totalRows: rows.value.length,
  }))

  // ─── 6. 行操作 ────────────────────────────────────────────────────────────

  /**
   * 更新指定行的可编辑字段
   */
  async function updateRow(
    rowIndex: number,
    field: keyof Pick<N5TaxAdjustmentRow, 'bookAmount' | 'taxAmount' | 'addBack' | 'deduct' | 'basis' | 'label'>,
    value: number | string,
  ): Promise<void> {
    const currentRows = rows.value.map(r => ({ ...r }))
    if (rowIndex >= 0 && rowIndex < currentRows.length) {
      ;(currentRows[rowIndex] as any)[field] = value
      await _saveRows(currentRows)
    }
  }

  /**
   * 新增动态行
   */
  async function addRow(row: Partial<N5TaxAdjustmentRow>): Promise<void> {
    const currentRows = rows.value.map(r => ({ ...r }))
    currentRows.push({
      index: currentRows.length + 1,
      code: row.code || '',
      label: row.label || '新增调整项',
      category: row.category || '其他',
      bookAmount: parseNum(row.bookAmount),
      taxAmount: parseNum(row.taxAmount),
      addBack: parseNum(row.addBack),
      deduct: parseNum(row.deduct),
      basis: row.basis || '',
      isFixed: false,
      linkedSource: row.linkedSource,
    })
    await _saveRows(currentRows)
  }

  /**
   * 删除指定行（仅非固定行）
   */
  async function removeRow(rowIndex: number): Promise<void> {
    const currentRows = rows.value.filter((r, i) => i !== rowIndex || r.isFixed)
    await _saveRows(currentRows)
  }

  // ─── 7. 同步调增/调减合计到N5-4 ──────────────────────────────────────────

  /**
   * 将调增/调减合计回填到N5-4当期计算表
   */
  async function syncTotalsToCurrentTaxCalc(): Promise<void> {
    await saveField('5', 'add-back-total', addBackTotal.value)
    await saveField('5', 'deduct-total', deductTotal.value)
  }

  // ─── 8. 内部helper ────────────────────────────────────────────────────────

  async function _saveRows(data: N5TaxAdjustmentRow[]): Promise<void> {
    const itemId = 'N5-5-adjustment-rows'
    const conclusion = JSON.stringify(data)
    // 直接更新本地 + 持久化
    allResponses.value.set(itemId, {
      item_id: itemId,
      conclusion,
      remark: null,
    })
    await saveField('5', 'adjustment-rows', data)
  }

  /**
   * 获取默认107行模板（精简核心行）
   */
  function _getDefaultRows(): N5TaxAdjustmentRow[] {
    // 仅返回核心分类占位行，完整107行从后端/导入获取
    const defaults: Array<{ label: string; category: TaxAdjustmentCategory; code: string }> = [
      { label: '视同销售收入', category: '收入类', code: 'A010000' },
      { label: '未按权责发生制确认收入', category: '收入类', code: 'A020000' },
      { label: '投资收益', category: '收入类', code: 'A030000' },
      { label: '不征税收入', category: '收入类', code: 'A050000' },
      { label: '视同销售成本', category: '扣除类', code: 'A060000' },
      { label: '职工薪酬', category: '扣除类', code: 'A070000' },
      { label: '业务招待费', category: '扣除类', code: 'A080000' },
      { label: '广告费和业务宣传费', category: '扣除类', code: 'A090000' },
      { label: '捐赠支出', category: '扣除类', code: 'A100000' },
      { label: '利息支出', category: '扣除类', code: 'A110000' },
      { label: '罚款/滞纳金/损失', category: '扣除类', code: 'A120000' },
      { label: '资产折旧/摊销', category: '资产类', code: 'A130000' },
      { label: '资产减值准备', category: '资产类', code: 'A140000' },
      { label: '资产损失', category: '资产类', code: 'A150000' },
      { label: '企业重组', category: '特殊事项', code: 'A160000' },
      { label: '政策性搬迁', category: '特殊事项', code: 'A170000' },
      { label: '研发费用加计扣除', category: '其他', code: 'A180000' },
      { label: '其他', category: '其他', code: 'A190000' },
    ]
    return defaults.map((d, i) => ({
      index: i + 1,
      code: d.code,
      label: d.label,
      category: d.category,
      bookAmount: 0,
      taxAmount: 0,
      addBack: 0,
      deduct: 0,
      basis: '',
      isFixed: true,
      linkedSource: d.code === 'A180000' ? 'N5-6-1' : undefined,
    }))
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // Computed
    rows,
    groupedByCategory,
    categorySubtotals,
    addBackTotal,
    deductTotal,
    netAdjustment,
    totals,
    // Actions
    updateRow,
    addRow,
    removeRow,
    syncTotalsToCurrentTaxCalc,
  }
}

export default useN5TaxAdjustment
