/**
 * VoucherEvidenceTag — 凭证检查行「来源」列里的凭证证据（spec attachment-voucher-evidence-binding 需求 3，变异 #14）
 *
 * - 本底稿这张凭证的证据按附件归组计数；别的可见底稿已有、本底稿没有的提示「他稿 n」并可逐份引用；
 * - 引用 / 上传 / 移除后重取本底稿链接与他稿索引；移除删该附件在本底稿的全部链接；
 * - 只读底稿与年审阶段的预审行只能查看；手工行（没有凭证键）不显示；
 * - 他稿查询按凭证键自带的年度（宿主缺省传年度 0 不影响）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, provide, ref } from 'vue'
import { mount } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), del: vi.fn(), confirmDelete: vi.fn(), handleApiError: vi.fn(),
  runtimeKey: Symbol('runtime-test'),
}))
vi.mock('@/utils/http', () => ({ default: { get: mocks.get, post: mocks.post, delete: mocks.del } }))
vi.mock('@/utils/confirm', () => ({ confirmDelete: mocks.confirmDelete }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: mocks.handleApiError }))
vi.mock('element-plus', () => ({
  ElMessage: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}))
vi.mock('@/components/workpaper/composables/useWorkpaperScaffold', () => ({ WorkpaperRuntimeContextKey: mocks.runtimeKey }))

import VoucherEvidenceTag from '../VoucherEvidenceTag.vue'
import { resetWpEvidenceLinksForTest } from '@/composables/useWpEvidenceLinks'
import { resetVoucherEvidenceIndexForTest } from '@/composables/useVoucherEvidenceIndex'

const PID = 'p1'
const WP = 'w1'
const VK = JSON.stringify(['2025', '重庆医药', '2025-01-07', '记', '0003'])
const OTHER = JSON.stringify(['2025', '重庆医药', '2025-01-08', '记', '0004'])
const LINKS_URL = `/api/projects/${PID}/workpapers/${WP}/evidence`
const QUERY_URL = `/api/projects/${PID}/ledger/voucher-evidence/query`
const REUSE_URL = `/api/projects/${PID}/workpapers/${WP}/evidence/voucher-reuse`

function link(id: string, attachmentId: string, vk: string | null, cell: string | null = null) {
  return {
    id, wp_id: WP, sheet_name: cell ? 'D2-4' : null, cell_ref: cell, attachment_id: attachmentId, page_ref: null,
    evidence_type: 'voucher', check_conclusion: null, voucher_key: vk, created_by: 'u1', created_at: null,
    attachment: { id: attachmentId, file_name: `${attachmentId}.pdf`, file_size: 1, file_type: 'pdf', attachment_type: null, ocr_status: null, created_at: null },
  }
}
const att = (id: string) => ({ id, file_name: `${id}.pdf`, file_type: 'pdf', ocr_status: null, evidence_type: 'voucher' })

const stubs = {
  'el-popover': { template: '<div class="popover"><slot name="reference" /><div class="panel"><slot /></div></div>' },
  'el-button': {
    inheritAttrs: false,
    props: ['type', 'size', 'link', 'loading'],
    emits: ['click'],
    template: '<button :data-testid="$attrs[\'data-testid\']" :aria-label="$attrs[\'aria-label\']" :data-type="type" @click="$emit(\'click\', $event)"><slot /></button>',
  },
  'el-icon': { template: '<i><slot /></i>' },
  'el-upload': { name: 'ElUploadStub', props: ['httpRequest', 'beforeUpload'], template: '<div class="upload"><slot /></div>' },
  AttachmentEyeButton: { props: ['attachmentId'], template: '<i class="eye" :data-id="attachmentId" />' },
}

function mountTag(opts: { row?: unknown; readonly?: boolean; locked?: boolean } = {}) {
  const Host = defineComponent({
    setup() {
      provide(mocks.runtimeKey, { wpId: ref(WP), projectId: ref(PID), year: ref(0), readonly: ref(!!opts.readonly) })
      return () => h(VoucherEvidenceTag, { row: opts.row ?? { id: 'r1', _gt: { vk: VK } }, projectId: PID, locked: opts.locked })
    },
  })
  return mount(Host, { global: { stubs } })
}

const settle = async () => {
  for (let i = 0; i < 8; i++) await Promise.resolve()
  await nextTick()
}

function serve(links: unknown[], evidence: Record<string, unknown[]>) {
  mocks.get.mockImplementation(async (url: string) => (url === LINKS_URL ? { data: { items: links } } : { data: {} }))
  mocks.post.mockImplementation(async (url: string) => {
    if (url === QUERY_URL) return { data: { evidence } }
    if (url === REUSE_URL) return { data: { link: { id: 'new' }, existed: false } }
    return { data: { attachment: { id: 'uploaded' }, evidence_link: { id: 'l-up' } } }
  })
}

const testIds = (w: ReturnType<typeof mountTag>, id: string) => w.findAll(`[data-testid="${id}"]`)

beforeEach(() => {
  resetWpEvidenceLinksForTest()
  resetVoucherEvidenceIndexForTest()
  for (const m of [mocks.get, mocks.post, mocks.del, mocks.confirmDelete, mocks.handleApiError]) m.mockReset()
  mocks.confirmDelete.mockResolvedValue(true)
  mocks.del.mockResolvedValue({ data: {} })
})

describe('VoucherEvidenceTag', () => {
  const here = [link('l1', 'a-x', VK, 'row:r1'), link('l2', 'a-x', VK), link('l3', 'a-y', VK, 'row:r2'), link('l4', 'a-z', OTHER, 'row:r3')]
  const elsewhere = {
    [VK]: [
      { working_paper_id: WP, wp_code: 'D2-4', wp_name: '本底稿', attachments: [att('a-x'), att('a-y')] },
      { working_paper_id: 'w-f1', wp_code: 'F1-7', wp_name: '应收账款', attachments: [att('a-x'), att('a-q')] },
    ],
  }

  it('本底稿按附件计数；他稿只提示本底稿还没有的；可写时有上传 / 移除 / 引用', async () => {
    serve(here, elsewhere)
    const w = mountTag()
    await settle()
    const ref0 = testIds(w, 'voucher-evidence-tag')[0]
    expect(ref0.text()).toBe('2')
    expect(ref0.attributes('aria-label')).toBe('凭证 2025-01-07 记-0003 已有证据 2 份')
    expect(w.findAll('.gt-voucher-evidence__name').map((n) => n.text())).toEqual(['a-x.pdf', 'a-y.pdf', 'a-q.pdf'])
    expect(testIds(w, 'voucher-evidence-remove')).toHaveLength(2)
    expect(testIds(w, 'voucher-evidence-reuse')).toHaveLength(1)
    expect(testIds(w, 'voucher-evidence-upload')).toHaveLength(1)
    // 他稿查询按凭证键自带的年度（宿主上下文年度是 0）
    const query = mocks.post.mock.calls.find((c) => c[0] === QUERY_URL)!
    expect(query[1]).toEqual({ year: 2025, keys: [VK] })
  })

  it('本底稿没有、他稿有 ⇒ 显示「他稿 n」', async () => {
    serve([], { [VK]: [elsewhere[VK][1]] })
    const w = mountTag()
    await settle()
    expect(testIds(w, 'voucher-evidence-tag')[0].text()).toBe('他稿 2')
    expect(w.find('.gt-voucher-evidence__empty').text()).toBe('本底稿还没有这张凭证的证据')
  })

  it('引用：POST voucher-reuse，随后重取本底稿链接与他稿索引', async () => {
    serve(here, elsewhere)
    const w = mountTag()
    await settle()
    const gets = mocks.get.mock.calls.length
    const queries = mocks.post.mock.calls.filter((c) => c[0] === QUERY_URL).length
    await testIds(w, 'voucher-evidence-reuse')[0].trigger('click')
    await settle()
    expect(mocks.post.mock.calls.find((c) => c[0] === REUSE_URL)![1]).toEqual({ voucher_key: VK, attachment_id: 'a-q' })
    expect(mocks.get.mock.calls.length).toBeGreaterThan(gets)
    expect(mocks.post.mock.calls.filter((c) => c[0] === QUERY_URL).length).toBe(queries + 1)
  })

  it('移除：确认后删除该附件在本底稿的全部链接（含本行识别留下的）', async () => {
    serve(here, elsewhere)
    const w = mountTag()
    await settle()
    await testIds(w, 'voucher-evidence-remove')[0].trigger('click')
    await settle()
    expect(mocks.confirmDelete).toHaveBeenCalledTimes(1)
    expect(mocks.del.mock.calls.map((c) => String(c[0]).split('/').pop())).toEqual(['l1', 'l2'])
  })

  it('移除取消 ⇒ 不删', async () => {
    serve(here, elsewhere)
    mocks.confirmDelete.mockRejectedValueOnce('cancel')
    const w = mountTag()
    await settle()
    await testIds(w, 'voucher-evidence-remove')[0].trigger('click')
    await settle()
    expect(mocks.del).not.toHaveBeenCalled()
  })

  it('上传：凭证级上传带 voucher_key、类型记凭证', async () => {
    serve([], {})
    const w = mountTag()
    await settle()
    const upload = w.findComponent({ name: 'ElUploadStub' })
    await (upload.props('httpRequest') as (r: { file: File }) => Promise<void>)({ file: new File(['x'], '回单.pdf') })
    await settle()
    const call = mocks.post.mock.calls.find((c) => c[1] instanceof FormData)!
    const form = call[1] as FormData
    expect([form.get('voucher_key'), form.get('evidence_type'), form.has('sheet_name')]).toEqual([VK, 'voucher', false])
  })

  it.each([
    [{ readonly: true }, '只读：可查看，不能上传或移除'],
    [{ locked: true }, '年审阶段的预审行只读'],
  ])('只读 %o：只能查看，不出上传 / 移除 / 引用', async (opts, hint) => {
    serve(here, elsewhere)
    const w = mountTag(opts)
    await settle()
    expect(testIds(w, 'voucher-evidence-tag')).toHaveLength(1)
    expect(w.findAll('.gt-voucher-evidence__name')).toHaveLength(3)
    for (const id of ['voucher-evidence-remove', 'voucher-evidence-reuse', 'voucher-evidence-upload']) {
      expect(testIds(w, id), id).toHaveLength(0)
    }
    expect(w.find('.gt-voucher-evidence__hint').text()).toBe(hint)
  })

  it('手工行（没有凭证键）不显示、不查；只读且本底稿与他稿都没有 ⇒ 不显示', async () => {
    serve([], {})
    const manual = mountTag({ row: { id: 'm1' } })
    await settle()
    expect(testIds(manual, 'voucher-evidence-tag')).toHaveLength(0)
    expect(mocks.post).not.toHaveBeenCalled()
    const empty = mountTag({ readonly: true })
    await settle()
    expect(testIds(empty, 'voucher-evidence-tag')).toHaveLength(0)
  })
})
