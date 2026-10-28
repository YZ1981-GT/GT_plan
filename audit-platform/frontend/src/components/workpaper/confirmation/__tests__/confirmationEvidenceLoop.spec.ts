/**
 * 函证附件抽屉 + 汇总表计数列（spec attachment-confirmation-evidence-loop 需求 1、2.3）
 *
 * mock 用挂载列表接口的真实形状（`link_id` / `upload_time` / `paired_outbound_attachment_id`），
 * http 桩返回 AxiosResponse（业务数据在 `.data`）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockDelete = vi.fn()
vi.mock('@/utils/http', () => ({
  default: {
    get: (...a: any[]) => mockGet(...a),
    post: (...a: any[]) => mockPost(...a),
    delete: (...a: any[]) => mockDelete(...a),
  },
}))
const mockHandleApiError = vi.fn()
vi.mock('@/utils/errorHandler', () => ({ handleApiError: (...a: any[]) => mockHandleApiError(...a) }))
vi.mock('element-plus', async (importOriginal) => {
  const actual: any = await importOriginal()
  return {
    ...actual,
    ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
    ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
  }
})
vi.mock('@/components/common/AttachmentPreviewDrawer.vue', () => ({
  default: defineComponent({ name: 'PreviewStub', setup: () => () => h('i', { class: 'preview-stub' }) }),
}))

import ElementPlus from 'element-plus'
import ConfirmationAttachmentDrawer from '../ConfirmationAttachmentDrawer.vue'
import ConfirmationMaster from '../ConfirmationMaster.vue'
import { useHubAttachmentCounts } from '../composables/useHubAttachmentCounts'

const axiosLike = (data: unknown) => Promise.resolve({ data, status: 200 })
const slot = (cls: string) => ({ template: `<div class="${cls}"><slot /><slot name="reference" /></div>` })
const stubs = {
  'el-drawer': slot('drawer-stub'),
  'el-upload': slot('upload-stub'),
  'el-select': slot('select-stub'),
  'el-option': { template: '<i />' },
  'el-tag': { template: '<span class="tag"><slot /></span>' },
  'el-divider': { template: '<hr />' },
  'el-input-number': { template: '<input />' },
  'el-date-picker': { template: '<input />' },
  'el-tooltip': slot('tooltip-stub'),
  'el-button': {
    template: '<button class="btn" :data-testid="$attrs[\'data-testid\']" @click="$emit(\'click\', $event)"><slot /></button>',
    inheritAttrs: false,
  },
}

// 时间按接口真实格式（带 `+00:00`，浏览器走查实测）：原夹具写成不带时区的裸时间，测不出「NaN-NaN-NaN」
const LINKS = [
  { link_id: 'L1', attachment_id: 'A1', role: 'outbound', paired_outbound_attachment_id: null, match_status: 'manual',
    file_name: '发函.pdf', upload_time: '2026-10-27T01:00:00.073276+00:00', ocr_status: 'pending',
    link_created_at: '2026-10-27T01:00:00.141253+00:00' },
  { link_id: 'L2', attachment_id: 'A2', role: 'inbound', paired_outbound_attachment_id: 'A1', match_status: 'manual',
    file_name: '回函.jpg', upload_time: '2026-10-28T01:00:00.634441+00:00', ocr_status: 'failed',
    link_created_at: '2026-10-28T01:00:00.996300+00:00' },
]

async function openDrawer(readonly = false) {
  mockGet.mockImplementation(() => axiosLike({ items: LINKS, total: LINKS.length }))
  const w = mount(ConfirmationAttachmentDrawer, {
    props: { visible: false, confirmationId: 'C1', projectId: 'P1', counterpartyName: '甲公司', readonly },
    global: { stubs },
  })
  await w.setProps({ visible: true })
  await flushPromises()
  return w
}

const buttons = (w: any, text: string) => w.findAll('button').filter((b: any) => b.text() === text)

describe('函证附件抽屉', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
    mockDelete.mockReset()
    mockHandleApiError.mockReset()
  })

  it('按挂载记录 id 解绑；时间、配对发函件名取接口真实字段', async () => {
    mockDelete.mockImplementation(() => axiosLike({ success: true }))
    const w = await openDrawer()
    expect(w.text()).toContain('2026-10-28')
    expect(w.text()).not.toContain('NaN')
    expect(w.text()).toContain('配对：发函.pdf')
    await buttons(w, '解绑')[1].trigger('click')
    await flushPromises()
    expect(mockDelete).toHaveBeenCalledWith('/api/projects/P1/confirmations/C1/attachments/L2')
  })

  it('回函件显示识别状态中文；识别比对静默请求，失败也重取列表', async () => {
    mockPost.mockImplementation(() => Promise.reject({ response: { status: 503, data: { detail: '识别服务不可用：x' } } }))
    const w = await openDrawer()
    expect(w.find('[data-testid="ocr-status"]').text()).toBe('识别失败')
    const before = mockGet.mock.calls.length
    await buttons(w, '识别比对')[0].trigger('click')
    await flushPromises()
    const [url, body, config] = mockPost.mock.calls[0]
    expect(url).toBe('/api/projects/P1/confirmations/attachments/A2/extract-compare')
    expect(body).toBeUndefined()
    expect(config).toMatchObject({ _silent: true }) // 不静默的话 5xx 会被自动重发两次（重复识别）
    expect(mockHandleApiError).toHaveBeenCalledWith(expect.anything(), '识别比对')
    expect(mockGet.mock.calls.length).toBe(before + 1)
    expect(w.text()).not.toContain('AI辅助·待人工确认') // 失败不出比对面板
  })

  it('只读：没有上传区、解绑、识别比对，仍可预览', async () => {
    const w = await openDrawer(true)
    expect(w.find('.upload-stub').exists()).toBe(false)
    expect(buttons(w, '解绑')).toHaveLength(0)
    expect(buttons(w, '识别比对')).toHaveLength(0)
    expect(buttons(w, '预览')).toHaveLength(2)
  })
})

describe('汇总表「函证附件」列', () => {
  const rows = [
    { _row_id: 'r1', entity_name: '甲公司', _hub_confirmation_id: 'C1' },
    { _row_id: 'r2', entity_name: '乙公司' },
  ]

  it('已同步行显示发 / 回件数并可点开，未同步行显示「未同步」', async () => {
    const w = mount(ConfirmationMaster, {
      props: { rows, readonly: true, selectedIds: [], attachmentCounts: { C1: { outbound: 1, inbound: 2 } } },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    const cell = w.find('[data-testid="hub-attachment-count"]')
    expect(cell.text()).toBe('发 1 · 回 2')
    expect(w.text()).toContain('未同步')
    await cell.trigger('click')
    expect(w.emitted('open-attachments')?.[0]?.[0]).toMatchObject({ _hub_confirmation_id: 'C1' })
  })

  it('不传计数时不显示该列（无项目上下文）', () => {
    const w = mount(ConfirmationMaster, {
      props: { rows, readonly: false, selectedIds: [] },
      global: { plugins: [ElementPlus] },
    })
    expect(w.text()).not.toContain('函证附件')
  })

  it('计数复用列表结果、改动后不去重重取；只对已同步行打开抽屉', async () => {
    const hub = useHubAttachmentCounts(() => 'P1')
    hub.ingest([{ id: 'C1', outbound_count: 2, inbound_count: 1 }, { id: '' }])
    expect(hub.counts.value).toEqual({ C1: { outbound: 2, inbound: 1 } })
    mockGet.mockImplementation(() => axiosLike({ items: [{ id: 'C1', outbound_count: 3, inbound_count: 3 }] }))
    await hub.reload()
    expect(mockGet).toHaveBeenCalledWith('/api/projects/P1/confirmations', { _silent: true, _dedupe: false })
    expect(hub.counts.value.C1).toEqual({ outbound: 3, inbound: 3 })
    hub.open({ entity_name: '乙公司' })
    expect(hub.drawer.visible).toBe(false)
    hub.open({ _hub_confirmation_id: 'C1', entity_name: '甲公司' })
    expect([hub.drawer.visible, hub.drawer.confirmationId, hub.drawer.counterparty]).toEqual([true, 'C1', '甲公司'])
  })
})

describe('汇总表「同步到函证中心」的函证 id 落库（需求 1.5）', () => {
  // 宿主 1900+ 行、setup 期要注入审计上下文与七个 composable，挂载代价过高 ⇒ 读源码（先剥注释）核对接线；
  // 行为另由浏览器走查覆盖（同步 → 刷新 → 计数列仍可点）。
  async function hostFunction(signature: string): Promise<string> {
    const { readFileSync } = await import('fs')
    const { resolve } = await import('path')
    const { stripJsComments } = await import('@/__tests__/_helpers/frontendSourceScan')
    const src = stripJsComments(readFileSync(resolve(__dirname, '../GtConfirmationSummary.vue'), 'utf-8'))
    const start = src.indexOf(signature)
    expect(start, `宿主里找不到 ${signature}`).toBeGreaterThan(0)
    let depth = 0
    for (let i = src.indexOf('{', start); i < src.length; i++) {
      if (src[i] === '{') depth++
      else if (src[i] === '}' && --depth === 0) return src.slice(start, i)
    }
    return src.slice(start)
  }

  it('有行新写入函证 id 且本表没有别的未保存改动时，同步后即落库', async () => {
    expect(await hostFunction('async function handleSyncHub()'))
      .toMatch(/if \(res\.remapped && !hasUnsavedChanges\.value\) emit\('save', data\.buildPayload\(\)\)/)
  })

  it('Excel 导入只改内存 ⇒ 标记未保存（否则同步会把未保存的导入行当作已保存一并落库）', async () => {
    expect(await hostFunction('async function handleImportFile(')).toMatch(/markDirty\(\)/)
  })
})
