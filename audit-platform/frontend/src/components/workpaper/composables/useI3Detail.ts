/**
 * useI3Detail — I3-2 商誉明细表（对齐致同 Excel 双表滚动）
 *
 * Excel 结构：
 *   左表「商誉明细表（原值）」：期初→本期增加→本期减少→期末→未审→账项调整→审定
 *   右表「商誉明细表（减值准备）」：同上滚动
 *   净值 = 原值审定期末 − 减值准备审定期末（商誉不摊销）
 *
 * HTML 区段：
 *   0 原值滚动 | 1 减值滚动 | 2 入账测算 | 3 基础信息
 *
 * 兼容：保留 goodwillOriginal / accImpairment* / currentImpairment 等旧字段，
 * 供 I3-5 针对性检查、I3-1 交叉验证引用；由滚动公式回写。
 *
 * Spec: .kiro/specs/i3-goodwill/ Task 3.4
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

export interface I3DetailRow {
  rowId: string

  // ── 共用：被投资单位 ──
  investee: string

  // ── Section 0 原值滚动（Excel 左表）──
  costOpening: number
  costIncrease: number
  costIncreaseMethod: string
  costDecrease: number
  costDecreaseReason: string
  /** 公式：期初+增加-减少 */
  costEnding: number
  /** 未审期末（客户端） */
  costUnadj: number
  costAje: number
  /** 公式：未审+账项调整 */
  costAudited: number

  // ── Section 1 减值准备滚动（Excel 右表）──
  impOpening: number
  impIncrease: number
  impIncreaseMethod: string
  impDecrease: number
  impDecreaseReason: string
  /** 公式：期初+增加-减少 */
  impEnding: number
  impUnadj: number
  impAje: number
  /** 公式：未审+账项调整 */
  impAudited: number

  // ── Section 2 入账测算（对接 I3-4）──
  mergerCost: number
  netAssetFairValue: number
  /**
   * 入账测算商誉原值 = 合并成本 − 可辨认净资产公允份额
   * 非同一控制下用于核对 costIncrease / costAudited
   */
  entryGoodwillCalc: number
  minorityInterest: number
  costConsideration: number
  costContingent: number
  costTransactionFee: number
  mergerDate: string
  valuationBaseDate: string
  valuationMethod: string
  valuationAppreciation: number
  entryRemark: string

  // ── Section 3 基础信息 ──
  acquisitionDate: string
  consideration: number
  counterpartyNetAsset: number
  shareholding: number
  controlType: string
  mergerType: string
  equityLevel: string
  industry: string
  basicRemark: string
  cguName: string
  recoverableAmount: number
  impairmentTestDate: string
  impairmentTestMethod: string
  impairmentIndicator: string
  impairmentRemark: string

  // ── 兼容旧字段 / 跨表引用 ──
  /** = costAudited（供 I3-1 / I3-5） */
  goodwillOriginal: number
  /** = impOpening */
  accImpairmentBegin: number
  /** = impIncrease（本期计提；商誉不可转回） */
  currentImpairment: number
  /** = impAudited */
  accImpairmentEnd: number
  /** = costAudited − impAudited */
  goodwillNetValue: number
  /**
   * Excel 本期借方发生额（= costIncrease）
   * 供 I3-5 检查比例 / I3-1 发生额勾稽，与滚动「本期增加」同源
   */
  periodDebit: number
  /**
   * Excel 本期贷方发生额（= costDecrease + impIncrease）
   * 原值减少转出 + 本期减值计提
   */
  periodCredit: number
}

export type I3DetailSection = 0 | 1 | 2 | 3

export const I3_DETAIL_SECTION_LABELS = ['原值滚动', '减值滚动', '入账测算', '基础信息'] as const

export interface I3DetailSummary {
  costOpening: number
  costIncrease: number
  costDecrease: number
  costEnding: number
  costUnadj: number
  costAje: number
  costAudited: number
  impOpening: number
  impIncrease: number
  impDecrease: number
  impEnding: number
  impUnadj: number
  impAje: number
  impAudited: number
  /** Σ 本期借方发生额（= Σ costIncrease） */
  periodDebit: number
  /** Σ 本期贷方发生额（= Σ costDecrease + Σ impIncrease） */
  periodCredit: number
  mergerCost: number
  netAssetFairValue: number
  entryGoodwillCalc: number
  minorityInterest: number
  costConsideration: number
  costContingent: number
  costTransactionFee: number
  consideration: number
  counterpartyNetAsset: number
  // 兼容
  goodwillOriginal: number
  accImpairmentBegin: number
  currentImpairment: number
  accImpairmentEnd: number
  goodwillNetValue: number
  recoverableAmount: number
}

export interface I3DetailCrossValidation {
  goodwillOriginalDiff: number
  accImpairmentDiff: number
  netValueDiff: number
  hasOriginalWarning: boolean
  hasImpairmentWarning: boolean
  hasNetValueWarning: boolean
  hasAnyWarning: boolean
}

/** 单行滚动勾稽校验 */
export interface I3RollForwardCheck {
  rowId: string
  investee: string
  costOk: boolean
  costDiff: number
  impOk: boolean
  impDiff: number
  costAuditOk: boolean
  costAuditDiff: number
  impAuditOk: boolean
  impAuditDiff: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'I3-2-rows'

const CONTROL_TYPE_OPTIONS = ['控制', '共同控制', '重大影响']
const MERGER_TYPE_OPTIONS = ['非同一控制', '同一控制']
const EQUITY_LEVEL_OPTIONS = ['直接', '间接']
const VALUATION_METHOD_OPTIONS = ['收益法', '市场法', '成本法']
const IMPAIRMENT_TEST_METHOD_OPTIONS = ['DCF', '市场法']
const IMPAIRMENT_INDICATOR_OPTIONS = ['是', '否', '待定']
export const COST_INCREASE_METHODS = ['企业合并新增', '同一控制下企业合并', '其他增加', ''] as const
export const COST_DECREASE_REASONS = ['处置子公司', '丧失控制权', '其他减少', ''] as const
export const IMP_INCREASE_METHODS = ['本期计提', '企业合并带入', '其他增加', ''] as const
export const IMP_DECREASE_REASONS = ['处置转出', '其他减少', ''] as const

// ─── Pure helpers（导出供测试）───────────────────────────────────────────────

export function calcRollEnding(opening: number, increase: number, decrease: number): number {
  return opening + increase - decrease
}

export function calcAudited(unadj: number, aje: number): number {
  return unadj + aje
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI3Detail(
  wpId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    adjGoodwillOriginalSubtotal?: Ref<number>
    adjAccImpairmentSubtotal?: Ref<number>
    adjNetValueSubtotal?: Ref<number>
    onSave?: (itemId: string, value: any) => void
  },
) {
  const rows = ref<I3DetailRow[]>([])
  const activeSection = ref<I3DetailSection>(0)
  const activeRowIndex = ref<number>(-1)

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
        rows.value = parsed.map((r) => {
          const row = _normalizeRow(r)
          _recalcRow(row)
          return row
        })
      } else {
        rows.value = []
      }
    } catch {
      rows.value = []
    }
  }

  function _n(v: any): number {
    const n = Number(v)
    return Number.isFinite(n) ? n : 0
  }

  function _normalizeRow(raw: any): I3DetailRow {
    // 兼容旧数据：无滚动字段时从 accImpairment*/goodwillOriginal 回填
    const costOpening = raw.costOpening != null ? _n(raw.costOpening) : _n(raw.goodwillOriginal)
    const costIncrease = _n(raw.costIncrease)
    const costDecrease = _n(raw.costDecrease)
    const costEndingRaw = raw.costEnding != null
      ? _n(raw.costEnding)
      : calcRollEnding(costOpening, costIncrease, costDecrease)
    const costUnadj = raw.costUnadj != null ? _n(raw.costUnadj) : costEndingRaw
    const costAje = _n(raw.costAje)

    const impOpening = raw.impOpening != null ? _n(raw.impOpening) : _n(raw.accImpairmentBegin)
    const impIncrease = raw.impIncrease != null ? _n(raw.impIncrease) : _n(raw.currentImpairment)
    const impDecrease = _n(raw.impDecrease)
    const impEndingRaw = raw.impEnding != null
      ? _n(raw.impEnding)
      : calcRollEnding(impOpening, impIncrease, impDecrease)
    const impUnadj = raw.impUnadj != null ? _n(raw.impUnadj) : impEndingRaw
    const impAje = _n(raw.impAje)

    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      investee: raw.investee ?? '',

      costOpening,
      costIncrease,
      costIncreaseMethod: raw.costIncreaseMethod ?? '',
      costDecrease,
      costDecreaseReason: raw.costDecreaseReason ?? '',
      costEnding: costEndingRaw,
      costUnadj,
      costAje,
      costAudited: 0,

      impOpening,
      impIncrease,
      impIncreaseMethod: raw.impIncreaseMethod ?? '',
      impDecrease,
      impDecreaseReason: raw.impDecreaseReason ?? '',
      impEnding: impEndingRaw,
      impUnadj,
      impAje,
      impAudited: 0,

      mergerCost: _n(raw.mergerCost),
      netAssetFairValue: _n(raw.netAssetFairValue),
      entryGoodwillCalc: 0,
      minorityInterest: _n(raw.minorityInterest),
      costConsideration: _n(raw.costConsideration),
      costContingent: _n(raw.costContingent),
      costTransactionFee: _n(raw.costTransactionFee),
      mergerDate: raw.mergerDate ?? '',
      valuationBaseDate: raw.valuationBaseDate ?? '',
      valuationMethod: raw.valuationMethod ?? '',
      valuationAppreciation: _n(raw.valuationAppreciation),
      entryRemark: raw.entryRemark ?? '',

      acquisitionDate: raw.acquisitionDate ?? '',
      consideration: _n(raw.consideration),
      counterpartyNetAsset: _n(raw.counterpartyNetAsset),
      shareholding: _n(raw.shareholding),
      controlType: raw.controlType ?? '',
      mergerType: raw.mergerType ?? '',
      equityLevel: raw.equityLevel ?? '',
      industry: raw.industry ?? '',
      basicRemark: raw.basicRemark ?? '',
      cguName: raw.cguName ?? '',
      recoverableAmount: _n(raw.recoverableAmount),
      impairmentTestDate: raw.impairmentTestDate ?? '',
      impairmentTestMethod: raw.impairmentTestMethod ?? '',
      impairmentIndicator: raw.impairmentIndicator ?? '',
      impairmentRemark: raw.impairmentRemark ?? '',

      goodwillOriginal: _n(raw.goodwillOriginal),
      accImpairmentBegin: impOpening,
      currentImpairment: impIncrease,
      accImpairmentEnd: 0,
      goodwillNetValue: 0,
      periodDebit: costIncrease,
      periodCredit: costDecrease + impIncrease,
    }
  }

  /**
   * 重算：
   * 1) 原值/减值滚动期末、审定
   * 2) 入账测算商誉
   * 3) 兼容字段回写；净值 = 原值审定 − 减值审定
   * 4) 商誉减值不可转回：impIncrease ≥ 0（处置转出走 decrease）
   */
  function _recalcRow(row: I3DetailRow): void {
    row.impIncrease = Math.max(0, row.impIncrease)

    row.costEnding = calcRollEnding(row.costOpening, row.costIncrease, row.costDecrease)
    row.costAudited = calcAudited(row.costUnadj, row.costAje)

    row.impEnding = calcRollEnding(row.impOpening, row.impIncrease, row.impDecrease)
    row.impAudited = calcAudited(row.impUnadj, row.impAje)

    row.entryGoodwillCalc = calcInitialGoodwill(row.mergerCost, row.netAssetFairValue)

    // 兼容旧字段
    row.goodwillOriginal = row.costAudited
    row.accImpairmentBegin = row.impOpening
    row.currentImpairment = row.impIncrease
    row.accImpairmentEnd = row.impAudited
    row.goodwillNetValue = calcGoodwillNetValue(row.costAudited, row.impAudited)
    // Excel 本期借/贷发生额（供 I3-5 检查比例勾稽）
    row.periodDebit = row.costIncrease
    row.periodCredit = row.costDecrease + row.impIncrease
  }

  function recalcAll(): void {
    for (const row of rows.value) _recalcRow(row)
  }

  const summaryRow: ComputedRef<I3DetailSummary> = computed(() => {
    const r = rows.value
    const sum = (fn: (x: I3DetailRow) => number) => calcSubtotal(r.map(fn))
    return {
      costOpening: sum((x) => x.costOpening),
      costIncrease: sum((x) => x.costIncrease),
      costDecrease: sum((x) => x.costDecrease),
      costEnding: sum((x) => x.costEnding),
      costUnadj: sum((x) => x.costUnadj),
      costAje: sum((x) => x.costAje),
      costAudited: sum((x) => x.costAudited),
      impOpening: sum((x) => x.impOpening),
      impIncrease: sum((x) => x.impIncrease),
      impDecrease: sum((x) => x.impDecrease),
      impEnding: sum((x) => x.impEnding),
      impUnadj: sum((x) => x.impUnadj),
      impAje: sum((x) => x.impAje),
      impAudited: sum((x) => x.impAudited),
      periodDebit: sum((x) => x.periodDebit),
      periodCredit: sum((x) => x.periodCredit),
      mergerCost: sum((x) => x.mergerCost),
      netAssetFairValue: sum((x) => x.netAssetFairValue),
      entryGoodwillCalc: sum((x) => x.entryGoodwillCalc),
      minorityInterest: sum((x) => x.minorityInterest),
      costConsideration: sum((x) => x.costConsideration),
      costContingent: sum((x) => x.costContingent),
      costTransactionFee: sum((x) => x.costTransactionFee),
      consideration: sum((x) => x.consideration),
      counterpartyNetAsset: sum((x) => x.counterpartyNetAsset),
      goodwillOriginal: sum((x) => x.goodwillOriginal),
      accImpairmentBegin: sum((x) => x.accImpairmentBegin),
      currentImpairment: sum((x) => x.currentImpairment),
      accImpairmentEnd: sum((x) => x.accImpairmentEnd),
      goodwillNetValue: sum((x) => x.goodwillNetValue),
      recoverableAmount: sum((x) => x.recoverableAmount),
    }
  })

  const crossValidation: ComputedRef<I3DetailCrossValidation> = computed(() => {
    const adjOriginal = options?.adjGoodwillOriginalSubtotal?.value ?? 0
    const adjImpairment = options?.adjAccImpairmentSubtotal?.value ?? 0
    const adjNetValue = options?.adjNetValueSubtotal?.value ?? 0

    const goodwillOriginalDiff = summaryRow.value.costAudited - adjOriginal
    const accImpairmentDiff = summaryRow.value.impAudited - adjImpairment
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

  /** 滚动勾稽：期末=期初+增-减；若未审已填则提示与计算期末差异 */
  const rollForwardChecks: ComputedRef<I3RollForwardCheck[]> = computed(() => {
    return rows.value.map((row) => {
      const costCalc = calcRollEnding(row.costOpening, row.costIncrease, row.costDecrease)
      const impCalc = calcRollEnding(row.impOpening, row.impIncrease, row.impDecrease)
      const costAuditCalc = calcAudited(row.costUnadj, row.costAje)
      const impAuditCalc = calcAudited(row.impUnadj, row.impAje)
      return {
        rowId: row.rowId,
        investee: row.investee,
        costOk: Math.abs(row.costEnding - costCalc) < 0.01,
        costDiff: row.costEnding - costCalc,
        impOk: Math.abs(row.impEnding - impCalc) < 0.01,
        impDiff: row.impEnding - impCalc,
        costAuditOk: Math.abs(row.costAudited - costAuditCalc) < 0.01,
        costAuditDiff: row.costAudited - costAuditCalc,
        impAuditOk: Math.abs(row.impAudited - impAuditCalc) < 0.01,
        impAuditDiff: row.impAudited - impAuditCalc,
      }
    })
  })

  const hasRollForwardWarning = computed(() =>
    rollForwardChecks.value.some((c) => !c.costOk || !c.impOk || !c.costAuditOk || !c.impAuditOk),
  )

  function switchSection(section: I3DetailSection): void {
    activeSection.value = section
  }

  function setActiveRow(index: number): void {
    activeRowIndex.value = index
  }

  function updateCell(
    rowIndex: number,
    field: keyof I3DetailRow,
    value: string | number,
  ): void {
    const row = rows.value[rowIndex]
    if (!row) return
    ;(row as any)[field] = value

    // 编辑未审时：若用户改的是计算期末相关输入，保持未审默认同步（仅当未审此前等于旧期末）
    if (field === 'costOpening' || field === 'costIncrease' || field === 'costDecrease') {
      const newEnding = calcRollEnding(row.costOpening, row.costIncrease, row.costDecrease)
      // 若未审一直跟着期末走（常见填法），自动同步
      if (Math.abs(row.costUnadj - row.costEnding) < 0.01 || row.costUnadj === 0) {
        row.costUnadj = newEnding
      }
    }
    if (field === 'impOpening' || field === 'impIncrease' || field === 'impDecrease') {
      const newEnding = calcRollEnding(row.impOpening, row.impIncrease, row.impDecrease)
      if (Math.abs(row.impUnadj - row.impEnding) < 0.01 || row.impUnadj === 0) {
        row.impUnadj = newEnding
      }
    }

    _recalcRow(row)
    _persist()
  }

  function _emptyRow(investee: string): I3DetailRow {
    const row: I3DetailRow = {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      investee,
      costOpening: 0,
      costIncrease: 0,
      costIncreaseMethod: '',
      costDecrease: 0,
      costDecreaseReason: '',
      costEnding: 0,
      costUnadj: 0,
      costAje: 0,
      costAudited: 0,
      impOpening: 0,
      impIncrease: 0,
      impIncreaseMethod: '',
      impDecrease: 0,
      impDecreaseReason: '',
      impEnding: 0,
      impUnadj: 0,
      impAje: 0,
      impAudited: 0,
      mergerCost: 0,
      netAssetFairValue: 0,
      entryGoodwillCalc: 0,
      minorityInterest: 0,
      costConsideration: 0,
      costContingent: 0,
      costTransactionFee: 0,
      mergerDate: '',
      valuationBaseDate: '',
      valuationMethod: '',
      valuationAppreciation: 0,
      entryRemark: '',
      acquisitionDate: '',
      consideration: 0,
      counterpartyNetAsset: 0,
      shareholding: 0,
      controlType: '',
      mergerType: '非同一控制',
      equityLevel: '直接',
      industry: '',
      basicRemark: '',
      cguName: '',
      recoverableAmount: 0,
      impairmentTestDate: '',
      impairmentTestMethod: '',
      impairmentIndicator: '',
      impairmentRemark: '',
      goodwillOriginal: 0,
      accImpairmentBegin: 0,
      currentImpairment: 0,
      accImpairmentEnd: 0,
      goodwillNetValue: 0,
      periodDebit: 0,
      periodCredit: 0,
    }
    _recalcRow(row)
    return row
  }

  async function addRow(): Promise<I3DetailRow | null> {
    try {
      const { value: name } = await ElMessageBox.prompt(
        '请输入被投资单位名称或形成商誉的事项',
        '新增商誉明细行',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '例如：XX科技有限公司',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '名称不能为空'
            return true
          },
        },
      )
      if (!name?.trim()) return null
      const newRow = _emptyRow(name.trim())
      rows.value.push(newRow)
      activeRowIndex.value = rows.value.length - 1
      _persist()
      return newRow
    } catch {
      return null
    }
  }

  function removeRow(rowIndex: number): void {
    if (rowIndex < 0 || rowIndex >= rows.value.length) return
    rows.value.splice(rowIndex, 1)
    if (activeRowIndex.value >= rows.value.length) {
      activeRowIndex.value = rows.value.length - 1
    }
    _persist()
  }

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

  function importRows(importedRows: Partial<I3DetailRow>[]): void {
    rows.value = importedRows.map((raw) => {
      const row = _normalizeRow(raw)
      _recalcRow(row)
      return row
    })
    activeRowIndex.value = rows.value.length > 0 ? 0 : -1
    _persist()
  }

  function exportRows(): I3DetailRow[] {
    return [...rows.value]
  }

  // ─── 列配置 ────────────────────────────────────────────────────────────────

  const costColumns = [
    { key: 'investee', label: '被投资单位/形成事项', width: 180, editable: true, type: 'text' as const },
    { key: 'costOpening', label: '期初数', width: 120, editable: true, type: 'number' as const },
    { key: 'costIncrease', label: '本期增加', width: 120, editable: true, type: 'number' as const, tooltip: '对应本期借方发生额；与 I3-5 检查比例勾稽' },
    { key: 'costIncreaseMethod', label: '增加方式', width: 130, editable: true, type: 'select' as const, options: [...COST_INCREASE_METHODS] },
    { key: 'costDecrease', label: '本期减少', width: 120, editable: true, type: 'number' as const },
    { key: 'costDecreaseReason', label: '减少原因', width: 120, editable: true, type: 'select' as const, options: [...COST_DECREASE_REASONS] },
    { key: 'costEnding', label: '期末数', width: 120, editable: false, type: 'formula' as const, tooltip: '期末=期初+本期增加−本期减少' },
    { key: 'costUnadj', label: '未审数', width: 120, editable: true, type: 'number' as const },
    { key: 'costAje', label: '账项调整', width: 110, editable: true, type: 'number' as const },
    { key: 'costAudited', label: '审定数', width: 120, editable: false, type: 'formula' as const, tooltip: '审定=未审+账项调整' },
    { key: 'periodDebit', label: '本期借方发生额', width: 130, editable: false, type: 'formula' as const, tooltip: '=本期增加（Excel N 列；供 I3-5）' },
    { key: 'periodCredit', label: '本期贷方发生额', width: 130, editable: false, type: 'formula' as const, tooltip: '=原值本期减少+减值本期计提（Excel O 列；供 I3-5）' },
  ]

  const impairmentColumns = [
    { key: 'investee', label: '被投资单位/形成事项', width: 180, editable: false, type: 'text' as const },
    { key: 'impOpening', label: '期初数', width: 120, editable: true, type: 'number' as const },
    { key: 'impIncrease', label: '本期增加(计提)', width: 130, editable: true, type: 'number' as const },
    { key: 'impIncreaseMethod', label: '增加方式', width: 120, editable: true, type: 'select' as const, options: [...IMP_INCREASE_METHODS] },
    { key: 'impDecrease', label: '本期减少', width: 120, editable: true, type: 'number' as const },
    { key: 'impDecreaseReason', label: '减少原因', width: 120, editable: true, type: 'select' as const, options: [...IMP_DECREASE_REASONS] },
    { key: 'impEnding', label: '期末数', width: 120, editable: false, type: 'formula' as const, tooltip: '期末=期初+本期增加−本期减少' },
    { key: 'impUnadj', label: '未审数', width: 120, editable: true, type: 'number' as const },
    { key: 'impAje', label: '账项调整', width: 110, editable: true, type: 'number' as const },
    { key: 'impAudited', label: '审定数', width: 120, editable: false, type: 'formula' as const, tooltip: '审定=未审+账项调整' },
    { key: 'goodwillNetValue', label: '商誉净值', width: 120, editable: false, type: 'formula' as const, tooltip: '净值=原值审定−减值审定（不摊销）' },
  /** 所属CGU（与 I3-6 同源下拉） */
  { key: 'cguName', label: '所属CGU', width: 130, editable: true, type: 'text' as const },
]

  const entryColumns = [
    { key: 'investee', label: '被投资单位', width: 180, editable: false, type: 'text' as const },
    { key: 'mergerCost', label: '合并成本', width: 130, editable: true, type: 'number' as const },
    { key: 'netAssetFairValue', label: '可辨认净资产公允份额', width: 160, editable: true, type: 'number' as const },
    { key: 'entryGoodwillCalc', label: '测算商誉原值', width: 130, editable: false, type: 'formula' as const, tooltip: '合并成本−可辨认净资产公允份额（非同一控制）' },
    { key: 'costAudited', label: '原值审定(对照)', width: 130, editable: false, type: 'formula' as const, tooltip: '来自原值滚动审定数，应与测算一致（新增商誉）' },
    { key: 'minorityInterest', label: '少数股东权益', width: 120, editable: true, type: 'number' as const },
    { key: 'costConsideration', label: '对价金额', width: 120, editable: true, type: 'number' as const },
    { key: 'costContingent', label: '或有对价', width: 110, editable: true, type: 'number' as const },
    { key: 'costTransactionFee', label: '交易费用', width: 110, editable: true, type: 'number' as const },
    { key: 'mergerDate', label: '合并日期', width: 120, editable: true, type: 'date' as const },
    { key: 'valuationMethod', label: '评估方法', width: 110, editable: true, type: 'select' as const, options: VALUATION_METHOD_OPTIONS },
    { key: 'entryRemark', label: '备注', width: 140, editable: true, type: 'text' as const },
  ]

  const basicColumns = [
    { key: 'investee', label: '被投资单位', width: 180, editable: true, type: 'text' as const },
    { key: 'acquisitionDate', label: '并购日期', width: 120, editable: true, type: 'date' as const },
    { key: 'consideration', label: '对价', width: 120, editable: true, type: 'number' as const },
    { key: 'counterpartyNetAsset', label: '被购方净资产', width: 130, editable: true, type: 'number' as const },
    { key: 'shareholding', label: '持股比例', width: 100, editable: true, type: 'number' as const },
    { key: 'controlType', label: '控制类型', width: 110, editable: true, type: 'select' as const, options: CONTROL_TYPE_OPTIONS },
    { key: 'mergerType', label: '合并方式', width: 120, editable: true, type: 'select' as const, options: MERGER_TYPE_OPTIONS },
    { key: 'equityLevel', label: '股权层级', width: 100, editable: true, type: 'select' as const, options: EQUITY_LEVEL_OPTIONS },
    { key: 'industry', label: '所属行业', width: 120, editable: true, type: 'text' as const },
    { key: 'impairmentTestMethod', label: '测试方法', width: 100, editable: true, type: 'select' as const, options: IMPAIRMENT_TEST_METHOD_OPTIONS },
    { key: 'impairmentIndicator', label: '减值迹象', width: 100, editable: true, type: 'select' as const, options: IMPAIRMENT_INDICATOR_OPTIONS },
    { key: 'basicRemark', label: '备注', width: 140, editable: true, type: 'text' as const },
  ]

  const sections = [
    { key: 0 as I3DetailSection, label: '原值滚动', columns: costColumns },
    { key: 1 as I3DetailSection, label: '减值滚动', columns: impairmentColumns },
    { key: 2 as I3DetailSection, label: '入账测算', columns: entryColumns },
    { key: 3 as I3DetailSection, label: '基础信息', columns: basicColumns },
  ]

  const activeColumns = computed(() => {
    return sections.find((s) => s.key === activeSection.value)?.columns ?? costColumns
  })

  function _persist(): void {
    options?.onSave?.(ITEM_ID_ROWS, rows.value)
  }

  /**
   * 从 I3-6 按 CGU 带入本期计提（合并确认商誉减值）→ impIncrease
   * 匹配：row.cguName === cgu；同 CGU 多行时按原值审定权重分摊
   */
  function syncImpIncreaseFromI3_6(byCgu: Record<string, number>): number {
    let updated = 0
    const groups = new Map<string, number[]>()
    rows.value.forEach((row, idx) => {
      const cgu = row.cguName || ''
      if (!cgu || byCgu[cgu] == null) return
      if (!groups.has(cgu)) groups.set(cgu, [])
      groups.get(cgu)!.push(idx)
    })

    for (const [cgu, indices] of groups) {
      const total = Math.max(0, byCgu[cgu] || 0)
      const weightSum = indices.reduce((s, i) => s + Math.max(rows.value[i].costAudited, 0), 0)
      indices.forEach((i, n) => {
        const row = rows.value[i]
        let share = 0
        if (weightSum > 0) {
          share = (Math.max(row.costAudited, 0) / weightSum) * total
        } else {
          share = total / indices.length
        }
        // 最后一行吃尾差
        if (n === indices.length - 1) {
          const allocated = indices.slice(0, -1).reduce((s, j) => s + rows.value[j].impIncrease, 0)
          // 先写前面的，最后一行用 residual — 简化：直接按 share
          share = total - indices.slice(0, n).reduce((s, j) => {
            const w = weightSum > 0 ? (Math.max(rows.value[j].costAudited, 0) / weightSum) * total : total / indices.length
            return s + w
          }, 0)
        }
        if (Math.abs(row.impIncrease - share) > 0.01) {
          row.impIncrease = Math.max(0, share)
          if (Math.abs(row.impUnadj - row.impEnding) < 0.01 || row.impUnadj === 0) {
            row.impUnadj = calcRollEnding(row.impOpening, row.impIncrease, row.impDecrease)
          }
          _recalcRow(row)
          updated++
        }
      })
    }
    if (updated > 0) _persist()
    return updated
  }

  /**
   * 从 I3-3 按被投资单位回写账项调整：costAje / impAje
   * 返回更新行数；未匹配项写入 lastSyncMeta 供 UI 提示
   */
  function syncAjeFromI3_3(
    byInvestee: Record<string, { costAje: number; impAje: number; net: number }>,
  ): { updated: number; applied: string[]; unmatched: string[]; unspecified: boolean } {
    let updated = 0
    const applied: string[] = []
    const detailKeys = new Set(rows.value.map((r) => r.investee?.trim()).filter(Boolean) as string[])
    const unmatched: string[] = []
    let unspecified = false

    for (const [key, src] of Object.entries(byInvestee)) {
      if (key === '未指定') {
        if (Math.abs(src.costAje) > 0.01 || Math.abs(src.impAje) > 0.01) unspecified = true
        continue
      }
      if (!detailKeys.has(key)) {
        unmatched.push(key)
        continue
      }
    }

    for (const row of rows.value) {
      const key = row.investee?.trim()
      if (!key || !byInvestee[key]) continue
      const src = byInvestee[key]
      let changed = false
      if (Math.abs(row.costAje - src.costAje) > 0.01) {
        row.costAje = src.costAje
        changed = true
      }
      if (Math.abs(row.impAje - src.impAje) > 0.01) {
        row.impAje = src.impAje
        changed = true
      }
      if (changed) {
        _recalcRow(row)
        updated++
        applied.push(key)
      }
    }
    if (updated > 0) _persist()
    return { updated, applied, unmatched, unspecified }
  }

  /**
   * 从 I3-4 带入：若本期增加为 0 且测算有商誉，写入 costIncrease；并回填入账测算字段
   */
  function syncFromI3_4(
    i4Rows: { investee?: string; projectName?: string; mergerCost?: number; netAssetFairValue?: number; goodwillAmount?: number }[],
  ): number {
    let updated = 0
    const map = new Map<string, typeof i4Rows[0]>()
    for (const r of i4Rows) {
      const k = String(r.investee || r.projectName || '').trim()
      if (k) map.set(k, r)
    }
    for (const row of rows.value) {
      const src = map.get(row.investee?.trim() || '')
      if (!src) continue
      let changed = false
      const gw = Number(src.goodwillAmount) || 0
      if (src.mergerCost != null && row.mergerCost !== Number(src.mergerCost)) {
        row.mergerCost = Number(src.mergerCost) || 0
        changed = true
      }
      if (src.netAssetFairValue != null && row.netAssetFairValue !== Number(src.netAssetFairValue)) {
        row.netAssetFairValue = Number(src.netAssetFairValue) || 0
        changed = true
      }
      if (gw > 0 && row.costIncrease === 0) {
        row.costIncrease = gw
        row.costIncreaseMethod = row.costIncreaseMethod || '企业合并新增'
        if (Math.abs(row.costUnadj - row.costEnding) < 0.01 || row.costUnadj === 0) {
          row.costUnadj = calcRollEnding(row.costOpening, row.costIncrease, row.costDecrease)
        }
        changed = true
      }
      if (changed) {
        _recalcRow(row)
        updated++
      }
    }
    if (updated > 0) _persist()
    return updated
  }

  watch(allResponses, () => _loadRows(), { immediate: true })

  return {
    rows,
    activeSection,
    activeRowIndex,
    summaryRow,
    crossValidation,
    rollForwardChecks,
    hasRollForwardWarning,
    activeColumns,
    sections,
    costColumns,
    impairmentColumns,
    entryColumns,
    basicColumns,
    switchSection,
    setActiveRow,
    updateCell,
    recalcAll,
    addRow,
    removeRow,
    moveRowUp,
    moveRowDown,
    importRows,
    exportRows,
    syncImpIncreaseFromI3_6,
    syncAjeFromI3_3,
    syncFromI3_4,
  }
}

export default useI3Detail
