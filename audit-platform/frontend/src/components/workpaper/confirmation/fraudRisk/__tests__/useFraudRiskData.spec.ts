/**
 * useFraudRiskData.spec.ts — D0-8 舞弊风险评价表 composable 单元测试
 */
import { describe, it, expect } from 'vitest'
import { useFraudRiskData } from '../composables/useFraudRiskData'
import { PRESET_FRAUD_ITEMS } from '../fraudRiskPresets'
import type { FraudRiskPayload, FraudRiskRow } from '../fraudRiskTypes'

function createComposable(htmlData: any = null) {
  return useFraudRiskData({
    htmlData: () => htmlData,
    readonly: false,
  })
}

describe('useFraudRiskData', () => {
  describe('初始化', () => {
    it('无数据时应初始化 19 条预置条目', () => {
      const data = createComposable(null)
      expect(data.items.value).toHaveLength(PRESET_FRAUD_ITEMS.length)
      expect(data.items.value[0]._preset).toBe(true)
      expect(data.items.value[0].seq).toBe(1)
      expect(data.items.value[0].is_exist).toBe('')
    })

    it('空对象时应初始化 19 条预置条目', () => {
      const data = createComposable({})
      expect(data.items.value).toHaveLength(19)
    })

    it('已有数据时应合并预置+自定义不覆盖', () => {
      const existing: FraudRiskPayload = {
        _format: 'fraud-risk-d08-v1',
        items: [
          {
            _row_id: 'existing-1',
            seq: 1,
            // 存量项目落库的是**旧版自造预置文字**（预置行 description 在 UI 上只读，
            // 用户无法编辑它）→ 合并时必须被最新预置文字取代，否则 2026-08-03 按
            // 源模板的更正传不到既有项目。用户数据只有下面三项。
            description: '被审计单位管理层凌驾于内部控制之上',
            is_exist: '是',
            source_ref: 'D0-1',
            countermeasure: '扩大样本',
            _preset: true,
          },
          {
            _row_id: 'custom-1',
            seq: 20,
            description: '自定义风险1',
            is_exist: '否',
            _preset: false,
          },
        ],
        summary: { statement_level_risk: '低' },
        conclusion: { conclusion_type: 'A' },
      }
      const data = createComposable(existing)

      // 预置 19 条 + 1 自定义 = 20 条
      expect(data.items.value).toHaveLength(20)

      // 第1条：用户数据保留，description 取最新预置（源模板逐字）
      const item1 = data.items.value.find((i) => i.seq === 1)!
      expect(item1.description).toBe('管理层不允许寄发询证函')
      expect(item1.description).not.toBe('被审计单位管理层凌驾于内部控制之上')
      expect(item1.is_exist).toBe('是')
      expect(item1.source_ref).toBe('D0-1')
      expect(item1.countermeasure).toBe('扩大样本')

      // 自定义条目保留
      const custom = data.items.value.find((i) => i.seq === 20)!
      expect(custom.description).toBe('自定义风险1')
      expect(custom._preset).toBe(false)

      // summary/conclusion 保留
      expect(data.summary.value.statement_level_risk).toBe('低')
      expect(data.conclusion.value.conclusion_type).toBe('A')
    })
  })

  describe('CRUD', () => {
    it('addItem 应添加自定义条目', () => {
      const data = createComposable(null)
      const before = data.items.value.length
      const newItem = data.addItem()

      expect(data.items.value).toHaveLength(before + 1)
      expect(newItem._preset).toBe(false)
      expect(newItem.seq).toBe(20)
      expect(data.isDirty.value).toBe(true)
    })

    it('deleteItem 不应删除预置条目', () => {
      const data = createComposable(null)
      const presetId = data.items.value[0]._row_id!
      data.deleteItem(presetId)
      expect(data.items.value).toHaveLength(19) // 仍然 19
    })

    it('deleteItem 应删除自定义条目', () => {
      const data = createComposable(null)
      const newItem = data.addItem()
      expect(data.items.value).toHaveLength(20)

      data.deleteItem(newItem._row_id!)
      expect(data.items.value).toHaveLength(19)
    })

    it('updateItem 应更新字段并标脏', () => {
      const data = createComposable(null)
      const rowId = data.items.value[2]._row_id!

      data.isDirty.value = false
      data.updateItem(rowId, 'is_exist', '是')
      expect(data.items.value[2].is_exist).toBe('是')
      expect(data.isDirty.value).toBe(true)
    })
  })

  describe('条件高亮', () => {
    it('is_exist=是 时行应高亮', () => {
      const data = createComposable(null)
      data.items.value[0].is_exist = '是'
      expect(data.isHighlighted(data.items.value[0])).toBe(true)
    })

    it('is_exist=否 时行不高亮', () => {
      const data = createComposable(null)
      data.items.value[0].is_exist = '否'
      expect(data.isHighlighted(data.items.value[0])).toBe(false)
    })

    it('is_exist=是 且应对空时需要警示', () => {
      const data = createComposable(null)
      data.items.value[0].is_exist = '是'
      data.items.value[0].countermeasure = ''
      expect(data.needsCountermeasure(data.items.value[0])).toBe(true)
    })

    it('is_exist=是 且应对已填时无需警示', () => {
      const data = createComposable(null)
      data.items.value[0].is_exist = '是'
      data.items.value[0].countermeasure = '扩大样本'
      expect(data.needsCountermeasure(data.items.value[0])).toBe(false)
    })
  })

  describe('看板指标', () => {
    it('初始状态所有指标为零（除 total）', () => {
      const data = createComposable(null)
      expect(data.metrics.value.total_count).toBe(19)
      expect(data.metrics.value.exist_count).toBe(0)
      expect(data.metrics.value.with_measure_count).toBe(0)
      expect(data.metrics.value.without_measure_count).toBe(0)
      expect(data.metrics.value.completion_rate).toBe(0)
    })

    it('标记若干条为"是"后指标正确', () => {
      const data = createComposable(null)
      data.items.value[0].is_exist = '是'
      data.items.value[0].countermeasure = '已填'
      data.items.value[1].is_exist = '是'
      data.items.value[1].countermeasure = ''
      data.items.value[2].is_exist = '否'

      expect(data.metrics.value.exist_count).toBe(2)
      expect(data.metrics.value.with_measure_count).toBe(1)
      expect(data.metrics.value.without_measure_count).toBe(1)
      // 3 条已评估 / 19 条
      expect(data.metrics.value.completion_rate).toBeCloseTo(15.79, 1)
    })
  })

  describe('buildPayload', () => {
    it('应输出正确的 _format', () => {
      const data = createComposable(null)
      const payload = data.buildPayload()
      expect(payload._format).toBe('fraud-risk-d08-v1')
      expect(payload.items).toHaveLength(19)
    })

    it('应包含 summary 和 conclusion', () => {
      const data = createComposable(null)
      data.summary.value = { statement_level_risk: '中' }
      data.conclusion.value = { conclusion_type: 'B' }

      const payload = data.buildPayload()
      expect(payload.summary.statement_level_risk).toBe('中')
      expect(payload.conclusion.conclusion_type).toBe('B')
    })
  })

  describe('importItems', () => {
    it('应追加自定义条目', () => {
      const data = createComposable(null)
      data.importItems([
        { seq: 0, description: '导入1', _preset: false } as FraudRiskRow,
        { seq: 0, description: '导入2', _preset: false } as FraudRiskRow,
      ])
      expect(data.items.value).toHaveLength(21)
      expect(data.items.value[19].description).toBe('导入1')
      expect(data.items.value[20].description).toBe('导入2')
      expect(data.isDirty.value).toBe(true)
    })
  })
})
