/**
 * GtWpPreparationHeader.spec.ts — workpaper 级编制信息表头单测
 *
 * 验证：
 * 1. 从 /preparation-info 拉取并渲染字段（被审计单位/截止日/编制人 等）
 * 2. 索引号常显于标题栏右上角；表内不再有单独索引号描述项
 * 3. indexNoOverride（sheet 级，如 D1A）优先于 workpaper 级 index_no
 * 4. 折叠：默认展开，点击标题栏切 is-collapsed + 文案切换
 *
 * Validates: 编制信息表头去重 + sheet 级索引号显示
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

// mock apiProxy（隔离网络）——可按用例改返回值
const { mockGet, prepRef } = vi.hoisted(() => {
  return {
    prepRef: {
      value: {
        entity_name: '辽宁卫生服务有限公司_2025',
        period_end: '2025-12-31',
        preparer: '张三',
        prep_date: '2026-05-16',
        reviewer: '李四',
        review_date: '',
        index_no: 'D1',
      } as Record<string, string>,
    },
    mockGet: vi.fn(),
  }
})

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: unknown[]) => {
      mockGet(...args)
      return Promise.resolve(prepRef.value)
    },
  },
}))

const globalStubs = {
  'el-descriptions': {
    template: '<div class="el-descriptions"><slot /></div>',
    props: ['column', 'border', 'size'],
  },
  'el-descriptions-item': {
    template: '<div class="el-descriptions-item" :data-label="label"><slot /></div>',
    props: ['label', 'span'],
  },
  'el-button': {
    template:
      '<button class="el-button" @click="$emit(\'click\', $event)"><slot /></button>',
    props: ['type', 'size', 'link'],
    emits: ['click'],
  },
}

const vLoading = { mounted() {}, updated() {} }

import GtWpPreparationHeader from '../GtWpPreparationHeader.vue'

function mountWith(props: Record<string, unknown> = {}) {
  return mount(GtWpPreparationHeader, {
    props: { wpId: 'wp-001', ...props },
    global: { stubs: globalStubs, directives: { loading: vLoading } },
  })
}

beforeEach(() => {
  mockGet.mockClear()
  prepRef.value = {
    entity_name: '辽宁卫生服务有限公司_2025',
    period_end: '2025-12-31',
    preparer: '张三',
    prep_date: '2026-05-16',
    reviewer: '李四',
    review_date: '',
    index_no: 'D1',
  }
})

describe('GtWpPreparationHeader — 数据加载 + 渲染', () => {
  it('挂载即拉取 preparation-info 并渲染字段', async () => {
    const wrapper = mountWith()
    await nextTick()
    await nextTick()
    expect(mockGet).toHaveBeenCalledWith('/api/workpapers/wp-001/preparation-info')
    expect(wrapper.html()).toContain('辽宁卫生服务有限公司_2025')
    expect(wrapper.html()).toContain('张三')
  })

  it('表内不再有单独「索引号」描述项', async () => {
    const wrapper = mountWith()
    await nextTick()
    await nextTick()
    const labels = wrapper
      .findAll('.el-descriptions-item')
      .map((n) => n.attributes('data-label'))
    expect(labels).not.toContain('索引号')
    expect(labels).toContain('被审计单位')
  })
})

describe('GtWpPreparationHeader — 索引号右上角 + sheet 级覆盖', () => {
  it('无覆盖时显示 workpaper 级 index_no（D1）', async () => {
    const wrapper = mountWith()
    await nextTick()
    await nextTick()
    const idx = wrapper.find('.gt-wp-prep__index')
    expect(idx.exists()).toBe(true)
    expect(idx.text()).toContain('D1')
  })

  it('indexNoOverride 优先于 workpaper 级 index_no（D1A 覆盖 D1）', async () => {
    const wrapper = mountWith({ indexNoOverride: 'D1A' })
    await nextTick()
    await nextTick()
    const idx = wrapper.find('.gt-wp-prep__index')
    expect(idx.text()).toContain('D1A')
    expect(idx.text()).not.toContain('D1-') // 不是别的
    expect((wrapper.vm as any).indexNo).toBe('D1A')
  })

  it('override 切换时索引号随之更新（模拟 sheet 切换）', async () => {
    const wrapper = mountWith({ indexNoOverride: 'D1A' })
    await nextTick()
    await nextTick()
    expect(wrapper.find('.gt-wp-prep__index').text()).toContain('D1A')
    await wrapper.setProps({ indexNoOverride: 'D1-1' })
    await nextTick()
    expect(wrapper.find('.gt-wp-prep__index').text()).toContain('D1-1')
  })

  it('override 为空串时回退 workpaper 级 index_no', async () => {
    const wrapper = mountWith({ indexNoOverride: '' })
    await nextTick()
    await nextTick()
    expect(wrapper.find('.gt-wp-prep__index').text()).toContain('D1')
  })

  it('既无 override 也无 index_no → 不渲染索引号块', async () => {
    prepRef.value = { entity_name: '某单位' }
    const wrapper = mountWith()
    await nextTick()
    await nextTick()
    expect(wrapper.find('.gt-wp-prep__index').exists()).toBe(false)
  })
})

describe('GtWpPreparationHeader — 折叠', () => {
  it('默认展开，点击标题栏切 is-collapsed + 文案切换', async () => {
    const wrapper = mountWith()
    await nextTick()
    await nextTick()
    const root = wrapper.find('.gt-wp-prep')
    const toggle = wrapper.find('.gt-wp-prep__toggle')
    expect(root.classes()).not.toContain('is-collapsed')
    expect(toggle.text()).toBe('收起')

    await wrapper.find('.gt-wp-prep__bar').trigger('click')
    await nextTick()
    expect(root.classes()).toContain('is-collapsed')
    expect(toggle.text()).toBe('展开')
  })
})
