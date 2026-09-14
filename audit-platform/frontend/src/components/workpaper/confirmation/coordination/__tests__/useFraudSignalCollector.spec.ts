/**
 * useFraudSignalCollector.spec.ts — 舞弊信号收集单元测试
 *
 * 覆盖：
 * - 信号添加与去重
 * - D0-2 红旗批量添加
 * - D0-7 不可靠信号
 * - D0-3 控制失败信号
 * - D0-1 低回函率信号
 * - 按检查项聚合
 * - 导出为 D0-8 格式
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  useFraudSignalCollector,
  type FraudSignal,
} from '../useFraudSignalCollector'

describe('useFraudSignalCollector — 舞弊信号收集', () => {
  function createInstance(initial: FraudSignal[] = []) {
    const signals = ref<FraudSignal[]>(initial)
    return useFraudSignalCollector({ signals })
  }

  describe('addSignal 基础', () => {
    it('添加信号成功', () => {
      const { addSignal, totalSignals } = createInstance()
      const success = addSignal({
        source: 'D0-2',
        confirm_index: 'IDX-001',
        signalType: 'RED_FLAG_ADDRESS_CLUSTER',
        description: '多家公司同一地址',
        severity: 'high',
      })
      expect(success).toBe(true)
      expect(totalSignals.value).toBe(1)
    })

    it('重复信号被去重', () => {
      const { addSignal, totalSignals } = createInstance()
      addSignal({
        source: 'D0-2',
        confirm_index: 'IDX-001',
        signalType: 'RED_FLAG_ADDRESS_CLUSTER',
        description: '多家公司同一地址',
        severity: 'high',
      })
      const duplicate = addSignal({
        source: 'D0-2',
        confirm_index: 'IDX-001',
        signalType: 'RED_FLAG_ADDRESS_CLUSTER',
        description: '重复添加',
        severity: 'high',
      })
      expect(duplicate).toBe(false)
      expect(totalSignals.value).toBe(1)
    })

    it('不同 confirm_index 不去重', () => {
      const { addSignal, totalSignals } = createInstance()
      addSignal({
        source: 'D0-2',
        confirm_index: 'IDX-001',
        signalType: 'RED_FLAG_ADDRESS_CLUSTER',
        description: 'A',
        severity: 'high',
      })
      addSignal({
        source: 'D0-2',
        confirm_index: 'IDX-002',
        signalType: 'RED_FLAG_ADDRESS_CLUSTER',
        description: 'B',
        severity: 'high',
      })
      expect(totalSignals.value).toBe(2)
    })
  })

  describe('D0-2 红旗批量添加', () => {
    it('批量添加多个红旗', () => {
      const { addD02RedFlags, totalSignals } = createInstance()
      const added = addD02RedFlags('IDX-001', [
        { type: 'RED_FLAG_ADDRESS_CLUSTER', description: '同地址', severity: 'high' },
        { type: 'RED_FLAG_PHONE_ADJACENT', description: '号段相邻', severity: 'medium' },
        { type: 'RED_FLAG_EMPLOYEE_MATCH', description: '撞员工', severity: 'high' },
      ])
      expect(added).toBe(3)
      expect(totalSignals.value).toBe(3)
    })

    it('部分重复时只添加新的', () => {
      const { addD02RedFlags, totalSignals } = createInstance()
      addD02RedFlags('IDX-001', [
        { type: 'RED_FLAG_ADDRESS_CLUSTER', description: '同地址', severity: 'high' },
      ])
      const added = addD02RedFlags('IDX-001', [
        { type: 'RED_FLAG_ADDRESS_CLUSTER', description: '重复', severity: 'high' },
        { type: 'RED_FLAG_SAME_SENDER', description: '同寄件人', severity: 'medium' },
      ])
      expect(added).toBe(1) // 只有 SAME_SENDER 是新的
      expect(totalSignals.value).toBe(2)
    })
  })

  describe('D0-7 不可靠信号', () => {
    it('添加成功并映射到第 7 条', () => {
      const { addD07Unreliable, signals } = createInstance()
      addD07Unreliable('IDX-001', '测试公司A')
      expect(signals.value[0].targetItemNo).toBe(7)
      expect(signals.value[0].severity).toBe('high')
    })
  })

  describe('D0-3 控制失败信号', () => {
    it('添加成功并映射到第 15 条', () => {
      const { addD03ControlFailure, signals } = createInstance()
      addD03ControlFailure('IDX-001', '测试公司B')
      expect(signals.value[0].targetItemNo).toBe(15)
      expect(signals.value[0].source).toBe('D0-3')
    })
  })

  describe('D0-1 低回函率信号', () => {
    it('回函率 < 50% 为 high', () => {
      const { addD01LowReplyRate, signals } = createInstance()
      addD01LowReplyRate(35.5)
      expect(signals.value[0].targetItemNo).toBe(14)
      expect(signals.value[0].severity).toBe('high')
    })

    it('回函率 50-80% 为 medium', () => {
      const { addD01LowReplyRate, signals } = createInstance()
      addD01LowReplyRate(65)
      expect(signals.value[0].severity).toBe('medium')
    })
  })

  describe('按检查项聚合', () => {
    it('signalsByItem 正确分组', () => {
      const { addD02RedFlags, addD07Unreliable, signalsByItem } = createInstance()
      addD02RedFlags('IDX-001', [
        { type: 'RED_FLAG_ADDRESS_CLUSTER', description: 'A', severity: 'high' },
        { type: 'RED_FLAG_PHONE_ADJACENT', description: 'B', severity: 'medium' },
      ])
      addD07Unreliable('IDX-002', '公司C')

      // D0-2 红旗都映射到第 10 条
      expect(signalsByItem.value.get(10)?.length).toBe(2)
      // D0-7 映射到第 7 条
      expect(signalsByItem.value.get(7)?.length).toBe(1)
    })
  })

  describe('hasHighSeverity', () => {
    it('有高严重度信号时为 true', () => {
      const { addD07Unreliable, hasHighSeverity } = createInstance()
      addD07Unreliable('IDX-001', '公司A')
      expect(hasHighSeverity.value).toBe(true)
    })

    it('无高严重度信号时为 false', () => {
      const { addD01LowReplyRate, hasHighSeverity } = createInstance()
      addD01LowReplyRate(70) // medium
      expect(hasHighSeverity.value).toBe(false)
    })
  })

  describe('exportForD08()', () => {
    it('导出格式正确', () => {
      const { addD02RedFlags, addD07Unreliable, exportForD08 } = createInstance()
      addD02RedFlags('IDX-001', [
        { type: 'RED_FLAG_ADDRESS_CLUSTER', description: '地址聚类', severity: 'high' },
      ])
      addD07Unreliable('IDX-002', '公司D')

      const exported = exportForD08()

      // 第 10 条
      const item10 = exported.get(10)
      expect(item10?.exists).toBe('是')
      expect(item10?.index_refs).toContain('IDX-001')
      expect(item10?.note).toContain('地址聚类')

      // 第 7 条
      const item7 = exported.get(7)
      expect(item7?.exists).toBe('是')
      expect(item7?.index_refs).toContain('IDX-002')
    })

    it('聚合信号去重 index_refs', () => {
      const { addD02RedFlags, exportForD08 } = createInstance()
      addD02RedFlags('IDX-001', [
        { type: 'RED_FLAG_ADDRESS_CLUSTER', description: 'A', severity: 'high' },
        { type: 'RED_FLAG_PHONE_ADJACENT', description: 'B', severity: 'medium' },
      ])

      const exported = exportForD08()
      const item10 = exported.get(10)
      // 同一 confirm_index 两个信号，去重后只有一个 ref
      expect(item10?.index_refs).toHaveLength(1)
      expect(item10?.index_refs[0]).toBe('IDX-001')
    })
  })
})
