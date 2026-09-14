/**
 * G7TabControlJudgment — 使用生产模型的单元测试（非本地假校验）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import {
  deriveControlTriadHint,
  validateQuestionnaireOverall,
  suggestRelationshipFromQuestionnaire,
  validateG7ControlJudgmentForSave,
  extractG7SubAiText,
  listG7ControlDecisions,
  filterDecisionsByCombination,
  createEmptyG7ControlDecision,
} from '../../../composables/g7ControlJudgmentModel'

vi.mock('../../../GtIndexChip.vue', () => ({
  default: defineComponent({ props: ['value'], template: '<span class="gt-index-chip" />' }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('../../../composables/useG7SubFormData', () => ({
  useG7SubFormData: () => ({
    load: vi.fn().mockResolvedValue(undefined),
    data: { value: new Map() },
    debouncedSave: vi.fn(),
    saveImmediate: vi.fn().mockResolvedValue(undefined),
  }),
}))

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue([]) },
}))

vi.mock('@/utils/http', () => ({
  default: { post: vi.fn() },
}))

import G7TabControlJudgment from '../G7TabControlJudgment.vue'

function createSectionsWithResults(config: {
  powerYesCount?: number
  returnYesCount?: number
  linkYesCount?: number
  overallAnswers?: Record<string, string>
}) {
  const { powerYesCount = 0, returnYesCount = 0, linkYesCount = 0, overallAnswers = {} } = config
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
        { dimension: '控制三要素同时满足', judgmentResult: overallAnswers['控制三要素同时满足'] ?? '' },
        { dimension: '共同控制条件满足', judgmentResult: overallAnswers['共同控制条件满足'] ?? '' },
        { dimension: '重大影响条件满足', judgmentResult: overallAnswers['重大影响条件满足'] ?? '' },
        { dimension: '被购买方构成业务', judgmentResult: overallAnswers['被购买方构成业务'] ?? '不适用' },
        { dimension: '同一最终控制方', judgmentResult: overallAnswers['同一最终控制方'] ?? '不适用' },
        { dimension: '控制权已实际转移', judgmentResult: overallAnswers['控制权已实际转移'] ?? '不适用' },
        { dimension: '前期结论变化已说明', judgmentResult: overallAnswers['前期结论变化已说明'] ?? '不适用' },
      ],
    },
  ]
}

describe('生产模型：三要素提示 / 问卷建议 / 保存门禁', () => {
  it('三要素区段均有“是” → control', () => {
    expect(deriveControlTriadHint(createSectionsWithResults({
      powerYesCount: 1, returnYesCount: 1, linkYesCount: 1,
    }))).toBe('control')
  })

  it('缺联系 → partial', () => {
    expect(deriveControlTriadHint(createSectionsWithResults({
      powerYesCount: 2, returnYesCount: 2, linkYesCount: 0,
    }))).toBe('partial_power_return')
  })

  it('综合判断显式“控制三要素同时满足” → 建议控制', () => {
    const sections = createSectionsWithResults({
      overallAnswers: { '控制三要素同时满足': '是' },
    })
    // 其余 overall 行填满以便保存门禁
    for (const row of sections[5].rows) {
      if (!row.judgmentResult) row.judgmentResult = '否'
    }
    expect(suggestRelationshipFromQuestionnaire(sections).relationshipType).toBe('控制')
  })

  it('综合判断未完成 → 保存门禁失败', () => {
    const sections = createSectionsWithResults({})
    const errors = validateQuestionnaireOverall(sections)
    expect(errors[0]).toContain('综合判断尚未完成')
  })

  it('决策+问卷齐全 → 保存门禁通过', () => {
    const sections = createSectionsWithResults({
      overallAnswers: {
        '控制三要素同时满足': '是',
        '共同控制条件满足': '否',
        '重大影响条件满足': '否',
        '被购买方构成业务': '是',
        '同一最终控制方': '是',
        '控制权已实际转移': '是',
        '前期结论变化已说明': '不适用',
      },
    })
    const decision = {
      ...createEmptyG7ControlDecision('甲公司'),
      relationshipType: '控制' as const,
      combinationType: '同一控制下企业合并' as const,
      combinationBasis: '同一最终控制方',
      acquisitionDate: '2026-01-01',
      acquisitionDateBasis: '已接管',
    }
    expect(validateG7ControlJudgmentForSave(decision, sections)).toEqual([])
  })

  it('extractG7SubAiText 优先 content', () => {
    expect(extractG7SubAiText({ content: '正文A' })).toBe('正文A')
    expect(extractG7SubAiText({ data: { content: '正文B' } })).toBe('正文B')
    expect(extractG7SubAiText({ conclusion: '旧字段' })).toBe('旧字段')
  })

  it('listG7ControlDecisions 含 additionalDecisions', () => {
    const names = filterDecisionsByCombination(
      listG7ControlDecisions({
        decision: {
          investeeName: '甲',
          relationshipType: '控制',
          combinationType: '同一控制下企业合并',
        },
        additionalDecisions: [
          {
            investeeName: '乙',
            relationshipType: '控制',
            combinationType: '同一控制下企业合并',
          },
          {
            investeeName: '丙',
            relationshipType: '控制',
            combinationType: '非同一控制下企业合并',
          },
        ],
      }),
      '同一控制下企业合并',
    )
    expect(names).toEqual(['甲', '乙'])
  })
})

describe('G7TabControlJudgment 组件渲染', () => {
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
        props: ['data'],
        template: '<div class="el-table"></div>',
      }),
      'el-table-column': true,
      'el-select': defineComponent({
        props: ['modelValue'],
        emits: ['update:modelValue', 'change'],
        template: '<select><slot /></select>',
      }),
      'el-option': true,
      'el-input': defineComponent({ props: ['modelValue'], template: '<input />' }),
      'el-tag': defineComponent({ props: ['type', 'size'], template: '<span class="el-tag"><slot /></span>' }),
      'el-card': defineComponent({
        props: ['shadow'],
        template: '<div class="el-card"><slot name="header" /><slot /></div>',
      }),
      'el-alert': defineComponent({ props: ['title', 'type'], template: '<div class="el-alert"><slot /></div>' }),
      'el-form': defineComponent({ template: '<form><slot /></form>' }),
      'el-form-item': defineComponent({ template: '<div><slot /></div>' }),
      'el-date-picker': true,
      GtIndexChip: true,
    },
  }

  beforeEach(() => {
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
    expect(wrapper.findAll('.section-header').length).toBe(6)
  })

  it('方法论上下文包含控制三要素', async () => {
    const wrapper = shallowMount(G7TabControlJudgment, {
      props: defaultProps,
      global: globalConfig,
    })
    await nextTick()
    const context = wrapper.find('.methodology-context')
    expect(context.text()).toContain('权力')
    expect(context.text()).toContain('可变回报')
  })

  it('getData 导出 47 行 + decision + additionalDecisions', async () => {
    const wrapper = shallowMount(G7TabControlJudgment, {
      props: defaultProps,
      global: globalConfig,
    })
    await nextTick()
    const data = (wrapper.vm as any).getData()
    expect(data.sections).toHaveLength(6)
    const totalRows = data.sections.reduce((sum: number, s: any) => sum + s.rows.length, 0)
    expect(totalRows).toBe(47)
    expect(data).toHaveProperty('decision')
    expect(data).toHaveProperty('additionalDecisions')
  })
})
