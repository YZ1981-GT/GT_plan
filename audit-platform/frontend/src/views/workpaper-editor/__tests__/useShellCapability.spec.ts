/**
 * 编辑器壳的能力快照（从 WorkpaperEditor 抽出；spec procedure-chain-hardening-and-java-contracts R10）：
 * 底稿打不开（403 / 404）时只给拒绝快照、不叠加「能力快照加载失败，请稍后重试」；其余失败照旧提示；晚到的旧回执丢弃。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'

const fetchSnap = vi.hoisted(() => vi.fn())
vi.mock('@/shell/formula/fetchCapabilitySnapshot', () => ({ fetchWorkpaperCapabilitySnapshot: fetchSnap }))

import { denyCapabilitySnapshot, useShellCapability } from '../useShellCapability'

const tick = () => new Promise((r) => setTimeout(r, 0))
const ctx = () => ({
  wpId: ref('w1'),
  projectId: ref('p1'),
  activeSheetContext: ref<{ sheetUid: string | null; ownerEpoch: number; wholeWorkbook: boolean }>({
    sheetUid: null, ownerEpoch: 1, wholeWorkbook: false,
  }),
})

beforeEach(() => { fetchSnap.mockReset() })

describe('useShellCapability', () => {
  it('取到快照 ⇒ 用它、清错误', async () => {
    const snap = { ...denyCapabilitySnapshot(1), formulaView: { allowed: true, reasonCode: null, owner: null, nextAction: null, zhMessage: null } }
    fetchSnap.mockResolvedValue(snap)
    const c = useShellCapability(ctx())
    await tick()
    expect(fetchSnap).toHaveBeenCalledWith({ wpId: 'w1', projectId: 'p1', sheetUid: null, ownerEpoch: 1 })
    expect(c.shellCapabilitySnapshot.value.formulaView.allowed).toBe(true)
    expect(c.shellError.value).toBeNull()
  })

  it.each([403, 404])('底稿打不开（%s）⇒ 拒绝快照、不叠加错误条', async (status) => {
    fetchSnap.mockRejectedValue({ response: { status } })
    const c = useShellCapability(ctx())
    await tick()
    expect(c.shellError.value).toBeNull()
    expect(c.shellCapabilitySnapshot.value.formulaView).toMatchObject({ allowed: false, reasonCode: 'workpaper_unavailable' })
  })

  it('其余失败（500 / 网络）⇒ 照旧给结构化错误', async () => {
    fetchSnap.mockRejectedValue({ response: { status: 500 } })
    const c = useShellCapability(ctx())
    await tick()
    expect(c.shellError.value).toMatchObject({ reasonCode: 'snapshot_fetch_failed', zhMessage: '能力快照加载失败，请稍后重试。' })
    expect(c.shellCapabilitySnapshot.value.formulaView.allowed).toBe(false)
  })

  it('换了底稿后旧回执晚到 ⇒ 丢弃', async () => {
    let resolveOld: (v: unknown) => void = () => undefined
    const fresh = { ...denyCapabilitySnapshot(1), subjectDigest: 'w2' }
    fetchSnap.mockImplementationOnce(() => new Promise((r) => { resolveOld = r })).mockResolvedValueOnce(fresh)
    const c0 = ctx()
    const c = useShellCapability(c0)
    c0.wpId.value = 'w2'
    await nextTick()
    await tick()
    resolveOld({ ...denyCapabilitySnapshot(1), subjectDigest: 'w1' })
    await tick()
    expect(c.shellCapabilitySnapshot.value.subjectDigest).toBe('w2')
  })
})
