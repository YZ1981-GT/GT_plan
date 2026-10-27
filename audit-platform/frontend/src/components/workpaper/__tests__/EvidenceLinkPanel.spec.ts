/**
 * EvidenceLinkPanel — 侧栏证据页签（spec attachment-evidence-intake 需求 3、5.3）
 *
 * 回归背景：新增链接要手填附件 UUID；类型选项有后端不认的 statement / other；清单只有单元格不见文件名。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, inject, provide } from 'vue'

const mockApiGet = vi.fn()
const mockApiPost = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockApiGet(...args),
    post: (...args: any[]) => mockApiPost(...args),
  },
}))
const mockHttpGet = vi.fn()
const mockHttpDelete = vi.fn()
vi.mock('@/utils/http', () => ({
  default: {
    get: (...args: any[]) => mockHttpGet(...args),
    delete: (...args: any[]) => mockHttpDelete(...args),
  },
}))
const confirmDelete = vi.fn()
vi.mock('@/utils/confirm', () => ({ confirmDelete: (...args: any[]) => confirmDelete(...args) }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return { ...actual, ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }
})

import EvidenceLinkPanel from '../EvidenceLinkPanel.vue'
import { EVIDENCE_TYPE_OPTIONS } from '@/components/attachment/workpaperEvidence'
import { resetWpEvidenceLinksForTest } from '@/composables/useWpEvidenceLinks'

const TableStub = defineComponent({
  name: 'ElTableStub',
  props: { data: { type: Array, default: () => [] } },
  setup(props, { slots }) {
    provide('stubRows', () => props.data)
    return () => h('div', { class: 'el-table-stub' }, slots.default?.())
  },
})
const ColumnStub = defineComponent({
  name: 'ElTableColumnStub',
  props: ['label', 'prop', 'width', 'minWidth', 'fixed', 'showOverflowTooltip'],
  setup(props, { slots }) {
    const rows = inject<() => any[]>('stubRows', () => [])
    return () => h('div', { class: 'col', 'data-label': props.label }, rows().map((row, i) =>
      h('div', { class: 'cell', key: i }, slots.default ? slots.default({ row }) : String(row[props.prop] ?? '')),
    ))
  },
})
const SelectStub = defineComponent({
  name: 'ElSelectStub',
  props: ['modelValue', 'filterable', 'loading', 'placeholder', 'noDataText', 'clearable'],
  emits: ['update:modelValue'],
  setup(props, { slots, emit, attrs }) {
    return () => h('select', {
      'data-testid': attrs['data-testid'],
      value: props.modelValue,
      onChange: (e: Event) => emit('update:modelValue', (e.target as HTMLSelectElement).value),
    }, [h('option', { value: '' }, ''), ...(slots.default?.() ?? [])])
  },
})

const stubs = {
  'el-table': TableStub,
  'el-table-column': ColumnStub,
  'el-select': SelectStub,
  'el-option': { template: '<option :value="value">{{ label }}</option>', props: ['label', 'value'] },
  'el-dialog': { template: '<div v-if="modelValue" class="el-dialog"><slot /><slot name="footer" /></div>', props: ['modelValue', 'title', 'width'] },
  'el-form': { template: '<form><slot /></form>' },
  'el-form-item': { template: '<label><slot /></label>', props: ['label'] },
  'el-input': {
    template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)">',
    props: ['modelValue', 'placeholder', 'maxlength'],
  },
  'el-button': { template: '<button :data-testid="$attrs[\'data-testid\']" :aria-label="$attrs[\'aria-label\']" @click="$emit(\'click\')"><slot /></button>', inheritAttrs: false },
  'el-icon': { template: '<i><slot /></i>' },
}

function link(id: string, fileName: string, cellRef: string, evidenceType: string | null = 'voucher') {
  return {
    id, wp_id: 'w1', sheet_name: 'D2A', cell_ref: cellRef, attachment_id: `att-${id}`, page_ref: null,
    evidence_type: evidenceType, check_conclusion: null, created_by: 'u1', created_at: null,
    attachment: { id: `att-${id}`, file_name: fileName, file_size: 1, file_type: 'pdf', attachment_type: 'voucher', ocr_status: null, created_at: null },
  }
}

function mountPanel() {
  return mount(EvidenceLinkPanel, {
    props: { projectId: 'p1', wpId: 'w1' },
    global: { stubs, directives: { loading: {} } },
  })
}

describe('EvidenceLinkPanel', () => {
  beforeEach(() => {
    resetWpEvidenceLinksForTest()
    for (const m of [mockApiGet, mockApiPost, mockHttpGet, mockHttpDelete, confirmDelete]) m.mockReset()
  })

  it('清单显示文件名、位置与中文类型', async () => {
    mockHttpGet.mockResolvedValueOnce({ data: { items: [link('l1', '凭证.pdf', 'item:3')] } })
    const wrapper = mountPanel()
    await flushPromises()
    expect(mockHttpGet.mock.calls[0][0]).toBe('/api/projects/p1/workpapers/w1/evidence')
    const text = wrapper.text()
    expect(text).toContain('凭证.pdf')
    expect(text).toContain('D2A · 第 3 项')
    expect(text).toContain('凭证 / 原始单据')
  })

  it('新增链接从本底稿附件里选，提交后重取清单', async () => {
    mockHttpGet
      .mockResolvedValueOnce({ data: { items: [] } })
      .mockResolvedValueOnce({ data: { items: [link('l9', '合同.pdf', 'B5', 'contract')] } })
    mockApiGet.mockResolvedValueOnce({ items: [{ id: 'att-9', file_name: '合同.pdf' }, { id: 'att-8', file_name: '对账单.pdf' }] })
    mockApiPost.mockResolvedValueOnce({ id: 'l9' })
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.find('[data-testid="evidence-link-add"]').trigger('click')
    await flushPromises()
    expect(mockApiGet).toHaveBeenCalledWith('/api/working-papers/w1/attachments')
    const picker = wrapper.find('select[data-testid="evidence-link-attachment"]')
    expect(picker.findAll('option').map((o) => o.text())).toEqual(['', '合同.pdf', '对账单.pdf'])
    expect(wrapper.find('input[placeholder="附件 UUID"]').exists()).toBe(false)
    await picker.setValue('att-9')
    await wrapper.find('[data-testid="evidence-link-submit"]').trigger('click')
    await flushPromises()

    expect(mockApiPost).toHaveBeenCalledWith('/api/projects/p1/workpapers/w1/evidence/link', expect.objectContaining({
      attachment_id: 'att-9', sheet_name: null, cell_ref: null, page_ref: null, evidence_type: null,
    }))
    expect(mockApiPost.mock.calls[0][1]).not.toHaveProperty('created_by')
    expect(mockHttpGet).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('合同.pdf')
  })

  it('证据类型选项与上传入口同一份（没有后端不认的 statement / other）', async () => {
    mockHttpGet.mockResolvedValueOnce({ data: { items: [] } })
    mockApiGet.mockResolvedValueOnce({ items: [] })
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.find('[data-testid="evidence-link-add"]').trigger('click')
    await flushPromises()
    const selects = wrapper.findAll('select')
    const typeValues = selects[selects.length - 1].findAll('option').map((o) => o.attributes('value')).filter(Boolean)
    expect(typeValues).toEqual(EVIDENCE_TYPE_OPTIONS.map((o) => o.value))
  })

  it('删除链接走 DELETE（附件保留）', async () => {
    mockHttpGet
      .mockResolvedValueOnce({ data: { items: [link('l1', '凭证.pdf', 'item:3')] } })
      .mockResolvedValueOnce({ data: { items: [] } })
    mockHttpDelete.mockResolvedValueOnce({ data: { ok: true } })
    confirmDelete.mockResolvedValueOnce(undefined)
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.find('button[aria-label="删除证据链接 凭证.pdf"]').trigger('click')
    await flushPromises()
    expect(mockHttpDelete).toHaveBeenCalledWith('/api/projects/p1/workpapers/w1/evidence/l1', expect.anything())
    expect(wrapper.text()).not.toContain('凭证.pdf')
  })
})
