/**
 * Unit Tests — G6-8 SPPI测试 composable
 *
 * Task 8.3: SPPI决策逻辑（任一FAIL→红色）、hasFailedSection计算、section结论推导
 * 另含：证据完整性闸门、全部不适用不得整体通过、合规陈述骨架
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
  findEvidenceGaps,
  SECTION_DEFINITIONS,
} from '../useG6SppiTest'
import type { SppiItem, SppiSection } from '../useG6SppiTest'

// ─── Helper: 创建测试用SppiItem ─────────────────────────────────────────────

function makeItem(
  isSPPISatisfied: 'yes' | 'no' | 'na' | null,
  extras?: Partial<SppiItem>,
): SppiItem {
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
    ...extras,
  }
}

function fillEvidence(item: SppiItem): void {
  item.contractTermSummary = '合同第X条：……'
  item.judgmentBasis = '与准则要求一致'
  if (item.isSPPISatisfied === 'no' || item.riskLevel === 'high') {
    item.indexRef = 'G6-2'
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
      // principal=10, interest=14, modified_time_value=12, prepayment=12, contractual_linked=12, comprehensive=10
      const expectedCounts = [10, 14, 12, 12, 12, 10]
      sections.value.forEach((section, idx) => {
        expect(section.items.length).toBe(expectedCounts[idx])
      })
    })

    it('默认包含一个投资项目', () => {
      const { instruments } = useG6SppiTest()
      expect(instruments.value).toHaveLength(1)
      expect(instruments.value[0].name).toContain('综合')
    })

    it('默认检查项为合规陈述（不含「是否存在」事实问句）', () => {
      const { sections } = useG6SppiTest()
      const allText = sections.value.flatMap(s => s.items.map(i => i.checkItem)).join('|')
      expect(allText).not.toMatch(/是否存在/)
      expect(allText).not.toMatch(/是否包含/)
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

    it("全部 'pass'/'na'（有pass、无证据缺口） → 'pass'", () => {
      const sections: SppiSection[] = [
        { id: 'a', title: 'A', items: [], sectionConclusion: 'pass' },
        { id: 'b', title: 'B', items: [], sectionConclusion: 'na' },
        { id: 'c', title: 'C', items: [], sectionConclusion: 'pass' },
      ]
      expect(deriveOverallConclusion(sections)).toBe('pass')
    })

    it("全部 'na' → null（不得整体通过）", () => {
      const sections: SppiSection[] = [
        { id: 'a', title: 'A', items: [], sectionConclusion: 'na' },
        { id: 'b', title: 'B', items: [], sectionConclusion: 'na' },
      ]
      expect(deriveOverallConclusion(sections)).toBeNull()
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

    it('判断为yes但缺证据 → 不得pass', () => {
      const item = makeItem('yes')
      const sections: SppiSection[] = [
        {
          id: 'a',
          title: 'A',
          items: [item],
          sectionConclusion: 'pass',
        },
      ]
      expect(findEvidenceGaps(sections).length).toBeGreaterThan(0)
      expect(deriveOverallConclusion(sections)).toBeNull()
    })

    it('requireEvidence=false 时可跳过证据闸门', () => {
      const item = makeItem('yes')
      const sections: SppiSection[] = [
        { id: 'a', title: 'A', items: [item], sectionConclusion: 'pass' },
      ]
      expect(deriveOverallConclusion(sections, { requireEvidence: false })).toBe('pass')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // hasFailedSection / failedSections 计算属性
  // ═══════════════════════════════════════════════════════════════════

  describe('hasFailedSection / failedSections 计算属性', () => {
    it('设置某section结论为fail后 hasFailedSection=true', () => {
      const { hasFailedSection, setSectionConclusion } = useG6SppiTest()
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

      for (const item of firstSection.items) {
        updateItem(firstSection.id, item.id, 'isSPPISatisfied', 'yes')
      }
      recalcConclusions()
      expect(firstSection.sectionConclusion).toBe('pass')

      updateItem(firstSection.id, firstItem.id, 'isSPPISatisfied', 'no')
      recalcConclusions()
      expect(firstSection.sectionConclusion).toBe('fail')
    })

    it('通过watch自动推导（补全证据后 nextTick）', async () => {
      const { sections, updateItem, overallConclusion } = useG6SppiTest()

      for (const section of sections.value) {
        for (const item of section.items) {
          updateItem(section.id, item.id, 'isSPPISatisfied', 'yes')
          updateItem(section.id, item.id, 'contractTermSummary', '摘录条款')
          updateItem(section.id, item.id, 'judgmentBasis', '满足基本借贷安排')
        }
      }
      await nextTick()
      expect(overallConclusion.value).toBe('pass')

      const targetSection = sections.value[2] // modified_time_value
      updateItem(targetSection.id, targetSection.items[0].id, 'isSPPISatisfied', 'no')
      updateItem(targetSection.id, targetSection.items[0].id, 'indexRef', 'G6-2')
      await nextTick()
      expect(overallConclusion.value).toBe('fail')
    })

    it('全部yes但无证据时 overall 仍为 null', async () => {
      const { sections, updateItem, overallConclusion, evidenceGaps } = useG6SppiTest()
      for (const section of sections.value) {
        for (const item of section.items) {
          updateItem(section.id, item.id, 'isSPPISatisfied', 'yes')
        }
      }
      await nextTick()
      expect(evidenceGaps.value.length).toBeGreaterThan(0)
      expect(overallConclusion.value).toBeNull()
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // loadData 部分数据（缺失section自动补全）
  // ═══════════════════════════════════════════════════════════════════

  describe('loadData 部分数据', () => {
    it('只提供部分section时缺失的用默认骨架填充', () => {
      const { sections, loadData } = useG6SppiTest()

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

      expect(sections.value).toHaveLength(6)
      expect(sections.value[0].items).toHaveLength(1)
      expect(sections.value[0].items[0].contractTermSummary).toBe('已填写内容')
      expect(sections.value[1].items.length).toBeGreaterThan(0)
    })

    it('loadData(null) 重置为默认', () => {
      const { sections, overallConclusion, loadData, setSectionConclusion } = useG6SppiTest()

      setSectionConclusion('principal', 'fail')

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
      // 10+14+12+12+12+10 = 70
      expect(totalRows.value).toBe(70)
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

  describe('findEvidenceGaps', () => {
    it('yes 缺摘要/依据 → 缺口', () => {
      const gaps = findEvidenceGaps([
        {
          id: 'a',
          title: 'A',
          sectionConclusion: 'pass',
          items: [makeItem('yes')],
        },
      ])
      expect(gaps[0].missing).toEqual(
        expect.arrayContaining(['contractTermSummary', 'judgmentBasis']),
      )
    })

    it('no 另需 indexRef', () => {
      const item = makeItem('no', {
        contractTermSummary: '有条款',
        judgmentBasis: '不满足',
      })
      const gaps = findEvidenceGaps([
        { id: 'a', title: 'A', sectionConclusion: 'fail', items: [item] },
      ])
      expect(gaps[0].missing).toContain('indexRef')
    })

    it('补全后无缺口', () => {
      const item = makeItem('yes')
      fillEvidence(item)
      expect(
        findEvidenceGaps([
          { id: 'a', title: 'A', sectionConclusion: 'pass', items: [item] },
        ]),
      ).toHaveLength(0)
    })
  })

  describe('多投资项目', () => {
    it('syncFromSeeds 按名称合并并保留已有作答', () => {
      const { instruments, syncFromSeeds, updateItem, sections, activeInstrumentId } = useG6SppiTest()
      const first = sections.value[0].items[0]
      updateItem(sections.value[0].id, first.id, 'isSPPISatisfied', 'yes')
      updateItem(sections.value[0].id, first.id, 'contractTermSummary', '保留摘要')
      const oldName = instruments.value[0].name

      const result = syncFromSeeds([
        { name: oldName },
        { name: '新债券A' },
        { name: '新债券A' }, // 去重
      ])
      expect(result.added).toBe(1)
      expect(instruments.value).toHaveLength(2)
      expect(instruments.value.some(i => i.name === '新债券A')).toBe(true)
      const kept = instruments.value.find(i => i.name === oldName)!
      expect(kept.sections[0].items[0].contractTermSummary).toBe('保留摘要')
      expect(activeInstrumentId.value).toBeTruthy()
    })

    it('syncFromSeeds 优先按稳定 ID 合并并回填', () => {
      const { instruments, syncFromSeeds, updateItem, sections } = useG6SppiTest()
      const first = sections.value[0].items[0]
      updateItem(sections.value[0].id, first.id, 'contractTermSummary', '旧答')
      instruments.value[0].name = '国债A'
      const ephemeralId = instruments.value[0].id

      const result = syncFromSeeds([
        { id: 'stable-1', name: '国债A' },
        { id: 'stable-2', name: '国债A' },
      ])
      expect(result.kept).toBe(1)
      expect(result.added).toBe(1)
      expect(instruments.value).toHaveLength(2)
      expect(instruments.value.map(i => i.id).sort()).toEqual(['stable-1', 'stable-2'])
      const kept = instruments.value.find(i => i.id === 'stable-1')!
      expect(kept.sections[0].items[0].contractTermSummary).toBe('旧答')
      expect(ephemeralId).not.toBe('stable-1')
    })

    it('旧格式仅 sections 可升级为历史项目', () => {
      const { loadData, instruments, toJSON } = useG6SppiTest()
      loadData({
        sections: [
          {
            id: 'principal',
            title: '(一)',
            sectionConclusion: null,
            items: [makeItem('yes', { contractTermSummary: 'x', judgmentBasis: 'y' })],
          },
        ],
        overallConclusion: null,
        hasFailedSection: false,
      } as any)
      expect(instruments.value[0].name).toContain('历史')
      expect(toJSON().instruments?.length).toBe(1)
    })
  })
})
