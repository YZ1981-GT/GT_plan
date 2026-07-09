/**
 * useH1Analysis — H1-6 分析表 composable
 *
 * 结构分析+变动分析双区域 + 8公式自动计算
 * 从H1-2 crossSheet取数 + 阈值异常判定
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.8
 * Requirements: 7.1-7.8
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import { calcChangeRate, calcProportion, calcSubtotal } from './useH1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 结构分析行 */
export interface StructureRow {
  category: string        // 资产分类
  originalCost: number    // 原值
  accDep: number          // 累计折旧
  netValue: number        // 净值
  proportion: number | null  // 净值占比(%)
  newRate: number | null     // 成新率(%)
}

/** 变动分析行 */
export interface ChangeRow {
  category: string           // 资产分类
  beginCost: number          // 期初原值
  endCost: number            // 期末原值
  increase: number           // 本期增加
  decrease: number           // 本期减少
  increaseRate: number | null  // 增加率(%)
  decreaseRate: number | null  // 减少率(%)
  netChangeRate: number | null // 净变动率(%)
  depCoverageRate: number | null // 折旧覆盖率(%)
}

/** 异常标记 */
export interface AnomalyFlag {
  category: string
  type: 'low_new_rate' | 'high_increase' | 'high_decrease'
  value: number
  threshold: number
  message: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H1-6'
const THRESHOLD_NEW_RATE = 20       // 成新率<20% 黄色
const THRESHOLD_CHANGE_RATE = 50    // 增/减率>50% 红色

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1Analysis(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    crossSheetDetailRows?: Ref<any[]>
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadData(): void {
    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  // ─── Computed: 从H1-2取数聚合 ─────────────────────────────────────────────

  const _detailRows = computed(() => options?.crossSheetDetailRows?.value ?? [])

  /** 按分类聚合 */
  const _byCategoryMap = computed(() => {
    const map = new Map<string, {
      originalCostBegin: number; originalCostEnd: number
      increase: number; decrease: number
      accDep: number; netValue: number; originalCost: number
    }>()

    for (const row of _detailRows.value) {
      const cat = row.category || '未分类'
      const existing = map.get(cat) ?? {
        originalCostBegin: 0, originalCostEnd: 0, increase: 0,
        decrease: 0, accDep: 0, netValue: 0, originalCost: 0,
      }
      existing.originalCostBegin += Number(row.originalCostBegin) || 0
      existing.originalCostEnd += Number(row.originalCostEnd) || 0
      existing.increase += Number(row.originalCostIncrease) || 0
      existing.decrease += Number(row.originalCostDecrease) || 0
      existing.accDep += Number(row.accDepEnd) || 0
      existing.netValue += Number(row.netValue) || 0
      existing.originalCost += Number(row.originalCostEnd) || 0
      map.set(cat, existing)
    }
    return map
  })

  // ─── Computed: 结构分析 ────────────────────────────────────────────────────

  const structureRows = computed<StructureRow[]>(() => {
    const totalNetValue = calcSubtotal(
      Array.from(_byCategoryMap.value.values()).map((v) => v.netValue),
    )
    return Array.from(_byCategoryMap.value.entries()).map(([cat, data]) => ({
      category: cat,
      originalCost: data.originalCost,
      accDep: data.accDep,
      netValue: data.netValue,
      proportion: calcProportion(data.netValue, totalNetValue),
      newRate: data.originalCost > 0 ? (data.netValue / data.originalCost * 100) : null,
    }))
  })

  // ─── Computed: 变动分析 ────────────────────────────────────────────────────

  const changeRows = computed<ChangeRow[]>(() => {
    return Array.from(_byCategoryMap.value.entries()).map(([cat, data]) => ({
      category: cat,
      beginCost: data.originalCostBegin,
      endCost: data.originalCostEnd,
      increase: data.increase,
      decrease: data.decrease,
      increaseRate: data.originalCostBegin > 0
        ? (data.increase / data.originalCostBegin * 100) : null,
      decreaseRate: data.originalCostBegin > 0
        ? (data.decrease / data.originalCostBegin * 100) : null,
      netChangeRate: calcChangeRate(data.originalCostEnd, data.originalCostBegin),
      depCoverageRate: data.originalCost > 0
        ? (data.accDep / data.originalCost * 100) : null,
    }))
  })

  // ─── Computed: 异常标记 ────────────────────────────────────────────────────

  const anomalies = computed<AnomalyFlag[]>(() => {
    const flags: AnomalyFlag[] = []

    for (const row of structureRows.value) {
      if (row.newRate != null && row.newRate < THRESHOLD_NEW_RATE) {
        flags.push({
          category: row.category,
          type: 'low_new_rate',
          value: row.newRate,
          threshold: THRESHOLD_NEW_RATE,
          message: `${row.category}成新率${row.newRate.toFixed(1)}%，老旧资产占比过高`,
        })
      }
    }

    for (const row of changeRows.value) {
      if (row.increaseRate != null && row.increaseRate > THRESHOLD_CHANGE_RATE) {
        flags.push({
          category: row.category,
          type: 'high_increase',
          value: row.increaseRate,
          threshold: THRESHOLD_CHANGE_RATE,
          message: `${row.category}增加率${row.increaseRate.toFixed(1)}%，变动幅度较大`,
        })
      }
      if (row.decreaseRate != null && row.decreaseRate > THRESHOLD_CHANGE_RATE) {
        flags.push({
          category: row.category,
          type: 'high_decrease',
          value: row.decreaseRate,
          threshold: THRESHOLD_CHANGE_RATE,
          message: `${row.category}减少率${row.decreaseRate.toFixed(1)}%，变动幅度较大`,
        })
      }
    }

    return flags
  })

  // ─── Save ──────────────────────────────────────────────────────────────────

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadData(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    auditNote,
    auditConclusion,
    structureRows,
    changeRows,
    anomalies,
    saveNote,
    saveConclusion,
  }
}

export default useH1Analysis
