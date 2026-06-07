/**
 * WorkpaperAIConclusionPanel.spec.ts — AI 结论面板组件测试
 *
 * spec workpaper-ai-conclusion-copilot Task 4
 *
 * 验证：
 * 4.1 D1-C/D2-C 结论区域渲染
 * 4.2 "生成 AI 草稿"按钮
 * 4.3 AI 草稿标签、来源摘要、missing 项展示
 * 4.4 确认、修订确认、拒绝交互
 * 4.5 目标绑定不完整或上下文 missing 时展示不可生成原因
 *
 * Validates: Requirements 4.1, 4.2, 4.3, 4.4
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import WorkpaperAIConclusionPanel from '../WorkpaperAIConclusionPanel.vue'

// ─── Element Plus stubs ───
const ElTag = {
  name: 'ElTag',
  template: '<span class="el-tag-stub" :data-type="type"><slot /></span>',
  props: ['type', 'effect', 'size'],
}
const ElButton = {
  name: 'ElButton',
  template: '<button class="el-button-stub" :data-type="type" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  props: ['type', 'loading', 'disabled'],
}
const ElAlert = {
  name: 'ElAlert',
  template: '<div class="el-alert-stub" :data-type="type"><slot name="title" /><slot /></div>',
  props: ['type', 'closable', 'showIcon'],
}
const ElInput = {
  name: 'ElInput',
  template: '<textarea class="el-input-stub"></textarea>',
  props: ['modelValue', 'type', 'rows', 'placeholder'],
}
const ElDialog = {
  name: 'ElDialog',
  template: '<div class="el-dialog-stub" v-if="modelValue"><slot /><slot name="footer" /></div>',
  props: ['modelValue', 'title', 'width', 'closeOnClickModal'],
}
const ElMessage = { warning: vi.fn() }

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn() },
}))

const globalConfig = {
  components: {
    'el-tag': ElTag,
    'el-button': ElButton,
    'el-alert': ElAlert,
    'el-input': ElInput,
    'el-dialog': ElDialog,
  },
}

// ─── Fixtures ───
const MOCK_DRAFT_PENDING = {
  log_id: 'test-log-id-001',
  generated_content: '基于审定表数据和程序执行情况，本科目期末余额变动合理。',
  confirm_action: 'pending',
  target_binding: {
    account_package_id: 'D1_fixed_assets',
    wp_id: 'wp-001',
    sheet_type: 'conclusion',
    field_id: 'd1.conclusion.overall',
  },
  source_summary: {
    wp_code: 'D1',
    conclusion_sheet: 'D1-C',
    sources: [
      { type: 'audit_sheet', label: '审定表', available: true },
      { type: 'program_status', label: '程序状态', available: true },
    ],
    source_count: 2,
  },
  missing: [
    { source: 'adjustment_impact', reason: 'no_adjustment_sheets', impact: '调整分录信息不可用' },
  ],
}

const MOCK_DRAFT_CONFIRMED = {
  ...MOCK_DRAFT_PENDING,
  confirm_action: 'confirmed',
}

// ─── 4.1: D1-C/D2-C 结论区域渲染 ───
describe('WorkpaperAIConclusionPanel — 结论区域', () => {
  it('渲染面板标题', () => {
    const wrapper = mount(WorkpaperAIConclusionPanel, {
      props: {
        sheetLabel: 'D1-C',
        accountPackageId: 'D1_fixed_assets',
        wpId: 'wp-001',
        fieldId: 'd1.conclusion.overall',
        projectId: 'proj-001',
      },
      global: globalConfig,
    })
    expect(wrapper.text()).toContain('D1-C 科目结论')
  })

  it('无草稿时显示生成按钮', () => {
    const wrapper = mount(WorkpaperAIConclusionPanel, {
      props: {
        sheetLabel: 'D2-C',
        accountPackageId: 'D2_accounts_receivable',
        wpId: 'wp-002',
        fieldId: 'd2.conclusion.overall',
        projectId: 'proj-001',
        draft: null,
      },
      global: globalConfig,
    })
    expect(wrapper.text()).toContain('生成 AI 草稿')
  })
})

// ─── 4.2: 生成按钮 ───
describe('WorkpaperAIConclusionPanel — 生成按钮', () => {
  it('点击生成按钮触发 generate 事件', async () => {
    const wrapper = mount(WorkpaperAIConclusionPanel, {
      props: {
        sheetLabel: 'D1-C',
        accountPackageId: 'D1_fixed_assets',
        wpId: 'wp-001',
        fieldId: 'd1.conclusion.overall',
        projectId: 'proj-001',
        draft: null,
      },
      global: globalConfig,
    })
    await wrapper.find('.el-button-stub').trigger('click')
    expect(wrapper.emitted('generate')).toBeTruthy()
  })

  it('cannotGenerate 为 true 时不显示生成按钮（按钮区域隐藏）', () => {
    const wrapper = mount(WorkpaperAIConclusionPanel, {
      props: {
        sheetLabel: 'D1-C',
        accountPackageId: 'D1_fixed_assets',
        wpId: 'wp-001',
        fieldId: 'd1.conclusion.overall',
        projectId: 'proj-001',
        cannotGenerate: true,
        cannotGenerateReason: '目标绑定不完整，缺少 wp_id',
      },
      global: globalConfig,
    })
    // 操作按钮区域应不存在
    expect(wrapper.find('.ai-conclusion-actions').exists()).toBe(false)
    // 阻断提示应存在
    expect(wrapper.find('.ai-conclusion-blocked').exists()).toBe(true)
    expect(wrapper.text()).toContain('无法生成 AI 草稿')
    expect(wrapper.text()).toContain('目标绑定不完整')
  })
})

// ─── 4.3: 草稿标签、来源摘要、missing 项 ───
describe('WorkpaperAIConclusionPanel — 草稿展示', () => {
  it('pending 状态显示 AI 草稿待确认标签', () => {
    const wrapper = mount(WorkpaperAIConclusionPanel, {
      props: {
        sheetLabel: 'D1-C',
        accountPackageId: 'D1_fixed_assets',
        wpId: 'wp-001',
        fieldId: 'd1.conclusion.overall',
        projectId: 'proj-001',
        draft: MOCK_DRAFT_PENDING,
      },
      global: globalConfig,
    })
    expect(wrapper.text()).toContain('AI 草稿待确认')
  })

  it('显示来源摘要标签', () => {
    const wrapper = mount(WorkpaperAIConclusionPanel, {
      props: {
        sheetLabel: 'D1-C',
        accountPackageId: 'D1_fixed_assets',
        wpId: 'wp-001',
        fieldId: 'd1.conclusion.overall',
        projectId: 'proj-001',
        draft: MOCK_DRAFT_PENDING,
      },
      global: globalConfig,
    })
    expect(wrapper.text()).toContain('审定表')
    expect(wrapper.text()).toContain('程序状态')
    expect(wrapper.text()).toContain('引用来源')
  })

  it('显示 missing 项', () => {
    const wrapper = mount(WorkpaperAIConclusionPanel, {
      props: {
        sheetLabel: 'D1-C',
        accountPackageId: 'D1_fixed_assets',
        wpId: 'wp-001',
        fieldId: 'd1.conclusion.overall',
        projectId: 'proj-001',
        draft: MOCK_DRAFT_PENDING,
      },
      global: globalConfig,
    })
    expect(wrapper.text()).toContain('缺失资料提示')
    expect(wrapper.text()).toContain('adjustment_impact')
    expect(wrapper.text()).toContain('调整分录信息不可用')
  })

  it('显示草稿内容', () => {
    const wrapper = mount(WorkpaperAIConclusionPanel, {
      props: {
        sheetLabel: 'D1-C',
        accountPackageId: 'D1_fixed_assets',
        wpId: 'wp-001',
        fieldId: 'd1.conclusion.overall',
        projectId: 'proj-001',
        draft: MOCK_DRAFT_PENDING,
      },
      global: globalConfig,
    })
    expect(wrapper.text()).toContain('本科目期末余额变动合理')
  })

  it('confirmed 状态显示已确认标签', () => {
    const wrapper = mount(WorkpaperAIConclusionPanel, {
      props: {
        sheetLabel: 'D1-C',
        accountPackageId: 'D1_fixed_assets',
        wpId: 'wp-001',
        fieldId: 'd1.conclusion.overall',
        projectId: 'proj-001',
        draft: MOCK_DRAFT_CONFIRMED,
      },
      global: globalConfig,
    })
    expect(wrapper.text()).toContain('已确认')
  })
})

// ─── 4.4: 确认、修订、拒绝交互 ───
describe('WorkpaperAIConclusionPanel — 确认/修订/拒绝', () => {
  it('pending 状态显示确认、修订、拒绝按钮', () => {
    const wrapper = mount(WorkpaperAIConclusionPanel, {
      props: {
        sheetLabel: 'D1-C',
        accountPackageId: 'D1_fixed_assets',
        wpId: 'wp-001',
        fieldId: 'd1.conclusion.overall',
        projectId: 'proj-001',
        draft: MOCK_DRAFT_PENDING,
      },
      global: globalConfig,
    })
    expect(wrapper.text()).toContain('确认采纳')
    expect(wrapper.text()).toContain('修订确认')
    expect(wrapper.text()).toContain('拒绝')
  })

  it('点击确认按钮触发 confirm 事件', async () => {
    const wrapper = mount(WorkpaperAIConclusionPanel, {
      props: {
        sheetLabel: 'D1-C',
        accountPackageId: 'D1_fixed_assets',
        wpId: 'wp-001',
        fieldId: 'd1.conclusion.overall',
        projectId: 'proj-001',
        draft: MOCK_DRAFT_PENDING,
      },
      global: globalConfig,
    })
    const confirmBtn = wrapper.findAll('.el-button-stub').find(b => b.text().includes('确认采纳'))
    await confirmBtn!.trigger('click')
    expect(wrapper.emitted('confirm')).toBeTruthy()
    expect(wrapper.emitted('confirm')![0]).toEqual(['test-log-id-001'])
  })

  it('confirmed 状态不显示操作按钮', () => {
    const wrapper = mount(WorkpaperAIConclusionPanel, {
      props: {
        sheetLabel: 'D1-C',
        accountPackageId: 'D1_fixed_assets',
        wpId: 'wp-001',
        fieldId: 'd1.conclusion.overall',
        projectId: 'proj-001',
        draft: MOCK_DRAFT_CONFIRMED,
      },
      global: globalConfig,
    })
    expect(wrapper.text()).not.toContain('确认采纳')
    expect(wrapper.text()).not.toContain('修订确认')
  })
})

// ─── 4.5: 不可生成原因展示 ───
describe('WorkpaperAIConclusionPanel — 不可生成', () => {
  it('目标绑定不完整时展示原因', () => {
    const wrapper = mount(WorkpaperAIConclusionPanel, {
      props: {
        sheetLabel: 'D1-C',
        accountPackageId: 'D1_fixed_assets',
        wpId: 'wp-001',
        fieldId: 'd1.conclusion.overall',
        projectId: 'proj-001',
        cannotGenerate: true,
        cannotGenerateReason: '目标绑定不完整，缺少 wp_id',
      },
      global: globalConfig,
    })
    expect(wrapper.text()).toContain('无法生成 AI 草稿')
    expect(wrapper.text()).toContain('目标绑定不完整')
  })

  it('上下文 missing 时展示缺失列表', () => {
    const draftWithMissing = {
      ...MOCK_DRAFT_PENDING,
      missing: [
        { source: 'confirmation_summary', reason: 'no_data', impact: '函证数据不可用' },
        { source: 'bad_debt_ecl', reason: 'no_ecl', impact: '坏账数据不可用' },
      ],
    }
    const wrapper = mount(WorkpaperAIConclusionPanel, {
      props: {
        sheetLabel: 'D2-C',
        accountPackageId: 'D2_accounts_receivable',
        wpId: 'wp-002',
        fieldId: 'd2.conclusion.overall',
        projectId: 'proj-001',
        cannotGenerate: true,
        cannotGenerateReason: '上下文数据不完整，请先补充以下资料',
        draft: draftWithMissing,
      },
      global: globalConfig,
    })
    expect(wrapper.text()).toContain('函证数据不可用')
    expect(wrapper.text()).toContain('坏账数据不可用')
  })
})
