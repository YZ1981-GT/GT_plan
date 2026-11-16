/**
 * 自定义模板摄取向导 —— ingest → preflight → authority → finalize 四阶段接线守卫。
 *
 * Spec: custom-workpaper-template-ingestion-and-sync-closure
 * 相关后端：`/api/custom-template-ingestion/{ingest,artifacts/{id}/preflight,
 * artifacts/{id}/unit-authority, artifacts/{id}/finalize}`
 *
 * 🔴 本文件防的故障形态：后端四阶段已接通，而前端仍停在「上传成功」——
 * 用户以为已就绪，实际 preflight / authority / finalize 一次都没跑。
 *
 * 判据分四层：
 * 1. 每阶段都真的发请求（端点字面量 + 方法）；
 * 2. 每阶段都带 `_silent`（调用方自管错误提示，避免全局 toast 弹两次）；
 * 3. 状态推进真实反映服务端返回（不伪造 PREFLIGHT_READY / ACTIVE）；
 * 4. finalize 后 **不得** 注册 host facts（只有 ACTIVE 才允许）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const post = vi.fn()
const put = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
    post: (...args: unknown[]) => post(...args),
    put: (...args: unknown[]) => put(...args),
    patch: vi.fn(),
    delete: vi.fn(),
    download: vi.fn(),
  },
}))

import { useCustomIngestionWizard } from '@/composables/useCustomIngestionWizard'

const BASE = '/api/custom-template-ingestion'
const PREFLIGHT_DIGEST = 'b'.repeat(64)
const MANIFEST_DIGEST = 'c'.repeat(64)

function ingested(sha = 'a'.repeat(64)) {
  return {
    artifactId: 'art-1',
    state: 'QUARANTINED',
    displayName: '客户报表.xlsx',
    sizeBytes: 2048,
    sha256: sha,
    policyVersion: 'v1',
    actionId: 'ingest_excel_template',
    message: '文件已进入隔离区；未发布，未生成项目底稿',
  }
}

beforeEach(() => {
  post.mockReset()
  put.mockReset()
})

describe('ingest 阶段', () => {
  it('上传走 multipart 且带 _silent，成功后停在 quarantined', async () => {
    post.mockResolvedValueOnce(ingested())
    const w = useCustomIngestionWizard()
    const file = new File([new Uint8Array([1, 2, 3])], 'a.xlsx')
    const result = await w.ingestFile(file)

    expect(result?.artifactId).toBe('art-1')
    const [url, body, config] = post.mock.calls[0]
    expect(url).toBe(`${BASE}/ingest`)
    expect(body).toBeInstanceOf(FormData)
    expect(config?._silent).toBe(true)

    expect(w.state.value.phase).toBe('quarantined')
    expect(w.state.value.artifactId).toBe('art-1')
    // 上传成功绝不注册 host facts
    expect(w.state.value.hostFactsRegistered).toBe(false)
  })

  it('上传失败写入可恢复 blocker，不伪造 artifactId', async () => {
    post.mockRejectedValueOnce({ response: { data: { detail: { code: 'EXTENSION_NOT_ALLOWED' } } } })
    const w = useCustomIngestionWizard()
    const result = await w.ingestFile(new File([new Uint8Array([1])], 'a.exe'))

    expect(result).toBeNull()
    expect(w.state.value.artifactId).toBeNull()
    expect(w.state.value.blockers[0].code).toBe('ingest_failed')
    expect(w.state.value.blockers[0].recoverable).toBe(true)
  })
})

describe('preflight 阶段', () => {
  it('PREFLIGHT_READY 才推进到 preflight，并冻结 digest', async () => {
    post.mockResolvedValueOnce({
      artifactId: 'art-1',
      state: 'PREFLIGHT_READY',
      preflight: { findings: [] },
      preflightDigest: PREFLIGHT_DIGEST,
    })
    const w = useCustomIngestionWizard()
    w.selectEntry('ingest_excel')
    const result = await w.runPreflight('art-1')

    expect(result?.preflightDigest).toBe(PREFLIGHT_DIGEST)
    expect(post.mock.calls[0][0]).toBe(`${BASE}/artifacts/art-1/preflight`)
    expect(post.mock.calls[0][2]?._silent).toBe(true)
    expect(w.state.value.phase).toBe('preflight')
    expect(w.state.value.preflightDigest).toBe(PREFLIGHT_DIGEST)
  })

  it('PREFLIGHT_FAILED 必须阻断，不得停在 preflight', async () => {
    post.mockResolvedValueOnce({
      artifactId: 'art-1',
      state: 'PREFLIGHT_FAILED',
      preflight: { findings: [{ code: 'PACKAGE.feature_xlsm' }] },
      preflightDigest: PREFLIGHT_DIGEST,
    })
    const w = useCustomIngestionWizard()
    w.selectEntry('ingest_excel')
    await w.runPreflight('art-1')

    expect(w.state.value.phase).toBe('blocked')
    expect(w.state.value.blockers.some((b) => b.code === 'preflight_failed')).toBe(true)
  })
})

describe('authority 阶段', () => {
  it('digest 未冻结时拒绝提交，不发请求', async () => {
    // 🔴 前提：artifact 已存在但 preflight 未跑（否则会先被 !artifactId 拦截，
    // 测不到 digest 判据 —— 首版就是这样漏判的）。
    post.mockResolvedValueOnce(ingested())
    const w = useCustomIngestionWizard()
    await w.ingestFile(new File([new Uint8Array([1])], 'a.xlsx'))
    expect(w.state.value.artifactId).toBe('art-1')
    expect(w.state.value.preflightDigest).toBeNull()

    const result = await w.putUnitAuthority({
      workingPaperId: 'wp-1',
      workbookSha256: 'a'.repeat(64),
      preflightDigest: PREFLIGHT_DIGEST,
      manifest: { regions: [] },
      manifestDigest: MANIFEST_DIGEST,
    })

    expect(result).toBeNull()
    expect(put).not.toHaveBeenCalled()
    expect(w.state.value.blockers[0].code).toBe('preflight_digest_mismatch')
  })

  it('digest 一致时 PUT 并记录 authorityId', async () => {
    post.mockResolvedValueOnce({
      artifactId: 'art-1',
      state: 'PREFLIGHT_READY',
      preflight: {},
      preflightDigest: PREFLIGHT_DIGEST,
    })
    put.mockResolvedValueOnce({
      authorityId: 'auth-1',
      workingPaperId: 'wp-1',
      workbookSha256: 'a'.repeat(64),
      manifestDigest: MANIFEST_DIGEST,
      idempotent: false,
    })
    const w = useCustomIngestionWizard()
    w.selectEntry('ingest_excel')
    await w.runPreflight('art-1')
    const result = await w.putUnitAuthority({
      workingPaperId: 'wp-1',
      workbookSha256: 'a'.repeat(64),
      preflightDigest: PREFLIGHT_DIGEST,
      manifest: { regions: [] },
      manifestDigest: MANIFEST_DIGEST,
    })

    expect(result?.authorityId).toBe('auth-1')
    expect(put.mock.calls[0][0]).toBe(`${BASE}/artifacts/art-1/unit-authority`)
    expect(put.mock.calls[0][2]?._silent).toBe(true)
    expect(w.state.value.authorityId).toBe('auth-1')
    expect(w.state.value.phase).toBe('mapping')
  })
})

describe('finalize 阶段', () => {
  it('finalize 后停在 pending_approval，且不注册 host facts', async () => {
    post.mockResolvedValueOnce({
      artifactId: 'art-1',
      state: 'PREFLIGHT_READY',
      preflight: {},
      preflightDigest: PREFLIGHT_DIGEST,
    })
    put.mockResolvedValueOnce({
      authorityId: 'auth-1',
      workingPaperId: 'wp-1',
      workbookSha256: 'a'.repeat(64),
      manifestDigest: MANIFEST_DIGEST,
      idempotent: false,
    })
    post.mockResolvedValueOnce({
      artifactId: 'art-1',
      phase: 'finalized',
      handoffId: 'handoff-1',
      handoffDigest: 'd'.repeat(64),
      idempotent: false,
      runtimeDiscoverable: false,
    })
    const w = useCustomIngestionWizard()
    w.selectEntry('ingest_excel')
    await w.runPreflight('art-1')
    await w.putUnitAuthority({
      workingPaperId: 'wp-1',
      workbookSha256: 'a'.repeat(64),
      preflightDigest: PREFLIGHT_DIGEST,
      manifest: { regions: [] },
      manifestDigest: MANIFEST_DIGEST,
    })
    const result = await w.finalizeAuthority({
      workingPaperId: 'wp-1',
      authorityId: 'auth-1',
      manifestDigest: MANIFEST_DIGEST,
      idempotencyKey: 'finalize-key-1',
    })

    expect(result?.runtimeDiscoverable).toBe(false)
    expect(w.state.value.phase).toBe('pending_approval')
    expect(w.state.value.handoffId).toBe('handoff-1')
    // finalize 是第三个 POST（ingest 未跑，preflight 是第 1 个）
    const finalizeCall = post.mock.calls.find(([url]) => String(url).endsWith('/finalize'))
    expect(finalizeCall?.[0]).toBe(`${BASE}/artifacts/art-1/finalize`)
    expect(finalizeCall?.[2]?._silent).toBe(true)
    // 🔴 关键不变量：finalize ≠ ACTIVE
    expect(w.state.value.hostFactsRegistered).toBe(false)
    expect(w.state.value.staticPreviewOnly).toBe(true)
  })

  it('没有 authorityId 时 finalize 不发请求', async () => {
    // 🔴 两个坑（首两版都漏判）：
    // ① 只断言 `result === null` 抓不住「守卫被删」：请求照样发出，mock 未设返回值
    //    → 解构 undefined 抛错 → 走 catch 仍返回 null。必须断言「一个请求都没发」。
    // ② 必须先上传拿到 artifactId，否则被前置的 `!id` 拦截，
    //    `!authorityId` 这条判据根本没被执行到（变异存活即此因）。
    post.mockResolvedValueOnce(ingested())
    const w = useCustomIngestionWizard()
    await w.ingestFile(new File([new Uint8Array([1])], 'a.xlsx'))
    expect(w.state.value.artifactId).toBe('art-1')
    expect(w.state.value.authorityId).toBeNull()
    post.mockClear()

    const result = await w.finalizeAuthority({
      workingPaperId: 'wp-1',
      authorityId: 'auth-1',
      manifestDigest: MANIFEST_DIGEST,
      idempotencyKey: 'finalize-key-2',
    })
    expect(result).toBeNull()
    expect(post).not.toHaveBeenCalled()
    expect(w.state.value.phase).not.toBe('pending_approval')
    expect(w.state.value.handoffId).toBeNull()
    // 未确认过单位 → 与「传了过期 authority」同一条判据，同一 blocker 码
    expect(w.state.value.blockers[0].code).toBe('authority_id_mismatch')
  })

  it('authorityId 与已冻结值不一致时拒绝定稿', async () => {
    post.mockResolvedValueOnce({
      artifactId: 'art-1',
      state: 'PREFLIGHT_READY',
      preflight: {},
      preflightDigest: PREFLIGHT_DIGEST,
    })
    put.mockResolvedValueOnce({
      authorityId: 'auth-1',
      workingPaperId: 'wp-1',
      workbookSha256: 'a'.repeat(64),
      manifestDigest: MANIFEST_DIGEST,
      idempotent: false,
    })
    const w = useCustomIngestionWizard()
    w.selectEntry('ingest_excel')
    await w.runPreflight('art-1')
    await w.putUnitAuthority({
      workingPaperId: 'wp-1',
      workbookSha256: 'a'.repeat(64),
      preflightDigest: PREFLIGHT_DIGEST,
      manifest: { regions: [] },
      manifestDigest: MANIFEST_DIGEST,
    })
    expect(w.state.value.authorityId).toBe('auth-1')
    post.mockClear()

    const result = await w.finalizeAuthority({
      workingPaperId: 'wp-1',
      authorityId: 'auth-stale',
      manifestDigest: MANIFEST_DIGEST,
      idempotencyKey: 'finalize-key-3',
    })
    expect(result).toBeNull()
    expect(post).not.toHaveBeenCalled()
    expect(w.state.value.blockers[0].code).toBe('authority_id_mismatch')
    expect(w.state.value.handoffId).toBeNull()
  })
})
