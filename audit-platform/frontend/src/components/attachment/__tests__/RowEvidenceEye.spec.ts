/**
 * RowEvidenceEye — 行内附件小眼睛（spec attachment-inline-preview ADR-AIP-03，变异 #4）
 *
 * 按位置（表页 + 行槽位）从本底稿共享链接仓取本行附件：0 份不显示、1 份小眼睛、多份「👁 n」列表；
 * 同一底稿多个实例只发一次列表请求；项目 id 缺省取路由参数。mock 用 GET …/evidence 真实形状。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const mockGet = vi.fn()
vi.mock('@/utils/http', () => ({
  default: { get: (...args: any[]) => mockGet(...args) },
  downloadFile: vi.fn(),
}))

const route = { params: { projectId: 'p-route' } as Record<string, unknown> }
vi.mock('vue-router', () => ({ useRoute: () => route }))

vi.mock('@/components/attachment/AttachmentEyeButton.vue', async () => {
  const vue = await import('vue')
  return {
    default: vue.defineComponent({
      name: 'AttachmentEyeButtonStub',
      props: ['attachmentId', 'fileName', 'fileType', 'ocrStatus'],
      setup(props: any) {
        return () => vue.h('i', { class: 'eye-stub', 'data-id': props.attachmentId, 'data-name': props.fileName })
      },
    }),
  }
})

import RowEvidenceEye from '../RowEvidenceEye.vue'
import { resetWpEvidenceLinksForTest } from '@/composables/useWpEvidenceLinks'

const stubs = {
  'el-popover': { template: '<div class="popover-stub"><slot name="reference" /><div class="popover-body"><slot /></div></div>' },
  'el-button': {
    template: '<button class="el-button" :class="$attrs.class" :aria-label="$attrs[\'aria-label\']" :data-testid="$attrs[\'data-testid\']"><slot /></button>',
    props: ['type', 'size', 'link'],
    inheritAttrs: false,
  },
  'el-icon': { template: '<i><slot /></i>' },
}

function linkRow(id: string, cellRef: string, fileName: string, sheetName = 'G8-6') {
  return {
    id,
    wp_id: 'w1',
    sheet_name: sheetName,
    cell_ref: cellRef,
    attachment_id: `att-${id}`,
    page_ref: null,
    evidence_type: 'voucher',
    check_conclusion: null,
    created_by: 'u1',
    created_at: '2026-10-27T08:00:00',
    attachment: {
      id: `att-${id}`, file_name: fileName, file_size: 10, file_type: 'pdf',
      attachment_type: 'voucher', ocr_status: 'completed', created_at: '2026-10-27T08:00:00',
    },
  }
}

function mountEye(props: Record<string, unknown> = {}) {
  return mount(RowEvidenceEye, {
    props: { projectId: 'p1', wpId: 'w1', sheetKey: 'G8-6', cellRef: 'row:r1', ...props },
    global: { stubs },
  })
}

describe('RowEvidenceEye', () => {
  beforeEach(() => {
    resetWpEvidenceLinksForTest()
    mockGet.mockReset()
    route.params = { projectId: 'p-route' }
  })

  it('本行没有附件：不显示', async () => {
    mockGet.mockResolvedValueOnce({ data: { items: [linkRow('l1', 'row:r2', '别的行.pdf')] } })
    const wrapper = mountEye()
    await flushPromises()
    expect(wrapper.find('[data-testid="row-evidence-eye"]').exists()).toBe(false)
  })

  it('一份：直接是这份附件的小眼睛', async () => {
    mockGet.mockResolvedValueOnce({ data: { items: [linkRow('l1', 'row:r1', '凭证.pdf'), linkRow('l2', 'row:r1', '他页.pdf', 'G8-7')] } })
    const wrapper = mountEye()
    await flushPromises()
    const eyes = wrapper.findAll('.eye-stub')
    expect(eyes).toHaveLength(1)
    expect(eyes[0].attributes('data-id')).toBe('att-l1')
    expect(eyes[0].attributes('data-name')).toBe('凭证.pdf')
  })

  it('多份：显示份数，列表里逐个有小眼睛', async () => {
    mockGet.mockResolvedValueOnce({ data: { items: [linkRow('l1', 'row:r1', '一.pdf'), linkRow('l2', 'row:r1', '二.jpg')] } })
    const wrapper = mountEye()
    await flushPromises()
    // 外层恒为 span（多份时按钮不直接挨着宿主按钮，避免吃到 12px 间距在窄列里换行）
    expect(wrapper.find('span[data-testid="row-evidence-eye"]').exists()).toBe(true)
    const btn = wrapper.find('[data-testid="row-evidence-eye"] button.gt-row-eye__multi')
    expect(btn.text()).toContain('2')
    expect(btn.attributes('aria-label')).toBe('本行附件 2 份，点开逐个预览')
    expect(wrapper.findAll('.popover-body .eye-stub').map((e) => e.attributes('data-name'))).toEqual(['一.pdf', '二.jpg'])
  })

  it('同一底稿多行只发一次列表请求', async () => {
    mockGet.mockResolvedValueOnce({ data: { items: [linkRow('l1', 'row:r1', '一.pdf')] } })
    const wrappers = ['row:r1', 'row:r2', 'row:r3'].map((cellRef) => mountEye({ cellRef }))
    await flushPromises()
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(mockGet.mock.calls[0][0]).toBe('/api/projects/p1/workpapers/w1/evidence')
    expect(wrappers[0].findAll('.eye-stub')).toHaveLength(1)
    expect(wrappers[1].findAll('.eye-stub')).toHaveLength(0)
  })

  it('不传项目 id 时取路由参数', async () => {
    mockGet.mockResolvedValueOnce({ data: { items: [] } })
    mountEye({ projectId: null })
    await flushPromises()
    expect(mockGet.mock.calls[0][0]).toBe('/api/projects/p-route/workpapers/w1/evidence')
  })
})
