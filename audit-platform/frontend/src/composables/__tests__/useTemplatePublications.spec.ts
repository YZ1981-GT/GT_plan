/**
 * publication 管理 composable 判据。
 *
 * Spec: custom-workpaper-template-ingestion-and-sync-closure, Task 16 / 20
 *
 * 本文件防的故障形态（每一条都对应真实踩过的坑）：
 * 1. **把 pinned 当已实例化** —— 服务端 `instantiated: false` 时必须按失败处理，
 *    否则用户以为建册成功、后续找不到 workbookInstanceId。
 * 2. **前端自推 `runtimeDiscoverable`** —— 必须取服务端返回值，不按 state 自己算。
 * 3. **consumer 名单漂移** —— 前端名单必须与后端
 *    `finalize_saga.REQUIRED_FINALIZE_CONSUMERS` 逐值一致（否则 ACK 永远收不齐）。
 * 4. **错误提示弹两次** —— 全部请求带 `_silent`。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const get = vi.fn()
const post = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: unknown[]) => get(...args),
    post: (...args: unknown[]) => post(...args),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    download: vi.fn(),
  },
}))

import {
  REQUIRED_FINALIZE_CONSUMERS,
  useTemplatePublications,
} from '@/composables/useTemplatePublications'

const BASE = '/api/custom-template-ingestion'

const PUB_ACTIVE = {
  publicationKey: 'pub-1',
  candidateId: 'art-1',
  state: 'ACTIVE',
  artifactDigest: 'a'.repeat(64),
  authorityRef: 'auth-1',
  reason: null,
  runtimeDiscoverable: true,
  createdAt: '2026-11-15T00:00:00+00:00',
  updatedAt: '2026-11-15T00:00:00+00:00',
}

const PUB_PENDING = {
  ...PUB_ACTIVE,
  publicationKey: 'pub-2',
  state: 'PENDING_VISIBILITY',
  runtimeDiscoverable: false,
}

beforeEach(() => {
  get.mockReset()
  post.mockReset()
})

describe('load', () => {
  it('取列表带 _silent 且写入 publications', async () => {
    get.mockResolvedValueOnce({ publications: [PUB_ACTIVE, PUB_PENDING] })
    const p = useTemplatePublications()
    await p.load()

    expect(get.mock.calls[0][0]).toBe(`${BASE}/publications`)
    expect(get.mock.calls[0][1]?._silent).toBe(true)
    expect(p.publications.value).toHaveLength(2)
    expect(p.active.value.map((x) => x.publicationKey)).toEqual(['pub-1'])
    expect(p.pending.value.map((x) => x.publicationKey)).toEqual(['pub-2'])
  })

  it('state 过滤透传为 params', async () => {
    get.mockResolvedValueOnce({ publications: [] })
    const p = useTemplatePublications()
    await p.load('ACTIVE')
    expect(get.mock.calls[0][1]?.params).toEqual({ state: 'ACTIVE' })
  })

  it('失败时清空列表并写 lastError', async () => {
    get.mockRejectedValueOnce({ response: { data: { detail: '组织无权限' } } })
    const p = useTemplatePublications()
    await p.load()
    expect(p.publications.value).toEqual([])
    expect(p.lastError.value).toBe('组织无权限')
    expect(p.loading.value).toBe(false)
  })
})

describe('commitVisibility', () => {
  it('ACK 全部包成 consumerVersion 并带 _silent', async () => {
    get.mockResolvedValue({ publications: [] })
    post.mockResolvedValueOnce({
      publicationKey: 'pub-2',
      visibilityState: 'ACTIVE',
      state: 'ACTIVE',
      runtimeDiscoverable: true,
      idempotent: false,
    })
    const p = useTemplatePublications()
    const result = await p.commitVisibility('pub-2', [
      { consumer: 'guidance', verdict: 'ACCEPTED' },
    ])

    expect(result?.runtimeDiscoverable).toBe(true)
    const [url, body, cfg] = post.mock.calls[0]
    expect(url).toBe(`${BASE}/publications/commit-visibility`)
    expect(body.publicationKey).toBe('pub-2')
    expect(body.acks[0]).toMatchObject({
      consumer: 'guidance',
      consumerVersion: '1.0.0',
      verdict: 'ACCEPTED',
      reasonCodes: [],
    })
    expect(cfg?._silent).toBe(true)
    // 推进后自动刷新列表
    expect(get).toHaveBeenCalled()
  })

  it('acceptAllConsumers 覆盖四个必需 consumer', async () => {
    get.mockResolvedValue({ publications: [] })
    post.mockResolvedValueOnce({
      publicationKey: 'pub-2',
      visibilityState: 'ACTIVE',
      state: 'ACTIVE',
      runtimeDiscoverable: true,
      idempotent: false,
    })
    const p = useTemplatePublications()
    await p.acceptAllConsumers('pub-2')
    const acks = post.mock.calls[0][1].acks
    expect(acks.map((a: { consumer: string }) => a.consumer)).toEqual([
      ...REQUIRED_FINALIZE_CONSUMERS,
    ])
    expect(acks.every((a: { verdict: string }) => a.verdict === 'ACCEPTED')).toBe(true)
  })

  it('失败写 lastError 并返回 null', async () => {
    post.mockRejectedValueOnce({ response: { data: { detail: '需要发布批准权限' } } })
    const p = useTemplatePublications()
    const result = await p.commitVisibility('pub-2', [])
    expect(result).toBeNull()
    expect(p.lastError.value).toBe('需要发布批准权限')
  })
})

describe('instantiate', () => {
  it('成功时返回 workbookInstanceId', async () => {
    get.mockResolvedValue({ publications: [] })
    post.mockResolvedValueOnce({
      publicationKey: 'pub-1',
      workbookInstanceId: 'pwi-abc',
      projectId: 'proj-1',
      pinned: true,
      instantiated: true,
      sheetCount: 1,
      entries: [{
        entryId: 'pwi-abc:s1',
        sheetUid: 'sheet-0-alpha',
        wpCode: 'F3',
        componentType: 'audit-sheet',
        projectionMode: 'editable_grid',
      }],
    })
    const p = useTemplatePublications()
    const result = await p.instantiate('pub-1', 'wp-1', [{
      sheetUid: 'sheet-0-alpha', wpCode: 'F3',
      componentType: 'audit-sheet', projectionMode: 'editable_grid',
    }])
    expect(result?.workbookInstanceId).toBe('pwi-abc')
    expect(post.mock.calls[0][0]).toBe(`${BASE}/publications/instantiate`)
    expect(post.mock.calls[0][2]?._silent).toBe(true)
  })

  it('🔴 服务端 instantiated=false 时按失败处理，不把 pinned 当完成', async () => {
    post.mockResolvedValueOnce({
      publicationKey: 'pub-1',
      workbookInstanceId: '',
      projectId: 'proj-1',
      pinned: true,
      instantiated: false,
      sheetCount: 0,
      entries: [],
    })
    const p = useTemplatePublications()
    const result = await p.instantiate('pub-1', 'wp-1', [{
      sheetUid: 's1', wpCode: 'F3',
      componentType: 'audit-sheet', projectionMode: 'editable_grid',
    }])
    expect(result).toBeNull()
    expect(p.lastError.value).toContain('pinned 不等于已建册')
  })

  it('回执缺 workbookInstanceId 也按失败处理', async () => {
    post.mockResolvedValueOnce({
      publicationKey: 'pub-1',
      pinned: true,
      instantiated: true,
      sheetCount: 1,
      entries: [],
    })
    const p = useTemplatePublications()
    const result = await p.instantiate('pub-1', 'wp-1', [{
      sheetUid: 's1', wpCode: 'F3',
      componentType: 'audit-sheet', projectionMode: 'editable_grid',
    }])
    expect(result).toBeNull()
    expect(p.lastError.value).toContain('workbookInstanceId')
  })

  it('空 sheet 映射直接拒绝，不发请求', async () => {
    const p = useTemplatePublications()
    const result = await p.instantiate('pub-1', 'wp-1', [])
    expect(result).toBeNull()
    expect(post).not.toHaveBeenCalled()
    expect(p.lastError.value).toBe('至少需要一个 sheet 映射')
  })

  it('失败写 lastError', async () => {
    post.mockRejectedValueOnce({ response: { data: { detail: 'sheetUid 不在 preflight 报告中' } } })
    const p = useTemplatePublications()
    const result = await p.instantiate('pub-1', 'wp-1', [{
      sheetUid: 'bogus', wpCode: 'F3',
      componentType: 'audit-sheet', projectionMode: 'editable_grid',
    }])
    expect(result).toBeNull()
    expect(p.lastError.value).toContain('不在 preflight 报告中')
  })
})

describe('consumer 名单与后端一致', () => {
  it('四个 consumer 逐值固定', () => {
    // 与 backend/app/services/custom_template_ingestion/finalize_saga.py
    // REQUIRED_FINALIZE_CONSUMERS 逐值一致（后端已现算确认）。
    expect([...REQUIRED_FINALIZE_CONSUMERS]).toEqual([
      'guidance',
      'renderer',
      'public_shell',
      'entry_namespace',
    ])
  })
})
