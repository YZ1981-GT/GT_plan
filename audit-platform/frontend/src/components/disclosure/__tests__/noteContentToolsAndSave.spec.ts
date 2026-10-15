/**
 * DisclosureNoteContentTools（R-19 / R-20）+ NoteContentTemplateSaveDialog（R-22）
 *
 * - 无写权限时入口拒绝打开（菜单另按同一条件隐藏，后端仍独立 403 / 423）；
 * - 写入成功上报被改写的章节，由编辑器作废全部缓存后强制刷新；
 * - 「保存为内容模板」走真实流程：预检 → 集团二次确认 → 携 digest 保存；来源变化 409 要求重新预检。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

const post = vi.fn()
const lockStatus = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    post: (...a: unknown[]) => post(...a),
    get: (url: string, ...rest: unknown[]) => (url.endsWith('/lock-status') ? lockStatus(url, ...rest) : Promise.resolve({})),
    delete: vi.fn(),
  },
}))
const confirm = vi.fn()
const warning = vi.fn()
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: (...a: unknown[]) => warning(...a), error: vi.fn() },
  ElMessageBox: { confirm: (...a: unknown[]) => confirm(...a) },
}))
const canOp = vi.fn((_op: string) => true)
vi.mock('@/composables/usePermissionMatrix', () => ({ usePermissionMatrix: () => ({ can: (op: string) => canOp(op) }) }))
const busHandlers: Record<string, Array<(p: unknown) => void>> = {}
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    on: (name: string, fn: (p: unknown) => void) => { (busHandlers[name] ||= []).push(fn) },
    off: (name: string, fn: (p: unknown) => void) => { busHandlers[name] = (busHandlers[name] || []).filter(h => h !== fn) },
    emit: vi.fn(),
  },
}))
vi.mock('@/components/disclosure/NoteDocUploadDialog.vue', () => ({
  // defineAsyncComponent 只在模块带 __esModule 时取 default；否则把模块对象本身当组件
  __esModule: true,
  default: defineComponent({
    name: 'NoteDocUploadDialogStub', emits: ['applied', 'update:visible'],
    setup: (_p, { emit }) => () => h('button', {
      class: 'upload-stub',
      onClick: () => emit('applied', { changed_notes: [{ id: 'n1', note_section: '一、1' }, { id: 'n2', note_section: '四、会计期间' }] }),
    }, '上传弹窗'),
  }),
}))

import DisclosureNoteContentTools from '@/components/disclosure/DisclosureNoteContentTools.vue'
import NoteContentTemplateSaveDialog from '@/components/disclosure/NoteContentTemplateSaveDialog.vue'

const stubs = {
  'el-dialog': { props: ['modelValue', 'title'], template: '<div class="el-dialog"><slot /><slot name="footer" /></div>' },
  'el-button': {
    props: ['disabled', 'loading', 'type'], emits: ['click'],
    template: '<button class="el-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
  'el-form': {
    props: ['model', 'rules'], template: '<form><slot /></form>',
    // 与 Element Plus 同语义：名称为空（去首尾空白后）⇒ 校验失败
    methods: { validate(this: any) { return this.model?.name?.trim() ? Promise.resolve(true) : Promise.reject(new Error('invalid')) } },
  },
  'el-form-item': { props: ['label'], template: '<div><slot /></div>' },
  'el-input': {
    props: ['modelValue', 'type', 'rows', 'maxlength', 'showWordLimit', 'placeholder'], emits: ['update:modelValue'],
    template: '<input class="el-input" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  'el-radio-group': { props: ['modelValue'], emits: ['update:modelValue'], template: '<div class="el-radio-group"><slot /></div>' },
  'el-radio': { props: ['value'], template: '<span class="el-radio"><slot /></span>' },
  'el-tag': { template: '<span class="el-tag"><slot /></span>' },
  'el-alert': { props: ['title'], template: '<div class="el-alert">{{ title }}</div>' },
}

const PREVIEW = { snapshot_digest: 'd'.repeat(64), source_project_name: '子甲', source_year: 2025, template_type: 'soe',
  report_scope: 'standalone', section_count: 3, quality_summary: { with_content: 2, high_risk: 1 },
  owner_scope: 'group', group_root_project_name: '集团' }

beforeEach(() => {
  post.mockReset()
  confirm.mockReset()
  warning.mockReset()
  lockStatus.mockReset()
  lockStatus.mockResolvedValue({ code: 200, data: { locked: false } })
  canOp.mockReset()
  canOp.mockReturnValue(true)
  Object.keys(busHandlers).forEach(k => delete busHandlers[k])
})

describe('DisclosureNoteContentTools', () => {
  it('无写权限：入口拒绝打开，不挂载任何弹窗', async () => {
    const wrapper = mount(DisclosureNoteContentTools, { props: { projectId: 'p1', year: 2025, canWrite: false } })
    expect((wrapper.vm as any).open('upload')).toBe(false)
    await flushPromises()
    expect(wrapper.find('.upload-stub').exists()).toBe(false)
    expect(warning).toHaveBeenCalled()
  })

  it('当前章节有未保存修改：三个入口都拒绝打开并提示先保存（写入后会重载附注，未保存修改会丢）', async () => {
    warning.mockClear()
    const wrapper = mount(DisclosureNoteContentTools,
      { props: { projectId: 'p1', year: 2025, canWrite: true, hasUnsavedChanges: true } })
    for (const kind of ['upload', 'apply', 'save']) expect((wrapper.vm as any).open(kind)).toBe(false)
    await flushPromises()
    expect(wrapper.find('.upload-stub').exists()).toBe(false)
    expect(warning).toHaveBeenCalledTimes(3)
    for (const [msg] of warning.mock.calls) expect(String(msg)).toContain('请先保存')
    await wrapper.setProps({ hasUnsavedChanges: false })
    expect((wrapper.vm as any).open('upload')).toBe(true)
  })

  it('合并锁定（AC-6.3）：入口不可用并拒绝打开；后端 423 事件到达后实时生效', async () => {
    const wrapper = mount(DisclosureNoteContentTools, { props: { projectId: 'p1', year: 2025, canWrite: true } })
    await flushPromises()
    // 必须关去重：同页锁定横幅几乎同时发同一个 GET，去重会取消先发的那一个，横幅就不显示（浏览器实测）
    expect(lockStatus).toHaveBeenCalledWith('/api/consolidation/p1/lock-status', { _dedupe: false, _silent: true })
    expect((wrapper.vm as any).available).toBe(true)
    lockStatus.mockResolvedValueOnce({ code: 200, data: { locked: true } })
    busHandlers['consol-lock:detected']?.forEach(h => h({ projectId: 'p1' }))
    await flushPromises()
    expect((wrapper.vm as any).available).toBe(false)
    warning.mockClear()
    expect((wrapper.vm as any).open('upload')).toBe(false)
    expect(String(warning.mock.calls[0]?.[0])).toContain('合并锁定')
  })

  it('锁定态查询失败不误报锁定（与锁定横幅同口径，后端仍独立 423）', async () => {
    lockStatus.mockRejectedValueOnce(new Error('network'))
    const wrapper = mount(DisclosureNoteContentTools, { props: { projectId: 'p1', year: 2025, canWrite: true } })
    await flushPromises()
    expect((wrapper.vm as any).available).toBe(true)
  })

  it('无附注编辑操作权限（note:edit，与后端 require_operation 同码）：入口不可用', async () => {
    canOp.mockImplementation((op: string) => op !== 'note:edit')
    const wrapper = mount(DisclosureNoteContentTools, { props: { projectId: 'p1', year: 2025, canWrite: true } })
    await flushPromises()
    expect((wrapper.vm as any).available).toBe(false)
    warning.mockClear()
    expect((wrapper.vm as any).open('save')).toBe(false)
    expect(String(warning.mock.calls[0]?.[0])).toContain('附注编辑权限')
  })

  it('写入成功上报全部被改写章节并关闭弹窗', async () => {
    const wrapper = mount(DisclosureNoteContentTools, { props: { projectId: 'p1', year: 2025, canWrite: true } })
    expect((wrapper.vm as any).open('upload')).toBe(true)
    await flushPromises()
    await wrapper.find('.upload-stub').trigger('click')
    expect(wrapper.emitted('applied')?.[0]).toEqual([['一、1', '四、会计期间']])
    await flushPromises()
    expect(wrapper.find('.upload-stub').exists()).toBe(false)
  })
})

describe('NoteContentTemplateSaveDialog', () => {
  async function mountDialog(scope: 'personal' | 'group') {
    const wrapper = mount(NoteContentTemplateSaveDialog, { props: { visible: true, projectId: 'p1', year: 2025 }, global: { stubs } })
    await wrapper.find('input.el-input').setValue('全套模板')
    if (scope === 'group') {
      wrapper.findComponent('.el-radio-group').vm.$emit('update:modelValue', 'group')
      await flushPromises()
    }
    return wrapper
  }
  const button = (w: any, text: string) => w.findAll('button').find((b: any) => b.text().includes(text))

  it('预检后才能保存；集团发布先二次确认，取消则不保存', async () => {
    const wrapper = await mountDialog('group')
    expect(button(wrapper, '保存').attributes('disabled')).toBeDefined()
    post.mockResolvedValueOnce(PREVIEW)
    await button(wrapper, '预检').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('发布范围：集团「集团」')
    confirm.mockRejectedValueOnce('cancel')
    await button(wrapper, '保存').trigger('click')
    await flushPromises()
    expect(post).toHaveBeenCalledTimes(1)
    confirm.mockResolvedValueOnce('confirm')
    post.mockResolvedValueOnce({ template_id: 't1', version_id: 'v1', version_no: 1, content_hash: 'h', reused: false })
    await button(wrapper, '保存').trigger('click')
    await flushPromises()
    expect(post.mock.calls[1][1]).toMatchObject({ owner_scope: 'group', snapshot_digest: 'd'.repeat(64) })
    expect(wrapper.emitted('saved')?.[0]?.[0]).toMatchObject({ version_no: 1 })
  })

  it('来源在预检后变化（409）：清掉预检结果，必须重新预检', async () => {
    const wrapper = await mountDialog('personal')
    post.mockResolvedValueOnce({ ...PREVIEW, owner_scope: 'personal', group_root_project_name: undefined })
    await button(wrapper, '预检').trigger('click')
    await flushPromises()
    post.mockRejectedValueOnce(Object.assign(new Error('409'), {
      response: { status: 409, data: { detail: { error_code: 'STALE_SNAPSHOT', message: '来源已变化' } } } }))
    await button(wrapper, '保存').trigger('click')
    await flushPromises()
    expect(confirm).not.toHaveBeenCalled()
    expect(button(wrapper, '保存').attributes('disabled')).toBeDefined()
  })

  it('预检后改表单 ⇒ 预检作废', async () => {
    const wrapper = await mountDialog('personal')
    post.mockResolvedValueOnce({ ...PREVIEW, owner_scope: 'personal' })
    await button(wrapper, '预检').trigger('click')
    await flushPromises()
    expect(button(wrapper, '保存').attributes('disabled')).toBeUndefined()
    await wrapper.find('input.el-input').setValue('改名')
    expect(button(wrapper, '保存').attributes('disabled')).toBeDefined()
  })
})
