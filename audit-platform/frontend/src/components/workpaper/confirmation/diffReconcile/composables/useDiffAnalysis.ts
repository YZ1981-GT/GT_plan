/**
 * useDiffAnalysis — D0-4 差异原因分析表 composable
 *
 * 职责：
 * - 按 diff_type 聚合笔数 + 净额金额 + 合计
 * - 未分类计数
 * - 明细变化时重算（不入库，仅 note/action 持久化）
 * - 提供编辑接口：updateAnalysisNote / updateAnalysisAction
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import type { DiffReconcileRow, DiffAnalysisGroup } from '../diffReconcileTypes'

// 固定排序的差异类型
const DIFF_TYPE_ORDER = ['time', 'accounting', 'unrecorded', 'other'] as const
const DIFF_TYPE_LABELS: Record<string, string> = {
  time: '时间性差异',
  accounting: '记账差异',
  unrecorded: '未达账项',
  other: '其他差异',
}

export interface UseDiffAnalysisProps {
  rows: Ref<DiffReconcileRow[]>
  analysisNotes: Ref<Record<string, { note?: string; action?: string }>>
  computeDifference: (row: DiffReconcileRow) => number
}

export interface UseDiffAnalysisReturn {
  /** 按差异类型分析表（4 行 + 合计） */
  analysisGroups: ComputedRef<DiffAnalysisGroup[]>
  /** 合计行 */
  analysisTotals: ComputedRef<{ count: number; net_amount: number; abs_amount: number }>
  /** 未分类行数 */
  unclassifiedCount: ComputedRef<number>
  /** 更新分析说明 */
  updateAnalysisNote: (diffType: string, note: string) => void
  /** 更新应对措施 */
  updateAnalysisAction: (diffType: string, action: string) => void
}

export function useDiffAnalysis(props: UseDiffAnalysisProps): UseDiffAnalysisReturn {
  const { rows, analysisNotes, computeDifference } = props

  const analysisGroups = computed<DiffAnalysisGroup[]>(() => {
    // 初始化 4 类型桶
    const buckets = new Map<string, { count: number; net: number; abs: number }>()
    for (const t of DIFF_TYPE_ORDER) {
      buckets.set(t, { count: 0, net: 0, abs: 0 })
    }

    for (const row of rows.value) {
      const t = row.diff_type || ''
      // 仅统计已分类的行
      if (!t || !buckets.has(t)) continue
      const bucket = buckets.get(t)!
      bucket.count++
      const diff = computeDifference(row)
      bucket.net += diff
      bucket.abs += Math.abs(diff)
    }

    const totalAbs = [...buckets.values()].reduce((s, b) => s + b.abs, 0) || 1

    return DIFF_TYPE_ORDER.map((t) => {
      const b = buckets.get(t)!
      return {
        diff_type: t,
        count: b.count,
        net_amount: Math.round(b.net * 100) / 100,
        abs_amount: Math.round(b.abs * 100) / 100,
        percentage: Math.round((b.abs / totalAbs) * 10000) / 100,
        note: analysisNotes.value[t]?.note,
        action: analysisNotes.value[t]?.action,
      }
    })
  })

  const analysisTotals = computed(() => {
    const groups = analysisGroups.value
    return {
      count: groups.reduce((s, g) => s + g.count, 0),
      net_amount: Math.round(groups.reduce((s, g) => s + g.net_amount, 0) * 100) / 100,
      abs_amount: Math.round(groups.reduce((s, g) => s + g.abs_amount, 0) * 100) / 100,
    }
  })

  const unclassifiedCount = computed(() => {
    return rows.value.filter((r) => !r.diff_type).length
  })

  function updateAnalysisNote(diffType: string, note: string) {
    if (!analysisNotes.value[diffType]) {
      analysisNotes.value[diffType] = {}
    }
    analysisNotes.value[diffType].note = note
  }

  function updateAnalysisAction(diffType: string, action: string) {
    if (!analysisNotes.value[diffType]) {
      analysisNotes.value[diffType] = {}
    }
    analysisNotes.value[diffType].action = action
  }

  return {
    analysisGroups,
    analysisTotals,
    unclassifiedCount,
    updateAnalysisNote,
    updateAnalysisAction,
  }
}

/** 差异类型标签映射（供 UI 使用） */
export { DIFF_TYPE_LABELS, DIFF_TYPE_ORDER }
