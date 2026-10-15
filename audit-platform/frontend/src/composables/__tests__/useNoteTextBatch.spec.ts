/**
 * useNoteTextBatch：请求载荷与后端契约一致（第二轮复盘 #6a）。
 *
 * 首版三处与后端不符：上传丢弃了服务端签名的 source_metadata、知识库不带 knowledge_doc_ids、
 * 内容模板按上传形态发正文（R-02）；apply 也不回传 preview 的手工映射 / 撤销项。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

const post = vi.fn()
const get = vi.fn()
const error = vi.fn()
const emit = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: { post: (...a: unknown[]) => post(...a), get: (...a: unknown[]) => get(...a) },
}))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: (...a: unknown[]) => error(...a) },
}))
vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: (...a: unknown[]) => emit(...a) } }))

import { toBatchError, toSelection, useNoteTextBatch, type PreviewItem } from '../useNoteTextBatch'

const PARSED = {
  source_kind: 'upload',
  source_metadata: { file_name: '附注.docx', file_hash: 'f'.repeat(64), byte_size: 10, file_format: 'docx', signature: 's'.repeat(64) },
  sections: [{ source_id: 'docx-s1', title: '公司基本情况', level: 2, html: '<p>原文</p>', confidence: 'candidate', warnings: [], metadata: {} }],
  warnings: [],
  needs_ocr: false,
}
const ITEM: PreviewItem = {
  source_id: 'docx-s1', source_title: '公司基本情况', target_note_id: 'n1', target_note_section: '一、1',
  target_section_title: '公司基本情况', match_kind: 'title_exact', evidence: '标题规范化一致', confidence: 'candidate',
  category: 'review', default_selected: false, unavailable_reason: null, before_html: '<p>旧</p>', before_hash: 'b'.repeat(64),
  proposed_html: '<p>原文</p>', proposed_hash: 'p'.repeat(64), append_html: '<p>旧</p><p>原文</p>', append_hash: 'a'.repeat(64),
  expected_updated_at: null, default_mode: 'replace', quality_flags: [], replacements: [],
}
const PREVIEW = { preview_digest: 'd'.repeat(64), items: [ITEM], summary: {}, warnings: [] }

function make() {
  return useNoteTextBatch({ projectId: ref('p1'), year: ref(2025) })
}

function axiosError(status: number, detail: unknown) {
  return Object.assign(new Error(`Request failed with status code ${status}`), { response: { status, data: { detail } } })
}

beforeEach(() => {
  post.mockReset()
  get.mockReset()
  error.mockReset()
  emit.mockReset()
})

describe('来源载荷', () => {
  it('上传：parse 响应原样回传（含服务端签名元数据），不再发 year', async () => {
    const b = make()
    post.mockResolvedValueOnce(structuredClone(PARSED)).mockResolvedValueOnce(PREVIEW)
    await b.parseUpload(new File(['x'], '附注.docx'))
    const form = post.mock.calls[0][1] as FormData
    expect([...form.keys()]).toEqual(['file'])
    await b.fetchPreview()
    const body = post.mock.calls[1][1]
    expect(body.source).toEqual({ source_kind: 'upload', parsed_source: PARSED })
    expect(body).toMatchObject({ year: 2025, manual_mappings: [], revoked_replacement_ids: [] })
  })

  it('知识库：带 knowledge_doc_ids 供后端重新判权', async () => {
    const b = make()
    post.mockResolvedValueOnce({ ...structuredClone(PARSED), source_kind: 'knowledge' }).mockResolvedValueOnce(PREVIEW)
    await b.parseKnowledge(['doc-1'])
    expect(post.mock.calls[0][1]).toEqual({ year: 2025, doc_ids: ['doc-1'] })
    await b.fetchPreview()
    expect(post.mock.calls[1][1].source).toMatchObject({ source_kind: 'knowledge', knowledge_doc_ids: ['doc-1'] })
  })

  it('内容模板：只传固定版本与 hash，不带任何正文（R-02）', async () => {
    const b = make()
    b.useTemplateVersion('v-1', 'h'.repeat(64))
    post.mockResolvedValueOnce(PREVIEW)
    await b.fetchPreview()
    expect(post.mock.calls[0][1].source).toEqual({
      source_kind: 'content_template', template_version_id: 'v-1', template_content_hash: 'h'.repeat(64),
    })
  })
})

describe('apply 与预览一致', () => {
  it('回传同一份手工映射 / 撤销项，带幂等键；追加模式提交 append_hash', async () => {
    const b = make()
    post.mockResolvedValueOnce(structuredClone(PARSED)).mockResolvedValueOnce(PREVIEW)
    await b.parseUpload(new File(['x'], '附注.docx'))
    b.setManualMapping('docx-s1', 'n1')
    b.toggleRevocation('rep-1')
    await b.fetchPreview()
    post.mockResolvedValueOnce({ applied_count: 1, changed_notes: [], changed_note_ids: [], warnings: [] })
    const key = b.mutationId.value
    await b.applyBatch([toSelection(ITEM, 'append')])
    const [, body, config] = post.mock.calls[2]
    expect(body).toMatchObject({
      preview_digest: PREVIEW.preview_digest,
      manual_mappings: [{ source_id: 'docx-s1', target_note_id: 'n1' }],
      revoked_replacement_ids: ['rep-1'],
    })
    expect(body.selections[0]).toMatchObject({ mode: 'append', proposed_hash: 'a'.repeat(64) })
    expect(body.selections[0]).not.toHaveProperty('proposed_html')
    expect(config.headers['X-Mutation-Id']).toBe(key)
    expect(b.mutationId.value).not.toBe(key)
  })

  it('预览后改正文 ⇒ 预览过期，不发 apply；重新预览后才可应用', async () => {
    const b = make()
    post.mockResolvedValueOnce(structuredClone(PARSED)).mockResolvedValueOnce(PREVIEW)
    await b.parseUpload(new File(['x'], '附注.docx'))
    await b.fetchPreview()
    b.updateSectionHtml('docx-s1', '<p>改过</p>')
    expect(b.previewStale.value).toBe(true)
    expect(await b.applyBatch([toSelection(ITEM, 'replace')])).toBeNull()
    expect(post).toHaveBeenCalledTimes(2)
    post.mockResolvedValueOnce(PREVIEW)
    await b.fetchPreview()
    expect(post.mock.calls[2][1].source.parsed_source.sections[0].html).toBe('<p>改过</p>')
    expect(b.canApply.value).toBe(true)
  })

  it('已编辑按内容判定：改回原文即不算已编辑', async () => {
    const b = make()
    post.mockResolvedValueOnce(structuredClone(PARSED))
    await b.parseUpload(new File(['x'], '附注.docx'))
    b.updateSectionHtml('docx-s1', '<p>改过</p>')
    expect(b.isDirty.value).toBe(true)
    b.updateSectionHtml('docx-s1', '<p>原文</p>')
    expect(b.isDirty.value).toBe(false)
  })

  it('网络错误保留幂等键重试；冲突类错误换新键并要求重新预览', async () => {
    const b = make()
    b.useTemplateVersion('v-1', 'h'.repeat(64))
    post.mockResolvedValueOnce(PREVIEW)
    await b.fetchPreview()
    const key = b.mutationId.value
    post.mockRejectedValueOnce(new Error('Network Error'))
    await b.applyBatch([toSelection(ITEM, 'replace')])
    expect(b.mutationId.value).toBe(key)
    expect(b.previewStale.value).toBe(false)
    post.mockRejectedValueOnce(axiosError(409, { error_code: 'NOTE_BATCH_STALE_PREVIEW', message: '以下章节在预览后已被修改，请重新预览：一、1', stale_notes: ['一、1'] }))
    await b.applyBatch([toSelection(ITEM, 'replace')])
    expect(b.mutationId.value).not.toBe(key)
    expect(b.previewStale.value).toBe(true)
    expect(b.lastError.value).toMatchObject({ code: 'NOTE_BATCH_STALE_PREVIEW', staleNotes: ['一、1'] })
  })
})

describe('toBatchError', () => {
  it('pydantic 英文校验错误换成中文提示', () => {
    const err = toBatchError(axiosError(422, [{ msg: 'Field required', loc: ['body', 'year'] }]), '失败')
    expect(err).toEqual({ code: 'VALIDATION_ERROR', message: '请求参数不合法，请刷新页面后重试', staleNotes: [] })
  })
})

describe('错误提示单一来源（#6c：全局拦截器静默，只由本 composable 弹一次中文提示）', () => {
  it('parse / preview / apply / 目标章节请求都带 _silent', async () => {
    const b = make()
    post.mockResolvedValueOnce(structuredClone(PARSED)).mockResolvedValueOnce(PREVIEW)
      .mockResolvedValueOnce({ applied_count: 1, changed_notes: [], changed_note_ids: [], warnings: [] })
    get.mockResolvedValueOnce({ items: [] })
    await b.parseUpload(new File(['x'], '附注.docx'))
    await b.fetchPreview()
    await b.applyBatch([toSelection(ITEM, 'replace')])
    await b.fetchTargetSections()
    expect(post).toHaveBeenCalledTimes(3)
    for (const call of post.mock.calls) expect(call[2]).toMatchObject({ _silent: true })
    expect(post.mock.calls[2][2].headers['X-Mutation-Id']).toBeTruthy()
    expect(get.mock.calls[0][1]).toMatchObject({ _silent: true, params: { year: 2025, scope: 'narrative' } })
  })

  it('无业务 detail 的 HTTP 错误（axios 英文 message）⇒ 只弹一次中文兜底并带状态码', async () => {
    const b = make()
    post.mockRejectedValueOnce(Object.assign(new Error('Request failed with status code 502'),
      { response: { status: 502, data: '' } }))
    expect(await b.parseUpload(new File(['x'], '附注.docx'))).toBe(false)
    expect(error).toHaveBeenCalledTimes(1)
    expect(error).toHaveBeenCalledWith('附注.docx：文档解析失败（HTTP 502）')
  })

  it('本地校验异常（无 response）保留中文原因', () => {
    expect(toBatchError(new Error('尚未解析来源'), '预览失败').message).toBe('尚未解析来源')
  })

  it('解析失败的提示带文件名（失败不清空当前来源，必须分清是哪个文件失败）', async () => {
    const b = make()
    post.mockResolvedValueOnce(structuredClone(PARSED))
    await b.parseUpload(new File(['x'], '附注.docx'))
    post.mockRejectedValueOnce(axiosError(422, { error_code: 'NEEDS_OCR', message: 'PDF 不含可提取文本' }))
    expect(await b.parseUpload(new File(['x'], '扫描件.pdf'))).toBe(false)
    expect(b.lastError.value?.message).toBe('扫描件.pdf：PDF 不含可提取文本')
    expect(error).toHaveBeenLastCalledWith('扫描件.pdf：PDF 不含可提取文本')
    expect(b.parsedSections.value).toHaveLength(1)  // 上一个来源仍在
  })

  it('前端拒收文件（扩展名 / 大小）同样落到 lastError，不残留上一次的错误', async () => {
    const b = make()
    post.mockRejectedValueOnce(axiosError(422, { error_code: 'BAD_SIGNATURE', message: '文件签名校验失败' }))
    await b.parseUpload(new File(['x'], '损坏.docx'))
    b.rejectFile('超大.docx', '文件大小不能超过 50MB')
    expect(b.lastError.value).toEqual({ code: 'INVALID_FILE', message: '超大.docx：文件大小不能超过 50MB', staleNotes: [] })
    expect(error).toHaveBeenLastCalledWith('超大.docx：文件大小不能超过 50MB')
    expect(post).toHaveBeenCalledTimes(1)
  })

  it('被 http 防重复提交取消的请求不弹「canceled」', async () => {
    const b = make()
    post.mockRejectedValueOnce(Object.assign(new Error('canceled'), { code: 'ERR_CANCELED', name: 'CanceledError' }))
    expect(await b.parseKnowledge(['doc-1'])).toBe(false)
    expect(error).not.toHaveBeenCalled()
  })

  it('合并锁定 423 ⇒ 通知锁定横幅刷新（静默后全局拦截器不再代发）', async () => {
    const b = make()
    b.useTemplateVersion('v-1', 'h'.repeat(64))
    post.mockResolvedValueOnce(PREVIEW)
    await b.fetchPreview()
    post.mockRejectedValueOnce(axiosError(423, '项目已被合并锁定，无法修改'))
    await b.applyBatch([toSelection(ITEM, 'replace')])
    expect(emit).toHaveBeenCalledWith('consol-lock:detected', { projectId: 'p1' })
    expect(error).toHaveBeenCalledTimes(1)
    expect(error).toHaveBeenCalledWith('项目已被合并锁定，无法修改')
  })
})
