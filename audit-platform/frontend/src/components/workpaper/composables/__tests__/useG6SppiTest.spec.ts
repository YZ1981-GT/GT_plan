/**
 * Unit Tests — G6-8 SPPI测试 composable
 *
 * Task 8.3: SPPI决策逻辑（任一FAIL→红色）、hasFailedSection计算、section结论推导
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/
 * Validates: Requirements 5.4, 5.5
 * Framework: vitest
 */
import { describe, it, expect } from 'vitest'
import { nextTick } from 'vue'
import {
  useG6SppiTest,
  deriveSectionConclusion,
  deriveOverallConclusion,
  SECTION_DEFINITIONS,
} from '../useG6SppiTest'
import type { SppiItem, SppiSection } from '../useG6SppiTest'

// ─── Helper: 创建测试用SppiItem ─────────────────────────────────────────────

function makeItem(isSPPISatisfied: 'yes' | 'no' | 'na' | null): SppiItem {
  return {
    id: `test-${Math.random().toString(36).slice(2)}`,
    seq: 1,
    checkArea: '测试区域',
    checkItem: '测试项目',
    casRequirement: '',
    contractTermSummary: '',
    isSPPISatisfied,
    judgmentBasis: '',
    riskLevel: null,
    indexRef: '',
    remark: '',
  }
}

function makeSection(id: string, conclusions: ('yes' | 'no' | 'na' | null)[]): SppiSection {
  return {
    id,
    title: `Section ${id}`,
    items: conclusions.map(c => makeItem(c)),
    sectionConclusion: null,
  }
}

// ═══════════════════════════════════════════════════════════════════
// 初始状态测试
// ═══════════════════════════════════════════════════════════════════

describe('Task 8.3: G6-8 SPPI测试', () => {
  describe('初始状态', () => {
    it('应有6个section', () => {
      const { sections } = useG6SppiTest()
      expect(sections.value).toHaveLength(6)
    })

    it('6个section id与SECTION_DEFINITIONS一致', () => {
      const { sections } = useG6SppiTest()
      const ids = sections.value.map(s => s.id)
      const expectedIds = SECTION_DEFINITIONS.map(d => d.id)
      expect(ids).toEqual(expectedIds)
    })

    it('每个section都有默认items', () => {
      const { sections } = useG6SppiTest()
      // principal=5, interest=8, modified_time_value=7, prepayment=7, contractual_linked=6, comprehensive=5
      const expectedCounts = [5, 8, 7, 7, 6, 5]
      sections.value.forEach((section, idx) => {
        expect(section.items.length).toBe(expectedCounts[idx])
      })
    })

    it('初始overallConclusion为null', () => {
      const { overallConclusion } = useG6SppiTest()
      expect(overallConclusion.value).toBeNull()
    })

    it('初始hasFailedSection为false', () => {
      const { hasFailedSection } = useG6SppiTest()
      expect(hasFailedSection.value).toBe(false)
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // deriveSectionConclusion 纯函数测试
  // ═══════════════════════════════════════════════════════════════════

  describe('deriveSectionConclusion 纯函数', () => {
    it("任一 'no' → 'fail'", () => {
      const items = [makeItem('yes'), makeItem('no'), makeItem('yes')]
      expect(deriveSectionConclusion(items)).toBe('fail')
    })

    it("全部 'yes' → 'pass'", () => {
      const items = [makeItem('yes'), makeItem('yes'), makeItem('yes')]
      expect(deriveSectionConclusion(items)).toBe('pass')
    })

    it("混合 'yes'+'na'（有yes） → 'pass'", () => {
      const items = [makeItem('yes'), makeItem('na'), makeItem('yes')]
      expect(deriveSectionConclusion(items)).toBe('pass')
    })

    it("全部 'na' → 'na'", () => {
      const items = [makeItem('na'), makeItem('na'), makeItem('na')]
      expect(deriveSectionConclusion(items)).toBe('na')
    })

    it('有null未填项 → null（未完成）', () => {
      const items = [makeItem('yes'), makeItem(null), makeItem('yes')]
      expect(deriveSectionConclusion(items)).toBeNull()
    })

    it("'no'优先级高于null → 'fail'", () => {
      const items = [makeItem('no'), makeItem(null), makeItem('yes')]
      expect(deriveSectionConclusion(items)).toBe('fail')
    })

    it('空数组 → null', () => {
      expect(deriveSectionConclusion([])).toBeNull()
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // deriveOverallConclusion 纯函数测试
  // ═══════════════════════════════════════════════════════════════════

  describe('deriveOverallConclusion 纯函数', () => {
    it("任一section 'fail' → 'fail'", () => {
      const sections: SppiSection[] = [
        { id: 'a', title: 'A', items: [], sectionConclusion: 'pass' },
        { id: 'b', title: 'B', items: [], sectionConclusion: 'fail' },
        { id: 'c', title: 'C', items: [], sectionConclusion: 'pass' },
      ]
      expect(deriveOverallConclusion(sections)).toBe('fail')
    })

    it("全部 'pass'/'na' → 'pass'", () => {
      const sections: SppiSection[] = [
        { id: 'a', title: 'A', items: [], sectionConclusion: 'pass' },
        { id: 'b', title: 'B', items: [], sectionConclusion: 'na' },
        { id: 'c', title: 'C', items: [], sectionConclusion: 'pass' },
      ]
      expect(deriveOverallConclusion(sections)).toBe('pass')
    })

    it('有section未完成(null) → null', () => {
      const sections: SppiSection[] = [
        { id: 'a', title: 'A', items: [], sectionConclusion: 'pass' },
        { id: 'b', title: 'B', items: [], sectionConclusion: null },
        { id: 'c', title: 'C', items: [], sectionConclusion: 'pass' },
      ]
      expect(deriveOverallConclusion(sections)).toBeNull()
    })

    it("'fail'优先级高于null → 'fail'", () => {
      const sections: SppiSection[] = [
        { id: 'a', title: 'A', items: [], sectionConclusion: 'fail' },
        { id: 'b', title: 'B', items: [], sectionConclusion: null },
      ]
      expect(deriveOverallConclusion(sections)).toBe('fail')
    })

    it('空数组 → null', () => {
      expect(deriveOverallConclusion([])).toBeNull()
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // hasFailedSection / failedSections 计算属性
  // ═══════════════════════════════════════════════════════════════════

  describe('hasFailedSection / failedSections 计算属性', () => {
    it('设置某section结论为fail后 hasFailedSection=true', () => {
      const { sections, hasFailedSection, setSectionConclusion } = useG6SppiTest()
      setSectionConclusion('principal', 'fail')
      expect(hasFailedSection.value).toBe(true)
    })

    it('failedSections 返回失败section列表', () => {
      const { failedSections, setSectionConclusion } = useG6SppiTest()
      setSectionConclusion('interest', 'fail')
      setSectionConclusion('prepayment', 'fail')
      expect(failedSections.value).toHaveLength(2)
      expect(failedSections.value.map(s => s.id)).toContain('interest')
      expect(failedSections.value.map(s => s.id)).toContain('prepayment')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // updateItem 触发重计算
  // ═══════════════════════════════════════════════════════════════════

  describe('updateItem 触发重计算', () => {
    it("设置某item为'no'后section结论重算为'fail'", async () => {
      const { sections, updateItem, recalcConclusions } = useG6SppiTest()
      const firstSection = sections.value[0]
      const firstItem = firstSection.items[0]

      // 先设置所有item为yes
      for (const item of firstSection.items) {
        updateItem(firstSection.id, item.id, 'isSPPISatisfied', 'yes')
      }
      recalcConclusions()
      expect(firstSection.sectionConclusion).toBe('pass')

      // 将第一项改为no
      updateItem(firstSection.id, firstItem.id, 'isSPPISatisfied', 'no')
      recalcConclusions()
      expect(firstSection.sectionConclusion).toBe('fail')
    })

    it('通过watch自动推导（nextTick后）', async () => {
      const { sections, updateItem, overallConclusion } = useG6SppiTest()

      // 将所有section的所有item设为yes
      for (const section of sections.value) {
        for (const item of section.items) {
          updateItem(section.id, item.id, 'isSPPISatisfied', 'yes')
        }
      }
      await nextTick()
      expect(overallConclusion.value).toBe('pass')

      // 将某section的某item设为no
      const targetSection = sections.value[2] // modified_time_value
      updateItem(targetSection.id, targetSection.items[0].id, 'isSPPISatisfied', 'no')
      await nextTick()
      expect(overallConclusion.value).toBe('fail')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // loadData 部分数据（缺失section自动补全）
  // ═══════════════════════════════════════════════════════════════════

  describe('loadData 部分数据', () => {
    it('只提供部分section时缺失的用默认骨架填充', () => {
      const { sections, loadData } = useG6SppiTest()

      // 只提供2个section的数据
      loadData({
        sections: [
          {
            id: 'principal',
            title: '(一) 本金定义',
            items: [
              {
                id: 'custom-1',
                seq: 1,
                checkArea: '本金确认',
                checkItem: '自定义检查项',
                casRequirement: '',
                contractTermSummary: '已填写内容',
                isSPPISatisfied: 'yes',
                judgmentBasis: '',
                riskLevel: null,
                indexRef: '',
                remark: '',
              },
            ],
            sectionConclusion: 'pass',
          },
        ],
        overallConclusion: null,
        hasFailedSection: false,
      })

      // 应有6个section
      expect(sections.value).toHaveLength(6)
      // 第一个section用加载的数据
      expect(sections.value[0].items).toHaveLength(1)
      expect(sections.value[0].items[0].contractTermSummary).toBe('已填写内容')
      // 其余section用默认骨架
      expect(sections.value[1].items.length).toBeGreaterThan(0)
    })

    it('loadData(null) 重置为默认', () => {
      const { sections, overallConclusion, loadData, setSectionConclusion } = useG6SppiTest()

      // 先修改数据
      setSectionConclusion('principal', 'fail')

      // 重置
      loadData(null)
      expect(sections.value).toHaveLength(6)
      expect(overallConclusion.value).toBeNull()
      expect(sections.value[0].sectionConclusion).toBeNull()
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // totalRows = sum of all section items
  // ═══════════════════════════════════════════════════════════════════

  describe('totalRows 计算', () => {
    it('默认totalRows等于所有section items总和', () => {
      const { sections, totalRows } = useG6SppiTest()
      const expectedTotal = sections.value.reduce((sum, s) => sum + s.items.length, 0)
      expect(totalRows.value).toBe(expectedTotal)
      // 5+8+7+7+6+5 = 38
      expect(totalRows.value).toBe(38)
    })

    it('新增item后totalRows增加', () => {
      const { totalRows, addItem } = useG6SppiTest()
      const before = totalRows.value
      addItem('principal', '新区域', '新检查项')
      expect(totalRows.value).toBe(before + 1)
    })

    it('删除item后totalRows减少', () => {
      const { sections, totalRows, removeItem } = useG6SppiTest()
      const before = totalRows.value
      const firstItem = sections.value[0].items[0]
      removeItem('principal', firstItem.id)
      expect(totalRows.value).toBe(before - 1)
    })
  })
})
