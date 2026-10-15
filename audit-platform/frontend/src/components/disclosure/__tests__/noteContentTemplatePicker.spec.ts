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
import { appliedHint, savedByLabel } from '@/components/disclosure/noteTextBatchLabels'
import type { ContentTemplateVersion } from '@/composables/useNoteContentTemplate'

const stubs = {
  'el-dialog': { props: ['modelValue', 'title'], template: '<div class="el-dialog"><slot /></div>' },
  'el-button': {
    props: ['disabled', 'loading', 'type'], emits: ['click'],
    template: '<button class="el-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
  'el-tag': { template: '<span class="el-tag"><slot /></span>' },
  'el-alert': { props: ['title'], template: '<div class="el-alert">{{ title }}</div>' },
}

const VERSION: ContentTemplateVersion = {
  id: 'v1', version_no: 1, source_project_name: '甲公司', source_year: 2025, template_type: 'soe',
  report_scope: 'standalone', quality_summary: { total: 3 }, content_hash: 'h'.repeat(64), byte_size: 10,
  created_at: '2026-10-01T00:00:00',
}
const V2: ContentTemplateVersion = { ...VERSION, id: 'v2', version_no: 2 }
const APPLIED_V1 = { version_id: 'v1', version_no: 1, applied_at: '2026-10-02T00:00:00' }
const item = (id: string, over: Record<string, unknown> = {}) =>
  ({ id, name: `模板${id}`, owner_scope: 'personal', description: null, current_version: VERSION, ...over })
const http500 = () => Object.assign(new Error('Request failed with status code 500'), { response: { status: 500, data: '' } })

function mountPicker() {
  return mount(NoteContentTemplatePicker, { props: { visible: true, projectId: 'p1', year: 2025 }, global: { stubs } })
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

  it('列表请求带编辑器年度：「已引用」按本项目本年度判定', async () => {
    get.mockResolvedValueOnce({ items: [], total: 0 })
    mountPicker()
    await flushPromises()
    expect(get.mock.calls[0][1]).toMatchObject({ params: { limit: 50, offset: 0, year: 2025 } })
  })

  it('AC-8.2：版本说明含保存人姓名与保存时间', async () => {
    get.mockResolvedValueOnce({ items: [item('A', { current_version: { ...VERSION, created_by_name: '经理甲' } })], total: 1 })
    const w = mountPicker()
    await flushPromises()
    expect(w.find('.gt-ntpk-item').text()).toContain('经理甲 保存于 2026-10-01')
  })

  it('AC-8.4：引用过旧版本 ⇒ 提示有新版本，入口改「重新预览」且选的是当前版本；引用的就是当前版本 ⇒ 只说明；未引用 ⇒ 不提示', async () => {
    get.mockResolvedValueOnce({ total: 3, items: [
      item('OLD', { current_version: V2, last_applied: APPLIED_V1 }), item('SAME', { last_applied: APPLIED_V1 }), item('NEVER')] })
    const w = mountPicker()
    await flushPromises()
    const block = (name: string) => w.findAll('.gt-ntpk-item').find(b => b.find('strong').text() === name)!
    const hint = (name: string) => block(name).find('.gt-ntpk-applied')
    expect(w.findAll('.gt-ntpk-applied')).toHaveLength(2)
    expect(hint('模板OLD').text()).toBe('有新版本 v2（本项目已引用 v1）：已写入的正文不会自动更新，点「重新预览」核对后才会写入')
    expect(hint('模板OLD').classes()).toContain('is-changed')
    expect(hint('模板SAME').text()).toBe('本项目已引用当前版本 v1')
    expect(hint('模板SAME').classes()).not.toContain('is-changed')
    expect(hint('模板NEVER').exists()).toBe(false)
    expect(block('模板SAME').findAll('button').map(b => b.text())).toContain('引用最新版本')
    expect(block('模板OLD').findAll('button').map(b => b.text())).toContain('重新预览')
    await block('模板OLD').findAll('button').find(b => b.text() === '重新预览')!.trigger('click')
    expect(w.emitted('select')![0][1]).toMatchObject({ id: 'v2' })
  })

  it('历史版本里标出本项目已引用的那一版', async () => {
    get.mockResolvedValueOnce({ items: [item('A', { current_version: V2, last_applied: APPLIED_V1 })], total: 1 })
    const w = mountPicker()
    await flushPromises()
    get.mockResolvedValueOnce({ items: [V2, VERSION] })
    await buttons(w, '历史版本')[0].trigger('click')
    await flushPromises()
    expect(w.findAll('.gt-ntpk-versions .gt-ntpk-row').map(r => r.find('.el-tag').exists())).toEqual([false, true])
  })
})

describe('模板引用标签', () => {
  it('appliedHint：模板内容回退到更早版本也算「不同」；没有当前版本时只说明已引用；从未引用为 null', () => {
    const applied = { version_id: 'v3', version_no: 3, applied_at: null }
    expect(appliedHint({ current_version: V2, last_applied: applied })).toEqual({ changed: true,
      text: '模板当前为 v2（本项目已引用 v3）：已写入的正文不会自动更新，点「重新预览」核对后才会写入' })
    expect(appliedHint({ current_version: null, last_applied: applied })).toEqual({ changed: false, text: '本项目已引用 v3' })
    expect(appliedHint({ current_version: VERSION, last_applied: null })).toBeNull()
  })

  it('savedByLabel：有姓名带姓名，无姓名只写时间，都没有为空', () => {
    expect(savedByLabel({ created_by_name: '经理甲', created_at: '2026-10-01T08:00:00' })).toBe('经理甲 保存于 2026-10-01')
    expect(savedByLabel({ created_by_name: null, created_at: '2026-10-01T08:00:00' })).toBe('保存于 2026-10-01')
    expect(savedByLabel({ created_by_name: '经理甲', created_at: null })).toBe('保存人 经理甲')
    expect(savedByLabel({ created_at: null })).toBe('')
  })
})
