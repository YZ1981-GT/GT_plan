/**
 * AccountPackageSheetNav.spec.ts — sheet_type 分组导航组件测试
 *
 * spec workpaper-account-package-d1-d2-pilot Task 4.2 / 5.2
 *
 * 覆盖：
 * - D1/D2 sheet_type 分组正确
 * - 分组排序
 * - 空状态
 * - 点击交互
 *
 * Validates: Requirements 2.2
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AccountPackageSheetNav from '../AccountPackageSheetNav.vue'
import type { SheetTypeGroup } from '@/composables/useAccountPackage'

// ─── Element Plus stubs ───
const ElBadge = {
  name: 'ElBadge',
  template: '<span class="el-badge-stub"><slot /></span>',
  props: ['value', 'max', 'type'],
}
const ElTag = {
  name: 'ElTag',
  template: '<span class="el-tag-stub"><slot /></span>',
  props: ['type', 'effect', 'size'],
}

const globalConfig = {
  components: { 'el-badge': ElBadge, 'el-tag': ElTag },
}

// ─── Fixtures ───
const D1_GROUPS: SheetTypeGroup[] = [
  {
    type: 'audit_sheet',
    label: '审定表',
    icon: '✅',
    sheets: [{ sheet_name: '审定表D1-1', sheet_type: 'audit_sheet', source_wp_code: 'D1' }],
  },
  {
    type: 'detail_table',
    label: '明细表',
    icon: '📑',
    sheets: [
      { sheet_name: '应收票据明细表D1-2', sheet_type: 'detail_table', source_wp_code: 'D1' },
      { sheet_name: '坏账准备明细表D1-4', sheet_type: 'detail_table', source_wp_code: 'D1' },
    ],
  },
  {
    type: 'disclosure',
    label: '附注披露',
    icon: '📝',
    sheets: [
      { sheet_name: '附注披露信息（上市公司）', sheet_type: 'disclosure', source_wp_code: 'D1', schema_ref: 'C-D1-disclosure.yaml' },
    ],
  },
]

const D2_GROUPS: SheetTypeGroup[] = [
  {
    type: 'control_panel',
    label: '程序控制台',
    icon: '🎯',
    sheets: [{ sheet_name: 'D2A 应收账款实质性程序表', sheet_type: 'control_panel', source_wp_code: 'D2' }],
  },
  {
    type: 'audit_sheet',
    label: '审定表',
    icon: '✅',
    sheets: [{ sheet_name: '审定表D2-1', sheet_type: 'audit_sheet', source_wp_code: 'D2' }],
  },
  {
    type: 'analysis',
    label: '分析',
    icon: '📈',
    sheets: [
      { sheet_name: '坏账准备明细表D2-3', sheet_type: 'analysis', source_wp_code: 'D2' },
      { sheet_name: '应收账款分析表D2-5', sheet_type: 'analysis', source_wp_code: 'D2-5' },
      { sheet_name: '应收坏账准备测算D2-9', sheet_type: 'analysis', source_wp_code: 'D2-6' },
      { sheet_name: '预期信用损失的计量测试D2-10', sheet_type: 'analysis', source_wp_code: 'D2-6' },
      { sheet_name: '应收账款业务模式分析D2-13', sheet_type: 'analysis', source_wp_code: 'D2-6' },
    ],
  },
]

// ─── 渲染测试 ───
describe('AccountPackageSheetNav — 分组渲染', () => {
  it('渲染 D1 分组标题和图标', () => {
    const wrapper = mount(AccountPackageSheetNav, {
      props: { groups: D1_GROUPS, activeSheet: '' },
      global: globalConfig,
    })

    expect(wrapper.text()).toContain('审定表')
    expect(wrapper.text()).toContain('明细表')
    expect(wrapper.text()).toContain('附注披露')
    expect(wrapper.text()).toContain('✅')
    expect(wrapper.text()).toContain('📑')
    expect(wrapper.text()).toContain('📝')
  })

  it('渲染 D2 分组包含程序控制台', () => {
    const wrapper = mount(AccountPackageSheetNav, {
      props: { groups: D2_GROUPS, activeSheet: '' },
      global: globalConfig,
    })

    expect(wrapper.text()).toContain('程序控制台')
    expect(wrapper.text()).toContain('🎯')
    expect(wrapper.text()).toContain('D2A 应收账款实质性程序表')
  })

  it('渲染各分组下的 sheet 名称', () => {
    const wrapper = mount(AccountPackageSheetNav, {
      props: { groups: D1_GROUPS, activeSheet: '' },
      global: globalConfig,
    })

    expect(wrapper.text()).toContain('审定表D1-1')
    expect(wrapper.text()).toContain('应收票据明细表D1-2')
    expect(wrapper.text()).toContain('坏账准备明细表D1-4')
    expect(wrapper.text()).toContain('附注披露信息（上市公司）')
  })

  it('有 schema_ref 的 sheet 显示 schema 标签', () => {
    const wrapper = mount(AccountPackageSheetNav, {
      props: { groups: D1_GROUPS, activeSheet: '' },
      global: globalConfig,
    })

    const tags = wrapper.findAll('.gt-sheet-nav__schema-tag')
    expect(tags.length).toBeGreaterThan(0)
  })
})

// ─── 空状态 ───
describe('AccountPackageSheetNav — 空状态', () => {
  it('groups 为空时显示暂无工作表', () => {
    const wrapper = mount(AccountPackageSheetNav, {
      props: { groups: [], activeSheet: '' },
      global: globalConfig,
    })

    expect(wrapper.text()).toContain('暂无工作表')
  })
})

// ─── 交互测试 ───
describe('AccountPackageSheetNav — 点击交互', () => {
  it('点击 sheet 触发 select 事件', async () => {
    const wrapper = mount(AccountPackageSheetNav, {
      props: { groups: D1_GROUPS, activeSheet: '' },
      global: globalConfig,
    })

    const sheets = wrapper.findAll('.gt-sheet-nav__sheet')
    await sheets[0].trigger('click')

    expect(wrapper.emitted('select')).toBeTruthy()
    expect(wrapper.emitted('select')![0]).toEqual(['审定表D1-1'])
  })

  it('activeSheet 对应 sheet 显示激活样式', () => {
    const wrapper = mount(AccountPackageSheetNav, {
      props: { groups: D1_GROUPS, activeSheet: '审定表D1-1' },
      global: globalConfig,
    })

    const activeItems = wrapper.findAll('.gt-sheet-nav__sheet--active')
    expect(activeItems.length).toBe(1)
    expect(activeItems[0].text()).toContain('审定表D1-1')
  })
})

// ─── D2 分组正确性 ───
describe('AccountPackageSheetNav — D2 分析分组', () => {
  it('D2 分析分组包含 5 个 sheet', () => {
    const wrapper = mount(AccountPackageSheetNav, {
      props: { groups: D2_GROUPS, activeSheet: '' },
      global: globalConfig,
    })

    expect(wrapper.text()).toContain('坏账准备明细表D2-3')
    expect(wrapper.text()).toContain('应收账款分析表D2-5')
    expect(wrapper.text()).toContain('应收坏账准备测算D2-9')
    expect(wrapper.text()).toContain('预期信用损失的计量测试D2-10')
    expect(wrapper.text()).toContain('应收账款业务模式分析D2-13')
  })
})
