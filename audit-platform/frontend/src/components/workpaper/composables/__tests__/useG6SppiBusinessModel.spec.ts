/**
 * Unit Tests — G6-7 业务模式分析 composable
 *
 * Task 7.3: 三section数据结构、综合判断推导逻辑
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/
 * Validates: Requirements 4.2
 * Framework: vitest
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import {
  useG6SppiBusinessModel,
  deriveBusinessModelConclusion,
} from '../useG6SppiBusinessModel'
import type { BusinessModelSection } from '../useG6SppiBusinessModel'

// ═══════════════════════════════════════════════════════════════════
// 初始状态测试
// ═══════════════════════════════════════════════════════════════════

describe('Task 7.3: G6-7 业务模式分析', () => {
  describe('初始状态', () => {
    it('section1 应有5个默认检查项', () => {
      const { section1 } = useG6SppiBusinessModel()
      expect(section1.value.items).toHaveLength(5)
    })

    it('section2 应有4个默认检查项', () => {
      const { section2 } = useG6SppiBusinessModel()
      expect(section2.value.items).toHaveLength(4)
    })

    it('所有检查项初始 isSatisfied 为 null', () => {
      const { section1, section2 } = useG6SppiBusinessModel()
      const allItems = [...section1.value.items, ...section2.value.items]
      expect(allItems.every(i => i.isSatisfied === null)).toBe(true)
    })

    it('初始 finalConclusion 为 null', () => {
      const { finalConclusion } = useG6SppiBusinessModel()
      expect(finalConclusion.value).toBeNull()
    })

    it('初始 isComplete 为 false', () => {
      const { isComplete } = useG6SppiBusinessModel()
      expect(isComplete.value).toBe(false)
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // deriveBusinessModelConclusion 纯函数测试
  // ═══════════════════════════════════════════════════════════════════

  describe('deriveBusinessModelConclusion 纯函数', () => {
    function makeSection(satisfiedValues: (boolean | null)[]): BusinessModelSection {
      return {
        items: satisfiedValues.map((v, i) => ({
          id: `item-${i}`,
          seq: i + 1,
          checkItem: `检查项${i}`,
          auditRequirement: '',
          managementExplanation: '',
          isSatisfied: v,
          auditConclusion: '',
          riskLevel: null,
          indexRef: '',
        })),
        sectionConclusion: '',
      }
    }

    it('全部满足 → hold_collect', () => {
      const s1 = makeSection([true, true, true, true, true])
      const s2 = makeSection([true, true, true, true])
      expect(deriveBusinessModelConclusion(s1, s2)).toBe('hold_collect')
    })

    it('section1有不满足 + section2全满足 → hold_and_sell', () => {
      const s1 = makeSection([true, false, true, true, true])
      const s2 = makeSection([true, true, true, true])
      expect(deriveBusinessModelConclusion(s1, s2)).toBe('hold_and_sell')
    })

    it('section1全满足 + section2有不满足 → hold_and_sell', () => {
      const s1 = makeSection([true, true, true, true, true])
      const s2 = makeSection([true, false, true, true])
      expect(deriveBusinessModelConclusion(s1, s2)).toBe('hold_and_sell')
    })

    it('section1有不满足 + section2有不满足 → other', () => {
      const s1 = makeSection([true, false, true, true, true])
      const s2 = makeSection([true, false, true, true])
      expect(deriveBusinessModelConclusion(s1, s2)).toBe('other')
    })

    it('存在未回答项(null) → null(未完成)', () => {
      const s1 = makeSection([true, null, true, true, true])
      const s2 = makeSection([true, true, true, true])
      expect(deriveBusinessModelConclusion(s1, s2)).toBeNull()
    })

    it('section2存在未回答项 → null', () => {
      const s1 = makeSection([true, true, true, true, true])
      const s2 = makeSection([true, true, null, true])
      expect(deriveBusinessModelConclusion(s1, s2)).toBeNull()
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // updateIsSatisfied 触发结论重新推导
  // ═══════════════════════════════════════════════════════════════════

  describe('updateIsSatisfied 触发结论推导', () => {
    it('填满所有项为true后结论自动推导为 hold_collect', async () => {
      const { section1, section2, updateIsSatisfied, finalConclusion } = useG6SppiBusinessModel()

      // 填满section1
      for (const item of section1.value.items) {
        updateIsSatisfied('section1', item.id, true)
      }
      // 填满section2
      for (const item of section2.value.items) {
        updateIsSatisfied('section2', item.id, true)
      }

      await nextTick()
      expect(finalConclusion.value).toBe('hold_collect')
    })

    it('将section2某项改为false后结论变为 hold_and_sell', async () => {
      const { section1, section2, updateIsSatisfied, finalConclusion } = useG6SppiBusinessModel()

      // 先全部满足
      for (const item of section1.value.items) {
        updateIsSatisfied('section1', item.id, true)
      }
      for (const item of section2.value.items) {
        updateIsSatisfied('section2', item.id, true)
      }
      await nextTick()
      expect(finalConclusion.value).toBe('hold_collect')

      // 将section2第一项改为false
      updateIsSatisfied('section2', section2.value.items[0].id, false)
      await nextTick()
      expect(finalConclusion.value).toBe('hold_and_sell')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // loadData / toJSON round-trip
  // ═══════════════════════════════════════════════════════════════════

  describe('loadData / toJSON round-trip', () => {
    it('toJSON后loadData恢复相同数据', () => {
      const instance1 = useG6SppiBusinessModel()

      // 修改一些数据
      instance1.updateIsSatisfied('section1', instance1.section1.value.items[0].id, true)
      instance1.updateIsSatisfied('section2', instance1.section2.value.items[1].id, false)
      instance1.setFinalAnalysis('综合分析说明文本')

      const json = instance1.toJSON()

      // 新实例加载数据
      const instance2 = useG6SppiBusinessModel()
      instance2.loadData(json)

      expect(instance2.section1.value.items[0].isSatisfied).toBe(true)
      expect(instance2.section2.value.items[1].isSatisfied).toBe(false)
      expect(instance2.finalAnalysis.value).toBe('综合分析说明文本')
    })

    it('loadData(null) 重置为默认', () => {
      const { section1, section2, finalConclusion, loadData } = useG6SppiBusinessModel()

      // 先设置一些数据
      section1.value.items[0].isSatisfied = true
      finalConclusion.value = 'hold_collect'

      // 重置
      loadData(null)

      expect(section1.value.items).toHaveLength(5)
      expect(section2.value.items).toHaveLength(4)
      expect(finalConclusion.value).toBeNull()
      expect(section1.value.items[0].isSatisfied).toBeNull()
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // completionRate 计算属性
  // ═══════════════════════════════════════════════════════════════════

  describe('completionRate 计算属性', () => {
    it('section1完成度: 0/5=0%', () => {
      const { section1CompletionRate } = useG6SppiBusinessModel()
      expect(section1CompletionRate.value).toBe(0)
    })

    it('section1回答2项后完成度: 2/5=40%', () => {
      const { section1, section1CompletionRate, updateIsSatisfied } = useG6SppiBusinessModel()
      updateIsSatisfied('section1', section1.value.items[0].id, true)
      updateIsSatisfied('section1', section1.value.items[1].id, false)
      expect(section1CompletionRate.value).toBe(40)
    })

    it('section2全部回答后完成度: 4/4=100%', () => {
      const { section2, section2CompletionRate, updateIsSatisfied } = useG6SppiBusinessModel()
      for (const item of section2.value.items) {
        updateIsSatisfied('section2', item.id, true)
      }
      expect(section2CompletionRate.value).toBe(100)
    })

    it('两个section都完成后 isComplete=true', () => {
      const { section1, section2, isComplete, updateIsSatisfied } = useG6SppiBusinessModel()
      for (const item of section1.value.items) {
        updateIsSatisfied('section1', item.id, true)
      }
      for (const item of section2.value.items) {
        updateIsSatisfied('section2', item.id, true)
      }
      expect(isComplete.value).toBe(true)
    })
  })
})
