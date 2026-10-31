/**
 * useVoucherEvidenceIndex — 凭证键 → 各可见底稿已取得的凭证证据（spec attachment-voucher-evidence-binding 需求 2.1、3.4，变异 #13）
 *
 * - 同一轮渲染里各行登记的键合成一次请求（请求体、静默、不参与 GET 去重），超过 500 个分段顺序发；
 * - 查过的键（含查无证据的）不再查；失败的键不进缓存、下次再查；年度未知不查；
 * - 竞态：晚到的旧响应不覆盖之后为同一个键发起的查询结果。
 * 并发判据挂起响应后再数调用次数（mock 立即返回时「只调 1 次」靠时序成立）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

const mockPost = vi.fn()
vi.mock('@/utils/http', () => ({ default: { post: (...a: any[]) => mockPost(...a) } }))

import {
  refreshVoucherEvidence,
  requestVoucherEvidence,
  resetVoucherEvidenceIndexForTest,
  useVoucherEvidenceIndex,
  voucherEvidenceOf,
} from '../useVoucherEvidenceIndex'

const PID = 'p1'
const vk = (no: string) => JSON.stringify(['2025', 'default', '2025-01-07', '记', no])
const entry = (wp: string, files: string[]) => ({
  working_paper_id: `wp-${wp}`, wp_code: wp, wp_name: wp,
  attachments: files.map((f) => ({ id: `att-${f}`, file_name: f, file_type: 'pdf', ocr_status: null, evidence_type: 'voucher' })),
})

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

const flush = async () => {
  for (let i = 0; i < 6; i++) await Promise.resolve()
  await nextTick()
}

beforeEach(() => {
  resetVoucherEvidenceIndexForTest()
  mockPost.mockReset()
})

describe('合批与分段', () => {
  it('同一轮登记的多个键只发一次请求（挂起响应再数）', async () => {
    const pending = deferred<unknown>()
    mockPost.mockReturnValueOnce(pending.promise)
    for (const no of ['0001', '0002', '0003']) requestVoucherEvidence(PID, 2025, vk(no))
    requestVoucherEvidence(PID, 2025, vk('0001'))
    expect(mockPost).not.toHaveBeenCalled() // 微任务里才发
    await flush()
    expect(mockPost).toHaveBeenCalledTimes(1)
    const [url, body, opts] = mockPost.mock.calls[0]
    expect(url).toBe(`/api/projects/${PID}/ledger/voucher-evidence/query`)
    expect(body).toEqual({ year: 2025, keys: [vk('0001'), vk('0002'), vk('0003')] })
    expect(opts).toMatchObject({ _silent: true, _dedupe: false })
    // 在查的键再登记不另发
    requestVoucherEvidence(PID, 2025, vk('0002'))
    await flush()
    expect(mockPost).toHaveBeenCalledTimes(1)
    pending.resolve({ data: { evidence: { [vk('0001')]: [entry('D2-4', ['a.pdf'])] } } })
    await flush()
    expect(voucherEvidenceOf(PID, 2025, vk('0001')).map((e) => e.wp_code)).toEqual(['D2-4'])
    expect(voucherEvidenceOf(PID, 2025, vk('0002'))).toEqual([])
  })

  it('超过 500 个键分段顺序发；查过的（含查无证据的）不再查', async () => {
    mockPost.mockResolvedValue({ data: { evidence: {} } })
    const keys = Array.from({ length: 1200 }, (_, i) => vk(String(i).padStart(4, '0')))
    await refreshVoucherEvidence(PID, 2025, keys)
    expect(mockPost.mock.calls.map((c) => (c[1] as { keys: string[] }).keys.length)).toEqual([500, 500, 200])
    for (const k of keys.slice(0, 10)) requestVoucherEvidence(PID, 2025, k)
    await flush()
    expect(mockPost).toHaveBeenCalledTimes(3)
  })
})

describe('缓存与失败', () => {
  it('失败的键不进缓存，下次再查；年度未知不查', async () => {
    mockPost.mockRejectedValueOnce(new Error('网络'))
    requestVoucherEvidence(PID, 2025, vk('0001'))
    await flush()
    expect(voucherEvidenceOf(PID, null, vk('0001'))).toEqual([])
    mockPost.mockResolvedValueOnce({ data: { evidence: { [vk('0001')]: [entry('F1', ['b.pdf'])] } } })
    expect(voucherEvidenceOf(PID, 2025, vk('0001'))).toEqual([]) // 登记重查
    await flush()
    expect(mockPost).toHaveBeenCalledTimes(2)
    expect(voucherEvidenceOf(PID, 2025, vk('0001')).map((e) => e.wp_code)).toEqual(['F1'])
    requestVoucherEvidence(PID, null, vk('0009'))
    await refreshVoucherEvidence(PID, undefined, [vk('0009')])
    await flush()
    expect(mockPost).toHaveBeenCalledTimes(2)
  })

  it('晚到的旧响应不覆盖之后为同一个键发起的查询结果', async () => {
    const slow = deferred<unknown>()
    mockPost.mockReturnValueOnce(slow.promise)
    requestVoucherEvidence(PID, 2025, vk('0001'))
    await flush()
    mockPost.mockResolvedValueOnce({ data: { evidence: { [vk('0001')]: [entry('D2-4', ['new.pdf'])] } } })
    await refreshVoucherEvidence(PID, 2025, [vk('0001')])
    slow.resolve({ data: { evidence: {} } })
    await flush()
    expect(voucherEvidenceOf(PID, 2025, vk('0001'))[0].attachments.map((a) => a.file_name)).toEqual(['new.pdf'])
  })
})

describe('useVoucherEvidenceIndex', () => {
  it('按（项目, 年度, 凭证键）响应式取证据；键变化后查新键', async () => {
    mockPost.mockImplementation(async (_u: string, body: { keys: string[] }) => ({
      data: { evidence: Object.fromEntries(body.keys.map((k) => [k, [entry('G4', [`${k.slice(-6, -2)}.pdf`])]])) },
    }))
    const key = ref<string | null>(vk('0001'))
    const scope = effectScope()
    const index = scope.run(() => useVoucherEvidenceIndex(() => PID, () => 2025, () => key.value))!
    await flush()
    expect(index.entries.value[0].attachments.map((a) => a.file_name)).toEqual(['0001.pdf'])
    key.value = vk('0002')
    await flush()
    expect(index.entries.value[0].attachments.map((a) => a.file_name)).toEqual(['0002.pdf'])
    key.value = null
    await flush()
    expect(index.entries.value).toEqual([])
    expect(mockPost).toHaveBeenCalledTimes(2)
    scope.stop()
  })
})
