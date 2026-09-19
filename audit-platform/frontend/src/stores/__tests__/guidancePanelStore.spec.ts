import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '@/services/apiProxy'
import {
  buildGuidanceCacheDataKey,
  buildGuidanceContextIdentity,
  GUIDANCE_CACHE_SCHEMA,
  useGuidancePanelStore,
  type GuidanceResponse,
  type WpContext,
} from '@/stores/guidancePanelStore'

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn() },
}))

function context(overrides: Partial<WpContext> = {}): WpContext {
  return {
    wpId: '11111111-1111-1111-1111-111111111111',
    wpCode: 'D0',
    wpName: '函证',
    componentType: 'confirmation-hub',
    projectId: '22222222-2222-2222-2222-222222222222',
    year: 2025,
    sheetCode: 'D0-1',
    sheetName: '函证结果汇总 D0-1',
    sheetUid: 'uid:D0:D0-1',
    host: 'html',
    wholeWorkbook: false,
    ownerEpoch: 1,
    contextRevision: 1,
    ...overrides,
  }
}

function response(overrides: Partial<GuidanceResponse> = {}): GuidanceResponse {
  return {
    wp_code: 'D0-1',
    wp_name: '函证结果汇总',
    requested_sheet_code: 'D0-1',
    requested_sheet_name: '函证结果汇总 D0-1',
    resolved_wp_code: 'D0-1',
    inherited_from_parent: false,
    resolution_status: 'exact',
    resolution_reason: 'child_exact_static',
    sheet_identity_reason: 'explicit_code',
    source: 'static_json',
    complexity: 'high',
    guidance_version: 'guidance-v2-v1',
    source_digest: 'a'.repeat(64),
    generated_at: '2026-09-07T00:00:00+00:00',
    missing_sections: [],
    ai_enabled: true,
    etag: '"guidance-v2-v1"',
    guidance: {
      sections: [{
        key: 'purpose',
        title: '编制目的',
        items: ['核对 D0-1'],
        source_refs: [{ kind: 'xlsx', path: 'backend/wp_templates/D/D0.xlsx' }],
      }],
      raw_text: '核对 D0-1',
    },
    recommended_questions: [],
    ...overrides,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('guidancePanelStore — 单请求、版本缓存与竞态隔离', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    sessionStorage.clear()
    vi.clearAllMocks()
  })

  it('同一 context 只由 setWpContext 发起一次请求', async () => {
    vi.mocked(api.get).mockResolvedValue(response())
    const store = useGuidancePanelStore()
    const ctx = context()

    store.setWpContext(ctx)
    store.setWpContext({ ...ctx })

    await vi.waitFor(() => expect(store.guidanceData?.guidance_version).toBe('guidance-v2-v1'))
    expect(api.get).toHaveBeenCalledTimes(1)
    expect(api.get).toHaveBeenCalledWith(
      expect.stringContaining('sheet_code=D0-1'),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
  })

  it('context/cache identity 同时隔离 project、wp instance、sheet、whole 与 schema/version；不含 revision', () => {
    const base = buildGuidanceContextIdentity(context())
    expect(base).toContain(GUIDANCE_CACHE_SCHEMA)
    expect(base).toContain('sheet-uid:uid:D0:D0-1')
    expect(buildGuidanceContextIdentity(context({ projectId: 'other-project' }))).not.toBe(base)
    expect(buildGuidanceContextIdentity(context({ wpId: 'other-wp' }))).not.toBe(base)
    expect(buildGuidanceContextIdentity(context({ sheetUid: 'uid:D0:D0-2', sheetCode: 'D0-2', sheetName: 'D0-2' }))).not.toBe(base)
    expect(buildGuidanceContextIdentity(context({ sheetCode: null, sheetUid: null, wholeWorkbook: true }))).not.toBe(base)
    expect(buildGuidanceContextIdentity(context({ contextRevision: 99, ownerEpoch: 9 }))).toBe(base)

    const dataKey = buildGuidanceCacheDataKey(base, 'guidance-v2-version-42')
    expect(dataKey).toContain(encodeURIComponent('guidance-v2-version-42'))
  })

  it('快速连续切换三个 sheet 时旧响应不能覆盖最后 context（含 epoch/revision 门）', async () => {
    const first = deferred<GuidanceResponse>()
    const second = deferred<GuidanceResponse>()
    const third = deferred<GuidanceResponse>()
    vi.mocked(api.get)
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise)
      .mockImplementationOnce(() => third.promise)

    const store = useGuidancePanelStore()
    store.setWpContext(context({ sheetCode: 'D0-1', sheetUid: 'uid:D0:D0-1', sheetName: 'D0-1', contextRevision: 1 }))
    store.setWpContext(context({ sheetCode: 'D0-2', sheetUid: 'uid:D0:D0-2', sheetName: 'D0-2', contextRevision: 2 }))
    store.setWpContext(context({ sheetCode: 'D0-3', sheetUid: 'uid:D0:D0-3', sheetName: 'D0-3', contextRevision: 3 }))

    third.resolve(response({
      wp_code: 'D0-3',
      requested_sheet_code: 'D0-3',
      resolved_wp_code: 'D0-3',
      guidance_version: 'guidance-v2-third',
    }))
    await vi.waitFor(() => expect(store.guidanceData?.wp_code).toBe('D0-3'))

    first.resolve(response({ wp_code: 'D0-1', guidance_version: 'guidance-v2-first' }))
    second.resolve(response({ wp_code: 'D0-2', guidance_version: 'guidance-v2-second' }))
    await Promise.resolve()
    await Promise.resolve()

    expect(store.wpContext?.sheetCode).toBe('D0-3')
    expect(store.wpContext?.contextRevision).toBe(3)
    expect(store.guidanceData?.wp_code).toBe('D0-3')
    expect(store.guidanceData?.guidance_version).toBe('guidance-v2-third')
  })

  it('ETag 304 保留短 TTL 预览并发送 If-None-Match', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce(response())
      .mockRejectedValueOnce({ response: { status: 304 } })

    const store = useGuidancePanelStore()
    const ctx = context()
    store.setWpContext(ctx)
    await vi.waitFor(() => expect(store.guidanceData?.guidance_version).toBe('guidance-v2-v1'))

    store.setWpContext({ ...ctx, contextRevision: 2 })
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledTimes(2))
    expect(vi.mocked(api.get).mock.calls[1][1]).toMatchObject({
      headers: { 'If-None-Match': '"guidance-v2-v1"' },
    })
    expect(store.guidanceData?.guidance_version).toBe('guidance-v2-v1')
    expect(store.guidanceError).toBeNull()
  })

  it('fresh cache 只作预览并后台 revalidate 到新版本', async () => {
    const refreshed = deferred<GuidanceResponse>()
    vi.mocked(api.get)
      .mockResolvedValueOnce(response({ guidance_version: 'guidance-v2-old', etag: '"guidance-v2-old"' }))
      .mockResolvedValueOnce(response({
        wp_code: 'D0-2',
        requested_sheet_code: 'D0-2',
        resolved_wp_code: 'D0-2',
        guidance_version: 'guidance-v2-sheet2',
        etag: '"guidance-v2-sheet2"',
      }))
      .mockImplementationOnce(() => refreshed.promise)

    const store = useGuidancePanelStore()
    const firstContext = context()
    store.setWpContext(firstContext)
    await vi.waitFor(() => expect(store.guidanceData?.guidance_version).toBe('guidance-v2-old'))

    store.setWpContext(context({ sheetCode: 'D0-2', sheetUid: 'uid:D0:D0-2', sheetName: 'D0-2', contextRevision: 2 }))
    await vi.waitFor(() => expect(store.guidanceData?.guidance_version).toBe('guidance-v2-sheet2'))

    store.setWpContext({ ...firstContext, contextRevision: 3 })
    expect(store.guidanceData?.guidance_version).toBe('guidance-v2-old')
    expect(api.get).toHaveBeenCalledTimes(3)

    refreshed.resolve(response({ guidance_version: 'guidance-v2-new', etag: '"guidance-v2-new"' }))
    await vi.waitFor(() => expect(store.guidanceData?.guidance_version).toBe('guidance-v2-new'))
  })

  it('请求失败会清理缓存预览、AI 状态与统一 AI context', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce(response({ ai_enabled: true }))
      .mockRejectedValueOnce(new Error('network down'))
    const store = useGuidancePanelStore()

    store.setWpContext(context())
    await vi.waitFor(() => expect(store.aiGuidanceContext?.guidanceVersion).toBe('guidance-v2-v1'))

    store.setWpContext(context({ sheetCode: 'D0-2', sheetUid: 'uid:D0:D0-2', sheetName: 'D0-2', contextRevision: 2 }))
    await vi.waitFor(() => expect(store.guidanceError).toContain('network down'))

    expect(store.guidanceData).toBeNull()
    expect(store.aiEnabled).toBe(false)
    expect(store.aiGuidanceContext).toBeNull()
  })

  it('旧面板卸载不能清除新 context，当前 owner 可安全清理', async () => {
    vi.mocked(api.get).mockResolvedValue(response())
    const store = useGuidancePanelStore()
    const first = context()
    const second = context({ sheetCode: 'D0-2', sheetUid: 'uid:D0:D0-2', sheetName: 'D0-2', contextRevision: 2 })
    const firstIdentity = buildGuidanceContextIdentity(first)
    const secondIdentity = buildGuidanceContextIdentity(second)

    store.setWpContext(first)
    store.setWpContext(second)
    await vi.waitFor(() => expect(store.contextIdentity).toBe(secondIdentity))

    expect(store.clearWpContext(firstIdentity)).toBe(false)
    expect(store.contextIdentity).toBe(secondIdentity)
    expect(store.wpContext?.sheetCode).toBe('D0-2')

    expect(store.clearWpContext(secondIdentity)).toBe(true)
    expect(store.contextIdentity).toBe('')
    expect(store.wpContext).toBeNull()
    expect(store.guidanceData).toBeNull()
    expect(store.aiGuidanceContext).toBeNull()
  })

  it('Univer 用 sheet_name 请求；OnlyOffice 整册显式发送 whole_workbook', async () => {
    vi.mocked(api.get).mockResolvedValue(response())
    const store = useGuidancePanelStore()

    store.setWpContext(context({
      sheetCode: null,
      sheetUid: null,
      sheetName: '商誉减值测试 A3-8',
      host: 'univer',
      contextRevision: 1,
    }))
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledTimes(1))
    expect(vi.mocked(api.get).mock.calls[0][0]).toContain('sheet_name=')
    expect(vi.mocked(api.get).mock.calls[0][0]).not.toContain('sheet_code=')

    store.setWpContext(context({
      sheetCode: null,
      sheetUid: null,
      sheetName: '',
      host: 'onlyoffice',
      wholeWorkbook: true,
      contextRevision: 2,
    }))
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledTimes(2))
    expect(vi.mocked(api.get).mock.calls[1][0]).toMatch(/\/guidance\?whole_workbook=true$/)
    expect(vi.mocked(api.get).mock.calls[1][0]).not.toContain('sheet_code=')
    expect(vi.mocked(api.get).mock.calls[1][0]).not.toContain('sheet_name=')
  })
})
