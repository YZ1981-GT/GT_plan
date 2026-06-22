/**
 * useDiffReconcileData 单测
 * 覆盖：CRUD + 差异自动算 + 合计/分组小计 + metrics + buildPayload
 */
import { describe, it, expect } from 'vitest'
import { useDiffReconcileData } from '../useDiffReconcileData'
import type { DiffReconcileRow, DiffReconcilePayload } from '../../diffReconcileTypes'

function createComposable(rows: DiffReconcileRow[] = [], extra: Record<string, any> = {}) {
  const payload = {
    _format: 'diff-reconcile-v1' as const,
    rows,
    ...extra,
  }
  return useDiffReconcileData({
    htmlData: () => payload,
    readonly: false,
  })
}

describe('useDiffReconcileData', () => {
  describe('初始化', () => {
    it('从 diff-reconcile-v1 格式正确初始化', () => {
      const { rows } = createComposable([
        { confirm_index: 'C001', sent_amount: 1000, reply_amount: 900 },
      ])
      expect(rows.value).toHaveLength(1)
      expect(rows.value[0].confirm_index).toBe('C001')
      expect(rows.value[0]._row_id).toBeTruthy()
    })

    it('非 diff-reconcile-v1 格式初始化为空', () => {
      const { rows } = useDiffReconcileData({
        htmlData: () => ({ _format: 'unknown' }),
        readonly: false,
      })
      expect(rows.value).toHaveLength(0)
    })
  })

  describe('CRUD', () => {
    it('addRow 自增序号', () => {
      const { rows, addRow } = createComposable([{ seq: 3 }])
      const newRow = addRow()
      expect(newRow.seq).toBe(4)
      expect(rows.value).toHaveLength(2)
    })

    it('deleteRows 按 ID 删除', () => {
      const { rows, deleteRows } = createComposable([
        { confirm_index: 'A', sent_amount: 100, reply_amount: 50 },
        { confirm_index: 'B', sent_amount: 200, reply_amount: 200 },
      ])
      const idToDelete = rows.value[0]._row_id!
      deleteRows([idToDelete])
      expect(rows.value).toHaveLength(1)
      expect(rows.value[0].confirm_index).toBe('B')
    })

    it('updateField 更新金额自动重算差异', () => {
      const { rows, updateField } = createComposable([
        { sent_amount: 1000, reply_amount: 800 },
      ])
      const id = rows.value[0]._row_id!
      updateField(id, 'reply_amount', 900)
      expect(rows.value[0].difference).toBe(100)
    })

    it('importRows 按 confirm_index 去重', () => {
      const { rows, importRows } = createComposable([
        { confirm_index: 'C001', sent_amount: 1000, reply_amount: 900 },
      ])
      importRows([
        { confirm_index: 'C001', sent_amount: 500, reply_amount: 400 },  // 重复
        { confirm_index: 'C002', sent_amount: 2000, reply_amount: 1500 },  // 新增
      ])
      expect(rows.value).toHaveLength(2)
      expect(rows.value[1].confirm_index).toBe('C002')
    })
  })

  describe('差异自动计算', () => {
    it('difference = sent_amount - reply_amount（精确小数）', () => {
      const { computeDifference } = createComposable()
      expect(computeDifference({ sent_amount: 100.01, reply_amount: 50.005 })).toBe(50.01)
    })

    it('金额为空时按 0 处理', () => {
      const { computeDifference } = createComposable()
      expect(computeDifference({})).toBe(0)
      expect(computeDifference({ sent_amount: 500 })).toBe(500)
    })
  })

  describe('合计 + 分组', () => {
    it('totals 全表合计', () => {
      const { totals } = createComposable([
        { sent_amount: 1000, reply_amount: 800 },
        { sent_amount: 2000, reply_amount: 2100 },
      ])
      expect(totals.value.sent).toBe(3000)
      expect(totals.value.reply).toBe(2900)
      expect(totals.value.difference).toBe(100) // 200 + (-100)
      expect(totals.value.abs_difference).toBe(300)  // 200 + 100
    })

    it('subjectSummary 按科目分组', () => {
      const { subjectSummary } = createComposable([
        { subject: '应收账款', sent_amount: 1000, reply_amount: 800, diff_type: 'time' },
        { subject: '应收账款', sent_amount: 500, reply_amount: 500 },
        { subject: '应付账款', sent_amount: 3000, reply_amount: 2800, needs_adjustment: true },
      ])
      expect(subjectSummary.value).toHaveLength(2)
      const ar = subjectSummary.value.find((s) => s.subject === '应收账款')!
      expect(ar.count).toBe(2)
      expect(ar.difference_total).toBe(200)
      expect(ar.analyzed_count).toBe(1)
      const ap = subjectSummary.value.find((s) => s.subject === '应付账款')!
      expect(ap.adjustment_count).toBe(1)
    })
  })

  describe('重要性检查', () => {
    it('无配置时不标记超重要性', () => {
      const { isOverMateriality } = createComposable([
        { sent_amount: 999999, reply_amount: 0 },
      ])
      expect(isOverMateriality({ sent_amount: 999999, reply_amount: 0 })).toBe(false)
    })

    it('有配置时差异≥PM 标记', () => {
      const { isOverMateriality } = createComposable(
        [{ sent_amount: 1000, reply_amount: 0 }],
        { materiality_config: { performance_materiality: 500 } }
      )
      expect(isOverMateriality({ sent_amount: 1000, reply_amount: 0 })).toBe(true)
      expect(isOverMateriality({ sent_amount: 600, reply_amount: 500 })).toBe(false)
    })
  })

  describe('metrics 看板', () => {
    it('正确计算已分析率 + 需调整', () => {
      const { metrics } = createComposable([
        { sent_amount: 1000, reply_amount: 800, diff_type: 'time', needs_adjustment: true },
        { sent_amount: 500, reply_amount: 300, diff_type: 'accounting' },
        { sent_amount: 200, reply_amount: 100 },  // 未分类
      ])
      expect(metrics.value.total_count).toBe(3)
      expect(metrics.value.analyzed_rate).toBeCloseTo(66.67, 1)
      expect(metrics.value.adjustment_count).toBe(1)
    })
  })

  describe('buildPayload', () => {
    it('输出 diff-reconcile-v1 格式', () => {
      const { buildPayload, rows } = createComposable([
        { confirm_index: 'C001', sent_amount: 1000, reply_amount: 900 },
      ])
      const payload = buildPayload()
      expect(payload._format).toBe('diff-reconcile-v1')
      expect(payload.rows).toHaveLength(1)
      expect(payload.rows[0].difference).toBe(100)
    })
  })
})
