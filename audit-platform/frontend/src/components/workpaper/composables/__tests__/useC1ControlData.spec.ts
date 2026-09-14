/**
 * useC1ControlData 单元测试 — C1 企业层面控制测试数据加载/保存
 *
 * Spec: .kiro/specs/c1-entity-level-control/  Task 3.1
 * Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, effectScope, type EffectScope } from 'vue'
import { flushPromises } from '@vue/test-utils'

const mockGet = vi.fn()
const mockPut = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn() },
}))

import { useC1ControlData } from '../useC1ControlData'

/** 在 effectScope 内运行 composable，返回句柄 + scope（可 stop 触发 onScopeDispose） */
function setup(wpId = 'wp-1', opts: any = {}) {
  let handle!: ReturnType<typeof useC1ControlData>
  const scope: EffectScope = effectScope()
  scope.run(() => {
    handle = useC1ControlData(ref(wpId), opts)
  })
  return { handle, scope }
}

describe('useC1ControlData — 加载', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPut.mockReset()
    mockPut.mockResolvedValue([])
  })

  it('loadAll 仅保留 C1- 前缀数据（Req 7.1/7.4）', async () => {
    mockGet.mockResolvedValue([
      { item_id: 'C1-ce-1-applicable', conclusion: 'Y', remark: null, wp_ref: null },
      { item_id: 'C1-ce-conclusion', conclusion: '有效', remark: null, wp_ref: null },
      { item_id: 'C2-1-applicable', conclusion: 'Y', remark: null, wp_ref: null }, // 非 C1-
      { item_id: 'TOC-S01', conclusion: 'Y', remark: null, wp_ref: null },
    ])
    const { handle } = setup()
    await handle.loadAll()

    expect(handle.responses.value.size).toBe(2)
    expect(handle.getConclusion('C1-ce-1-applicable')).toBe('Y')
    expect(handle.getConclusion('C1-ce-conclusion')).toBe('有效')
    expect(handle.responses.value.has('C2-1-applicable')).toBe(false)
  })

  it('loadAll 兼容 {data:[...]} 包裹结构', async () => {
    mockGet.mockResolvedValue({ data: [
      { item_id: 'C1-fr-1-result', conclusion: null, remark: '已测试', wp_ref: null },
    ] })
    const { handle } = setup()
    await handle.loadAll()
    expect(handle.getRemark('C1-fr-1-result')).toBe('已测试')
  })

  it('loadAll 失败时保留空 map 并置 error（Req 7.5）', async () => {
    mockGet.mockRejectedValue(new Error('boom'))
    const { handle } = setup()
    await handle.loadAll()
    expect(handle.responses.value.size).toBe(0)
    expect(handle.error.value).toBe('boom')
  })
})

describe('useC1ControlData — 即时保存（适用性/测试方法/结论，Req 7.3）', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPut.mockReset()
    mockPut.mockResolvedValue([])
  })

  it('setApplicable 立即 PUT，conclusion=Y/N + 理由入 remark', async () => {
    const { handle } = setup()
    handle.setApplicable('C1-bu-section-applicable', false, '非集团审计')
    await flushPromises()

    expect(mockPut).toHaveBeenCalledTimes(1)
    const [, body] = mockPut.mock.calls[0]
    expect(body.items).toEqual([
      { item_id: 'C1-bu-section-applicable', conclusion: 'N', remark: '非集团审计', wp_ref: null },
    ])
    expect(handle.isApplicable('C1-bu-section-applicable')).toBe(false)
  })

  it('setApplicable 不适用无理由 → 拒绝保存（返回 false，Req 3.2）', async () => {
    const { handle } = setup()
    const ok1 = handle.setApplicable('C1-ce-1-applicable', false)
    const ok2 = handle.setApplicable('C1-ce-1-applicable', false, '   ')
    await flushPromises()
    expect(ok1).toBe(false)
    expect(ok2).toBe(false)
    expect(mockPut).not.toHaveBeenCalled()
    // 有理由则保存成功
    const ok3 = handle.setApplicable('C1-ce-1-applicable', false, '本项目非集团审计')
    await flushPromises()
    expect(ok3).toBe(true)
    expect(mockPut).toHaveBeenCalledTimes(1)
  })

  it('setApplicable 标记适用（true）无需理由即可保存', async () => {
    const { handle } = setup()
    const ok = handle.setApplicable('C1-ce-1-applicable', true)
    await flushPromises()
    expect(ok).toBe(true)
    expect(mockPut.mock.calls[0][1].items[0]).toMatchObject({
      item_id: 'C1-ce-1-applicable',
      conclusion: 'Y',
      remark: null,
    })
  })

  it('setConclusion 立即 PUT enum 结论', async () => {
    const { handle } = setup()
    handle.setConclusion('C1-overall-conclusion', '部分有效')
    await flushPromises()
    expect(mockPut).toHaveBeenCalledTimes(1)
    expect(mockPut.mock.calls[0][1].items[0]).toMatchObject({
      item_id: 'C1-overall-conclusion',
      conclusion: '部分有效',
    })
  })

  it('传入 projectId 时写入 body.project_id', async () => {
    const { handle } = setup('wp-9', { projectId: ref('proj-42') })
    handle.setConclusion('C1-ce-conclusion', '有效')
    await flushPromises()
    expect(mockPut.mock.calls[0][1].project_id).toBe('proj-42')
  })
})

describe('useC1ControlData — debounce 文本保存（Req 7.2）', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockReset()
    mockPut.mockReset()
    mockPut.mockResolvedValue([])
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('setText 2s 内不保存，2s 后保存一次', async () => {
    const { handle } = setup()
    handle.setText('C1-fr-1-result', '测试结果说明')

    await vi.advanceTimersByTimeAsync(1900)
    expect(mockPut).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(200)
    expect(mockPut).toHaveBeenCalledTimes(1)
    expect(mockPut.mock.calls[0][1].items[0]).toMatchObject({
      item_id: 'C1-fr-1-result',
      remark: '测试结果说明',
    })
  })

  it('连续输入只在最后一次停顿后保存一次（debounce 合并）', async () => {
    const { handle } = setup()
    handle.setText('C1-fr-1-result', 'a')
    await vi.advanceTimersByTimeAsync(1000)
    handle.setText('C1-fr-1-result', 'ab')
    await vi.advanceTimersByTimeAsync(1000)
    handle.setText('C1-fr-1-result', 'abc')
    expect(mockPut).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(2000)
    expect(mockPut).toHaveBeenCalledTimes(1)
    expect(mockPut.mock.calls[0][1].items[0].remark).toBe('abc')
  })

  it('即时保存会顺带 flush 尚未到期的 debounce 文本（不丢失）', async () => {
    const { handle } = setup()
    handle.setText('C1-fr-1-result', '未到期文本')
    await vi.advanceTimersByTimeAsync(500)
    // 立即保存另一字段 → 应把 pending 文本一并 flush
    handle.setConclusion('C1-fr-conclusion', '有效')
    await vi.advanceTimersByTimeAsync(0)

    expect(mockPut).toHaveBeenCalledTimes(1)
    const savedIds = mockPut.mock.calls[0][1].items.map((i: any) => i.item_id)
    expect(savedIds).toContain('C1-fr-1-result')
    expect(savedIds).toContain('C1-fr-conclusion')
  })
})

describe('useC1ControlData — readonly / 失败保留 / flush', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPut.mockReset()
    mockPut.mockResolvedValue([])
  })

  it('readonly=true 时不发起任何保存（Req 8.1）', async () => {
    const { handle } = setup('wp-1', { readonly: ref(true) })
    handle.setConclusion('C1-ce-conclusion', '有效')
    handle.setText('C1-fr-1-result', 'x')
    handle.flushPendingSave()
    await flushPromises()
    expect(mockPut).not.toHaveBeenCalled()
  })

  it('保存失败时保留本地编辑，下次 flush 重试（Req 7.5）', async () => {
    mockPut.mockRejectedValueOnce(new Error('net'))
    const { handle } = setup()
    handle.setConclusion('C1-ce-conclusion', '有效')
    await flushPromises()
    expect(mockPut).toHaveBeenCalledTimes(1)
    // 本地值保留
    expect(handle.getConclusion('C1-ce-conclusion')).toBe('有效')

    // 下次 flush 重试成功
    mockPut.mockResolvedValueOnce([])
    handle.flushPendingSave()
    await flushPromises()
    expect(mockPut).toHaveBeenCalledTimes(2)
  })

  it('scope 停止（组件卸载）时 flush 未保存的 debounce 文本', async () => {
    vi.useFakeTimers()
    const { handle, scope } = setup()
    handle.setText('C1-fr-1-result', '待 flush')
    // 未到 2s 就卸载
    scope.stop()
    vi.useRealTimers()
    await flushPromises()
    expect(mockPut).toHaveBeenCalledTimes(1)
    expect(mockPut.mock.calls[0][1].items[0].remark).toBe('待 flush')
  })
})
