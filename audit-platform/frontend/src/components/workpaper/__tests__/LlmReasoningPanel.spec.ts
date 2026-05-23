/**
 * LlmReasoningPanel.spec.ts — proposal-remaining-18 task 4.2 (K-4)
 *
 * 验证目标：
 * 1. 全字段为空时不渲染（hasContent=false）
 * 2. 仅 reasoning 时正常显示
 * 3. references 数组渲染（type/code/section）
 * 4. data_sources 数组以 tag 形式显示
 * 5. confidence 计算 percent 与 tag type
 * 6. defaultOpen=true 时面板默认展开
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import LlmReasoningPanel from '../LlmReasoningPanel.vue'

const STUBS = {
  'el-collapse': {
    name: 'ElCollapse',
    template: '<div class="el-collapse-stub"><slot /></div>',
    props: ['modelValue'],
  },
  'el-collapse-item': {
    name: 'ElCollapseItem',
    template:
      '<div class="el-collapse-item-stub"><div class="title-slot"><slot name="title" /></div><div class="content-slot"><slot /></div></div>',
    props: ['name'],
  },
  'el-tag': {
    name: 'ElTag',
    template: '<span class="el-tag-stub" :data-type="type"><slot /></span>',
    props: ['type', 'size', 'effect'],
  },
  'el-progress': {
    name: 'ElProgress',
    template: '<div class="el-progress-stub" :data-percent="percentage" />',
    props: ['percentage', 'strokeWidth', 'color'],
  },
}

describe('LlmReasoningPanel (K-4)', () => {
  it('1. 全部字段为空时不渲染', () => {
    const wrapper = mount(LlmReasoningPanel, {
      props: {},
      global: { stubs: STUBS },
    })
    expect(wrapper.find('.el-collapse-stub').exists()).toBe(false)
  })

  it('1b. 全部字段为空（显式传 null/[]）时不渲染', () => {
    const wrapper = mount(LlmReasoningPanel, {
      props: {
        reasoning: null,
        references: [],
        dataSources: [],
        confidence: 0,
      },
      global: { stubs: STUBS },
    })
    expect(wrapper.find('.el-collapse-stub').exists()).toBe(false)
  })

  it('2. 仅 reasoning 字段时正常显示', () => {
    const wrapper = mount(LlmReasoningPanel, {
      props: {
        reasoning: '基于规则引擎对 2 个费用类别的对比分析',
      },
      global: { stubs: STUBS },
    })
    expect(wrapper.find('.el-collapse-stub').exists()).toBe(true)
    expect(wrapper.text()).toContain('推理依据')
    expect(wrapper.text()).toContain('基于规则引擎')
  })

  it('3. references 数组渲染（type/code/section）', () => {
    const wrapper = mount(LlmReasoningPanel, {
      props: {
        references: [
          { type: 'CAS', code: 'CAS 8', section: '减值测试' },
          { type: 'ISA', code: 'ISA 540', section: '估计与披露' },
        ],
      },
      global: { stubs: STUBS },
    })
    const text = wrapper.text()
    expect(text).toContain('CAS')
    expect(text).toContain('CAS 8')
    expect(text).toContain('减值测试')
    expect(text).toContain('ISA')
    expect(text).toContain('ISA 540')
  })

  it('4. data_sources 渲染为 tag', () => {
    const wrapper = mount(LlmReasoningPanel, {
      props: {
        dataSources: ['TB:1601:期末余额', 'WP:H1:折旧分配分析表'],
      },
      global: { stubs: STUBS },
    })
    const tags = wrapper.findAll('.el-tag-stub')
    const texts = tags.map((t) => t.text())
    expect(texts).toContain('TB:1601:期末余额')
    expect(texts).toContain('WP:H1:折旧分配分析表')
  })

  it('5a. confidence 计算 percent（>=0.8 → success）', () => {
    const wrapper = mount(LlmReasoningPanel, {
      props: { confidence: 0.85, reasoning: 'x' },
      global: { stubs: STUBS },
    })
    const progress = wrapper.find('.el-progress-stub')
    expect(progress.attributes('data-percent')).toBe('85')
    // 标题内含置信度 tag (success type)
    const tagTexts = wrapper.findAll('.el-tag-stub').map((t) => t.text())
    expect(tagTexts.some((t) => t.includes('85%'))).toBe(true)
  })

  it('5b. confidence < 0.5 → info type', () => {
    const wrapper = mount(LlmReasoningPanel, {
      props: { confidence: 0.3, reasoning: 'x' },
      global: { stubs: STUBS },
    })
    const tags = wrapper.findAll('.el-tag-stub')
    const labelTag = tags.find((t) => t.text().includes('30%'))
    expect(labelTag?.attributes('data-type')).toBe('info')
  })

  it('5c. confidence 0 时不显示 confidence label tag', () => {
    const wrapper = mount(LlmReasoningPanel, {
      props: { reasoning: 'r', confidence: 0 },
      global: { stubs: STUBS },
    })
    // hasContent=true 因为有 reasoning，但 confidenceLabel 应为空 → 进度条仍显示但 percent=0
    const progress = wrapper.find('.el-progress-stub')
    // confidence === 0 → reasoning section 是显示的，但 confidence section 因 v-if 控制
    // 该面板 confidence section v-if="confidence !== undefined && confidence !== null"
    // 所以 confidence=0 仍渲染（合理）；但 confidence label tag 不渲染
    const labelTags = wrapper.findAll('.el-tag-stub').filter((t) => t.text().includes('%'))
    expect(labelTags.length).toBe(0)
    expect(progress.exists()).toBe(true)
  })

  it('6. defaultOpen=true 时初始 v-model 包含 paneName', () => {
    const wrapper = mount(LlmReasoningPanel, {
      props: { reasoning: 'r', defaultOpen: true, paneName: 'test-pane' },
      global: { stubs: STUBS },
    })
    const collapse = wrapper.findComponent({ name: 'ElCollapse' })
    expect(collapse.props('modelValue')).toEqual(['test-pane'])
  })

  it('7. confidence 越界（>1）夹断到 100', () => {
    const wrapper = mount(LlmReasoningPanel, {
      props: { confidence: 2.5 },
      global: { stubs: STUBS },
    })
    const progress = wrapper.find('.el-progress-stub')
    expect(progress.attributes('data-percent')).toBe('100')
  })

  it('8. references + data_sources 同时存在时摘要 meta 显示数量', () => {
    const wrapper = mount(LlmReasoningPanel, {
      props: {
        references: [
          { type: 'CAS', code: 'CAS 8' },
          { type: 'CAS', code: 'CAS 22' },
        ],
        dataSources: ['WP:H1', 'WP:I3', 'WP:G14'],
      },
      global: { stubs: STUBS },
    })
    const text = wrapper.text()
    expect(text).toContain('引用 2 项')
    expect(text).toContain('数据 3 处')
  })
})
