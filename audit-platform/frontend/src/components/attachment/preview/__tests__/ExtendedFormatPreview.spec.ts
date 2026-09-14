/**
 * ArchiveEntryList 三要素 + ExtendedFormatPreview module Worker 状态机
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ArchiveEntryList from '../archive/ArchiveEntryList.vue'
import ExtendedFormatPreview from '../ExtendedFormatPreview.vue'
import { EMAIL_LIMITS } from '../email/emailLimits'
import { DRAWING_LIMITS } from '../drawing/drawingLimits'

vi.mock('@/utils/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), log: vi.fn() },
}))

vi.mock('@/utils/http', () => ({
  default: { get: vi.fn() },
}))

import http from '@/utils/http'

class ProtocolWorker {
  static instances: ProtocolWorker[] = []
  static responseRequestId: ((requestId: string) => string) | null = null
  static emailResult: unknown = { status: 'limit' }

  readonly terminate = vi.fn()
  readonly postMessage = vi.fn((payload: any, transfer: Transferable[] = []) => {
    this.lastTransfer = transfer
    queueMicrotask(() => {
      const requestId = ProtocolWorker.responseRequestId?.(payload.requestId) ?? payload.requestId
      const result = payload.requestId.startsWith('archive-')
        ? {
            status: 'ok',
            entries: [
              {
                name: 'worker-entry.txt',
                size: 3,
                declaredSize: 3,
                mtime: null,
                isDirectory: false,
                suspicious: false,
                suspiciousReasons: [],
                unparsable: false,
                method: 0,
              },
            ],
          }
        : payload.requestId.startsWith('email-')
          ? ProtocolWorker.emailResult
          : { status: 'limit' }
      this.emit('message', { data: { requestId, ok: true, result } })
    })
  })
  readonly listeners: Record<string, Set<(event: any) => void>> = {
    message: new Set(),
    error: new Set(),
  }
  lastTransfer: Transferable[] = []

  constructor(readonly url: URL, readonly options: WorkerOptions) {
    ProtocolWorker.instances.push(this)
  }

  addEventListener(type: string, listener: (event: any) => void): void {
    this.listeners[type]?.add(listener)
  }

  removeEventListener(type: string, listener: (event: any) => void): void {
    this.listeners[type]?.delete(listener)
  }

  private emit(type: string, event: any): void {
    for (const listener of this.listeners[type] ?? []) listener(event)
  }
}

describe('ArchiveEntryList render tree 三要素', () => {
  it('N 条模型 → N 行；字段嵌套在行内', () => {
    const entries = [
      {
        name: 'a.txt',
        size: 3,
        declaredSize: 3,
        mtime: null,
        isDirectory: false,
        suspicious: false,
        suspiciousReasons: [],
        unparsable: false,
        method: 0,
      },
      {
        name: 'b/',
        size: 0,
        declaredSize: 0,
        mtime: null,
        isDirectory: true,
        suspicious: true,
        suspiciousReasons: ['dotdot'],
        unparsable: false,
        method: null,
      },
    ]
    const wrapper = mount(ArchiveEntryList, { props: { entries } })
    const rows = wrapper.findAll('[data-testid="archive-entry-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].find('[data-field="name"]').text()).toBe('a.txt')
    expect(rows[0].find('[data-field="size"]').text()).toBe('3')
    expect(rows[1].find('[data-field="directory"]').text()).toBe('dir')
    expect(rows[1].find('[data-field="suspicious"]').exists()).toBe(true)
  })

  it('空列表 → 0 行', () => {
    const wrapper = mount(ArchiveEntryList, { props: { entries: [] } })
    expect(wrapper.findAll('[data-testid="archive-entry-row"]')).toHaveLength(0)
  })
})

describe('ExtendedFormatPreview', () => {
  beforeEach(() => {
    vi.mocked(http.get).mockReset()
    ProtocolWorker.instances = []
    ProtocolWorker.responseRequestId = null
    ProtocolWorker.emailResult = { status: 'limit' }
    vi.stubGlobal('Worker', ProtocolWorker)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('dev/Vitest 也走真实协议 fake module Worker，匹配 requestId 后渲染 zip 清单', async () => {
    const bytes = new ArrayBuffer(8)
    vi.mocked(http.get).mockResolvedValue({
      data: { type: 'application/octet-stream', size: 8, arrayBuffer: async () => bytes },
      headers: { 'content-type': 'application/octet-stream' },
      status: 200,
    })
    const wrapper = mount(ExtendedFormatPreview, {
      props: {
        attachmentId: 'att-z',
        downloadUrl: '/api/attachments/att-z/download',
        fileName: '证据.zip',
        typeHint: 'zip',
      },
    })

    await vi.waitFor(() => expect((wrapper.vm as any).state).toBe('ready'))
    await flushPromises()
    await nextTick()

    expect(ProtocolWorker.instances).toHaveLength(1)
    const worker = ProtocolWorker.instances[0]
    expect(String(worker.url)).toContain('archive.worker.ts')
    expect(worker.options).toEqual({ type: 'module' })
    expect(worker.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ requestId: 'archive-1', bytes, hintExt: 'zip' }),
      [bytes],
    )
    expect(worker.terminate).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-testid="archive-entry-list"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-testid="archive-entry-row"]')).toHaveLength(1)
    wrapper.unmount()
    expect(worker.terminate).toHaveBeenCalledTimes(1)
  })

  it('email 传入输入上限并直接 transfer 原始 buffer，不 slice', async () => {
    const bytes = new ArrayBuffer(8)
    vi.mocked(http.get).mockResolvedValue({
      data: { type: 'message/rfc822', size: 8, arrayBuffer: async () => bytes },
      headers: { 'content-type': 'message/rfc822' },
      status: 200,
    })
    const wrapper = mount(ExtendedFormatPreview, {
      props: {
        attachmentId: 'att-e',
        downloadUrl: '/api/attachments/att-e/download',
        fileName: 'mail.eml',
        typeHint: 'eml',
      },
    })

    await vi.waitFor(() => expect((wrapper.vm as any).state).toBe('limit_reached'))
    const worker = ProtocolWorker.instances[0]
    const [payload, transfer] = worker.postMessage.mock.calls[0]
    expect(payload.bytes).toBe(bytes)
    expect(transfer).toEqual([bytes])
    expect(payload.hintExt).toBe('eml')
    expect(worker.terminate).toHaveBeenCalledTimes(1)
  })

  it('Email CID object URL 由宿主 PreviewResourceScope 统一持有并在卸载释放', async () => {
    if (typeof URL.createObjectURL !== 'function') {
      ;(URL as any).createObjectURL = () => 'blob:cid-host'
    }
    if (typeof URL.revokeObjectURL !== 'function') {
      ;(URL as any).revokeObjectURL = () => undefined
    }
    const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:cid-host')
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    ProtocolWorker.emailResult = {
      status: 'ok',
      email: {
        from: 'a@example.com',
        to: ['b@example.com'],
        cc: [],
        subject: 'CID evidence',
        date: null,
        html: '<img src="cid:image@x">',
        text: 'fallback',
        attachments: [],
        inlineParts: [{
          canonicalCid: 'image@x',
          declaredMime: 'image/png',
          bytes: new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]).buffer,
        }],
        ambiguousCids: [],
      },
    }
    const bytes = new ArrayBuffer(8)
    vi.mocked(http.get).mockResolvedValue({
      data: { type: 'message/rfc822', size: 8, arrayBuffer: async () => bytes },
      headers: { 'content-type': 'message/rfc822' },
      status: 200,
    })
    const wrapper = mount(ExtendedFormatPreview, {
      props: {
        attachmentId: 'att-cid',
        downloadUrl: '/api/attachments/att-cid/download',
        fileName: 'cid.eml',
      },
    })

    await vi.waitFor(() => expect((wrapper.vm as any).state).toBe('ready'))
    await flushPromises()
    await vi.waitFor(() => expect((wrapper.vm as any).getResourceSnapshot().objectUrls).toBe(1))
    expect(create).toHaveBeenCalledTimes(1)
    wrapper.unmount()
    expect(revoke).toHaveBeenCalledWith('blob:cid-host')
    create.mockRestore()
    revoke.mockRestore()
  })

  it('Worker 响应 requestId 不匹配时拒绝结果并进入 parse_failed', async () => {
    ProtocolWorker.responseRequestId = () => 'wrong-request'
    vi.mocked(http.get).mockResolvedValue({
      data: { type: 'application/octet-stream', size: 1, arrayBuffer: async () => new ArrayBuffer(1) },
      headers: { 'content-type': 'application/octet-stream' },
      status: 200,
    })
    const wrapper = mount(ExtendedFormatPreview, {
      props: {
        attachmentId: 'att-z',
        downloadUrl: '/api/attachments/att-z/download',
        fileName: 'evidence.zip',
      },
    })
    await vi.waitFor(() => expect((wrapper.vm as any).state).toBe('parse_failed'))
    expect(ProtocolWorker.instances[0].terminate).toHaveBeenCalledTimes(1)
  })

  it('email blob.size 超过 EMAIL_LIMITS 时不调用 arrayBuffer/Worker', async () => {
    const arrayBuffer = vi.fn(async () => new ArrayBuffer(1))
    vi.mocked(http.get).mockResolvedValue({
      data: { type: 'message/rfc822', size: EMAIL_LIMITS.maxInputBytes + 1, arrayBuffer },
      headers: { 'content-type': 'message/rfc822' },
      status: 200,
    })
    const wrapper = mount(ExtendedFormatPreview, {
      props: {
        attachmentId: 'att-big',
        downloadUrl: '/api/attachments/att-big/download',
        fileName: 'big.eml',
      },
    })
    await vi.waitFor(() => expect((wrapper.vm as any).state).toBe('limit_reached'))
    expect(arrayBuffer).not.toHaveBeenCalled()
    expect(ProtocolWorker.instances).toHaveLength(0)
  })

  it('drawing Worker 消费单一真源的 10 秒 deadline', async () => {
    const timeoutSpy = vi.spyOn(globalThis, 'setTimeout')
    const bytes = new ArrayBuffer(8)
    vi.mocked(http.get).mockResolvedValue({
      data: { type: 'application/dxf', size: 8, arrayBuffer: async () => bytes },
      headers: { 'content-type': 'application/dxf' },
      status: 200,
    })
    const wrapper = mount(ExtendedFormatPreview, {
      props: {
        attachmentId: 'att-dxf',
        downloadUrl: '/api/attachments/att-dxf/download',
        fileName: 'plan.dxf',
      },
    })
    try {
      await vi.waitFor(() => expect((wrapper.vm as any).state).toBe('limit_reached'))
      expect(timeoutSpy.mock.calls.some((call) => call[1] === DRAWING_LIMITS.deadlineMs)).toBe(true)
      expect(String(ProtocolWorker.instances[0].url)).toContain('dxf.worker.ts')
    } finally {
      wrapper.unmount()
      timeoutSpy.mockRestore()
    }
  })

  it('dwg 不取字节也不建 Worker，显示下载提示', async () => {
    const wrapper = mount(ExtendedFormatPreview, {
      props: {
        attachmentId: 'att-d',
        downloadUrl: '/api/attachments/att-d/download',
        fileName: 'plan.dwg',
      },
    })
    await flushPromises()
    expect(http.get).not.toHaveBeenCalled()
    expect(ProtocolWorker.instances).toHaveLength(0)
    expect(wrapper.find('[data-testid="extended-preview-fallback"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="extended-preview-download"]').exists()).toBe(true)
  })
})
