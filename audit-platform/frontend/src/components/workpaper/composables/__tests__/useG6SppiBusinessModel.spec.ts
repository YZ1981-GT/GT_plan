/**
 * Unit Tests — G6-7 业务模式分析 composable
 *
 * Task 7.3 + 后续改进（关键项加权、覆盖锁、G6-8 交叉、出售汇总）
 */
import { describe, it, expect } from 'vitest'
import { nextTick } from 'vue'
import {
  useG6SppiBusinessModel,
  deriveBusinessModelConclusion,
  evaluateG67G68Consistency,
  buildBusinessModelAiSummary,
  buildG6ClassificationSummary,
  inferCriticalFlag,
} from '../useG6SppiBusinessModel'
import type { BusinessModelSection } from '../useG6SppiBusinessModel'
import { summarizeG62SaleActivity } from '../g6CrossHelpers'

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

    it('默认关键项：管理目标与业绩评价', () => {
      const { section1, section2 } = useG6SppiBusinessModel()
      expect(section1.value.items[0].critical).toBe(true)
      expect(section1.value.items[2].critical).toBe(true)
      expect(section2.value.items[1].critical).toBe(true)
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

  describe('deriveBusinessModelConclusion 纯函数', () => {
    function makeSection(
      satisfiedValues: (boolean | null)[],
      opts?: { criticalIndexes?: number[]; labels?: string[] },
    ): BusinessModelSection {
      return {
        items: satisfiedValues.map((v, i) => ({
          id: `item-${i}`,
          seq: i + 1,
          checkItem: opts?.labels?.[i] || `检查项${i}`,
          auditRequirement: '',
          managementExplanation: '',
          isSatisfied: v,
          auditConclusion: '',
          riskLevel: null,
          indexRef: '',
          critical: opts?.criticalIndexes?.includes(i) || false,
        })),
        sectionConclusion: '',
      }
    }

    it('全部满足 → hold_collect', () => {
      const s1 = makeSection([true, true, true, true, true])
      const s2 = makeSection([true, true, true, true])
      expect(deriveBusinessModelConclusion(s1, s2)).toBe('hold_collect')
    })

    it('非关键不满足 + section2全满足 → hold_and_sell', () => {
      const s1 = makeSection([true, false, true, true, true])
      const s2 = makeSection([true, true, true, true])
      expect(deriveBusinessModelConclusion(s1, s2)).toBe('hold_and_sell')
    })

    it('关键项不满足 → other', () => {
      const s1 = makeSection([false, true, true, true, true], { criticalIndexes: [0] })
      const s2 = makeSection([true, true, true, true])
      expect(deriveBusinessModelConclusion(s1, s2)).toBe('other')
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

    it('inferCriticalFlag 识别管理目标/业绩评价/出售原因', () => {
      expect(inferCriticalFlag('管理金融资产的目标是否为收取合同现金流量')).toBe(true)
      expect(inferCriticalFlag('业绩评价方式是否基于公允价值')).toBe(true)
      expect(inferCriticalFlag('出售原因是否表明业务模式变更')).toBe(true)
      expect(inferCriticalFlag('本期出售的频率和金额')).toBe(false)
    })
  })

  describe('updateIsSatisfied 触发结论推导', () => {
    it('填满所有项为true后结论自动推导为 hold_collect', async () => {
      const { section1, section2, updateIsSatisfied, finalConclusion } = useG6SppiBusinessModel()
      for (const item of section1.value.items) updateIsSatisfied('section1', item.id, true)
      for (const item of section2.value.items) updateIsSatisfied('section2', item.id, true)
      await nextTick()
      expect(finalConclusion.value).toBe('hold_collect')
    })

    it('将section2某项改为false后结论变为 hold_and_sell', async () => {
      const { section1, section2, updateIsSatisfied, finalConclusion } = useG6SppiBusinessModel()
      for (const item of section1.value.items) updateIsSatisfied('section1', item.id, true)
      for (const item of section2.value.items) updateIsSatisfied('section2', item.id, true)
      await nextTick()
      expect(finalConclusion.value).toBe('hold_collect')
      updateIsSatisfied('section2', section2.value.items[0].id, false)
      await nextTick()
      expect(finalConclusion.value).toBe('hold_and_sell')
    })

    it('关键项选否 → other，并默认高风险', async () => {
      const { section1, section2, updateIsSatisfied, finalConclusion } = useG6SppiBusinessModel()
      for (const item of section1.value.items) updateIsSatisfied('section1', item.id, true)
      for (const item of section2.value.items) updateIsSatisfied('section2', item.id, true)
      await nextTick()
      updateIsSatisfied('section1', section1.value.items[0].id, false)
      await nextTick()
      expect(finalConclusion.value).toBe('other')
      expect(section1.value.items[0].riskLevel).toBe('high')
    })

    it('手工覆盖后修改 isSatisfied 不再覆盖 finalConclusion', async () => {
      const {
        section1,
        section2,
        updateIsSatisfied,
        setFinalConclusion,
        finalConclusion,
        manualOverride,
        derivedConclusion,
      } = useG6SppiBusinessModel()

      for (const item of section1.value.items) updateIsSatisfied('section1', item.id, true)
      for (const item of section2.value.items) updateIsSatisfied('section2', item.id, true)
      await nextTick()
      setFinalConclusion('other')
      expect(manualOverride.value).toBe(true)
      updateIsSatisfied('section2', section2.value.items[0].id, false)
      await nextTick()
      expect(derivedConclusion.value).toBe('hold_and_sell')
      expect(finalConclusion.value).toBe('other')
    })

    it('clearManualOverride 恢复自动推导', async () => {
      const {
        section1,
        section2,
        updateIsSatisfied,
        setFinalConclusion,
        clearManualOverride,
        finalConclusion,
        manualOverride,
      } = useG6SppiBusinessModel()

      for (const item of section1.value.items) updateIsSatisfied('section1', item.id, true)
      for (const item of section2.value.items) updateIsSatisfied('section2', item.id, true)
      await nextTick()
      setFinalConclusion('hold_and_sell')
      clearManualOverride()
      expect(manualOverride.value).toBe(false)
      expect(finalConclusion.value).toBe('hold_collect')
    })
  })

  describe('检查项增删与出售预填', () => {
    it('addItem / removeItem', () => {
      const { section1, addItem, removeItem } = useG6SppiBusinessModel()
      const before = section1.value.items.length
      addItem('section1', '自定义检查', '要求')
      expect(section1.value.items).toHaveLength(before + 1)
      const id = section1.value.items[before].id
      expect(removeItem('section1', id)).toBe(true)
      expect(section1.value.items).toHaveLength(before)
    })

    it('removeItem 至少保留一项', () => {
      const { section1, removeItem } = useG6SppiBusinessModel()
      while (section1.value.items.length > 1) {
        removeItem('section1', section1.value.items[0].id)
      }
      expect(removeItem('section1', section1.value.items[0].id)).toBe(false)
      expect(section1.value.items).toHaveLength(1)
    })

    it('applySaleDraft 写入出售频率相关空说明', () => {
      const { applySaleDraft, section1, section2 } = useG6SppiBusinessModel()
      const n = applySaleDraft('出售草稿测试')
      expect(n).toBeGreaterThan(0)
      const filled = [...section1.value.items, ...section2.value.items].filter(
        i => i.managementExplanation === '出售草稿测试',
      )
      expect(filled.length).toBe(n)
    })
  })

  describe('loadData / toJSON round-trip', () => {
    it('toJSON后loadData恢复相同数据', () => {
      const instance1 = useG6SppiBusinessModel()
      instance1.updateIsSatisfied('section1', instance1.section1.value.items[0].id, true)
      instance1.updateIsSatisfied('section2', instance1.section2.value.items[1].id, false)
      instance1.setFinalAnalysis('综合分析说明文本')
      instance1.setFinalConclusion('other')
      const json = instance1.toJSON()
      expect(json.manualOverride).toBe(true)

      const instance2 = useG6SppiBusinessModel()
      instance2.loadData(json)
      expect(instance2.section1.value.items[0].isSatisfied).toBe(true)
      expect(instance2.section2.value.items[1].isSatisfied).toBe(false)
      expect(instance2.finalAnalysis.value).toBe('综合分析说明文本')
      expect(instance2.finalConclusion.value).toBe('other')
      expect(instance2.manualOverride.value).toBe(true)
    })

    it('loadData(null) 重置为默认', () => {
      const { section1, section2, finalConclusion, manualOverride, loadData, setFinalConclusion } =
        useG6SppiBusinessModel()
      section1.value.items[0].isSatisfied = true
      setFinalConclusion('hold_collect')
      loadData(null)
      expect(section1.value.items).toHaveLength(5)
      expect(section2.value.items).toHaveLength(4)
      expect(finalConclusion.value).toBeNull()
      expect(manualOverride.value).toBe(false)
    })
  })

  describe('evaluateG67G68Consistency / AI摘要', () => {
    it('任一侧未完成 → 无提示', () => {
      expect(evaluateG67G68Consistency(null, 'pass').level).toBeNull()
      expect(evaluateG67G68Consistency('hold_and_sell', null).level).toBeNull()
    })

    it('兼有 + SPPI通过 → FVOCI-Debt ok', () => {
      const r = evaluateG67G68Consistency('hold_and_sell', 'pass')
      expect(r.level).toBe('ok')
      expect(r.expectedClassification).toBe('FVOCI-Debt')
    })

    it('业务模式其他 → FVTPL warning', () => {
      const r = evaluateG67G68Consistency('other', 'pass')
      expect(r.level).toBe('warning')
      expect(r.expectedClassification).toBe('FVTPL')
    })

    it('SPPI失败 → FVTPL warning', () => {
      const r = evaluateG67G68Consistency('hold_and_sell', 'fail')
      expect(r.level).toBe('warning')
      expect(r.expectedClassification).toBe('FVTPL')
    })

    it('buildBusinessModelAiSummary 优先收集不满足项', () => {
      const bm = useG6SppiBusinessModel()
      bm.updateIsSatisfied('section1', bm.section1.value.items[0].id, false)
      bm.updateAuditConclusion('section1', bm.section1.value.items[0].id, '目标不符')
      const summary = buildBusinessModelAiSummary(bm.toJSON())
      expect(summary.unsatisfiedOrHighRisk.length).toBeGreaterThan(0)
      expect(summary.unsatisfiedOrHighRisk[0].auditConclusion).toContain('目标不符')
    })
  })

  describe('buildG6ClassificationSummary', () => {
    it('顶层为组合聚合，instruments 为项目级矩阵', () => {
      const summary = buildG6ClassificationSummary({
        businessModel: 'hold_and_sell',
        sppiOverall: 'fail',
        instruments: [
          { id: 'a', name: '债A', overallConclusion: 'pass' },
          { id: 'b', name: '债B', overallConclusion: 'fail' },
        ],
        source: 'G6-8',
      })
      expect(summary.expectedClassification).toBe('FVTPL')
      expect(summary.accountConflict).toBe(true)
      expect(summary.instruments).toHaveLength(2)
      expect(summary.instruments![0].expectedClassification).toBe('FVOCI-Debt')
      expect(summary.instruments![0].accountConflict).toBe(false)
      expect(summary.instruments![1].expectedClassification).toBe('FVTPL')
      expect(summary.instruments![1].accountConflict).toBe(true)
    })
  })

  describe('summarizeG62SaleActivity', () => {
    it('优先使用 periodDecrease', () => {
      const s = summarizeG62SaleActivity([
        { investProject: '债A', openingSubtotal: 1000, periodDecrease: 200, periodCostChange: 50 },
      ])
      expect(s.method).toBe('periodDecrease')
      expect(s.decreaseProxy).toBe(200)
      expect(s.ratio).toBeCloseTo(0.2)
      expect(s.draftText).toContain('预填')
    })

    it('无 periodDecrease 时用负成本变动代理', () => {
      const s = summarizeG62SaleActivity([
        { investProject: '债B', openingCost: 500, periodCostChange: -80 },
      ])
      expect(s.method).toBe('negativeCostChange')
      expect(s.decreaseProxy).toBe(80)
    })
  })

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

    it('两个section都完成后 isComplete=true', () => {
      const { section1, section2, isComplete, unansweredCount, updateIsSatisfied } =
        useG6SppiBusinessModel()
      for (const item of section1.value.items) updateIsSatisfied('section1', item.id, true)
      for (const item of section2.value.items) updateIsSatisfied('section2', item.id, true)
      expect(unansweredCount.value).toBe(0)
      expect(isComplete.value).toBe(true)
    })
  })
})
