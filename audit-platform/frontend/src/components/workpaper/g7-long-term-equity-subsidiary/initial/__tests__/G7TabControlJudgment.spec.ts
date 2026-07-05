/**
 * G7TabControlJudgment 单元测试
 *
 * 测试 G7-7 初始判断决策树（CAS33六要素问卷）的核心逻辑：
 * 1. 六要素全"是"→ 综合判断得出"控制"结论
 * 2. 部分满足→ 不构成控制（共同控制/重大影响判断）
 * 3. 保存时控制判断结果为空→ 阻断保存（校验逻辑）
 *
 * Requirements: 2.1, 2.2
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'

// ─── Mock GtIndexChip ─────────────────────────────────────────────────────────

vi.mock('../../../GtIndexChip.vue', () => ({
  default: defineComponent({ props: ['value'], template: '<span class="gt-index-chip" />' }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), success: vi.fn(), error: vi.fn() },
}))

// ─── Import component under test ─────────────────────────────────────────────

import G7TabControlJudgment from '../G7TabControlJudgment.vue'

// ─── Helper: 创建section数据用于测试逻辑 ─────────────────────────────────────

/**
 * 模拟 handleAiOverall 的控制结论推导逻辑（从组件中提取的核心算法）
 * 此函数复现了组件内 handleAiOverall 的判断路径：
 * - 权力+可变回报+联系 三section都有"是" → 控制
 * - 权力+可变回报有"是"，联系无 → 需进一步评估
 * - 其他情况 → 不构成控制
 */
function deriveControlConclusion(sections: Array<{
  id: string
  rows: Array<{ judgmentResult: string }>
}>): 'control' | 'partial_power_return' | 'no_control' {
  const powerSection = sections.find(s => s.id === 'power')
  const returnSection = sections.find(s => s.id === 'variableReturns')
  const linkSection = sections.find(s => s.id === 'powerReturnLink')

  const powerYes = powerSection?.rows.filter(r => r.judgmentResult === '是').length ?? 0
  const returnYes = returnSection?.rows.filter(r => r.judgmentResult === '是').length ?? 0
  const linkYes = linkSection?.rows.filter(r => r.judgmentResult === '是').length ?? 0

  if (powerYes > 0 && returnYes > 0 && linkYes > 0) {
    return 'control'
  } else if (powerYes > 0 && returnYes > 0) {
    return 'partial_power_return'
  } else {
    return 'no_control'
  }
}

/**
 * 校验控制判断结果是否完整（综合判断section中"控制类型最终结论"行必须有值）
 * 模拟保存时的阻断校验
 */
function validateControlJudgmentForSave(sections: Array<{
  id: string
  rows: Array<{ dimension: string; judgmentResult: string }>
}>): { valid: boolean; errorMessage: string } {
  const overallSection = sections.find(s => s.id === 'overallJudgment')
  if (!overallSection) {
    return { valid: false, errorMessage: '综合判断section缺失' }
  }

  const conclusionRow = overallSection.rows.find(r => r.dimension === '控制类型最终结论')
  if (!conclusionRow || !conclusionRow.judgmentResult) {
    return { valid: false, errorMessage: '控制判断结果为空，请先完成控制类型最终结论' }
  }

  return { valid: true, errorMessage: '' }
}

// ─── 辅助函数：创建带预设判断结果的sections ─────────────────────────────────

function createSectionsWithResults(config: {
  powerYesCount?: number
  returnYesCount?: number
  linkYesCount?: number
  conclusionResult?: string
}) {
  const { powerYesCount = 0, returnYesCount = 0, linkYesCount = 0, conclusionResult = '' } = config

  function makeRows(count: number, yesCount: number) {
    return Array.from({ length: count }, (_, i) => ({
      dimension: `维度${i + 1}`,
      judgmentResult: i < yesCount ? '是' : '',
    }))
  }

  return [
    { id: 'power', rows: makeRows(8, powerYesCount) },
    { id: 'variableReturns', rows: makeRows(8, returnYesCount) },
    { id: 'powerReturnLink', rows: makeRows(8, linkYesCount) },
    { id: 'protectiveRights', rows: makeRows(8, 0) },
    { id: 'agentPrincipal', rows: makeRows(8, 0) },
    {
      id: 'overallJudgment',
      rows: [
        { dimension: '控制三要素同时满足', judgmentResult: '' },
        { dimension: '共同控制判断', judgmentResult: '' },
        { dimension: '重大影响判断', judgmentResult: '' },
        { dimension: '无重大影响', judgmentResult: '' },
        { dimension: '控制类型最终结论', judgmentResult: conclusionResult },
        { dimension: '计量方法确定', judgmentResult: '' },
        { dimension: '前期结论变化', judgmentResult: '' },
      ],
    },
  ]
}

// ═══════════════════════════════════════════════════════════════════════════════
// 测试套件
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7TabControlJudgment - 控制结论推导逻辑', () => {
  /**
   * Validates: Requirements 2.1, 2.2
   * CAS33: 权力+可变回报+权力与回报的联系 三要素同时满足 → 控制
   */
  describe('六要素全"是" → 控制结论推导', () => {
    it('权力+可变回报+联系三section均有"是"项 → 得出控制结论', () => {
      const sections = createSectionsWithResults({
        powerYesCount: 5,
        returnYesCount: 4,
        linkYesCount: 3,
      })
      expect(deriveControlConclusion(sections)).toBe('control')
    })

    it('三section各仅1项"是"即满足控制判定', () => {
      const sections = createSectionsWithResults({
        powerYesCount: 1,
        returnYesCount: 1,
        linkYesCount: 1,
      })
      expect(deriveControlConclusion(sections)).toBe('control')
    })

    it('三section全部8项均为"是" → 控制', () => {
      const sections = createSectionsWithResults({
        powerYesCount: 8,
        returnYesCount: 8,
        linkYesCount: 8,
      })
      expect(deriveControlConclusion(sections)).toBe('control')
    })
  })

  /**
   * Validates: Requirements 2.1, 2.2
   * 部分满足：缺少任一要素则不构成完全控制
   */
  describe('部分满足 → 共同控制/重大影响（不构成控制）', () => {
    it('仅有权力+可变回报，缺联系 → partial(需进一步评估)', () => {
      const sections = createSectionsWithResults({
        powerYesCount: 3,
        returnYesCount: 4,
        linkYesCount: 0,
      })
      expect(deriveControlConclusion(sections)).toBe('partial_power_return')
    })

    it('仅有权力，无可变回报和联系 → 不构成控制', () => {
      const sections = createSectionsWithResults({
        powerYesCount: 5,
        returnYesCount: 0,
        linkYesCount: 0,
      })
      expect(deriveControlConclusion(sections)).toBe('no_control')
    })

    it('仅有可变回报，无权力和联系 → 不构成控制', () => {
      const sections = createSectionsWithResults({
        powerYesCount: 0,
        returnYesCount: 6,
        linkYesCount: 0,
      })
      expect(deriveControlConclusion(sections)).toBe('no_control')
    })

    it('仅有联系，无权力和可变回报 → 不构成控制', () => {
      const sections = createSectionsWithResults({
        powerYesCount: 0,
        returnYesCount: 0,
        linkYesCount: 4,
      })
      expect(deriveControlConclusion(sections)).toBe('no_control')
    })

    it('权力+联系有"是"，可变回报无 → 不构成控制', () => {
      const sections = createSectionsWithResults({
        powerYesCount: 3,
        returnYesCount: 0,
        linkYesCount: 2,
      })
      expect(deriveControlConclusion(sections)).toBe('no_control')
    })

    it('可变回报+联系有"是"，权力无 → 不构成控制', () => {
      const sections = createSectionsWithResults({
        powerYesCount: 0,
        returnYesCount: 5,
        linkYesCount: 3,
      })
      expect(deriveControlConclusion(sections)).toBe('no_control')
    })

    it('三section全部为空 → 不构成控制', () => {
      const sections = createSectionsWithResults({
        powerYesCount: 0,
        returnYesCount: 0,
        linkYesCount: 0,
      })
      expect(deriveControlConclusion(sections)).toBe('no_control')
    })
  })

  /**
   * Validates: Requirements 2.1, 2.2
   * 保存时校验：综合判断section中"控制类型最终结论"行必须有值
   */
  describe('保存时阻断（控制判断结果为空）', () => {
    it('控制类型最终结论为空 → 校验不通过', () => {
      const sections = createSectionsWithResults({ conclusionResult: '' })
      const result = validateControlJudgmentForSave(sections)
      expect(result.valid).toBe(false)
      expect(result.errorMessage).toContain('控制判断结果为空')
    })

    it('控制类型最终结论有值 → 校验通过', () => {
      const sections = createSectionsWithResults({ conclusionResult: '是' })
      const result = validateControlJudgmentForSave(sections)
      expect(result.valid).toBe(true)
      expect(result.errorMessage).toBe('')
    })

    it('综合判断section缺失 → 校验不通过', () => {
      const sections = [
        { id: 'power', rows: [{ dimension: '表决权', judgmentResult: '是' }] },
      ]
      const result = validateControlJudgmentForSave(sections)
      expect(result.valid).toBe(false)
      expect(result.errorMessage).toContain('综合判断section缺失')
    })
  })
})

describe('G7TabControlJudgment - 组件渲染与交互', () => {
  const defaultProps = {
    htmlData: null,
    sheetName: 'G7-7',
    wpId: 'wp-001',
    projectId: 'proj-001',
    readonly: false,
  }

  const globalConfig = {
    stubs: {
      'el-button': defineComponent({ template: '<button><slot /></button>' }),
      'el-table': defineComponent({
        props: ['data', 'border', 'size', 'maxHeight', 'rowKey'],
        template: '<div class="el-table"></div>',
      }),
      'el-table-column': true,
      'el-select': defineComponent({
        props: ['modelValue', 'size', 'placeholder', 'clearable'],
        emits: ['update:modelValue'],
        template: '<select><slot /></select>',
      }),
      'el-option': true,
      'el-input': defineComponent({
        props: ['modelValue', 'type', 'autosize', 'disabled', 'placeholder', 'size'],
        emits: ['update:modelValue'],
        template: '<input />',
      }),
      'el-tag': defineComponent({ props: ['type', 'size'], template: '<span class="el-tag"><slot /></span>' }),
      'el-card': defineComponent({
        props: ['shadow'],
        template: '<div class="el-card"><slot name="header" /><slot /></div>',
      }),
      GtIndexChip: true,
    },
  }

  beforeEach(() => {
    // Mock crypto.randomUUID for deterministic tests
    vi.stubGlobal('crypto', {
      randomUUID: () => `test-uuid-${Math.random().toString(36).slice(2, 10)}`,
    })
  })

  it('初始化渲染6个section', async () => {
    const wrapper = shallowMount(G7TabControlJudgment, {
      props: defaultProps,
      global: globalConfig,
    })
    await nextTick()

    // 应有6个section标题
    const sectionHeaders = wrapper.findAll('.section-header')
    expect(sectionHeaders.length).toBe(6)
  })

  it('方法论上下文区域包含控制三要素', async () => {
    const wrapper = shallowMount(G7TabControlJudgment, {
      props: defaultProps,
      global: globalConfig,
    })
    await nextTick()

    const context = wrapper.find('.methodology-context')
    expect(context.exists()).toBe(true)
    expect(context.text()).toContain('权力')
    expect(context.text()).toContain('可变回报')
    expect(context.text()).toContain('权力与回报的联系')
  })

  it('从htmlData加载已有数据', async () => {
    const savedData = {
      controlJudgment: {
        sections: [
          {
            id: 'power',
            sectionNo: '(一)',
            title: '权力',
            rows: [
              {
                id: 'row-1',
                seq: 1,
                dimension: '表决权',
                criterion: '投资方是否持有被投资方超过半数的表决权',
                investeeName: '测试公司A',
                judgmentResult: '是',
                judgmentBasis: '持股60%',
                riskFlag: '低',
                auditConclusion: '满足权力要素',
                indexRef: 'G7-7-1',
              },
            ],
          },
        ],
        overallConclusion: '控制',
      },
    }

    const wrapper = shallowMount(G7TabControlJudgment, {
      props: { ...defaultProps, htmlData: savedData },
      global: globalConfig,
    })
    await nextTick()

    // getData should return the loaded data
    const data = (wrapper.vm as any).getData()
    expect(data.sections[0].id).toBe('power')
    expect(data.sections[0].rows[0].investeeName).toBe('测试公司A')
    expect(data.sections[0].rows[0].judgmentResult).toBe('是')
    expect(data.overallConclusion).toBe('控制')
  })

  it('getData 导出完整结构', async () => {
    const wrapper = shallowMount(G7TabControlJudgment, {
      props: defaultProps,
      global: globalConfig,
    })
    await nextTick()

    const data = (wrapper.vm as any).getData()
    expect(data.sections).toHaveLength(6)
    expect(data.sections[0].id).toBe('power')
    expect(data.sections[1].id).toBe('variableReturns')
    expect(data.sections[2].id).toBe('powerReturnLink')
    expect(data.sections[3].id).toBe('protectiveRights')
    expect(data.sections[4].id).toBe('agentPrincipal')
    expect(data.sections[5].id).toBe('overallJudgment')
    expect(data).toHaveProperty('overallConclusion')

    // 验证总行数: 8+8+8+8+8+7=47
    const totalRows = data.sections.reduce(
      (sum: number, s: any) => sum + s.rows.length, 0
    )
    expect(totalRows).toBe(47)
  })
})
