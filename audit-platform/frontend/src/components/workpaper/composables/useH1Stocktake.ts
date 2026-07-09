/**
 * useH1Stocktake — H1-9~11 监盘组 composable
 *
 * 计划/检查/小结三阶段共用状态
 * FixedAssetStocktakeDialog集成
 * 盘盈/盘亏自动汇总 + 账实相符率
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.11
 * Requirements: 10.1-10.10
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import { calcSubtotal } from './useH1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 监盘计划基本信息 */
export interface StocktakePlanInfo {
  stocktakeDate: string          // 盘点日期
  location: string               // 盘点地点
  participants: string           // 参与人
  scope: string                  // 盘点范围
  method: string                 // 盘点方法(全面盘点/抽样盘点)
}

/** 样本选取行 */
export interface SampleSelectionRow {
  rowId: string
  category: string               // 资产分类
  selectionCriteria: string      // 选取标准
  sampleSize: number             // 样本量
  coverageAmount: number         // 金额覆盖
  coverageRate: number           // 覆盖率(%)
}

/** 盘点检查行 (H1-10) */
export interface StocktakeCheckRow {
  rowId: string
  seq: number                    // 序号
  name: string                   // 资产名称
  assetNo: string                // 资产编号
  location: string               // 存放地点
  bookCost: number               // 账面原值
  bookNetValue: number           // 账面净值
  actualStatus: string           // 实际状态(在用/闲置/报废)
  photoUrl: string               // 实物照片
  nameplateCheck: string         // 铭牌核对(一致/不一致)
  quantityCheck: string          // 数量核对(一致/不一致)
  conditionAssess: string        // 成色评估
  result: string                 // 盘点结果(账实相符/盘盈/盘亏)
  diffReason: string             // 差异原因
  diffAmount: number             // 差异金额
  suggestion: string             // 处理建议
  checker: string                // 盘点人
  remark: string                 // 备注
}

/** 监盘统计 */
export interface StocktakeStatistics {
  totalChecked: number           // 已盘点资产数
  matchCount: number             // 账实相符数
  surplusCount: number           // 盘盈数
  deficitCount: number           // 盘亏数
  matchRate: number              // 账实相符率(%)
  surplusAmount: number          // 盘盈金额
  deficitAmount: number          // 盘亏金额
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX_PLAN = 'H1-9'
const ITEM_PREFIX_CHECK = 'H1-10'
const ITEM_PREFIX_SUMMARY = 'H1-11'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1Stocktake(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  // H1-9 计划
  const planInfo = ref<StocktakePlanInfo>({
    stocktakeDate: '', location: '', participants: '', scope: '', method: '抽样盘点',
  })
  const sampleSelections = ref<SampleSelectionRow[]>([])

  // H1-10 检查
  const checkRows = ref<StocktakeCheckRow[]>([])

  // H1-11 小结
  const summaryNote = ref('')
  const summaryConclusion = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadData(): void {
    // Plan
    const planItem = allResponses.value.get(`${ITEM_PREFIX_PLAN}-info`)
    if (planItem?.remark) {
      try { Object.assign(planInfo.value, JSON.parse(planItem.remark)) } catch { /* */ }
    }
    const selectItem = allResponses.value.get(`${ITEM_PREFIX_PLAN}-selections`)
    if (selectItem?.remark) {
      try {
        const parsed = JSON.parse(selectItem.remark)
        sampleSelections.value = Array.isArray(parsed) ? parsed : []
      } catch { sampleSelections.value = [] }
    }

    // Check
    const checkItem = allResponses.value.get(`${ITEM_PREFIX_CHECK}-rows`)
    if (checkItem?.remark) {
      try {
        const parsed = JSON.parse(checkItem.remark)
        checkRows.value = Array.isArray(parsed) ? parsed.map(_normalizeCheckRow) : []
      } catch { checkRows.value = [] }
    }

    // Summary
    summaryNote.value = _getString(`${ITEM_PREFIX_SUMMARY}-note`)
    summaryConclusion.value = _getString(`${ITEM_PREFIX_SUMMARY}-conclusion`)
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeCheckRow(raw: any, idx: number): StocktakeCheckRow {
    return {
      rowId: raw.rowId ?? `stk-${Math.random().toString(36).slice(2, 10)}`,
      seq: raw.seq ?? idx + 1,
      name: raw.name ?? '',
      assetNo: raw.assetNo ?? '',
      location: raw.location ?? '',
      bookCost: Number(raw.bookCost) || 0,
      bookNetValue: Number(raw.bookNetValue) || 0,
      actualStatus: raw.actualStatus ?? '在用',
      photoUrl: raw.photoUrl ?? '',
      nameplateCheck: raw.nameplateCheck ?? '',
      quantityCheck: raw.quantityCheck ?? '',
      conditionAssess: raw.conditionAssess ?? '',
      result: raw.result ?? '',
      diffReason: raw.diffReason ?? '',
      diffAmount: Number(raw.diffAmount) || 0,
      suggestion: raw.suggestion ?? '',
      checker: raw.checker ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Computed: 统计 ────────────────────────────────────────────────────────

  const statistics = computed<StocktakeStatistics>(() => {
    const total = checkRows.value.length
    const matchCount = checkRows.value.filter((r) => r.result === '账实相符').length
    const surplusList = checkRows.value.filter((r) => r.result === '盘盈')
    const deficitList = checkRows.value.filter((r) => r.result === '盘亏')
    return {
      totalChecked: total,
      matchCount,
      surplusCount: surplusList.length,
      deficitCount: deficitList.length,
      matchRate: total > 0 ? (matchCount / total * 100) : 0,
      surplusAmount: calcSubtotal(surplusList.map((r) => Math.abs(r.diffAmount))),
      deficitAmount: calcSubtotal(deficitList.map((r) => Math.abs(r.diffAmount))),
    }
  })

  /** 盘盈明细 */
  const surplusRows = computed(() =>
    checkRows.value.filter((r) => r.result === '盘盈'),
  )

  /** 盘亏明细 */
  const deficitRows = computed(() =>
    checkRows.value.filter((r) => r.result === '盘亏'),
  )

  // ─── CRUD: 检查行 ─────────────────────────────────────────────────────────

  function addCheckRow(name: string): void {
    const newRow: StocktakeCheckRow = {
      rowId: `stk-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: checkRows.value.length + 1,
      name, assetNo: '', location: '',
      bookCost: 0, bookNetValue: 0, actualStatus: '在用',
      photoUrl: '', nameplateCheck: '', quantityCheck: '',
      conditionAssess: '', result: '', diffReason: '', diffAmount: 0,
      suggestion: '', checker: '', remark: '',
    }
    checkRows.value.push(newRow)
    _persistCheck()
  }

  function removeCheckRow(rowId: string): void {
    const idx = checkRows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      checkRows.value.splice(idx, 1)
      checkRows.value.forEach((r, i) => { r.seq = i + 1 })
      _persistCheck()
    }
  }

  function updateCheckCell(rowId: string, field: keyof StocktakeCheckRow, value: any): void {
    const row = checkRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persistCheck()
  }

  // ─── Update Plan ───────────────────────────────────────────────────────────

  function updatePlanInfo(field: keyof StocktakePlanInfo, value: string): void {
    planInfo.value[field] = value
    options?.onSave?.(`${ITEM_PREFIX_PLAN}-info`, planInfo.value)
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistCheck(): void {
    options?.onSave?.(`${ITEM_PREFIX_CHECK}-rows`, checkRows.value)
  }

  function saveSummaryNote(note: string): void {
    summaryNote.value = note
    options?.onSave?.(`${ITEM_PREFIX_SUMMARY}-note`, note)
  }

  function saveSummaryConclusion(conclusion: string): void {
    summaryConclusion.value = conclusion
    options?.onSave?.(`${ITEM_PREFIX_SUMMARY}-conclusion`, conclusion)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadData(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // Plan (H1-9)
    planInfo,
    sampleSelections,
    updatePlanInfo,
    // Check (H1-10)
    checkRows,
    addCheckRow,
    removeCheckRow,
    updateCheckCell,
    // Summary (H1-11)
    summaryNote,
    summaryConclusion,
    saveSummaryNote,
    saveSummaryConclusion,
    // Computed
    statistics,
    surplusRows,
    deficitRows,
  }
}

export default useH1Stocktake
