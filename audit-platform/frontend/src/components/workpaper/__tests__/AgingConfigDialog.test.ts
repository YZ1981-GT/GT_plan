/**
 * AgingConfigDialog.vue — Unit tests (Task 11.2)
 *
 * Feature: aging-config-enhancement
 *
 * Covers Requirement 7 acceptance criteria:
 * - 预设切换 UI 行为 (Req 7.1, 7.2, 7.3): radio 切换 3年段/5年段/自定义；
 *   预设模式展示只读段标签；自定义模式展示可编辑段列表 (add/remove)
 * - 自定义段校验逻辑 (Req 7.4): 空名/重复名/段数越界 → validationError → 确认按钮禁用
 * - 确认提交流程 (Req 7.4, 7.5): 确认调用 PUT API + dispatch aging-config:changed EventBus；
 *   段被移除时弹数据丢失警告并需显式确认
 *
 * 说明：Element Plus 组件以轻量 stub 挂载（避免 el-dialog teleport / transition 干扰），
 * ElMessage/ElMessageBox 与 apiProxy 均被 mock，以隔离 UI 行为与网络。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'

// ── Mock apiProxy (GET config on open / PUT config on confirm) ────────────────
let mockConfigResponse: any = null
const mockGet = vi.fn(async () => mockConfigResponse)
const mockPut = vi.fn(async () => ({}))
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

// ── Mock Element Plus messaging (ElMessage / ElMessageBox) ────────────────────
const mockMsgBoxConfirm = vi.fn()
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
  ElMessageBox: { confirm: (...args: any[]) => mockMsgBoxConfirm(...args) },
}))

import AgingConfigDialog from '../AgingConfigDialog.vue'
import { PRESET_SEGMENTS } from '@/composables/useAgingConfig'

// ── Element Plus stubs (single-root so class fall-through works) ──────────────
const ElDialog = {
  name: 'ElDialog',
  props: ['modelValue', 'title', 'width', 'closeOnClickModal'],
  emits: ['update:modelValue', 'open'],
  // 挂载时若可见则模拟 el-dialog 的 @open 事件，触发配置加载
  mounted(this: any) {
    if (this.modelValue) this.$emit('open')
  },
  template: `<div class="el-dialog"><slot /><div class="el-dialog__footer"><slot name="footer" /></div></div>`,
}
const ElRadioGroup = {
  name: 'ElRadioGroup',
  props: ['modelValue'],
  emits: ['update:modelValue', 'change'],
  template: `<div class="el-radio-group"><slot /></div>`,
}
const ElRadio = {
  name: 'ElRadio',
  props: ['value'],
  template: `<label class="el-radio"><slot /></label>`,
}
const ElInput = {
  name: 'ElInput',
  props: ['modelValue', 'placeholder', 'size'],
  emits: ['update:modelValue'],
  template: `<input class="el-input" :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" />`,
}
const ElButton = {
  name: 'ElButton',
  props: ['disabled', 'type', 'loading', 'link', 'size'],
  emits: ['click'],
  template: `<button class="el-button" :disabled="disabled" @click="$emit('click')"><slot /></button>`,
}
const ElTag = {
  name: 'ElTag',
  props: ['type', 'size'],
  template: `<span class="el-tag"><slot /></span>`,
}
const ElSelect = {
  name: 'ElSelect',
  props: ['modelValue', 'size', 'placeholder', 'clearable'],
  emits: ['update:modelValue'],
  template: `<select class="el-select"><slot /></select>`,
}
const ElOption = {
  name: 'ElOption',
  props: ['label', 'value'],
  template: `<option :value="value">{{ label }}</option>`,
}

function fiveYearResponse() {
  return {
    preset: 'FIVE_YEAR',
    effective_segments: PRESET_SEGMENTS.FIVE_YEAR.map((s) => ({ ...s })),
    subject_overrides: {},
  }
}

async function mountDialog(): Promise<VueWrapper<any>> {
  const wrapper = mount(AgingConfigDialog, {
    props: { projectId: 'proj-1', visible: true },
    global: {
      stubs: {
        'el-dialog': ElDialog,
        'el-radio-group': ElRadioGroup,
        'el-radio': ElRadio,
        'el-input': ElInput,
        'el-button': ElButton,
        'el-tag': ElTag,
        'el-select': ElSelect,
        'el-option': ElOption,
      },
      directives: {
        loading: {}, // no-op stub for v-loading
      },
    },
  })
  await flushPromises() // resolve onDialogOpen → api.get
  await nextTick()
  return wrapper
}

/** 通过 radio-group 切换预设（等价于用户点选 radio） */
async function switchPreset(wrapper: VueWrapper<any>, preset: string) {
  const group = wrapper.findComponent({ name: 'ElRadioGroup' })
  group.vm.$emit('update:modelValue', preset) // v-model → form.preset
  group.vm.$emit('change', preset) // @change → onPresetChange
  await nextTick()
}

function findConfirmButton(wrapper: VueWrapper<any>) {
  const buttons = wrapper.findAllComponents({ name: 'ElButton' })
  return buttons.find((b) => b.text().includes('确认保存'))!
}

beforeEach(() => {
  mockConfigResponse = fiveYearResponse()
  mockGet.mockClear()
  mockPut.mockClear()
  mockMsgBoxConfirm.mockReset()
  mockMsgBoxConfirm.mockResolvedValue(true)
})

// ─────────────────────────────────────────────────────────────────────────────
describe('AgingConfigDialog — 预设切换 UI 行为 (Req 7.1, 7.2, 7.3)', () => {
  it('打开时加载配置并展示三个预设选项 3年段/5年段/自定义', async () => {
    const wrapper = await mountDialog()
    expect(mockGet).toHaveBeenCalledWith(
      '/api/projects/proj-1/aging/config',
      expect.anything(),
    )
    const radios = wrapper.findAllComponents({ name: 'ElRadio' })
    const labels = radios.map((r) => r.text())
    expect(labels).toContain('3年段')
    expect(labels).toContain('5年段')
    expect(labels).toContain('自定义')
  })

  it('预设模式(5年段) 展示只读段标签, 无可编辑输入项 (Req 7.2)', async () => {
    const wrapper = await mountDialog()
    // 只读列表存在，编辑列表不存在
    expect(wrapper.find('.segment-readonly-list').exists()).toBe(true)
    expect(wrapper.find('.segment-edit-list').exists()).toBe(false)
    // 5年段 → 6 个只读标签
    const tags = wrapper.findAllComponents({ name: 'ElTag' })
    expect(tags).toHaveLength(PRESET_SEGMENTS.FIVE_YEAR.length)
    expect(tags.map((t) => t.text())).toEqual(
      PRESET_SEGMENTS.FIVE_YEAR.map((s) => s.label),
    )
  })

  it('切换到 3年段 → 展示 4 个只读标签 (Req 7.2)', async () => {
    const wrapper = await mountDialog()
    await switchPreset(wrapper, 'THREE_YEAR')
    const tags = wrapper.findAllComponents({ name: 'ElTag' })
    expect(tags).toHaveLength(PRESET_SEGMENTS.THREE_YEAR.length)
    expect(tags.map((t) => t.text())).toEqual(
      PRESET_SEGMENTS.THREE_YEAR.map((s) => s.label),
    )
  })

  it('切换到自定义 → 展示可编辑段列表与增删控件 (Req 7.3)', async () => {
    const wrapper = await mountDialog()
    await switchPreset(wrapper, 'CUSTOM')
    // 编辑列表出现，只读列表消失
    expect(wrapper.find('.segment-edit-list').exists()).toBe(true)
    expect(wrapper.find('.segment-readonly-list').exists()).toBe(false)
    // 每个自定义段一个可编辑输入 + “添加段”按钮存在
    const items = wrapper.findAll('.segment-edit-item')
    expect(items.length).toBe(PRESET_SEGMENTS.FIVE_YEAR.length)
    expect(wrapper.find('.add-segment-btn').exists()).toBe(true)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('AgingConfigDialog — 自定义段校验逻辑 (Req 7.4)', () => {
  it('全部有效自定义段 → 确认按钮可用', async () => {
    const wrapper = await mountDialog()
    await switchPreset(wrapper, 'CUSTOM')
    expect(findConfirmButton(wrapper).props('disabled')).toBe(false)
  })

  it('存在空段名 → 校验错误 + 确认按钮禁用', async () => {
    const wrapper = await mountDialog()
    await switchPreset(wrapper, 'CUSTOM')
    const inputs = wrapper.findAll('.segment-edit-item input.el-input')
    await inputs[0].setValue('') // 清空第一个段名
    await nextTick()
    expect(wrapper.find('.validation-error').text()).toContain('不能为空')
    expect(findConfirmButton(wrapper).props('disabled')).toBe(true)
  })

  it('存在重复段名 → 校验错误 + 确认按钮禁用', async () => {
    const wrapper = await mountDialog()
    await switchPreset(wrapper, 'CUSTOM')
    const inputs = wrapper.findAll('.segment-edit-item input.el-input')
    const firstLabel = (inputs[0].element as HTMLInputElement).value
    await inputs[1].setValue(firstLabel) // 第二段改为与第一段同名
    await nextTick()
    expect(wrapper.find('.validation-error').text()).toContain('不能重复')
    expect(findConfirmButton(wrapper).props('disabled')).toBe(true)
  })

  it('删除按钮在仅剩 2 段时禁用（下限保护）', async () => {
    const wrapper = await mountDialog()
    await switchPreset(wrapper, 'CUSTOM')
    // 逐个删除直到剩 2 段
    let removeBtns = wrapper
      .findAllComponents({ name: 'ElButton' })
      .filter((b) => b.text() === '删除')
    while (wrapper.findAll('.segment-edit-item').length > 2) {
      const btn = wrapper
        .findAllComponents({ name: 'ElButton' })
        .filter((b) => b.text() === '删除')
        .find((b) => !b.props('disabled'))!
      await btn.trigger('click')
      await nextTick()
    }
    expect(wrapper.findAll('.segment-edit-item').length).toBe(2)
    removeBtns = wrapper
      .findAllComponents({ name: 'ElButton' })
      .filter((b) => b.text() === '删除')
    expect(removeBtns.every((b) => b.props('disabled') === true)).toBe(true)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('AgingConfigDialog — 确认提交流程 (Req 7.4, 7.5)', () => {
  it('无段移除时确认 → 调用 PUT + 派发 EventBus + emit config-saved（不弹警告）', async () => {
    const wrapper = await mountDialog()

    let eventFired = false
    const handler = () => { eventFired = true }
    window.addEventListener('aging-config:changed', handler)

    await findConfirmButton(wrapper).trigger('click')
    await flushPromises()

    // 未移除任何段 → 不弹数据丢失警告
    expect(mockMsgBoxConfirm).not.toHaveBeenCalled()
    // PUT 调用且 payload 为当前预设
    expect(mockPut).toHaveBeenCalledTimes(1)
    const [url, payload] = mockPut.mock.calls[0] as any[]
    expect(url).toBe('/api/projects/proj-1/aging/config')
    expect(payload.preset).toBe('FIVE_YEAR')
    // 全局事件派发
    expect(eventFired).toBe(true)
    // 事件与关闭
    expect(wrapper.emitted('config-saved')).toBeTruthy()
    expect(wrapper.emitted('update:visible')).toBeTruthy()

    window.removeEventListener('aging-config:changed', handler)
  })

  it('段被移除(5年段→3年段) 时确认 → 弹数据丢失警告后再 PUT', async () => {
    const wrapper = await mountDialog()
    await switchPreset(wrapper, 'THREE_YEAR') // 移除 3-4年/4-5年/5年以上

    await findConfirmButton(wrapper).trigger('click')
    await flushPromises()

    // 弹出数据丢失警告
    expect(mockMsgBoxConfirm).toHaveBeenCalledTimes(1)
    // 用户确认后继续 PUT
    expect(mockPut).toHaveBeenCalledTimes(1)
    const [, payload] = mockPut.mock.calls[0] as any[]
    expect(payload.preset).toBe('THREE_YEAR')
  })

  it('数据丢失警告被取消 → 不调用 PUT', async () => {
    mockMsgBoxConfirm.mockRejectedValue('cancel')
    const wrapper = await mountDialog()
    await switchPreset(wrapper, 'THREE_YEAR')

    await findConfirmButton(wrapper).trigger('click')
    await flushPromises()

    expect(mockMsgBoxConfirm).toHaveBeenCalledTimes(1)
    expect(mockPut).not.toHaveBeenCalled()
    // 未保存 → 不 emit config-saved
    expect(wrapper.emitted('config-saved')).toBeFalsy()
  })

  it('自定义预设确认 → PUT payload 含 custom_segments', async () => {
    const wrapper = await mountDialog()
    await switchPreset(wrapper, 'CUSTOM')

    await findConfirmButton(wrapper).trigger('click')
    await flushPromises()

    expect(mockPut).toHaveBeenCalledTimes(1)
    const [, payload] = mockPut.mock.calls[0] as any[]
    expect(payload.preset).toBe('CUSTOM')
    expect(Array.isArray(payload.custom_segments)).toBe(true)
    expect(payload.custom_segments.length).toBe(PRESET_SEGMENTS.FIVE_YEAR.length)
    expect(payload.custom_segments[0]).toHaveProperty('label')
    expect(payload.custom_segments[0]).toHaveProperty('key')
  })
})
