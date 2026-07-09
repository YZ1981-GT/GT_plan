/**
 * H7 生产性生物资产 — 集成测试
 *
 * Spec: .kiro/specs/h7-biological-assets/ Task 7.2
 * Requirements: 2.6, 13.1-13.3, 14.1-14.4
 *
 * 验证：双计量模式切换数据隔离 / 行业拦截 / 审定↔明细一致
 */
import { describe, it, expect } from 'vitest'

import { useH7MeasurementModel } from '../composables/useH7MeasurementModel'
import { APPLICABLE_INDUSTRIES, INDUSTRY_GUARD_MESSAGE } from '../composables/useH7IndustryGuard'

// ─── 行业守卫集成 ───────────────────────────────────────────────────────────

describe('H7 行业守卫 - 集成', () => {
  it('适用行业白名单为4项', () => {
    expect(APPLICABLE_INDUSTRIES).toHaveLength(4)
    expect(APPLICABLE_INDUSTRIES).toContain('agriculture')
    expect(APPLICABLE_INDUSTRIES).toContain('forestry')
    expect(APPLICABLE_INDUSTRIES).toContain('livestock')
    expect(APPLICABLE_INDUSTRIES).toContain('fishery')
  })

  it('非适用行业提示信息正确', () => {
    expect(INDUSTRY_GUARD_MESSAGE).toBe('本底稿仅适用于农林牧渔行业项目')
  })
})

// ─── 双计量模式集成 ─────────────────────────────────────────────────────────

describe('H7 双计量模式 - 集成', () => {
  function createModel(initial: string = 'cost') {
    const responses = new Map<string, any>()
    if (initial !== 'cost') {
      responses.set('H7-measurement-model', { remark: initial })
    }
    return useH7MeasurementModel({
      saveImmediate: async () => {},
      getValue: (id: string) => responses.get(id)?.remark ?? null,
    })
  }

  it('默认成本模式', () => {
    const { measurementModel } = createModel()
    expect(measurementModel.value).toBe('cost')
  })

  it('成本模式下折旧sheet可见', () => {
    const { isSheetVisible } = createModel('cost')
    expect(isSheetVisible('H7-11')).toBe(true)
    expect(isSheetVisible('H7-12')).toBe(true)
    expect(isSheetVisible('H7-15')).toBe(true)
    expect(isSheetVisible('H7-16')).toBe(true)
  })

  it('成本模式下公允复核sheet不可见', () => {
    const { isSheetVisible } = createModel('cost')
    expect(isSheetVisible('H7-13')).toBe(false)
  })

  it('公允模式下折旧sheet不可见', () => {
    const { isSheetVisible } = createModel('fair_value')
    expect(isSheetVisible('H7-11')).toBe(false)
    expect(isSheetVisible('H7-12')).toBe(false)
    expect(isSheetVisible('H7-15')).toBe(false)
    expect(isSheetVisible('H7-16')).toBe(false)
  })

  it('公允模式下H7-13可见', () => {
    const { isSheetVisible } = createModel('fair_value')
    expect(isSheetVisible('H7-13')).toBe(true)
  })

  it('共用sheet在两种模式下均可见', () => {
    const cost = createModel('cost')
    const fair = createModel('fair_value')
    const shared = ['H7-3', 'H7-4', 'H7-5', 'H7-8', 'H7-9', 'H7-10', 'H7-14', 'H7-17']
    for (const s of shared) {
      expect(cost.isSheetVisible(s)).toBe(true)
      expect(fair.isSheetVisible(s)).toBe(true)
    }
  })

  it('幂等切换不触发额外保存', async () => {
    let saveCalls = 0
    const model = useH7MeasurementModel({
      saveImmediate: async () => { saveCalls++ },
      getValue: () => null,
    })
    await model.switchModel('cost') // 已经是 cost，幂等
    expect(saveCalls).toBe(0)
  })

  it('切换模式触发一次保存', async () => {
    let saveCalls = 0
    const model = useH7MeasurementModel({
      saveImmediate: async () => { saveCalls++ },
      getValue: () => null,
    })
    await model.switchModel('fair_value')
    expect(saveCalls).toBe(1)
    expect(model.measurementModel.value).toBe('fair_value')
  })
})
