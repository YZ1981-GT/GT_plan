/**
 * useI1Detail — I1-2 无形资产明细表 composable
 *
 * 56列宽表拆分为4区段Tab：
 *   Tab1 基础信息：类型/名称/取得日期/使用寿命/残值率/摊销方法
 *   Tab2 原值变动：期初/增加/减少/期末
 *   Tab3 摊销：累计摊销期初/本期摊销/摊销转出/期末/净值
 *   Tab4 减值：减值期初/计提/转回/期末
 *
 * 核心功能：
 * - Tab切换时保持行同步（activeRowIndex统一）
 * - 公式自动计算：
 *   · 期末原值 = 期初 + 增加 - 减少 (calcAssetEndBalance)
 *   · 累计摊销期末 = 期初 + 摊销 - 转出 (calcContraEndBalance)
 *   · 减值期末 = 期初 + 计提 - 转回 (calcContraEndBalance)
 *   · 净值 = 原值期末 - 摊销期末 - 减值期末 (calcNetValue)
 * - 合计行（不可编辑）：每列numeric SUM (calcSubtotal)
 * - 交叉验证：合计行 vs I1审定表小计（黄色警告）
 * - 动态行添加：ElMessageBox.prompt输入名称
 * - 导入导出三级（委托useI1ImportExport）
 * - 持久化：rows JSON → checklist_responses item_id "I1-2-rows"
 *
 * Spec: .kiro/specs/i1-intangible-assets/
 * Task: 3.4
 * Requirements: 3.1-3.7
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import type { ChecklistItem } from './useI1FormData'
import {
  calcAssetEndBalance,
  calcContraEndBalance,
  calcNetValue,
  calcSubtotal,
} from './useI1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** I1-2 明细行完整结构（56列拆分到4区段） */
export interface I1DetailRow {
  rowId: string

  // ── Tab1 基础信息 ──
  category: string              // 资产分类（专利权/商标权/著作权/土地使用权/软件/非专利技术/特许经营权/其他）
  name: string                  // 资产名称
  acquisitionDate: string       // 取得日期（YYYY-MM-DD）
  usefulLifeMonths: number      // 使用寿命（月），0=不确定
  salvageRate: number           // 残值率（0~1）
  amortizationMethod: string    // 摊销方法（直线法/剩余年限法/产量法）

  // ── Tab2 原值变动 ──
  costBegin: number             // 原值期初
  costIncrease: number          // 原值增加
  costDecrease: number          // 原值减少
  costEnd: number               // 原值期末（公式：期初+增加-减少）

  // ── Tab3 摊销 ──
  accAmortBegin: number         // 累计摊销期初
  amortProvision: number        // 本期摊销
  amortTransferOut: number      // 摊销转出
  accAmortEnd: number           // 累计摊销期末（公式：期初+摊销-转出）
  netValue: number              // 净值（公式：原值期末-摊销期末-减值期末）

  // ── Tab4 减值 ──
  impairmentBegin: number       // 减值期初
  impairmentProvision: number   // 本期计提
  impairmentReversal: number    // 本期转回
  impairmentEnd: number         // 减值期末（公式：期初+计提-转回）
}

/** 4区段Tab枚举 */
export type I1DetailTab = 'basic' | 'cost' | 'amort' | 'impairment'

/** 合计行结构（所有numeric列的SUM） */
export interface I1DetailSummary {
  costBegin: number
  costIncrease: number
  costDecrease: number
  costEnd: number
  accAmortBegin: number
  amortProvision: number
  amortTransferOut: number
  accAmortEnd: number
  netValue: number
  impairmentBegin: number
  impairmentProvision: number
  impairmentReversal: number
  impairmentEnd: number
}

/** 交叉验证结果（与I1审定表对比） */
export interface I1DetailCrossValidation {
  costDiff: number              // 原值期末合计 vs 审定表原值小计
  amortDiff: number             // 摊销期末合计 vs 审定表摊销小计
  impairDiff: number            // 减值期末合计 vs 审定表减值小计
  hasCostWarning: boolean
  hasAmortWarning: boolean
  hasImpairWarning: boolean
  hasAnyWarning: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'I1-2-rows'

const DEFAULT_CATEGORIES = [
  '专利权', '商标权', '著作权', '土地使用权', '软件', '非专利技术', '特许经营权', '其他',
]

const DEFAULT_AMORTIZATION_METHOD = '直线法'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI1Detail(
  wpId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    /** 审定表三科目小计（用于交叉验证） */
    adjCostSubtotal?: Ref<number>
    adjAmortSubtotal?: Ref<number>
    adjImpairSubtotal?: Ref<number>
    /** 保存回调 */
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  /** 明细行数据 */
  const rows = ref<I1DetailRow[]>([])

  /** 当前激活的区段Tab */
  const activeTab = ref<I1DetailTab>('basic')

  /** 当前选中行索引（跨Tab同步） */
  const activeRowIndex = ref<number>(-1)

  // ─── Load from allResponses ────────────────────────────────────────────────

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion
    if (!raw) {
      rows.value = []
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) {
        rows.value = parsed.map(_normalizeRow)
      } else {
        rows.value = []
      }
    } catch {
      rows.value = []
    }
  }

  function _normalizeRow(raw: any): I1DetailRow {
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      // Tab1 基础信息
      category: raw.category ?? '',
      name: raw.name ?? '',
      acquisitionDate: raw.acquisitionDate ?? '',
      usefulLifeMonths: Number(raw.usefulLifeMonths) || 0,
      salvageRate: Number(raw.salvageRate) || 0,
      amortizationMethod: raw.amortizationMethod ?? DEFAULT_AMORTIZATION_METHOD,
      // Tab2 原值变动
      costBegin: Number(raw.costBegin) || 0,
      costIncrease: Number(raw.costIncrease) || 0,
      costDecrease: Number(raw.costDecrease) || 0,
      costEnd: Number(raw.costEnd) || 0,
      // Tab3 摊销
      accAmortBegin: Number(raw.accAmortBegin) || 0,
      amortProvision: Number(raw.amortProvision) || 0,
      amortTransferOut: Number(raw.amortTransferOut) || 0,
      accAmortEnd: Number(raw.accAmortEnd) || 0,
      netValue: Number(raw.netValue) || 0,
      // Tab4 减值
      impairmentBegin: Number(raw.impairmentBegin) || 0,
      impairmentProvision: Number(raw.impairmentProvision) || 0,
      impairmentReversal: Number(raw.impairmentReversal) || 0,
      impairmentEnd: Number(raw.impairmentEnd) || 0,
    }
  }

  // ─── Formula Recalculation ─────────────────────────────────────────────────

  /**
   * 对指定行重算所有公式列：
   * - costEnd = costBegin + costIncrease - costDecrease (资产类借方1701)
   * - accAmortEnd = accAmortBegin + amortProvision - amortTransferOut (备抵类贷方1702)
   * - impairmentEnd = impairmentBegin + impairmentProvision - impairmentReversal (备抵类贷方1703)
   * - netValue = costEnd - accAmortEnd - impairmentEnd
   */
  function _recalcRow(row: I1DetailRow): void {
    // 原值期末 = 期初 + 增加 - 减少（资产类借方：begin + debit - credit）
    row.costEnd = calcAssetEndBalance(row.costBegin, row.costIncrease, row.costDecrease)
    // 累计摊销期末 = 期初 + 本期摊销(贷方) - 转出(借方)（备抵类：begin + credit - debit）
    row.accAmortEnd = calcContraEndBalance(row.accAmortBegin, row.amortTransferOut, row.amortProvision)
    // 减值期末 = 期初 + 计提(贷方) - 转回(借方)（备抵类：begin + credit - debit）
    row.impairmentEnd = calcContraEndBalance(row.impairmentBegin, row.impairmentReversal, row.impairmentProvision)
    // 净值 = 原值期末 - 摊销期末 - 减值期末
    row.netValue = calcNetValue(row.costEnd, row.accAmortEnd, row.impairmentEnd)
  }

  /** 对所有行重算公式 */
  function recalcAll(): void {
    for (const row of rows.value) {
      _recalcRow(row)
    }
  }

  // ─── Computed: 合计行（不可编辑）──────────────────────────────────────────

  /** 合计行：所有numeric列的SUM */
  const summaryRow: ComputedRef<I1DetailSummary> = computed(() => {
    const r = rows.value
    return {
      costBegin: calcSubtotal(r.map((x) => x.costBegin)),
      costIncrease: calcSubtotal(r.map((x) => x.costIncrease)),
      costDecrease: calcSubtotal(r.map((x) => x.costDecrease)),
      costEnd: calcSubtotal(r.map((x) => x.costEnd)),
      accAmortBegin: calcSubtotal(r.map((x) => x.accAmortBegin)),
      amortProvision: calcSubtotal(r.map((x) => x.amortProvision)),
      amortTransferOut: calcSubtotal(r.map((x) => x.amortTransferOut)),
      accAmortEnd: calcSubtotal(r.map((x) => x.accAmortEnd)),
      netValue: calcSubtotal(r.map((x) => x.netValue)),
      impairmentBegin: calcSubtotal(r.map((x) => x.impairmentBegin)),
      impairmentProvision: calcSubtotal(r.map((x) => x.impairmentProvision)),
      impairmentReversal: calcSubtotal(r.map((x) => x.impairmentReversal)),
      impairmentEnd: calcSubtotal(r.map((x) => x.impairmentEnd)),
    }
  })

  // ─── Computed: 交叉验证（Req 3.4 & 3.5）────────────────────────────────

  /**
   * 交叉验证：明细表合计行 vs I1审定表三科目小计。
   * 当差异绝对值 > 0.01 时显示黄色警告。
   */
  const crossValidation: ComputedRef<I1DetailCrossValidation> = computed(() => {
    const adjCost = options?.adjCostSubtotal?.value ?? 0
    const adjAmort = options?.adjAmortSubtotal?.value ?? 0
    const adjImpair = options?.adjImpairSubtotal?.value ?? 0

    const costDiff = summaryRow.value.costEnd - adjCost
    const amortDiff = summaryRow.value.accAmortEnd - adjAmort
    const impairDiff = summaryRow.value.impairmentEnd - adjImpair

    const hasCostWarning = Math.abs(costDiff) > 0.01
    const hasAmortWarning = Math.abs(amortDiff) > 0.01
    const hasImpairWarning = Math.abs(impairDiff) > 0.01

    return {
      costDiff,
      amortDiff,
      impairDiff,
      hasCostWarning,
      hasAmortWarning,
      hasImpairWarning,
      hasAnyWarning: hasCostWarning || hasAmortWarning || hasImpairWarning,
    }
  })

  // ─── Tab 切换 + 行同步 ─────────────────────────────────────────────────────

  /**
   * 切换区段Tab，保持行同步（Req 3.2）。
   * activeRowIndex 不重置，确保切换Tab后高亮行不变。
   */
  function switchTab(tab: I1DetailTab): void {
    activeTab.value = tab
  }

  /** 设置当前选中行 */
  function setActiveRow(index: number): void {
    activeRowIndex.value = index
  }

  // ─── updateCell: 编辑单元格 ────────────────────────────────────────────────

  /**
   * 更新明细表某行某字段值，自动重算公式列，并持久化。
   */
  function updateCell(
    rowIndex: number,
    field: keyof I1DetailRow,
    value: string | number,
  ): void {
    const row = rows.value[rowIndex]
    if (!row) return

    // 设置值
    ;(row as any)[field] = value

    // 重算公式列
    _recalcRow(row)

    // 持久化
    _persist()
  }

  // ─── addRow: 动态行添加（Req 3.6）─────────────────────────────────────────

  /**
   * 添加动态行：先弹 ElMessageBox.prompt 输入资产名称确认后创建。
   * Req 3.6: 动态行添加弹ElMessageBox.prompt输入名称。
   */
  async function addRow(defaultCategory?: string): Promise<I1DetailRow | null> {
    try {
      const { value: name } = await ElMessageBox.prompt(
        '请输入无形资产名称',
        '新增明细行',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '例如：XXX专利权',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '名称不能为空'
            return true
          },
        },
      )

      if (!name?.trim()) return null

      const newRow: I1DetailRow = {
        rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        category: defaultCategory ?? '',
        name: name.trim(),
        acquisitionDate: '',
        usefulLifeMonths: 0,
        salvageRate: 0,
        amortizationMethod: DEFAULT_AMORTIZATION_METHOD,
        costBegin: 0,
        costIncrease: 0,
        costDecrease: 0,
        costEnd: 0,
        accAmortBegin: 0,
        amortProvision: 0,
        amortTransferOut: 0,
        accAmortEnd: 0,
        netValue: 0,
        impairmentBegin: 0,
        impairmentProvision: 0,
        impairmentReversal: 0,
        impairmentEnd: 0,
      }

      rows.value.push(newRow)
      activeRowIndex.value = rows.value.length - 1
      _persist()
      return newRow
    } catch {
      // 用户取消
      return null
    }
  }

  // ─── removeRow: 删除行 ─────────────────────────────────────────────────────

  function removeRow(rowIndex: number): void {
    if (rowIndex < 0 || rowIndex >= rows.value.length) return
    rows.value.splice(rowIndex, 1)
    // 修正 activeRowIndex
    if (activeRowIndex.value >= rows.value.length) {
      activeRowIndex.value = rows.value.length - 1
    }
    _persist()
  }

  // ─── moveRow: 行上移/下移 ──────────────────────────────────────────────────

  function moveRowUp(rowIndex: number): void {
    if (rowIndex <= 0 || rowIndex >= rows.value.length) return
    const temp = rows.value[rowIndex]
    rows.value[rowIndex] = rows.value[rowIndex - 1]
    rows.value[rowIndex - 1] = temp
    activeRowIndex.value = rowIndex - 1
    _persist()
  }

  function moveRowDown(rowIndex: number): void {
    if (rowIndex < 0 || rowIndex >= rows.value.length - 1) return
    const temp = rows.value[rowIndex]
    rows.value[rowIndex] = rows.value[rowIndex + 1]
    rows.value[rowIndex + 1] = temp
    activeRowIndex.value = rowIndex + 1
    _persist()
  }

  // ─── importRows: 导入行数据（供 useI1ImportExport 调用）────────────────────

  /**
   * 批量导入行数据（覆盖现有行），自动重算公式并持久化。
   * Req 3.7: 支持导入导出三级。
   */
  function importRows(importedRows: Partial<I1DetailRow>[]): void {
    rows.value = importedRows.map((raw) => {
      const row = _normalizeRow(raw)
      _recalcRow(row)
      return row
    })
    activeRowIndex.value = rows.value.length > 0 ? 0 : -1
    _persist()
  }

  /** 获取当前行数据（供导出使用） */
  function exportRows(): I1DetailRow[] {
    return [...rows.value]
  }

  // ─── getTabColumns: 4区段Tab列配置 ─────────────────────────────────────────

  /** Tab1 基础信息列定义 */
  const basicColumns = [
    { key: 'category', label: '资产分类', width: 120, editable: true, type: 'select' as const, options: DEFAULT_CATEGORIES },
    { key: 'name', label: '资产名称', width: 180, editable: true, type: 'text' as const },
    { key: 'acquisitionDate', label: '取得日期', width: 120, editable: true, type: 'date' as const },
    { key: 'usefulLifeMonths', label: '使用寿命(月)', width: 110, editable: true, type: 'number' as const },
    { key: 'salvageRate', label: '残值率', width: 90, editable: true, type: 'number' as const },
    { key: 'amortizationMethod', label: '摊销方法', width: 120, editable: true, type: 'select' as const, options: ['直线法', '剩余年限法', '产量法'] },
  ]

  /** Tab2 原值变动列定义 */
  const costColumns = [
    { key: 'name', label: '资产名称', width: 180, editable: false, type: 'text' as const },
    { key: 'costBegin', label: '期初原值', width: 130, editable: true, type: 'number' as const },
    { key: 'costIncrease', label: '本期增加', width: 130, editable: true, type: 'number' as const },
    { key: 'costDecrease', label: '本期减少', width: 130, editable: true, type: 'number' as const },
    { key: 'costEnd', label: '期末原值', width: 130, editable: false, type: 'formula' as const, tooltip: '期末=期初+增加-减少' },
  ]

  /** Tab3 摊销列定义 */
  const amortColumns = [
    { key: 'name', label: '资产名称', width: 180, editable: false, type: 'text' as const },
    { key: 'costEnd', label: '摊销原值', width: 130, editable: false, type: 'formula' as const, tooltip: '摊销原值=原值期末（摊销计算基数），来源"原值变动"区段' },
    { key: 'accAmortBegin', label: '摊销期初', width: 130, editable: true, type: 'number' as const },
    { key: 'amortProvision', label: '本期摊销', width: 130, editable: true, type: 'number' as const },
    { key: 'amortTransferOut', label: '摊销转出', width: 130, editable: true, type: 'number' as const },
    { key: 'accAmortEnd', label: '摊销期末', width: 130, editable: false, type: 'formula' as const, tooltip: '期末=期初+摊销-转出' },
    { key: 'netValue', label: '净值', width: 130, editable: false, type: 'formula' as const, tooltip: '净值=原值期末-摊销期末-减值期末' },
  ]

  /** Tab4 减值列定义 */
  const impairmentColumns = [
    { key: 'name', label: '资产名称', width: 180, editable: false, type: 'text' as const },
    { key: 'impairmentBegin', label: '减值期初', width: 130, editable: true, type: 'number' as const },
    { key: 'impairmentProvision', label: '本期计提', width: 130, editable: true, type: 'number' as const },
    { key: 'impairmentReversal', label: '本期转回', width: 130, editable: true, type: 'number' as const },
    { key: 'impairmentEnd', label: '减值期末', width: 130, editable: false, type: 'formula' as const, tooltip: '期末=期初+计提-转回' },
  ]

  /** 4区段Tab定义 */
  const tabs = [
    { key: 'basic' as I1DetailTab, label: '基础信息', columns: basicColumns },
    { key: 'cost' as I1DetailTab, label: '原值变动', columns: costColumns },
    { key: 'amort' as I1DetailTab, label: '摊销', columns: amortColumns },
    { key: 'impairment' as I1DetailTab, label: '减值', columns: impairmentColumns },
  ]

  /** 当前Tab对应的列配置 */
  const activeColumns = computed(() => {
    return tabs.find((t) => t.key === activeTab.value)?.columns ?? basicColumns
  })

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    options?.onSave?.(ITEM_ID_ROWS, rows.value)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    rows,
    activeTab,
    activeRowIndex,

    // Computed
    summaryRow,
    crossValidation,
    activeColumns,

    // Tab定义
    tabs,
    basicColumns,
    costColumns,
    amortColumns,
    impairmentColumns,

    // Actions — Tab & Row同步
    switchTab,
    setActiveRow,

    // Actions — Cell编辑
    updateCell,
    recalcAll,

    // Actions — 动态行
    addRow,
    removeRow,
    moveRowUp,
    moveRowDown,

    // Actions — 导入导出
    importRows,
    exportRows,
  }
}

export default useI1Detail
