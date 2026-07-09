/**
 * useI3Detail — I3-2 商誉明细表 composable（30列3区段Tab）
 *
 * 30列宽表拆分为3区段Tab：
 *   Section 0 "基础"：被投资单位/并购日期/对价/被购方净资产/持股比例/控制类型/合并方式/股权层级/所属行业/备注
 *   Section 1 "入账"：合并成本/可辨认净资产公允/商誉原值(公式)/少数股东权益/合并成本明细(对价+或有+交易费)/合并日期/评估基准日/评估方法/评估增值率/入账备注
 *   Section 2 "减值"：累计减值期初/本期减值/累计减值期末/商誉净值(公式)/所属CGU/可收回金额/减值测试日/测试方法/减值迹象/减值备注
 *
 * 核心功能：
 * - Tab切换时保持行同步（activeRowIndex统一）
 * - 公式自动计算：
 *   · 商誉原值 = 合并成本 - 可辨认净资产公允价值 (calcInitialGoodwill)
 *   · 累计减值期末 = 累计减值期初 + 本期减值
 *   · 商誉净值 = 商誉原值 - 累计减值期末 (calcGoodwillNetValue)
 * - 合计行（不可编辑）：每列numeric SUM (calcSubtotal)
 * - 交叉验证：合计行 vs I3-1审定表小计（黄色警告）
 * - 动态行添加：ElMessageBox.prompt输入被投资单位名称
 * - 持久化：rows JSON → checklist_responses item_id "I3-2-rows"
 *
 * Spec: .kiro/specs/i3-goodwill/
 * Task: 3.4
 * Requirements: 3.1-3.4
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import type { ChecklistItem } from './useI3FormData'
import {
  calcInitialGoodwill,
  calcGoodwillNetValue,
  calcSubtotal,
} from './useI3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** I3-2 明细行完整结构（30列拆分到3区段） */
export interface I3DetailRow {
  rowId: string

  // ── Section 0 基础信息 ──
  investee: string                // 被投资单位名称
  acquisitionDate: string         // 并购日期（YYYY-MM-DD）
  consideration: number           // 对价
  counterpartyNetAsset: number    // 被购方净资产
  shareholding: number            // 持股比例（0~1）
  controlType: string             // 控制类型（控制/共同控制/重大影响）
  mergerType: string              // 合并方式（非同一控制/同一控制）
  equityLevel: string             // 股权层级（直接/间接）
  industry: string                // 所属行业
  basicRemark: string             // 基础备注

  // ── Section 1 入账信息 ──
  mergerCost: number              // 合并成本
  netAssetFairValue: number       // 可辨认净资产公允价值
  goodwillOriginal: number        // 商誉原值（公式：合并成本 - 可辨认净资产公允）
  minorityInterest: number        // 少数股东权益
  costConsideration: number       // 对价金额（合并成本明细）
  costContingent: number          // 或有对价
  costTransactionFee: number      // 交易费用
  mergerDate: string              // 合并日期
  valuationBaseDate: string       // 评估基准日
  valuationMethod: string         // 评估方法（收益法/市场法/成本法）
  valuationAppreciation: number   // 评估增值率
  entryRemark: string             // 入账备注

  // ── Section 2 减值信息 ──
  accImpairmentBegin: number      // 累计减值期初
  currentImpairment: number       // 本期减值
  accImpairmentEnd: number        // 累计减值期末（公式：期初 + 本期）
  goodwillNetValue: number        // 商誉净值（公式：原值 - 累计减值期末）
  cguName: string                 // 所属CGU（资产组）
  recoverableAmount: number       // 可收回金额
  impairmentTestDate: string      // 减值测试日
  impairmentTestMethod: string    // 测试方法（DCF/市场法）
  impairmentIndicator: string     // 减值迹象（是/否/待定）
  impairmentRemark: string        // 减值备注
}

/** 3区段Tab索引 */
export type I3DetailSection = 0 | 1 | 2

/** 3区段Tab标签 */
export const I3_DETAIL_SECTION_LABELS = ['基础', '入账', '减值'] as const

/** 合计行结构（所有numeric列的SUM） */
export interface I3DetailSummary {
  // Section 0
  consideration: number
  counterpartyNetAsset: number
  // Section 1
  mergerCost: number
  netAssetFairValue: number
  goodwillOriginal: number
  minorityInterest: number
  costConsideration: number
  costContingent: number
  costTransactionFee: number
  valuationAppreciation: number
  // Section 2
  accImpairmentBegin: number
  currentImpairment: number
  accImpairmentEnd: number
  goodwillNetValue: number
  recoverableAmount: number
}

/** 交叉验证结果（与I3-1审定表对比） */
export interface I3DetailCrossValidation {
  goodwillOriginalDiff: number     // 商誉原值合计 vs 审定表初始确认小计
  accImpairmentDiff: number        // 累计减值合计 vs 审定表累计减值小计
  netValueDiff: number             // 净值合计 vs 审定表净额小计
  hasOriginalWarning: boolean
  hasImpairmentWarning: boolean
  hasNetValueWarning: boolean
  hasAnyWarning: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'I3-2-rows'

const CONTROL_TYPE_OPTIONS = ['控制', '共同控制', '重大影响']
const MERGER_TYPE_OPTIONS = ['非同一控制', '同一控制']
const EQUITY_LEVEL_OPTIONS = ['直接', '间接']
const VALUATION_METHOD_OPTIONS = ['收益法', '市场法', '成本法']
const IMPAIRMENT_TEST_METHOD_OPTIONS = ['DCF', '市场法']
const IMPAIRMENT_INDICATOR_OPTIONS = ['是', '否', '待定']

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI3Detail(
  wpId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    /** 审定表小计（用于交叉验证） */
    adjGoodwillOriginalSubtotal?: Ref<number>
    adjAccImpairmentSubtotal?: Ref<number>
    adjNetValueSubtotal?: Ref<number>
    /** 保存回调 */
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  /** 明细行数据 */
  const rows = ref<I3DetailRow[]>([])

  /** 当前激活的区段Tab（0=基础, 1=入账, 2=减值） */
  const activeSection = ref<I3DetailSection>(0)

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

  function _normalizeRow(raw: any): I3DetailRow {
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      // Section 0 基础
      investee: raw.investee ?? '',
      acquisitionDate: raw.acquisitionDate ?? '',
      consideration: Number(raw.consideration) || 0,
      counterpartyNetAsset: Number(raw.counterpartyNetAsset) || 0,
      shareholding: Number(raw.shareholding) || 0,
      controlType: raw.controlType ?? '',
      mergerType: raw.mergerType ?? '',
      equityLevel: raw.equityLevel ?? '',
      industry: raw.industry ?? '',
      basicRemark: raw.basicRemark ?? '',
      // Section 1 入账
      mergerCost: Number(raw.mergerCost) || 0,
      netAssetFairValue: Number(raw.netAssetFairValue) || 0,
      goodwillOriginal: Number(raw.goodwillOriginal) || 0,
      minorityInterest: Number(raw.minorityInterest) || 0,
      costConsideration: Number(raw.costConsideration) || 0,
      costContingent: Number(raw.costContingent) || 0,
      costTransactionFee: Number(raw.costTransactionFee) || 0,
      mergerDate: raw.mergerDate ?? '',
      valuationBaseDate: raw.valuationBaseDate ?? '',
      valuationMethod: raw.valuationMethod ?? '',
      valuationAppreciation: Number(raw.valuationAppreciation) || 0,
      entryRemark: raw.entryRemark ?? '',
      // Section 2 减值
      accImpairmentBegin: Number(raw.accImpairmentBegin) || 0,
      currentImpairment: Number(raw.currentImpairment) || 0,
      accImpairmentEnd: Number(raw.accImpairmentEnd) || 0,
      goodwillNetValue: Number(raw.goodwillNetValue) || 0,
      cguName: raw.cguName ?? '',
      recoverableAmount: Number(raw.recoverableAmount) || 0,
      impairmentTestDate: raw.impairmentTestDate ?? '',
      impairmentTestMethod: raw.impairmentTestMethod ?? '',
      impairmentIndicator: raw.impairmentIndicator ?? '',
      impairmentRemark: raw.impairmentRemark ?? '',
    }
  }

  // ─── Formula Recalculation ─────────────────────────────────────────────────

  /**
   * 对指定行重算所有公式列（12公式覆盖）：
   * - goodwillOriginal = mergerCost - netAssetFairValue (calcInitialGoodwill)
   * - accImpairmentEnd = accImpairmentBegin + currentImpairment
   * - goodwillNetValue = goodwillOriginal - accImpairmentEnd (calcGoodwillNetValue)
   *
   * 商誉不摊销！净值仅受减值影响。
   * 商誉减值不可转回：currentImpairment 不允许负数。
   */
  function _recalcRow(row: I3DetailRow): void {
    // 商誉原值 = 合并成本 - 可辨认净资产公允价值
    row.goodwillOriginal = calcInitialGoodwill(row.mergerCost, row.netAssetFairValue)
    // 累计减值期末 = 期初 + 本期减值（商誉减值不可转回，clamp≥0）
    const clampedImpairment = Math.max(0, row.currentImpairment)
    row.accImpairmentEnd = row.accImpairmentBegin + clampedImpairment
    // 商誉净值 = 原值 - 累计减值期末（无摊销！）
    row.goodwillNetValue = calcGoodwillNetValue(row.goodwillOriginal, row.accImpairmentEnd)
  }

  /** 对所有行重算公式 */
  function recalcAll(): void {
    for (const row of rows.value) {
      _recalcRow(row)
    }
  }

  // ─── Computed: 合计行（不可编辑）──────────────────────────────────────────

  /** 合计行：所有numeric列的SUM（Req 3.3 合计行联动审定表） */
  const summaryRow: ComputedRef<I3DetailSummary> = computed(() => {
    const r = rows.value
    return {
      // Section 0
      consideration: calcSubtotal(r.map((x) => x.consideration)),
      counterpartyNetAsset: calcSubtotal(r.map((x) => x.counterpartyNetAsset)),
      // Section 1
      mergerCost: calcSubtotal(r.map((x) => x.mergerCost)),
      netAssetFairValue: calcSubtotal(r.map((x) => x.netAssetFairValue)),
      goodwillOriginal: calcSubtotal(r.map((x) => x.goodwillOriginal)),
      minorityInterest: calcSubtotal(r.map((x) => x.minorityInterest)),
      costConsideration: calcSubtotal(r.map((x) => x.costConsideration)),
      costContingent: calcSubtotal(r.map((x) => x.costContingent)),
      costTransactionFee: calcSubtotal(r.map((x) => x.costTransactionFee)),
      valuationAppreciation: 0, // 增值率不做SUM
      // Section 2
      accImpairmentBegin: calcSubtotal(r.map((x) => x.accImpairmentBegin)),
      currentImpairment: calcSubtotal(r.map((x) => x.currentImpairment)),
      accImpairmentEnd: calcSubtotal(r.map((x) => x.accImpairmentEnd)),
      goodwillNetValue: calcSubtotal(r.map((x) => x.goodwillNetValue)),
      recoverableAmount: calcSubtotal(r.map((x) => x.recoverableAmount)),
    }
  })

  // ─── Computed: 交叉验证（Req 3.3 合计行联动审定表）─────────────────────────

  /**
   * 交叉验证：明细表合计行 vs I3-1审定表小计。
   * 对比项：商誉原值合计/累计减值合计/净值合计。
   * 差异绝对值 > 0.01 时显示黄色警告。
   */
  const crossValidation: ComputedRef<I3DetailCrossValidation> = computed(() => {
    const adjOriginal = options?.adjGoodwillOriginalSubtotal?.value ?? 0
    const adjImpairment = options?.adjAccImpairmentSubtotal?.value ?? 0
    const adjNetValue = options?.adjNetValueSubtotal?.value ?? 0

    const goodwillOriginalDiff = summaryRow.value.goodwillOriginal - adjOriginal
    const accImpairmentDiff = summaryRow.value.accImpairmentEnd - adjImpairment
    const netValueDiff = summaryRow.value.goodwillNetValue - adjNetValue

    const hasOriginalWarning = Math.abs(goodwillOriginalDiff) > 0.01
    const hasImpairmentWarning = Math.abs(accImpairmentDiff) > 0.01
    const hasNetValueWarning = Math.abs(netValueDiff) > 0.01

    return {
      goodwillOriginalDiff,
      accImpairmentDiff,
      netValueDiff,
      hasOriginalWarning,
      hasImpairmentWarning,
      hasNetValueWarning,
      hasAnyWarning: hasOriginalWarning || hasImpairmentWarning || hasNetValueWarning,
    }
  })

  // ─── Section 切换 + 行同步 ─────────────────────────────────────────────────

  /**
   * 切换区段Tab，保持行同步（Req 3.1 3区段Tab）。
   * activeRowIndex 不重置，确保切换Tab后高亮行不变。
   */
  function switchSection(section: I3DetailSection): void {
    activeSection.value = section
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
    field: keyof I3DetailRow,
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

  // ─── addRow: 动态行添加（Req 3.4）─────────────────────────────────────────

  /**
   * 添加动态行：先弹 ElMessageBox.prompt 输入被投资单位名称确认后创建。
   * Req 3.4: 动态行弹ElMessageBox输入被投资单位名称。
   */
  async function addRow(): Promise<I3DetailRow | null> {
    try {
      const { value: name } = await ElMessageBox.prompt(
        '请输入被投资单位名称',
        '新增商誉明细行',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '例如：XX科技有限公司',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '被投资单位名称不能为空'
            return true
          },
        },
      )

      if (!name?.trim()) return null

      const newRow: I3DetailRow = {
        rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        // Section 0
        investee: name.trim(),
        acquisitionDate: '',
        consideration: 0,
        counterpartyNetAsset: 0,
        shareholding: 0,
        controlType: '',
        mergerType: '非同一控制',
        equityLevel: '直接',
        industry: '',
        basicRemark: '',
        // Section 1
        mergerCost: 0,
        netAssetFairValue: 0,
        goodwillOriginal: 0,
        minorityInterest: 0,
        costConsideration: 0,
        costContingent: 0,
        costTransactionFee: 0,
        mergerDate: '',
        valuationBaseDate: '',
        valuationMethod: '',
        valuationAppreciation: 0,
        entryRemark: '',
        // Section 2
        accImpairmentBegin: 0,
        currentImpairment: 0,
        accImpairmentEnd: 0,
        goodwillNetValue: 0,
        cguName: '',
        recoverableAmount: 0,
        impairmentTestDate: '',
        impairmentTestMethod: '',
        impairmentIndicator: '',
        impairmentRemark: '',
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

  // ─── importRows / exportRows（供 useI3ImportExport 调用）───────────────────

  /**
   * 批量导入行数据（覆盖现有行），自动重算公式并持久化。
   */
  function importRows(importedRows: Partial<I3DetailRow>[]): void {
    rows.value = importedRows.map((raw) => {
      const row = _normalizeRow(raw)
      _recalcRow(row)
      return row
    })
    activeRowIndex.value = rows.value.length > 0 ? 0 : -1
    _persist()
  }

  /** 获取当前行数据（供导出使用） */
  function exportRows(): I3DetailRow[] {
    return [...rows.value]
  }

  // ─── getSectionColumns: 3区段Tab列配置 ─────────────────────────────────────

  /** Section 0 基础信息列定义（10列） */
  const basicColumns = [
    { key: 'investee', label: '被投资单位', width: 180, editable: true, type: 'text' as const },
    { key: 'acquisitionDate', label: '并购日期', width: 120, editable: true, type: 'date' as const },
    { key: 'consideration', label: '对价', width: 130, editable: true, type: 'number' as const },
    { key: 'counterpartyNetAsset', label: '被购方净资产', width: 130, editable: true, type: 'number' as const },
    { key: 'shareholding', label: '持股比例', width: 100, editable: true, type: 'number' as const },
    { key: 'controlType', label: '控制类型', width: 120, editable: true, type: 'select' as const, options: CONTROL_TYPE_OPTIONS },
    { key: 'mergerType', label: '合并方式', width: 120, editable: true, type: 'select' as const, options: MERGER_TYPE_OPTIONS },
    { key: 'equityLevel', label: '股权层级', width: 100, editable: true, type: 'select' as const, options: EQUITY_LEVEL_OPTIONS },
    { key: 'industry', label: '所属行业', width: 120, editable: true, type: 'text' as const },
    { key: 'basicRemark', label: '备注', width: 150, editable: true, type: 'text' as const },
  ]

  /** Section 1 入账信息列定义（12列，含1公式列） */
  const entryColumns = [
    { key: 'investee', label: '被投资单位', width: 180, editable: false, type: 'text' as const },
    { key: 'mergerCost', label: '合并成本', width: 130, editable: true, type: 'number' as const },
    { key: 'netAssetFairValue', label: '可辨认净资产公允', width: 150, editable: true, type: 'number' as const },
    { key: 'goodwillOriginal', label: '商誉原值', width: 130, editable: false, type: 'formula' as const, tooltip: '商誉原值=合并成本-可辨认净资产公允价值' },
    { key: 'minorityInterest', label: '少数股东权益', width: 130, editable: true, type: 'number' as const },
    { key: 'costConsideration', label: '对价金额', width: 120, editable: true, type: 'number' as const },
    { key: 'costContingent', label: '或有对价', width: 120, editable: true, type: 'number' as const },
    { key: 'costTransactionFee', label: '交易费用', width: 120, editable: true, type: 'number' as const },
    { key: 'mergerDate', label: '合并日期', width: 120, editable: true, type: 'date' as const },
    { key: 'valuationBaseDate', label: '评估基准日', width: 120, editable: true, type: 'date' as const },
    { key: 'valuationMethod', label: '评估方法', width: 110, editable: true, type: 'select' as const, options: VALUATION_METHOD_OPTIONS },
    { key: 'valuationAppreciation', label: '评估增值率', width: 110, editable: true, type: 'number' as const },
  ]

  /** Section 2 减值信息列定义（10列，含2公式列） */
  const impairmentColumns = [
    { key: 'investee', label: '被投资单位', width: 180, editable: false, type: 'text' as const },
    { key: 'accImpairmentBegin', label: '累计减值期初', width: 130, editable: true, type: 'number' as const },
    { key: 'currentImpairment', label: '本期减值', width: 120, editable: true, type: 'number' as const },
    { key: 'accImpairmentEnd', label: '累计减值期末', width: 130, editable: false, type: 'formula' as const, tooltip: '累计减值期末=期初+本期减值' },
    { key: 'goodwillNetValue', label: '商誉净值', width: 130, editable: false, type: 'formula' as const, tooltip: '商誉净值=商誉原值-累计减值期末（不摊销！）' },
    { key: 'cguName', label: '所属CGU', width: 150, editable: true, type: 'text' as const },
    { key: 'recoverableAmount', label: '可收回金额', width: 130, editable: true, type: 'number' as const },
    { key: 'impairmentTestDate', label: '减值测试日', width: 120, editable: true, type: 'date' as const },
    { key: 'impairmentTestMethod', label: '测试方法', width: 110, editable: true, type: 'select' as const, options: IMPAIRMENT_TEST_METHOD_OPTIONS },
    { key: 'impairmentIndicator', label: '减值迹象', width: 100, editable: true, type: 'select' as const, options: IMPAIRMENT_INDICATOR_OPTIONS },
  ]

  /** 3区段Tab定义 */
  const sections = [
    { key: 0 as I3DetailSection, label: '基础', columns: basicColumns },
    { key: 1 as I3DetailSection, label: '入账', columns: entryColumns },
    { key: 2 as I3DetailSection, label: '减值', columns: impairmentColumns },
  ]

  /** 当前Section对应的列配置 */
  const activeColumns = computed(() => {
    return sections.find((s) => s.key === activeSection.value)?.columns ?? basicColumns
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
    activeSection,
    activeRowIndex,

    // Computed
    summaryRow,
    crossValidation,
    activeColumns,

    // Section定义
    sections,
    basicColumns,
    entryColumns,
    impairmentColumns,

    // Actions — Section & Row同步
    switchSection,
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

export default useI3Detail
