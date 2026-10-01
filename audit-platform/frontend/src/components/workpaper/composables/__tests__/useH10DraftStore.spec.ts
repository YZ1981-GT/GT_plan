/**
 * useH10FormData 草稿存储归口的**行为级**判据（spec h2-h6-h10 Task 5 ②③）。
 *
 * 🔴 为什么行为级测试不可省：后端 `test_h_lane3_draft_store_hardening.py` 是**文本/位置**
 * 判据（门在不在、在不在 setItem 之前），它抓得住「门被删/被挪后」，但抓不住
 * 「门在、可 `draftsSuspended` 从来没被置真」这种接线断裂。这里直接跑真逻辑：
 * 让 PUT 必失败，再分别在挂起 / 未挂起两种状态下断言草稿有没有落盘。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const putMock = vi.fn()
const getMock = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...a: unknown[]) => getMock(...a),
    put: (...a: unknown[]) => putMock(...a),
  },
}))
vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn() },
}))

const WP = 'wp-h10-test'
const PREFIX = `h10-draft:${WP}:`

function countDrafts(): number {
  let n = 0
  for (let i = 0; i < localStorage.length; i++) {
    if (localStorage.key(i)?.startsWith(PREFIX)) n += 1
  }
  return n
}

async function makeComposable() {
  const { useH10FormData } = await import('../useH10FormData')
  return useH10FormData({ wpId: ref(WP), projectId: ref('proj-1') })
}

describe('useH10FormData 草稿存储归口', () => {
  beforeEach(() => {
    localStorage.clear()
    putMock.mockReset()
    getMock.mockReset()
    getMock.mockResolvedValue([])
  })

  it('② 未挂起时 PUT 全败 → 落本地草稿，且计数可见', async () => {
    putMock.mockRejectedValue(new Error('network down'))
    const fd = await makeComposable()
    expect(fd.draftsSuspended.value).toBe(false)

    await fd.saveImmediate('H10-detail-rows', { remark: '[]' }, 1)

    expect(countDrafts()).toBe(1)
    expect(fd.pendingDraftCount.value).toBe(1)
  })

  it('② adapter 回写窗口内 PUT 全败 → **不落草稿**（避免下次回灌盖回旧值）', async () => {
    putMock.mockRejectedValue(new Error('network down'))
    const fd = await makeComposable()
    fd.setDraftsSuspended(true)

    await fd.saveImmediate('H10-detail-rows', { remark: '[]' }, 1)

    expect(countDrafts()).toBe(0)
    expect(fd.pendingDraftCount.value).toBe(0)
  })

  it('② 窗口关闭后恢复落草稿 —— 门是临时的，不是永久关掉这条路', async () => {
    putMock.mockRejectedValue(new Error('network down'))
    const fd = await makeComposable()
    fd.setDraftsSuspended(true)
    await fd.saveImmediate('H10-adj-rows', { remark: '[]' }, 1)
    expect(countDrafts()).toBe(0)

    fd.setDraftsSuspended(false)
    await fd.saveImmediate('H10-adj-rows', { remark: '[]' }, 1)
    expect(countDrafts()).toBe(1)
  })

  it('③ PUT 成功后草稿被删且计数归零', async () => {
    putMock.mockRejectedValue(new Error('network down'))
    const fd = await makeComposable()
    await fd.saveImmediate('H10-check-rows', { remark: '[]' }, 1)
    expect(fd.pendingDraftCount.value).toBe(1)

    putMock.mockReset()
    putMock.mockResolvedValue({})
    await fd.saveImmediate('H10-check-rows', { remark: '[]' }, 1)

    expect(countDrafts()).toBe(0)
    expect(fd.pendingDraftCount.value).toBe(0)
  })

  it('③ 计数是现算的：别处塞进来的草稿也数得到', async () => {
    const fd = await makeComposable()
    localStorage.setItem(`${PREFIX}H10-foreign`, JSON.stringify({ item_id: 'H10-foreign' }))
    localStorage.setItem('unrelated-key', 'x')

    fd.refreshPendingDraftCount()

    expect(fd.pendingDraftCount.value).toBe(1)
  })
})
