/**
 * 替代程序检查表行内附件（spec attachment-confirmation-evidence-loop 需求 3.1、3.3，变异 M4 / M5）
 *
 * - 附件列只读也显示（小眼睛），编辑态多一个 📎；
 * - 识别请求带单据类型 + 行级位置（表页 = 页编码、单元格 = `row:{行 id}`）；
 * - 填入只写勾选的空白列，经 CheckBlock 的 `update-field` 回到宿主；「仅上传」走证据入口、类型「支持文件」。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import ElementPlus from 'element-plus'

const mockPost = vi.fn()
const mockGet = vi.fn()
vi.mock('@/utils/http', () => ({
  default: { post: (...a: any[]) => mockPost(...a), get: (...a: any[]) => mockGet(...a), delete: vi.fn() },
  downloadFile: vi.fn(),
}))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { projectId: 'P1' } }) }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/components/attachment/RowEvidenceEye.vue', () => ({
  default: defineComponent({
    name: 'RowEvidenceEyeStub',
    props: ['wpId', 'sheetKey', 'cellRef', 'projectId'],
    setup: (p: any) => () => h('i', { class: 'eye-stub', 'data-sheet': p.sheetKey, 'data-cell': p.cellRef }),
  }),
}))
vi.mock('@/components/attachment/AttachmentEyeButton.vue', () => ({
  default: defineComponent({ name: 'EyeButtonStub', props: ['attachmentId'], setup: (p: any) => () => h('i', { class: 'doc-eye', 'data-id': p.attachmentId }) }),
}))

import CheckBlock from '../CheckBlock.vue'
import { BLOCK_COLUMN_CONFIGS } from '../blockColumnConfigs'

const UploadStub = defineComponent({
  name: 'ElUploadStub',
  props: ['onChange', 'accept'],
  setup: (_p, { slots }) => () => h('div', { class: 'upload-stub' }, slots.default?.()),
})
const DialogStub = defineComponent({
  name: 'ElDialogStub',
  props: ['modelValue'],
  setup: (p: any, { slots }) => () => (p.modelValue ? h('div', { class: 'dialog-stub' }, [slots.default?.(), slots.footer?.()]) : null),
})
const axiosLike = (data: unknown) => Promise.resolve({ data, status: 200 })

function mountBlock(readonly: boolean, rows = [{ _row_id: 'r1', seq: 1, bank_payer: '原有付款方', is_abnormal: '否' }]) {
  return mount(CheckBlock, {
    props: {
      config: BLOCK_COLUMN_CONFIGS.block3, rows, totals: {}, readonly,
      wpId: 'W1', projectId: 'P1', evidenceSheet: 'D0-5',
    },
    global: { plugins: [ElementPlus], stubs: { 'el-upload': UploadStub, 'el-dialog': DialogStub } },
  })
}

async function pickAndSubmit(w: any, file: File) {
  await w.find('[data-testid="alt-row-upload"]').trigger('click')
  await flushPromises()
  w.findComponent(UploadStub).props('onChange')({ raw: file })
  await flushPromises()
  await w.find('[data-testid="alt-doc-submit"]').trigger('click')
  await flushPromises()
}

describe('替代程序行内附件', () => {
  beforeEach(() => {
    mockPost.mockReset()
    mockGet.mockReset()
    mockGet.mockImplementation(() => axiosLike([]))
  })

  it('只读：附件列仍在、只有小眼睛（复核人看得到），没有 📎', async () => {
    const w = mountBlock(true)
    await flushPromises()
    const eye = w.find('.eye-stub')
    expect(eye.exists()).toBe(true)
    expect([eye.attributes('data-sheet'), eye.attributes('data-cell')]).toEqual(['D0-5', 'row:r1'])
    expect(w.find('[data-testid="alt-row-upload"]').exists()).toBe(false)
  })

  it('识别：请求带单据类型与本行位置；只填勾选的空白列', async () => {
    mockPost.mockImplementation(() => axiosLike({
      attachment_id: 'A1', document_type: 'bank_receipt', ocr_text: 'x', confidence: 0.6,
      extracted_fields: { date: '2025-12-31', payer: '甲公司', amount: 100, doc_no: '', payee: '', summary: '' },
    }))
    const w = mountBlock(false)
    await flushPromises()
    await pickAndSubmit(w, new File(['%PDF'], '回单.pdf', { type: 'application/pdf' }))

    const [url, form] = mockPost.mock.calls[0]
    expect(url).toBe('/api/workpapers/W1/confirmation-alternative/doc-ocr')
    expect([form.get('document_type'), form.get('evidence_sheet'), form.get('evidence_cell')])
      .toEqual(['bank_receipt', 'D0-5', 'row:r1']) // 缺省选本区块第一种可识别类型
    expect(w.find('.doc-eye').attributes('data-id')).toBe('A1') // 识别后可直接预览原件

    const planRows = w.findAll('[data-testid="alt-doc-plan"] tbody tr').map((r) => r.attributes('data-field'))
    expect(planRows).toEqual(['bank_payer']) // 银行回单只填本区块「银行回单」列；付款方已有值
    expect(w.text()).toContain('已有值，不覆盖')
    expect(w.find('[data-testid="alt-doc-fill"]').attributes('disabled')).toBeDefined() // 没有可填的空白列
  })

  it('填入：只发勾选的空白列（经 update-field 回到宿主）', async () => {
    mockPost.mockImplementation(() => axiosLike({
      attachment_id: 'A2', document_type: 'bank_receipt', ocr_text: 'x', confidence: 0.5,
      extracted_fields: { payer: '甲公司', date: '', doc_no: '', payee: '', amount: 0, summary: '' },
    }))
    const w = mountBlock(false, [{ _row_id: 'r1', seq: 1, is_abnormal: '否' }] as any)
    await flushPromises()
    await pickAndSubmit(w, new File(['%PDF'], '回单.pdf'))
    await w.find('[data-testid="alt-doc-fill"]').trigger('click')
    expect(w.emitted('update-field')).toEqual([['r1', 'bank_payer', '甲公司']])
  })

  it('仅上传：走证据入口挂到本行，类型「支持文件」，不调识别', async () => {
    mockPost.mockImplementation(() => axiosLike({ attachment: { id: 'A3' }, evidence_link: { id: 'E1' } }))
    const w = mountBlock(false)
    await flushPromises()
    await w.find('[data-testid="alt-row-upload"]').trigger('click')
    await flushPromises()
    const radios = w.findAll('[data-testid="alt-doc-types"] input[type="radio"]')
    await radios[radios.length - 1].setValue(true) // 最后一项 = 仅上传，不识别
    w.findComponent(UploadStub).props('onChange')({ raw: new File(['x'], '说明.docx') })
    await flushPromises()
    await w.find('[data-testid="alt-doc-submit"]').trigger('click')
    await flushPromises()
    const [url, form] = mockPost.mock.calls[0]
    expect(url).toBe('/api/projects/P1/workpapers/W1/evidence/upload')
    expect([form.get('evidence_type'), form.get('sheet_name'), form.get('cell_ref')]).toEqual(['support', 'D0-5', 'row:r1'])
  })

  it('没有底稿上下文时不显示附件列', async () => {
    const w = mount(CheckBlock, {
      props: { config: BLOCK_COLUMN_CONFIGS.block3, rows: [{ _row_id: 'r1' }], totals: {}, readonly: false },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    expect(w.find('.eye-stub').exists()).toBe(false)
  })
})
