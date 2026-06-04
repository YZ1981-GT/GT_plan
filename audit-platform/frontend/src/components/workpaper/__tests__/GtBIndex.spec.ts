/**
 * GtBIndex.spec.ts — B 类底稿目录组件单元测试
 *
 * 验证：
 * 1. 编制信息从 htmlData.preparation_info 自动填充（entity_name / period_end / preparer 等）
 * 2. preparation_info 缺失/空值时友好降级（显示 '—' 占位）
 * 3. 编制信息区可折叠：默认展开，点击标题栏收起；收起时显示概要（单位 · 索引号）
 * 4. 架构图节点点击 → handleNavigate → emit jump-to-section
 * 5. props.htmlData 变化时重新初始化
 *
 * 注：B-Index 索引导航已于 2026-06-02 由表格式重写为 GtBArchitectureTree 流程图，
 * 原"无需打印"批量切换/索引 chip 点击逻辑已移除，本测试已同步该重构。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import GtBIndex, { type BIndexSchema } from '../GtBIndex.vue'

// 流程图子组件 stub：仅暴露一个可触发 navigate 的按钮（隔离其内部取数逻辑）
vi.mock('@/components/workpaper/GtBArchitectureTree.vue', () => ({
  default: {
    name: 'GtBArchitectureTree',
    template:
      '<div class="gt-b-arch-tree-mock" @click="$emit(\'navigate\', \'D1-1\')">tree</div>',
    props: ['wpId', 'projectId', 'activeSheet', 'htmlData'],
    emits: ['navigate'],
  },
}))

// useRoute stub（组件用 route.params.projectId）
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'proj-001' } }),
}))

const globalStubs = {
  'el-descriptions': {
    template: '<div class="el-descriptions"><slot /></div>',
    props: ['title', 'column', 'border', 'size'],
  },
  'el-descriptions-item': {
    template: '<div class="el-descriptions-item" :data-label="label"><slot /></div>',
    props: ['label', 'span'],
  },
  'el-button': {
    template:
      '<button class="el-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'disabled', 'link'],
    emits: ['click'],
  },
}

function buildSchema(): BIndexSchema {
  return {
    component_type: 'b-index',
    preparation_info_fields: [
      { field: 'entity_name', label: '被审计单位' },
      { field: 'period_end', label: '截止日' },
      { field: 'preparer', label: '编制人' },
      { field: 'prep_date', label: '编制日期' },
      { field: 'reviewer', label: '复核人' },
      { field: 'review_date', label: '复核日期' },
      { field: 'index_no', label: '索引号' },
    ],
  }
}

function buildHtmlData() {
  return {
    preparation_info: {
      entity_name: '宜宾大药房有限公司',
      period_end: '2025年12月31日',
      preparer: '张三',
      prep_date: '2026.1.10',
      reviewer: '李四',
      review_date: '2026.1.15',
      index_no: 'D1',
    },
    navigation_rows: [
      { seq: 1, content: '应收账款审定表', index_ref: 'D2-1', no_print: false },
      { seq: 2, content: '应收账款实质性程序', index_ref: 'D2A', no_print: false },
    ],
  }
}

function mountIndex(htmlData: any, readonly = false) {
  return mount(GtBIndex, {
    props: {
      wpId: 'wp-001',
      sheetName: '底稿目录',
      schema: buildSchema(),
      htmlData,
      readonly,
    },
    global: { stubs: globalStubs },
  })
}

describe('GtBIndex — 编制信息自动填充', () => {
  it('preparation_info 完整时正确填充各字段', () => {
    const wrapper = mountIndex(buildHtmlData())
    const vm = wrapper.vm as any
    expect(vm.preparationInfo.entity_name).toBe('宜宾大药房有限公司')
    expect(vm.preparationInfo.period_end).toBe('2025年12月31日')
    expect(vm.preparationInfo.preparer).toBe('张三')
    expect(vm.preparationInfo.reviewer).toBe('李四')
    expect(vm.preparationInfo.index_no).toBe('D1')
  })

  it('preparation_info 缺失时友好降级（显示 "—"）', () => {
    const wrapper = mountIndex({ navigation_rows: [] } as any)
    expect(wrapper.html()).toContain('—')
    const vm = wrapper.vm as any
    expect(vm.preparationInfo.entity_name).toBeUndefined()
  })

  it('部分字段缺失时仅缺失字段降级', () => {
    const wrapper = mountIndex({
      preparation_info: { entity_name: '宜宾大药房有限公司', preparer: '张三' },
      navigation_rows: [],
    })
    const vm = wrapper.vm as any
    expect(vm.preparationInfo.entity_name).toBe('宜宾大药房有限公司')
    expect(vm.preparationInfo.preparer).toBe('张三')
    expect(vm.preparationInfo.period_end).toBeUndefined()
    expect(wrapper.html()).toContain('—')
  })

  it('字段为空字符串时降级到 "—"', () => {
    const wrapper = mountIndex({
      preparation_info: { entity_name: '', period_end: '', preparer: '' },
      navigation_rows: [],
    })
    expect(wrapper.html()).toContain('—')
  })
})

describe('GtBIndex — 编制信息折叠', () => {
  it('默认展开：descriptions 可见、不带 is-collapsed', () => {
    const wrapper = mountIndex(buildHtmlData())
    const vm = wrapper.vm as any
    expect(vm.prepCollapsed).toBe(false)
    expect(wrapper.find('.gt-b-index__preparation').classes()).not.toContain('is-collapsed')
    expect(wrapper.find('.el-descriptions').isVisible()).toBe(true)
  })

  it('点击标题栏切换折叠状态，descriptions 随之隐藏/显示', async () => {
    const wrapper = mountIndex(buildHtmlData())
    const vm = wrapper.vm as any
    const bar = wrapper.find('.gt-b-index__preparation-bar')
    expect(bar.exists()).toBe(true)

    await bar.trigger('click')
    await nextTick()
    expect(vm.prepCollapsed).toBe(true)
    expect(wrapper.find('.gt-b-index__preparation').classes()).toContain('is-collapsed')

    // 再次点击展开
    await bar.trigger('click')
    await nextTick()
    expect(vm.prepCollapsed).toBe(false)
    expect(wrapper.find('.gt-b-index__preparation').classes()).not.toContain('is-collapsed')
  })

  it('折叠按钮文案随状态切换（收起 ↔ 展开）', async () => {
    const wrapper = mountIndex(buildHtmlData())
    const toggle = wrapper.find('.gt-b-index__preparation-toggle')
    expect(toggle.text()).toBe('收起')
    await wrapper.find('.gt-b-index__preparation-bar').trigger('click')
    await nextTick()
    expect(toggle.text()).toBe('展开')
  })

  it('收起时显示概要：被审计单位 · 索引号', async () => {
    const wrapper = mountIndex(buildHtmlData())
    const vm = wrapper.vm as any
    expect(vm.prepSummary).toBe('宜宾大药房有限公司 · D1')
    await wrapper.find('.gt-b-index__preparation-bar').trigger('click')
    await nextTick()
    expect(wrapper.find('.gt-b-index__preparation-summary').text()).toBe(
      '宜宾大药房有限公司 · D1',
    )
  })

  it('概要在字段缺失时降级为 "—"', () => {
    const wrapper = mountIndex({ navigation_rows: [] } as any)
    const vm = wrapper.vm as any
    expect(vm.prepSummary).toBe('—')
  })

  it('索引号常显于标题栏右上角，且表内不再有单独索引号行', () => {
    const wrapper = mountIndex(buildHtmlData())
    const vm = wrapper.vm as any
    expect(vm.indexNo).toBe('D1')
    const idx = wrapper.find('.gt-b-index__preparation-index')
    expect(idx.exists()).toBe(true)
    expect(idx.text()).toContain('D1')
    // 表内不应再出现 label="索引号" 的描述项
    const labels = wrapper
      .findAll('.el-descriptions-item')
      .map((n) => n.attributes('data-label'))
    expect(labels).not.toContain('索引号')
  })

  it('索引号缺失时标题栏不渲染索引号块', () => {
    const wrapper = mountIndex({
      preparation_info: { entity_name: '某单位' },
      navigation_rows: [],
    })
    const vm = wrapper.vm as any
    expect(vm.indexNo).toBe('')
    expect(wrapper.find('.gt-b-index__preparation-index').exists()).toBe(false)
  })
})

describe('GtBIndex — 架构图导航跳转', () => {
  it('架构图 navigate → emit jump-to-section 携带 sheetName', async () => {
    const wrapper = mountIndex(buildHtmlData())
    await wrapper.find('.gt-b-arch-tree-mock').trigger('click')
    await nextTick()
    const emitted = wrapper.emitted('jump-to-section')
    expect(emitted).toBeDefined()
    expect(emitted!.length).toBe(1)
    expect(emitted![0][0]).toBe('D1-1')
  })

  it('handleNavigate 直接调用也 emit jump-to-section', async () => {
    const wrapper = mountIndex(buildHtmlData())
    const vm = wrapper.vm as any
    vm.handleNavigate('D2-1')
    await nextTick()
    expect(wrapper.emitted('jump-to-section')![0][0]).toBe('D2-1')
  })
})

describe('GtBIndex — htmlData 响应式同步', () => {
  it('props.htmlData 变化时重新初始化数据', async () => {
    const wrapper = mountIndex(buildHtmlData())
    const vm = wrapper.vm as any
    expect(vm.preparationInfo.entity_name).toBe('宜宾大药房有限公司')

    await wrapper.setProps({
      htmlData: {
        preparation_info: { entity_name: '新单位', period_end: '2026-12-31' },
        navigation_rows: [{ seq: 1, content: '新行', index_ref: 'X1', no_print: false }],
      },
    })
    await nextTick()

    expect(vm.preparationInfo.entity_name).toBe('新单位')
    expect(vm.navigationRows.length).toBe(1)
    expect(vm.navigationRows[0].index_ref).toBe('X1')
  })
})
