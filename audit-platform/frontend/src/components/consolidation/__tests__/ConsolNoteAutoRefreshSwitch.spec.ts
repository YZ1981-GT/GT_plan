/**
 * 合并附注「自动刷新」开关（spec consol-note-header-library-and-node-reaggregate R7.1）：
 * 读写后端项目级开关；写成功才翻转，失败保持原状并按操作语境提示；全局开启时不可改；读失败不可改并说明原因。
 * el-switch 用桩：点击时调 before-change，返回 true 才发 update:modelValue（Element Plus 同语义，浏览器另测真组件）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

const { service, message, handleApiError } = vi.hoisted(() => ({
  service: { getConsolNoteAutoRefresh: vi.fn(), setConsolNoteAutoRefresh: vi.fn() },
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
  handleApiError: vi.fn(),
}))
vi.mock('@/services/consolidationApi', () => service)
vi.mock('element-plus', () => ({ ElMessage: message }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError }))

import ConsolNoteAutoRefreshSwitch from '../ConsolNoteAutoRefreshSwitch.vue'

const SwitchStub = defineComponent({
  props: ['modelValue', 'disabled', 'loading', 'beforeChange', 'ariaLabel'],
  emits: ['update:modelValue'],
  setup(p, { emit }) {
    return () => h('button', {
      class: 'switch', 'data-checked': String(!!p.modelValue), disabled: !!p.disabled, 'aria-label': p.ariaLabel,
      onClick: async () => {
        if (p.disabled) return
        const ok = p.beforeChange ? await p.beforeChange() : true
        if (ok) emit('update:modelValue', !p.modelValue)
      },
    })
  },
})
const TooltipStub = defineComponent({
  props: ['content'],
  setup(p, { slots }) { return () => h('div', { class: 'tip', 'data-content': p.content }, slots.default?.()) },
})

function mountSwitch(projectId = 'p1') {
  return mount(ConsolNoteAutoRefreshSwitch, {
    props: { projectId },
    global: { stubs: { 'el-switch': SwitchStub, 'el-tooltip': TooltipStub } },
  })
}
const off = { project_enabled: false, global_enabled: false, effective_enabled: false }
const on = { project_enabled: true, global_enabled: false, effective_enabled: true }

beforeEach(() => {
  Object.values(service).forEach((f) => f.mockReset())
  Object.values(message).forEach((f) => f.mockClear())
  handleApiError.mockClear()
})

describe('ConsolNoteAutoRefreshSwitch', () => {
  it('挂载即读开关；说明写明开启后做什么、拉来的数不覆盖', async () => {
    service.getConsolNoteAutoRefresh.mockResolvedValue(off)
    const w = mountSwitch()
    await flushPromises()
    expect(service.getConsolNoteAutoRefresh).toHaveBeenCalledWith('p1')
    const sw = w.get('button.switch')
    expect(sw.attributes('data-checked')).toBe('false')
    expect(sw.attributes('disabled')).toBeUndefined()
    expect(sw.attributes('aria-label')).toBe('试算表变动后自动刷新合并附注')
    const tip = w.get('.tip').attributes('data-content')
    expect(tip).toContain('开启后，试算表、调整分录或影响附注的底稿保存后，自动按公式刷新合并附注')
    expect(tip).toContain('从单体附注拉来的数不覆盖、只标「待更新」')
  })

  it('切换：写成功才翻转，提示已开启', async () => {
    service.getConsolNoteAutoRefresh.mockResolvedValue(off)
    service.setConsolNoteAutoRefresh.mockResolvedValue(on)
    const w = mountSwitch()
    await flushPromises()
    await w.get('button.switch').trigger('click')
    await flushPromises()
    expect(service.setConsolNoteAutoRefresh).toHaveBeenCalledWith('p1', true)
    expect(w.get('button.switch').attributes('data-checked')).toBe('true')
    expect(message.success).toHaveBeenCalledWith(expect.stringContaining('已开启自动刷新'))
  })

  it('写失败（如 403 无编辑权限）：保持原状，按操作语境提示', async () => {
    service.getConsolNoteAutoRefresh.mockResolvedValue(off)
    const err = { response: { status: 403, data: { detail: '权限不足' } } }
    service.setConsolNoteAutoRefresh.mockRejectedValue(err)
    const w = mountSwitch()
    await flushPromises()
    await w.get('button.switch').trigger('click')
    await flushPromises()
    expect(w.get('button.switch').attributes('data-checked')).toBe('false')
    expect(handleApiError).toHaveBeenCalledWith(err, '修改自动刷新开关')
    expect(message.success).not.toHaveBeenCalled()
  })

  it('已开启时再点 = 关闭', async () => {
    service.getConsolNoteAutoRefresh.mockResolvedValue(on)
    service.setConsolNoteAutoRefresh.mockResolvedValue(off)
    const w = mountSwitch()
    await flushPromises()
    expect(w.get('button.switch').attributes('data-checked')).toBe('true')
    await w.get('button.switch').trigger('click')
    await flushPromises()
    expect(service.setConsolNoteAutoRefresh).toHaveBeenCalledWith('p1', false)
    expect(w.get('button.switch').attributes('data-checked')).toBe('false')
    expect(message.success).toHaveBeenCalledWith('已关闭自动刷新')
  })

  it('全局开关开着：显示开启、不可改、说明全局已开启', async () => {
    service.getConsolNoteAutoRefresh.mockResolvedValue({ project_enabled: false, global_enabled: true, effective_enabled: true })
    const w = mountSwitch()
    await flushPromises()
    const sw = w.get('button.switch')
    expect(sw.attributes('data-checked')).toBe('true')
    expect(sw.attributes('disabled')).toBeDefined()
    expect(w.get('.tip').attributes('data-content')).toContain('全局已开启')
    await sw.trigger('click')
    await flushPromises()
    expect(service.setConsolNoteAutoRefresh).not.toHaveBeenCalled()
  })

  it('读失败：不可改，说明原因', async () => {
    service.getConsolNoteAutoRefresh.mockRejectedValue({ response: { status: 404, data: { detail: '项目不存在' } } })
    const w = mountSwitch()
    await flushPromises()
    expect(w.get('button.switch').attributes('disabled')).toBeDefined()
    expect(w.get('.tip').attributes('data-content')).toBe('自动刷新开关读取失败：项目不存在')
  })

  it('换项目重读；写入期间换了项目则结果不落到新项目', async () => {
    service.getConsolNoteAutoRefresh.mockResolvedValueOnce(off).mockResolvedValueOnce(off)
    let release!: (v: unknown) => void
    service.setConsolNoteAutoRefresh.mockReturnValue(new Promise((r) => { release = r }))
    const w = mountSwitch('p1')
    await flushPromises()
    void w.get('button.switch').trigger('click')
    await flushPromises()
    await w.setProps({ projectId: 'p2' })
    await flushPromises()
    expect(service.getConsolNoteAutoRefresh).toHaveBeenLastCalledWith('p2')
    release(on)
    await flushPromises()
    expect(w.get('button.switch').attributes('data-checked')).toBe('false')
  })
})
