/**
 * useDiffAnalysis 单测
 * 覆盖：聚合 + 合计 + 未分类计数 + note/action 编辑
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useDiffAnalysis } from '../useDiffAnalysis'
import type { DiffReconcileRow } from '../../diffReconcileTypes'

function computeDifference(row: DiffReconcileRow): number {
  return Math.round(((row.sent_amount ?? 0) - (row.reply_amount ?? 0)) * 100) / 100
}

describe('useDiffAnalysis', () => {
  it('按 4 类型聚合笔数+金额', () => {
    const rows = ref<DiffReconcileRow[]>([
      { diff_type: 'time', sent_amount: 1000, reply_amount: 800 },
      { diff_type: 'time', sent_amount: 500, reply_amount: 300 },
      { diff_type: 'accounting', sent_amount: 2000, reply_amount: 2100 },
      { diff_type: 'unrecorded', sent_amount: 300, reply_amount: 0 },
    ])
    const analysisNotes = ref<Record<string, { note?: string; action?: string }>>({})

    const { analysisGroups, analysisTotals } = useDiffAnalysis({
      rows,
      analysisNotes,
      computeDifference,
    })

    const timeGroup = analysisGroups.value.find((g) => g.diff_type === 'time')!
    expect(timeGroup.count).toBe(2)
    expect(timeGroup.net_amount).toBe(400) // 200 + 200

    const accGroup = analysisGroups.value.find((g) => g.diff_type === 'accounting')!
    expect(accGroup.count).toBe(1)
    expect(accGroup.net_amount).toBe(-100)

    expect(analysisTotals.value.count).toBe(4)
  })

  it('未分类行不计入分析表', () => {
    const rows = ref<DiffReconcileRow[]>([
      { diff_type: 'time', sent_amount: 100, reply_amount: 50 },
      { sent_amount: 200, reply_amount: 100 },  // 无 diff_type
    ])
    const analysisNotes = ref({})

    const { unclassifiedCount, analysisTotals } = useDiffAnalysis({
      rows,
      analysisNotes,
      computeDifference,
    })

    expect(unclassifiedCount.value).toBe(1)
    expect(analysisTotals.value.count).toBe(1) // 仅已分类
  })

  it('updateAnalysisNote/Action 持久化到 analysisNotes', () => {
    const rows = ref<DiffReconcileRow[]>([])
    const analysisNotes = ref<Record<string, { note?: string; action?: string }>>({})

    const { updateAnalysisNote, updateAnalysisAction } = useDiffAnalysis({
      rows,
      analysisNotes,
      computeDifference,
    })

    updateAnalysisNote('time', '月末截止差异')
    updateAnalysisAction('time', '取得银行对账单核实')

    expect(analysisNotes.value.time).toEqual({
      note: '月末截止差异',
      action: '取得银行对账单核实',
    })
  })

  it('percentage 合计 100%', () => {
    const rows = ref<DiffReconcileRow[]>([
      { diff_type: 'time', sent_amount: 300, reply_amount: 0 },
      { diff_type: 'accounting', sent_amount: 200, reply_amount: 0 },
      { diff_type: 'unrecorded', sent_amount: 500, reply_amount: 0 },
    ])
    const analysisNotes = ref({})

    const { analysisGroups } = useDiffAnalysis({ rows, analysisNotes, computeDifference })
    const totalPct = analysisGroups.value.reduce((s, g) => s + g.percentage, 0)
    expect(totalPct).toBeCloseTo(100, 0)
  })
})
