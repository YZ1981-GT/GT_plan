/**
 * GtC22ControlSheet.evidence.spec.ts — 附件上传 + OCR merge + 证据索引号 + 持久化
 *
 * Spec: .kiro/specs/c22-itgc-bundle/  Task 8.2
 * Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5
 *
 * 覆盖：
 *  - 📎 附件上传（审计证据区 + 样本记录行）（Req 11.1）
 *  - 证据索引号自动建议 C22.{控制点}-{序号}（Req 11.2）
 *  - OCR 识别 + 确认弹窗 merge 填入样本记录（Req 11.3）
 *  - OCR 失败时提示手动填写并保留附件（Req 11.4）
 *  - 附件与 item_id 关联持久化 + 只读模式仅可查看（Req 11.5）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// ─── Mocks (hoisted vi.mock factories cannot reference outer vars) ───

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('@/utils/http', () => ({
  default: {
    post: vi.fn(),
  },
}))

vi.mock('@/services/commonApi', () => ({
  uploadAttachment: vi.fn(),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

vi.mock('@/services/apiPaths', () => ({
  attachments: {
    associate: (id: string) => `/api/attachments/${id}/associate`,
    upload: (pid: string) => `/api/projects/${pid}/attachments`,
  },
}))

vi.mock('@/composables/useWpAiSuggest', () => ({
  useWpAiSuggest: () => ({
    aiEnabled: { value: false },
    aiLoading: { value: false },
    showSuggestionPanel: { value: false },
    currentSuggestion: { value: null },
    requestSuggestion: vi.fn(),
    adoptSuggestion: vi.fn(),
    ignoreSuggestion: vi.fn(),
  }),
}))

// Import mocked modules to get references
import { api } from '@/services/apiProxy'
import http from '@/utils/http'
import { uploadAttachment } from '@/services/commonApi'
import { ElMessage, ElMessageBox } from 'element-plus'

const mockGet = api.get as ReturnType<typeof vi.fn>
const mockPut = api.put as ReturnType<typeof vi.fn>
const mockPost = api.post as ReturnType<typeof vi.fn>
const mockHttpPost = (http as any).post as ReturnType<typeof vi.fn>
const mockUploadAttachment = uploadAttachment as ReturnType<typeof vi.fn>
const mockElMessage = ElMessage as { success: ReturnType<typeof vi.fn>; warning: ReturnType<typeof vi.fn>; error: ReturnType<typeof vi.fn>; info: ReturnType<typeof vi.fn> }
const mockElMessageBox = ElMessageBox as { confirm: ReturnType<typeof vi.fn> }

import GtC22ControlSheet from '../GtC22ControlSheet.vue'
import { C22_BUNDLE_TABS, itgcItemId, suggestEvidenceIndex, type TabDef } from '../composables/useC22BundleState'

function findTab(id: string): TabDef {
  const t = C22_BUNDLE_TABS.find(t => t.id === id)
  if (!t) throw new Error(`tab ${id} not found`)
  return t
}

const stubs = {
  'el-card': { template: '<div class="el-card"><slot name="header" /><slot /></div>' },
  'el-input': {
    props: ['modelValue', 'readonly', 'type'],
    emits: ['update:modelValue', 'input'],
    template: '<textarea class="el-input" :readonly="readonly" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value); $emit(\'input\', $event.target.value)" />',
  },
  'el-select': {
    props: ['modelValue', 'disabled'],
    emits: ['update:modelValue', 'change'],
    template: '<select class="el-select" :disabled="disabled" :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value); $emit(\'change\', $event.target.value)"><slot /></select>',
  },
  'el-option': { props: ['label', 'value'], template: '<option :value="value">{{ label }}</option>' },
  'el-radio-group': { props: ['modelValue', 'disabled'], emits: ['update:modelValue', 'change'], template: '<div class="el-radio-group"><slot /></div>' },
  'el-radio-button': { props: ['label'], template: '<label class="el-radio-button">{{ label }}</label>' },
  'el-table': { props: ['data'], template: '<table class="el-table"><slot /></table>' },
  'el-table-column': { template: '<div class="el-table-column"><slot :row="{}" :$index="0" /></div>' },
  'el-button': { template: '<button class="el-button"><slot /></button>' },
  'el-tag': { template: '<span class="el-tag"><slot /></span>' },
  'el-tooltip': { props: ['content'], template: '<span :data-tip="content"><slot /></span>' },
  'el-upload': { template: '<div class="el-upload"><slot /></div>' },
}

function mountSheet(opts: { tab?: TabDef; responses?: any[]; readonly?: boolean } = {}) {
  const tab = opts.tab ?? findTab('SA-3')
  mockGet.mockImplementation((url: string) => {
    if (typeof url === 'string' && url.includes('/checklist-responses')) {
      return Promise.resolve(opts.responses ?? [])
    }
    return Promise.resolve([])
  })
  mockPut.mockResolvedValue({})
  mockPost.mockResolvedValue({})
  return mount(GtC22ControlSheet, {
    props: {
      wpId: 'wp-c22',
      projectId: 'proj-1',
      tab,
      matrixRow: { row: tab.matrixRow, controlNo: tab.id, description: '账号权限管理', appSystem: 'A系统' },
      readonly: opts.readonly ?? false,
    },
    global: { stubs, directives: { loading: {} } },
  })
}

beforeEach(() => {
  mockGet.mockReset()
  mockPut.mockReset()
  mockPost.mockReset()
  mockHttpPost.mockReset()
  mockUploadAttachment.mockReset()
  mockElMessage.success.mockReset()
  mockElMessage.warning.mockReset()
  mockElMessage.error.mockReset()
  mockElMessage.info.mockReset()
  mockElMessageBox.confirm.mockReset()
  vi.useRealTimers()
})

// ═══════════════════════════════════════════════════════════════════════════════
// Req 11.1: 审计证据区与样本记录行提供 📎 附件上传
// ═══════════════════════════════════════════════════════════════════════════════

describe('GtC22ControlSheet — 📎 附件上传（Req 11.1）', () => {
  it('审计证据区附件上传成功 → 附件记录加入 evidenceAttachments', async () => {
    mockUploadAttachment.mockResolvedValue({ id: 'att-001' })
    const wrapper = mountSheet()
    await flushPromises()

    const file = new File(['test'], 'policy.docx', { type: 'application/msword' })
    await (wrapper.vm as any).onUploadEvidence(file)
    await flushPromises()

    const attachments = (wrapper.vm as any).evidenceAttachments
    expect(attachments.length).toBe(1)
    expect(attachments[0].id).toBe('att-001')
    expect(attachments[0].name).toBe('policy.docx')
  })

  it('样本记录行附件上传成功 → 附件关联到样本行', async () => {
    mockUploadAttachment.mockResolvedValue({ id: 'att-sample-1' })
    const wrapper = mountSheet()
    await flushPromises()

    // 先添加样本行
    ;(wrapper.vm as any).form.sampleSize = '5'
    ;(wrapper.vm as any).addSampleRow()

    const file = new File(['test'], 'approval.pdf', { type: 'application/pdf' })
    await (wrapper.vm as any).onUploadSampleAttachment(0, file)
    await flushPromises()

    const row = (wrapper.vm as any).sampleRecords[0]
    expect(row.attachment).toBeDefined()
    expect(row.attachment.id).toBe('att-sample-1')
    expect(row.attachment.name).toBe('approval.pdf')
  })

  it('文件超过 20MB → 拒绝上传并提示', async () => {
    const wrapper = mountSheet()
    await flushPromises()

    // 创建超过 20MB 的 mock 文件
    const bigFile = new File(['x'.repeat(100)], 'big.pdf', { type: 'application/pdf' })
    Object.defineProperty(bigFile, 'size', { value: 25 * 1024 * 1024 })

    await (wrapper.vm as any).onUploadEvidence(bigFile)
    await flushPromises()

    expect(mockUploadAttachment).not.toHaveBeenCalled()
    expect(mockElMessage.warning).toHaveBeenCalled()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Req 11.2: 证据索引号自动建议 C22.{控制点}-{序号}
// ═══════════════════════════════════════════════════════════════════════════════

describe('GtC22ControlSheet — 证据索引号自动建议（Req 11.2）', () => {
  it('首个附件建议 C22.SA-3-1，第二个建议 C22.SA-3-2', async () => {
    mockUploadAttachment.mockResolvedValue({ id: 'att-001' })
    const wrapper = mountSheet()
    await flushPromises()

    // 第一次上传
    const file1 = new File(['a'], 'evidence1.docx', { type: 'application/msword' })
    await (wrapper.vm as any).onUploadEvidence(file1)
    await flushPromises()

    expect((wrapper.vm as any).evidenceAttachments[0].index).toBe('C22.SA-3-1')

    // 第二次上传
    mockUploadAttachment.mockResolvedValue({ id: 'att-002' })
    const file2 = new File(['b'], 'evidence2.docx', { type: 'application/msword' })
    await (wrapper.vm as any).onUploadEvidence(file2)
    await flushPromises()

    expect((wrapper.vm as any).evidenceAttachments[1].index).toBe('C22.SA-3-2')
  })

  it('evidenceIndexHint 显示下一个待用索引号', async () => {
    const wrapper = mountSheet()
    await flushPromises()

    // 初始无附件时，hint = C22.SA-3-1
    expect((wrapper.vm as any).evidenceIndexHint).toBe('C22.SA-3-1')
  })

  it('suggestEvidenceIndex 纯函数正确生成格式', () => {
    expect(suggestEvidenceIndex('SA-3', 1)).toBe('C22.SA-3-1')
    expect(suggestEvidenceIndex('PE-3a', 5)).toBe('C22.PE-3a-5')
    expect(suggestEvidenceIndex('PM-4c', 10)).toBe('C22.PM-4c-10')
    expect(suggestEvidenceIndex('NS-1', 1)).toBe('C22.NS-1-1')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Req 11.3: OCR 识别 + 确认弹窗 merge 填入样本记录
// ═══════════════════════════════════════════════════════════════════════════════

describe('GtC22ControlSheet — OCR merge（Req 11.3）', () => {
  it('图片/PDF 上传 → 调用 OCR → 确认 → merge 到审计证据描述', async () => {
    mockUploadAttachment.mockResolvedValue({ id: 'att-ocr-1' })
    mockHttpPost.mockResolvedValue({
      data: { data: { extracted_fields: { title: '数据安全管理制度', approval_date: '2024-06-01', approver: '张三' } } },
    })
    mockElMessageBox.confirm.mockResolvedValue('confirm')

    const wrapper = mountSheet()
    await flushPromises()

    const file = new File(['img'], 'policy.jpg', { type: 'image/jpeg' })
    await (wrapper.vm as any).onUploadEvidence(file)
    await flushPromises()

    // OCR 被调用
    expect(mockHttpPost).toHaveBeenCalledWith(
      '/api/workpapers/wp-c22/d4/contract-ocr',
      expect.any(FormData),
      expect.objectContaining({ headers: { 'Content-Type': 'multipart/form-data' } }),
    )

    // 确认弹窗被调用
    expect(mockElMessageBox.confirm).toHaveBeenCalled()
    const confirmMsg = mockElMessageBox.confirm.mock.calls[0][0]
    expect(confirmMsg).toContain('制度名称')
    expect(confirmMsg).toContain('数据安全管理制度')

    // merge 到 designEvidence 字段
    expect((wrapper.vm as any).form.designEvidence).toContain('数据安全管理制度')
    expect((wrapper.vm as any).form.designEvidence).toContain('审批人：张三')

    // 附件标记 ocrMerged
    expect((wrapper.vm as any).evidenceAttachments[0].ocrMerged).toBe(true)
  })

  it('用户取消确认弹窗 → 不 merge，附件保留', async () => {
    mockUploadAttachment.mockResolvedValue({ id: 'att-ocr-2' })
    mockHttpPost.mockResolvedValue({
      data: { data: { extracted_fields: { title: '制度X' } } },
    })
    mockElMessageBox.confirm.mockRejectedValue('cancel')

    const wrapper = mountSheet()
    await flushPromises()

    const file = new File(['img'], 'doc.png', { type: 'image/png' })
    await (wrapper.vm as any).onUploadEvidence(file)
    await flushPromises()

    // 附件保留但未 merge
    expect((wrapper.vm as any).evidenceAttachments.length).toBe(1)
    expect((wrapper.vm as any).evidenceAttachments[0].ocrMerged).toBe(false)
    expect((wrapper.vm as any).form.designEvidence).toBe('')
  })

  it('非 OCR 类型文件（.docx）→ 不调用 OCR', async () => {
    mockUploadAttachment.mockResolvedValue({ id: 'att-non-ocr' })

    const wrapper = mountSheet()
    await flushPromises()

    const file = new File(['doc'], 'report.docx', { type: 'application/msword' })
    await (wrapper.vm as any).onUploadEvidence(file)
    await flushPromises()

    expect(mockHttpPost).not.toHaveBeenCalled()
    expect((wrapper.vm as any).evidenceAttachments.length).toBe(1)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Req 11.4: OCR 失败时提示手动填写并保留附件
// ═══════════════════════════════════════════════════════════════════════════════

describe('GtC22ControlSheet — OCR 失败处理（Req 11.4）', () => {
  it('OCR 请求失败 → 提示手动填写，附件保留', async () => {
    mockUploadAttachment.mockResolvedValue({ id: 'att-ocr-fail' })
    mockHttpPost.mockRejectedValue(new Error('OCR 服务不可用'))

    const wrapper = mountSheet()
    await flushPromises()

    const file = new File(['img'], 'scan.pdf', { type: 'application/pdf' })
    await (wrapper.vm as any).onUploadEvidence(file)
    await flushPromises()

    // 附件保留
    expect((wrapper.vm as any).evidenceAttachments.length).toBe(1)
    expect((wrapper.vm as any).evidenceAttachments[0].ocrMerged).toBe(false)
    // 提示手动填写
    expect(mockElMessage.warning).toHaveBeenCalledWith('OCR 识别失败，请手动填写证据信息')
  })

  it('OCR 返回空 fields → 提示手动补充，附件保留', async () => {
    mockUploadAttachment.mockResolvedValue({ id: 'att-ocr-empty' })
    mockHttpPost.mockResolvedValue({ data: { data: { extracted_fields: {} } } })

    const wrapper = mountSheet()
    await flushPromises()

    const file = new File(['img'], 'blank.jpg', { type: 'image/jpeg' })
    await (wrapper.vm as any).onUploadEvidence(file)
    await flushPromises()

    expect((wrapper.vm as any).evidenceAttachments.length).toBe(1)
    expect(mockElMessage.info).toHaveBeenCalledWith('OCR 未识别到可填充字段，请手动补充')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Req 11.5: 附件与 item_id 关联持久化 + 只读模式
// ═══════════════════════════════════════════════════════════════════════════════

describe('GtC22ControlSheet — 附件持久化与只读（Req 11.5）', () => {
  it('附件上传后 persistAttachments → PUT checklist-responses（evidence-attachments JSON）', async () => {
    mockUploadAttachment.mockResolvedValue({ id: 'att-persist' })
    const wrapper = mountSheet()
    await flushPromises()
    mockPut.mockClear()

    const file = new File(['a'], 'file.xlsx', { type: 'application/vnd.ms-excel' })
    await (wrapper.vm as any).onUploadEvidence(file)
    await flushPromises()

    // PUT 被调用并包含 evidence-attachments item_id
    expect(mockPut).toHaveBeenCalledWith(
      '/api/workpapers/wp-c22/checklist-responses',
      expect.objectContaining({
        items: [expect.objectContaining({
          item_id: 'C22.SA-3.evidence-attachments',
          remark: expect.stringContaining('att-persist'),
        })],
      }),
    )
  })

  it('加载已有附件 JSON → 回填 evidenceAttachments', async () => {
    const existingAttachments = [
      { id: 'att-prev-1', name: 'old.pdf', index: 'C22.SA-3-1', ocrMerged: true },
      { id: 'att-prev-2', name: 'old2.docx', index: 'C22.SA-3-2', ocrMerged: false },
    ]
    const responses = [
      { item_id: itgcItemId('SA-3', 'evidence-attachments'), conclusion: null, remark: JSON.stringify(existingAttachments) },
    ]
    const wrapper = mountSheet({ responses })
    await flushPromises()

    const attachments = (wrapper.vm as any).evidenceAttachments
    expect(attachments.length).toBe(2)
    expect(attachments[0].id).toBe('att-prev-1')
    expect(attachments[0].ocrMerged).toBe(true)
    expect(attachments[1].name).toBe('old2.docx')
  })

  it('只读模式 → onUploadEvidence 不执行', async () => {
    const wrapper = mountSheet({ readonly: true })
    await flushPromises()

    const file = new File(['x'], 'test.pdf', { type: 'application/pdf' })
    await (wrapper.vm as any).onUploadEvidence(file)
    await flushPromises()

    expect(mockUploadAttachment).not.toHaveBeenCalled()
    expect((wrapper.vm as any).evidenceAttachments.length).toBe(0)
  })

  it('只读模式 → removeEvidenceAttachment 不执行', async () => {
    const existingAttachments = [{ id: 'att-1', name: 'x.pdf', index: 'C22.SA-3-1', ocrMerged: false }]
    const responses = [
      { item_id: itgcItemId('SA-3', 'evidence-attachments'), conclusion: null, remark: JSON.stringify(existingAttachments) },
    ]
    const wrapper = mountSheet({ readonly: true, responses })
    await flushPromises()

    ;(wrapper.vm as any).removeEvidenceAttachment(0)
    expect((wrapper.vm as any).evidenceAttachments.length).toBe(1)
  })

  it('删除附件 → 更新 evidenceAttachments 并持久化', async () => {
    const existingAttachments = [
      { id: 'att-1', name: 'a.pdf', index: 'C22.SA-3-1', ocrMerged: false },
      { id: 'att-2', name: 'b.pdf', index: 'C22.SA-3-2', ocrMerged: true },
    ]
    const responses = [
      { item_id: itgcItemId('SA-3', 'evidence-attachments'), conclusion: null, remark: JSON.stringify(existingAttachments) },
    ]
    const wrapper = mountSheet({ responses })
    await flushPromises()
    mockPut.mockClear()

    ;(wrapper.vm as any).removeEvidenceAttachment(0)
    await flushPromises()

    expect((wrapper.vm as any).evidenceAttachments.length).toBe(1)
    expect((wrapper.vm as any).evidenceAttachments[0].id).toBe('att-2')
    expect(mockPut).toHaveBeenCalled()
  })
})
