/**
 * useD01DiffImport 单测
 * 覆盖：映射 + 去重 + 未回函过滤 + 降级
 */
import { describe, it, expect, vi } from 'vitest'
import { useD01DiffImport } from '../useD01DiffImport'
import type { ConfirmationRow } from '../../../confirmationTypes'

describe('useD01DiffImport', () => {
  describe('mapD01Row', () => {
    it('已回函+差异≠0 映射成功', () => {
      const onImport = vi.fn()
      const { mapD01Row } = useD01DiffImport({
        existingIndexes: () => new Set(),
        onImport,
      })
      const result = mapD01Row({
        confirm_index: 'C001',
        entity_name: '测试公司',
        account_type: '应收账款',
        amount: 1000,
        reply_amount: 800,
        is_replied: true,
      })
      expect(result).not.toBeNull()
      expect(result!.confirm_index).toBe('C001')
      expect(result!.subject).toBe('应收账款')
      expect(result!.sent_amount).toBe(1000)
      expect(result!.reply_amount).toBe(800)
      expect(result!.difference).toBe(200)
      expect(result!._source).toBe('auto')
    })

    it('未回函行返回 null', () => {
      const onImport = vi.fn()
      const { mapD01Row } = useD01DiffImport({
        existingIndexes: () => new Set(),
        onImport,
      })
      const result = mapD01Row({
        confirm_index: 'C002',
        amount: 1000,
        reply_amount: 0,
        is_replied: false,
      })
      expect(result).toBeNull()
    })

    it('差异=0 行返回 null', () => {
      const onImport = vi.fn()
      const { mapD01Row } = useD01DiffImport({
        existingIndexes: () => new Set(),
        onImport,
      })
      const result = mapD01Row({
        confirm_index: 'C003',
        amount: 500,
        reply_amount: 500,
        is_replied: true,
      })
      expect(result).toBeNull()
    })
  })

  describe('fetchAndImport', () => {
    it('正确过滤+去重+导入', () => {
      const onImport = vi.fn()
      const { fetchAndImport, lastImportCount } = useD01DiffImport({
        existingIndexes: () => new Set(['C001']),  // C001 已有
        onImport,
      })

      const d01Rows: ConfirmationRow[] = [
        { confirm_index: 'C001', amount: 1000, reply_amount: 800, is_replied: true },  // 去重
        { confirm_index: 'C002', amount: 2000, reply_amount: 1500, is_replied: true }, // 导入
        { confirm_index: 'C003', amount: 500, reply_amount: 500, is_replied: true },   // 差异=0
        { confirm_index: 'C004', amount: 300, reply_amount: 0, is_replied: false },    // 未回函
      ]

      fetchAndImport(d01Rows)

      expect(onImport).toHaveBeenCalledTimes(1)
      const imported = onImport.mock.calls[0][0]
      expect(imported).toHaveLength(1)
      expect(imported[0].confirm_index).toBe('C002')
      expect(lastImportCount.value).toBe(1)
    })

    it('D0-1 数据为空时不调用 onImport', () => {
      const onImport = vi.fn()
      const { fetchAndImport, lastImportCount } = useD01DiffImport({
        existingIndexes: () => new Set(),
        onImport,
      })

      fetchAndImport([])
      expect(onImport).not.toHaveBeenCalled()
      expect(lastImportCount.value).toBe(0)
    })
  })
})
