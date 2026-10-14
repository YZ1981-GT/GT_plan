/**
 * NoteContentTemplatePicker（#6c 浏览器实测发现）
 *
 * 真库首次打开选择器时列表端点 500（本地库未跑 V187），首版选择器把失败显示成
 * 「暂无可用的附注内容模板」——用户会以为没有模板，失败被藏起来。
 * 另：列表固定只取前 50 个、超出部分无任何提示（静默截断）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'

const get = vi.fn()
vi.mock('@/services/apiProxy', () => ({ api: { get: (...a: unknown[]) => get(...a), post: vi.fn(), delete: vi.fn() } }))
vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: vi.fn() } }))

import NoteContentTemplatePicker from '@/components/disclosure/NoteContentTemplatePicker.vue'

const stubs = {
  'el-dialog': { props: ['modelValue', 'title'], template: '<div class="el-dialog"><slot /></div>' },
  'el-button': {
    props: ['disabled', 'loading', 'type'], emits: ['click'],
    template: '<button class="el-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
  'el-tag': { template: '<span class="el-tag"><slot /></span>' },
  'el-alert': { props: ['title'], template: '<div class="el-alert">{{ title }}</div>' },
}

const VERSION = {
  id: 'v1', version_no: 1, source_project_name: '甲公司', source_year: 2025, template_type: 'soe',
  report_scope: 'standalone', quality_summary: { total: 3 }, content_hash: 'h'.repeat(64), byte_size: 10,
  created_at: '2026-10-01T00:00:00',
}
const item = (id: string) => ({ id, name: `模板${id}`, owner_scope: 'personal', description: null, current_version: VERSION })
const http500 = () => Object.assign(new Error('Request failed with status code 500'), { response: { status: 500, data: '' } })

function mountPicker() {
  return mount(NoteContentTemplatePicker, { props: { visible: true, projectId: 'p1' }, global: { stubs } })
}
function buttons(w: VueWrapper, text: string) {
  return w.findAll('button').filter(b => b.text() === text)
}

beforeEach(() => get.mockReset())

describe('NoteContentTemplatePicker', () => {
  it('加载失败 ⇒ 显示失败原因与重试，不显示「暂无模板」；重试成功后列出模板', async () => {
    get.mockRejectedValueOnce(http500())
    const w = mountPicker()
    await flushPromises()
    expect(w.find('.el-alert').text()).toBe('模板列表加载失败（HTTP 500）')
    expect(w.text()).not.toContain('暂无可用')
    get.mockResolvedValueOnce({ items: [item('A')], total: 1 })
    await buttons(w, '重试')[0].trigger('click')
    await flushPromises()
    expect(w.text()).toContain('模板A')
    expect(w.text()).not.toContain('加载失败')
  })

  it('成功且确实没有模板 ⇒ 才显示「暂无可用」', async () => {
    get.mockResolvedValueOnce({ items: [], total: 0 })
    const w = mountPicker()
    await flushPromises()
    expect(w.text()).toContain('暂无可用的附注内容模板')
    expect(buttons(w, '重试')).toHaveLength(0)
  })

  it('总数多于已载 ⇒ 提示已显示条数，「加载更多」以已载条数为 offset 追加', async () => {
    get.mockResolvedValueOnce({ items: [item('A')], total: 2 })
    const w = mountPicker()
    await flushPromises()
    expect(w.text()).toContain('已显示 1 / 共 2 个')
    get.mockResolvedValueOnce({ items: [item('B')], total: 2 })
    await buttons(w, '加载更多')[0].trigger('click')
    await flushPromises()
    expect(get.mock.calls[1][1]).toMatchObject({ params: { limit: 50, offset: 1 } })
    expect(w.text()).toContain('模板A')
    expect(w.text()).toContain('模板B')
    expect(buttons(w, '加载更多')).toHaveLength(0)
  })

  it('历史版本加载失败 ⇒ 不展开空的版本区', async () => {
    get.mockResolvedValueOnce({ items: [item('A')], total: 1 })
    const w = mountPicker()
    await flushPromises()
    get.mockRejectedValueOnce(http500())
    await buttons(w, '历史版本')[0].trigger('click')
    await flushPromises()
    expect(buttons(w, '收起版本')).toHaveLength(0)
    expect(w.find('.gt-ntpk-versions').exists()).toBe(false)
  })
})
