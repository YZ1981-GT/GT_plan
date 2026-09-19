/**
 * NoteCellSourceDrawer.spec.ts — 单元格来源面板测试
 *
 * Spec:    .kiro/specs/disclosure-note-semantic-structure-and-presentation/ Task 7.5
 * Design:  公式治理与单元格来源面板
 * Reqs:    4.1, 4.2, 4.4, 5.5
 *
 * 用例：
 *   1. 渲染带公式的单元格信息
 *   2. 渲染带手工覆盖的单元格信息
 *   3. 点击跳转按钮 emit navigate-source
 *   4. 点击恢复自动 emit restore-auto
 *   5. 关闭/空状态
 *   6. 公式错误展示
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import NoteCellSourceDrawer from '../NoteCellSourceDrawer.vue'
import type { CellSourceInfo } from '../NoteCellSourceDrawer.vue'

// Element Plus stubs
const ElDrawerStub = {
  name: 'ElDrawer',
  template: '<div data-test="drawer"><slot v-if="modelValue" /><slot name="default" v-if="modelValue" /></div>',
  props: ['modelValue', 'title', 'direction', 'size', 'appendToBody', 'destroyOnClose'],
  emits: ['update:modelValue'],
}

const ElTagStub = {
  name: 'ElTag',
  template: '<span data-test="tag" :data-type="type"><slot /></span>',
  props: ['type', 'size'],
}

const ElDescriptionsStub = {
  name: 'ElDescriptions',
  template: '<div data-test="descriptions"><slot /></div>',
  props: ['column', 'size', 'border'],
}

const ElDescriptionsItemStub = {
  name: 'ElDescriptionsItem',
  template: '<div data-test="desc-item" :data-label="label"><span class="label">{{ label }}</span><slot /></div>',
  props: ['label'],
}

const ElButtonStub = {
  name: 'ElButton',
  template: '<button data-test="button" :data-type="type" @click="$emit(\'click\')"><slot /></button>',
  props: ['type', 'size', 'plain', 'link'],
  emits: ['click'],
}

const ElAlertStub = {
  name: 'ElAlert',
  template: '<div data-test="alert" :data-type="type">{{ title }}</div>',
  props: ['type', 'title', 'description', 'showIcon', 'closable'],
}

const ElEmptyStub = {
  name: 'ElEmpty',
  template: '<div data-test="empty">{{ description }}</div>',
  props: ['description', 'imageSize'],
}

const globalStubs = {
  stubs: {
    'el-drawer': ElDrawerStub,
    'el-tag': ElTagStub,
    'el-descriptions': ElDescriptionsStub,
    'el-descriptions-item': ElDescriptionsItemStub,
    'el-button': ElButtonStub,
    'el-alert': ElAlertStub,
    'el-empty': ElEmptyStub,
  },
}

const formulaCellInfo: CellSourceInfo = {
  value: 100.00,
  mode: 'formula',
  tableId: 'aging_analysis',
  rowId: 'within_1_year',
  colId: 'closing_balance',
  bindingId: 'ar_aging_within_1y_closing',
  formula: {
    formulaId: 'f_ar_001',
    expr: "WP('D2','附注披露表','within_1_year_closing')",
    source: 'template',
    dependencies: [
      { type: 'workpaper', wp_code: 'D2', field: 'within_1_year_closing' },
    ],
    lastResult: '100.00',
    lastError: null,
    lastEvaluatedAt: '2026-06-06T00:00:00Z',
  },
}

const manualOverrideCellInfo: CellSourceInfo = {
  value: 200.00,
  mode: 'manual',
  tableId: 'aging_analysis',
  rowId: 'within_1_year',
  colId: 'closing_balance',
  bindingId: 'ar_aging_within_1y_closing',
  manualOverride: {
    overrideValue: 200.00,
    originalAutoValue: 150.00,
    overriddenAt: '2026-06-05T10:30:00Z',
  },
}

const errorCellInfo: CellSourceInfo = {
  value: null,
  mode: 'formula',
  tableId: 'aging_analysis',
  rowId: 'total',
  colId: 'closing_balance',
  formula: {
    formulaId: 'f_ar_002',
    expr: "WP('D2','附注披露表','total_closing')",
    source: 'template',
    dependencies: [
      { type: 'workpaper', wp_code: 'D2', field: 'total_closing' },
      { type: 'trial_balance' },
    ],
    lastResult: undefined,
    lastError: '底稿 D2 未找到字段 total_closing',
    lastEvaluatedAt: '2026-06-06T01:00:00Z',
  },
}

describe('NoteCellSourceDrawer — 渲染带公式的单元格信息', () => {
  it('展示当前值和模式标签', () => {
    const wrapper = mount(NoteCellSourceDrawer, {
      props: { visible: true, cellInfo: formulaCellInfo },
      global: globalStubs,
    })
    expect(wrapper.text()).toContain('100')
    // mode tag
    const tags = wrapper.findAll('[data-test="tag"]')
    const modeTag = tags.find(t => t.text() === '公式')
    expect(modeTag).toBeTruthy()
    expect(modeTag!.attributes('data-type')).toBe('success')
  })

  it('展示 binding_id 和表/行/列信息', () => {
    const wrapper = mount(NoteCellSourceDrawer, {
      props: { visible: true, cellInfo: formulaCellInfo },
      global: globalStubs,
    })
    expect(wrapper.text()).toContain('ar_aging_within_1y_closing')
    expect(wrapper.text()).toContain('aging_analysis')
    expect(wrapper.text()).toContain('within_1_year')
    expect(wrapper.text()).toContain('closing_balance')
  })

  it('展示公式 ID、表达式、来源、结果和执行时间', () => {
    const wrapper = mount(NoteCellSourceDrawer, {
      props: { visible: true, cellInfo: formulaCellInfo },
      global: globalStubs,
    })
    expect(wrapper.text()).toContain('f_ar_001')
    expect(wrapper.text()).toContain("WP('D2','附注披露表','within_1_year_closing')")
    expect(wrapper.text()).toContain('template')
    expect(wrapper.text()).toContain('100.00')
    expect(wrapper.text()).toContain('2026-06-06T00:00:00Z')
  })

  it('展示公式依赖标签', () => {
    const wrapper = mount(NoteCellSourceDrawer, {
      props: { visible: true, cellInfo: formulaCellInfo },
      global: globalStubs,
    })
    expect(wrapper.text()).toContain('WP:D2.within_1_year_closing')
  })
})

describe('NoteCellSourceDrawer — 渲染带手工覆盖的单元格信息', () => {
  it('展示覆盖值和原自动值', () => {
    const wrapper = mount(NoteCellSourceDrawer, {
      props: { visible: true, cellInfo: manualOverrideCellInfo },
      global: globalStubs,
    })
    expect(wrapper.text()).toContain('200')
    expect(wrapper.text()).toContain('150')
  })

  it('展示覆盖时间', () => {
    const wrapper = mount(NoteCellSourceDrawer, {
      props: { visible: true, cellInfo: manualOverrideCellInfo },
      global: globalStubs,
    })
    expect(wrapper.text()).toContain('2026-06-05T10:30:00Z')
  })

  it('模式标签为"手工"且类型 warning', () => {
    const wrapper = mount(NoteCellSourceDrawer, {
      props: { visible: true, cellInfo: manualOverrideCellInfo },
      global: globalStubs,
    })
    const tags = wrapper.findAll('[data-test="tag"]')
    const modeTag = tags.find(t => t.text() === '手工')
    expect(modeTag).toBeTruthy()
    expect(modeTag!.attributes('data-type')).toBe('warning')
  })

  it('显示恢复自动取数按钮', () => {
    const wrapper = mount(NoteCellSourceDrawer, {
      props: { visible: true, cellInfo: manualOverrideCellInfo },
      global: globalStubs,
    })
    const buttons = wrapper.findAll('[data-test="button"]')
    const restoreBtn = buttons.find(b => b.text() === '恢复自动取数')
    expect(restoreBtn).toBeTruthy()
  })

  it('locked 模式不显示恢复自动按钮', () => {
    const lockedInfo: CellSourceInfo = {
      ...manualOverrideCellInfo,
      mode: 'locked',
    }
    const wrapper = mount(NoteCellSourceDrawer, {
      props: { visible: true, cellInfo: lockedInfo },
      global: globalStubs,
    })
    const buttons = wrapper.findAll('[data-test="button"]')
    const restoreBtn = buttons.find(b => b.text() === '恢复自动取数')
    expect(restoreBtn).toBeUndefined()
  })
})

describe('NoteCellSourceDrawer — navigate-source emit', () => {
  it('点击底稿跳转按钮 emit navigate-source', async () => {
    const wrapper = mount(NoteCellSourceDrawer, {
      props: { visible: true, cellInfo: formulaCellInfo },
      global: globalStubs,
    })
    const buttons = wrapper.findAll('[data-test="button"]')
    const wpBtn = buttons.find(b => b.text().includes('底稿 D2'))
    expect(wpBtn).toBeTruthy()
    await wpBtn!.trigger('click')

    const emitted = wrapper.emitted('navigate-source')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual({
      type: 'workpaper',
      id: undefined,
      wp_code: 'D2',
    })
  })

  it('多种依赖类型生成多个跳转按钮', () => {
    const wrapper = mount(NoteCellSourceDrawer, {
      props: { visible: true, cellInfo: errorCellInfo },
      global: globalStubs,
    })
    const buttons = wrapper.findAll('[data-test="button"]')
    const wpBtn = buttons.find(b => b.text().includes('底稿 D2'))
    const tbBtn = buttons.find(b => b.text().includes('试算表'))
    expect(wpBtn).toBeTruthy()
    expect(tbBtn).toBeTruthy()
  })
})

describe('NoteCellSourceDrawer — restore-auto emit', () => {
  it('点击恢复自动按钮 emit restore-auto', async () => {
    const wrapper = mount(NoteCellSourceDrawer, {
      props: { visible: true, cellInfo: manualOverrideCellInfo },
      global: globalStubs,
    })
    const buttons = wrapper.findAll('[data-test="button"]')
    const restoreBtn = buttons.find(b => b.text() === '恢复自动取数')
    expect(restoreBtn).toBeTruthy()
    await restoreBtn!.trigger('click')

    const emitted = wrapper.emitted('restore-auto')
    expect(emitted).toBeTruthy()
    expect(emitted!.length).toBe(1)
  })
})

describe('NoteCellSourceDrawer — 关闭/空状态', () => {
  it('visible=false 时不渲染内容', () => {
    const wrapper = mount(NoteCellSourceDrawer, {
      props: { visible: false, cellInfo: formulaCellInfo },
      global: globalStubs,
    })
    // ElDrawer stub only renders slot when modelValue=true
    expect(wrapper.text()).not.toContain('当前值')
  })

  it('cellInfo=null 时展示空状态', () => {
    const wrapper = mount(NoteCellSourceDrawer, {
      props: { visible: true, cellInfo: null },
      global: globalStubs,
    })
    const empty = wrapper.find('[data-test="empty"]')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('未选中单元格')
  })
})

describe('NoteCellSourceDrawer — 公式错误展示', () => {
  it('公式有错误时展示 error alert', () => {
    const wrapper = mount(NoteCellSourceDrawer, {
      props: { visible: true, cellInfo: errorCellInfo },
      global: globalStubs,
    })
    const alert = wrapper.find('[data-test="alert"]')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-type')).toBe('error')
    expect(alert.text()).toContain('底稿 D2 未找到字段 total_closing')
  })

  it('公式无错误时不展示 alert', () => {
    const wrapper = mount(NoteCellSourceDrawer, {
      props: { visible: true, cellInfo: formulaCellInfo },
      global: globalStubs,
    })
    const alert = wrapper.find('[data-test="alert"]')
    expect(alert.exists()).toBe(false)
  })
})
