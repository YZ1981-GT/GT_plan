import { afterEach, describe, expect, it, vi } from 'vitest'

import { WorksheetVersionConflictError } from '@/services/consolWorksheetDataApi'
import {
  markManualRcl,
  mergeSavedTbSummaryRows,
  serializeTbSummaryRows,
  useTbSummaryPersistence,
  type TbSummaryPersistContext,
  type TbSummaryPersistRow,
} from '../useTbSummaryPersistence'

interface Deferred<T> {
  promise: Promise<T>
  resolve: (value: T) => void
  reject: (reason: unknown) => void
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const CONTEXT_A: TbSummaryPersistContext = {
  projectId: 'project-a',
  year: 2025,
  sheetKey: 'tb_summary_balance_sheet',
}
const CONTEXT_B: TbSummaryPersistContext = {
  projectId: 'project-b',
  year: 2026,
  sheetKey: 'tb_summary_income_statement',
}

afterEach(() => {
  vi.useRealTimers()
})

describe('TB 汇总行序列化与手工重分类标记', () => {
  it('只序列化持久化字段，并把 undefined 归一为 null', () => {
    const result = serializeTbSummaryRows([{
      row_code: '1',
      row_name: '货币资金',
      rcl_dr: 0,
      extra: '不得落库',
    }])

    expect(result).toEqual([{
      row_code: '1',
      row_name: '货币资金',
      unadjusted: null,
      aje_dr: null,
      aje_cr: null,
      rcl_dr: 0,
      rcl_cr: null,
      formula_detached: false,
      manual_rcl_dr: false,
      manual_rcl_cr: false,
    }])
  })

  it('只标记用户实际提交的重分类格', () => {
    const row: TbSummaryPersistRow = {}
    markManualRcl(row, 'rcl_dr')
    expect(row).toMatchObject({ manual_rcl_dr: true })
    expect(row.manual_rcl_cr).toBeUndefined()

    markManualRcl(row, 'rcl_cr')
    expect(row.manual_rcl_cr).toBe(true)
  })
})

describe('TB 已存影子行合并', () => {
  it('手工标记格强制恢复 null、0 和非零值，未标记格保留审批计算值', () => {
    const current: TbSummaryPersistRow[] = [
      { row_code: '1', unadjusted: 100, rcl_dr: 7, rcl_cr: 8 },
      { row_code: '2', unadjusted: 200, rcl_dr: 9, rcl_cr: 10 },
      { row_code: '3', unadjusted: null, rcl_dr: null, rcl_cr: null },
    ]
    mergeSavedTbSummaryRows(current, [
      { row_code: '1', manual_rcl_dr: true, rcl_dr: null, manual_rcl_cr: true, rcl_cr: 0 },
      { row_code: '2', rcl_dr: 90, rcl_cr: 100 },
      { row_code: '3', rcl_dr: 30, rcl_cr: 40 },
    ])

    expect(current[0]).toMatchObject({ rcl_dr: null, rcl_cr: 0, manual_rcl_dr: true, manual_rcl_cr: true })
    expect(current[1]).toMatchObject({ rcl_dr: 9, rcl_cr: 10 })
    expect(current[2]).toMatchObject({ rcl_dr: 30, rcl_cr: 40 })
  })

  it('断开公式行恢复手工未审数，同时仍按逐格标记覆盖重分类', () => {
    const current: TbSummaryPersistRow[] = [{ row_code: '1', unadjusted: 500, rcl_dr: 5, rcl_cr: 6 }]
    mergeSavedTbSummaryRows(current, [{
      row_code: '1',
      formula_detached: true,
      unadjusted: 0,
      manual_rcl_dr: true,
      rcl_dr: 0,
      manual_rcl_cr: true,
      rcl_cr: null,
    }])

    expect(current[0]).toMatchObject({
      formula_detached: true,
      unadjusted: 0,
      rcl_dr: 0,
      rcl_cr: null,
    })
  })

  it('旧版断开公式行没有逐格标记时，沿用原规则恢复并迁移非空 RCL', () => {
    const current: TbSummaryPersistRow[] = [{ row_code: '1', unadjusted: 500, rcl_dr: 5, rcl_cr: 6 }]
    mergeSavedTbSummaryRows(current, [{
      row_code: '1', formula_detached: true, unadjusted: 400, rcl_dr: 100, rcl_cr: 200,
    }])

    expect(current[0]).toMatchObject({
      formula_detached: true,
      unadjusted: 400,
      rcl_dr: 100,
      rcl_cr: 200,
      manual_rcl_dr: true,
      manual_rcl_cr: true,
    })
  })
})

function setupController(options?: {
  context?: TbSummaryPersistContext | null
  rows?: TbSummaryPersistRow[]
  canSave?: boolean
  load?: ReturnType<typeof vi.fn>
  save?: ReturnType<typeof vi.fn>
}) {
  let context = options?.context === undefined ? CONTEXT_A : options.context
  let rows = options?.rows ?? [{ row_code: '1', rcl_dr: 1 }]
  let canSave = options?.canSave ?? true
  const save = options?.save ?? vi.fn().mockResolvedValue({ ok: true, version: 1 })
  const onError = vi.fn()
  const controller = useTbSummaryPersistence({
    getContext: () => context,
    getRows: () => rows,
    canSave: () => canSave,
    delayMs: 200,
    ...(options?.load ? { load: options.load } : {}),
    save,
    onError,
  })
  return {
    controller,
    load: options?.load,
    save,
    onError,
    setContext: (next: TbSummaryPersistContext | null) => { context = next },
    setRows: (next: TbSummaryPersistRow[]) => { rows = next },
    setCanSave: (next: boolean) => { canSave = next },
  }
}

describe('useTbSummaryPersistence 加载与版本初始化', () => {
  it('加载成功后按逐格手工标记合并，并以响应版本 prime CAS', async () => {
    const rows: TbSummaryPersistRow[] = [{ row_code: '1', rcl_dr: 9 }]
    const load = vi.fn().mockResolvedValue({
      status: 'loaded',
      data: { rows: [{ row_code: '1', rcl_dr: 0, manual_rcl_dr: true }] },
      versions: { [CONTEXT_A.sheetKey]: 12 },
    })
    const state = setupController({ rows, load })

    expect(await state.controller.hydrate(CONTEXT_A)).toBe(true)
    expect(load).toHaveBeenCalledWith(CONTEXT_A.projectId, CONTEXT_A.year, CONTEXT_A.sheetKey)
    expect(rows[0]).toMatchObject({ rcl_dr: 0, manual_rcl_dr: true })
    expect(state.controller.versionOf(CONTEXT_A)).toBe(12)
  })

  it('加载失败或加载期间切换上下文时不合并、不 prime 版本', async () => {
    const delayed = deferred<any>()
    const rows: TbSummaryPersistRow[] = [{ row_code: '1', rcl_dr: 9 }]
    const stale = setupController({ rows, load: vi.fn(() => delayed.promise) })
    const hydrating = stale.controller.hydrate(CONTEXT_A)
    stale.setContext(CONTEXT_B)
    delayed.resolve({
      status: 'loaded', data: { rows: [{ row_code: '1', rcl_dr: 0, manual_rcl_dr: true }] },
      versions: { [CONTEXT_A.sheetKey]: 4 },
    })
    expect(await hydrating).toBe(false)
    expect(rows[0].rcl_dr).toBe(9)
    expect(stale.controller.versionOf(CONTEXT_A)).toBeUndefined()

    const failed = setupController({ load: vi.fn().mockResolvedValue({ status: 'error', data: {}, versions: {} }) })
    expect(await failed.controller.hydrate(CONTEXT_A)).toBe(false)
    expect(failed.controller.versionOf(CONTEXT_A)).toBeUndefined()
  })

  it('只允许当前已加载行集对应的上下文保存，缓存过的旧版本不能与别的行集重组', () => {
    const state = setupController()
    state.controller.prime(CONTEXT_A, 2)
    state.setContext(CONTEXT_B)
    expect(state.controller.queue()).toBe(false)
    expect(state.save).not.toHaveBeenCalled()

    state.controller.prime(CONTEXT_B, 8)
    state.setContext(CONTEXT_A)
    expect(state.controller.queue()).toBe(false)
    expect(state.save).not.toHaveBeenCalled()
  })
})

describe('useTbSummaryPersistence 自动保存队列', () => {
  it('200ms 内多次提交只保存最后一份冻结快照', async () => {
    vi.useFakeTimers()
    const state = setupController()
    state.controller.prime(CONTEXT_A, 4)

    expect(state.controller.queue()).toBe(true)
    await vi.advanceTimersByTimeAsync(100)
    state.setRows([{ row_code: '1', rcl_dr: 2, manual_rcl_dr: true }])
    expect(state.controller.queue()).toBe(true)
    await vi.advanceTimersByTimeAsync(199)
    expect(state.save).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)

    expect(state.save).toHaveBeenCalledTimes(1)
    expect(state.save).toHaveBeenCalledWith(
      CONTEXT_A.projectId,
      CONTEXT_A.year,
      CONTEXT_A.sheetKey,
      { rows: [expect.objectContaining({ rcl_dr: 2, manual_rcl_dr: true })] },
      4,
    )
    expect(state.controller.dirty.value).toBe(false)
    expect(state.controller.versionOf(CONTEXT_A)).toBe(1)
  })

  it('飞行中继续编辑进入第二批，并使用第一批响应的新版本', async () => {
    vi.useFakeTimers()
    const first = deferred<{ ok: boolean; version: number }>()
    const second = deferred<{ ok: boolean; version: number }>()
    const save = vi.fn()
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise)
    const state = setupController({ save })
    state.controller.prime(CONTEXT_A, 7)

    state.controller.queue()
    await vi.advanceTimersByTimeAsync(200)
    expect(save).toHaveBeenCalledTimes(1)
    expect(save.mock.calls[0][4]).toBe(7)

    state.setRows([{ row_code: '1', rcl_dr: 22, manual_rcl_dr: true }])
    state.controller.queue()
    await vi.advanceTimersByTimeAsync(200)
    expect(save).toHaveBeenCalledTimes(1)

    first.resolve({ ok: true, version: 8 })
    await Promise.resolve()
    await Promise.resolve()
    expect(save).toHaveBeenCalledTimes(2)
    expect(save.mock.calls[1][3]).toEqual({ rows: [expect.objectContaining({ rcl_dr: 22 })] })
    expect(save.mock.calls[1][4]).toBe(8)

    second.resolve({ ok: true, version: 9 })
    await vi.runAllTimersAsync()
    expect(state.controller.versionOf(CONTEXT_A)).toBe(9)
    expect(state.controller.dirty.value).toBe(false)
  })

  it.each([
    [new WorksheetVersionConflictError(3, 4), '自动保存冲突'],
    [{ response: { status: 403 } }, '没有编辑权限'],
    [{ response: { status: 423 } }, '项目已归档'],
    [new Error('网络断开'), '请点击保存重试'],
  ])('保存失败会阻断自动重试并保留 dirty：%s', async (error, expectedMessage) => {
    vi.useFakeTimers()
    const state = setupController({ save: vi.fn().mockRejectedValue(error) })
    state.controller.prime(CONTEXT_A, 3)
    state.controller.queue()
    await vi.advanceTimersByTimeAsync(200)

    expect(state.controller.dirty.value).toBe(true)
    expect(state.controller.blocked.value).toBe(true)
    expect(state.controller.errorMessage.value).toContain(expectedMessage)
    expect(state.onError).toHaveBeenCalledTimes(1)

    state.controller.queue()
    await vi.advanceTimersByTimeAsync(1000)
    expect(state.save).toHaveBeenCalledTimes(1)
  })

  it('显式 flush 会提交调用瞬间最新快照，并可用原 CAS 版本重试', async () => {
    const save = vi.fn()
      .mockRejectedValueOnce(new Error('网络断开'))
      .mockResolvedValueOnce({ ok: true, version: 6 })
    const state = setupController({ save })
    state.controller.prime(CONTEXT_A, 5)

    state.controller.queue()
    expect(await state.controller.flush()).toBe(false)
    expect(state.controller.blocked.value).toBe(true)

    state.setRows([{ row_code: '1', rcl_cr: 45, manual_rcl_cr: true }])
    expect(await state.controller.flush(true)).toBe(true)
    expect(save).toHaveBeenCalledTimes(2)
    expect(save.mock.calls[1][3]).toEqual({ rows: [expect.objectContaining({ rcl_cr: 45 })] })
    expect(save.mock.calls[1][4]).toBe(5)
    expect(state.controller.versionOf(CONTEXT_A)).toBe(6)
  })

  it('用户明确放弃冲突修改后可清除 blocked/dirty，并重新 hydrate 新版本', async () => {
    const load = vi.fn().mockResolvedValue({ status: 'empty', data: {}, versions: { [CONTEXT_A.sheetKey]: 9 } })
    const state = setupController({
      load,
      save: vi.fn().mockRejectedValue(new WorksheetVersionConflictError(3, 9)),
    })
    state.controller.prime(CONTEXT_A, 3)
    state.controller.queue()
    expect(await state.controller.flush()).toBe(false)
    expect(state.controller.blocked.value).toBe(true)

    state.controller.discard()
    expect(state.controller.dirty.value).toBe(false)
    expect(state.controller.blocked.value).toBe(false)
    expect(state.controller.errorMessage.value).toBe('')
    expect(await state.controller.hydrate(CONTEXT_A)).toBe(true)
    expect(state.controller.versionOf(CONTEXT_A)).toBe(9)
  })

  it('版本未知、无权限或上下文为空时不发 PUT', async () => {
    const state = setupController()
    expect(state.controller.queue()).toBe(false)
    expect(state.controller.dirty.value).toBe(true)
    expect(state.controller.errorMessage.value).toContain('刷新试算平衡表')
    expect(await state.controller.flush(true)).toBe(false)
    expect(state.save).not.toHaveBeenCalled()

    state.controller.prime(CONTEXT_A, 0)
    state.setCanSave(false)
    expect(state.controller.queue()).toBe(false)
    expect(await state.controller.flush(true)).toBe(false)
    expect(state.save).not.toHaveBeenCalled()

    state.setCanSave(true)
    state.setContext(null)
    expect(state.controller.queue()).toBe(false)
    expect(state.save).not.toHaveBeenCalled()
  })

  it('切换上下文时旧批次按旧 key 完成，新批次保留自己的上下文与 CAS', async () => {
    const first = deferred<{ ok: boolean; version: number }>()
    const second = deferred<{ ok: boolean; version: number }>()
    const save = vi.fn()
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise)
    const state = setupController({ save })
    state.controller.prime(CONTEXT_A, 2)
    state.controller.queue()
    const draining = state.controller.flush()

    state.setContext(CONTEXT_B)
    state.controller.prime(CONTEXT_B, 10)
    state.setRows([{ row_code: '2', rcl_dr: 99, manual_rcl_dr: true }])
    state.controller.queue()

    first.resolve({ ok: true, version: 3 })
    await Promise.resolve()
    await Promise.resolve()
    expect(save).toHaveBeenCalledTimes(2)
    expect(save.mock.calls[1].slice(0, 3)).toEqual([
      CONTEXT_B.projectId, CONTEXT_B.year, CONTEXT_B.sheetKey,
    ])
    expect(save.mock.calls[1][4]).toBe(10)
    expect(state.controller.versionOf(CONTEXT_A)).toBe(3)
    expect(state.controller.versionOf(CONTEXT_B)).toBe(10)
    expect(state.controller.dirty.value).toBe(true)

    second.resolve({ ok: true, version: 11 })
    await draining
    expect(state.controller.versionOf(CONTEXT_B)).toBe(11)
    expect(state.controller.dirty.value).toBe(false)
  })

  it('同一 key 重载会提升 generation，使重载前响应失效', async () => {
    const first = deferred<{ ok: boolean; version: number }>()
    const save = vi.fn().mockImplementationOnce(() => first.promise)
    const state = setupController({ save })
    state.controller.prime(CONTEXT_A, 2)
    state.controller.queue()
    const draining = state.controller.flush()

    state.controller.prime(CONTEXT_A, 20)
    first.resolve({ ok: true, version: 3 })
    await draining

    expect(state.controller.versionOf(CONTEXT_A)).toBe(20)
    expect(state.controller.savedRevision.value).toBe(0)
  })

  it('dispose 清除定时任务，飞行中响应也不再更新版本', async () => {
    vi.useFakeTimers()
    const first = deferred<{ ok: boolean; version: number }>()
    const state = setupController({ save: vi.fn().mockImplementation(() => first.promise) })
    state.controller.prime(CONTEXT_A, 1)
    state.controller.queue()
    state.controller.dispose()
    await vi.advanceTimersByTimeAsync(500)
    expect(state.save).not.toHaveBeenCalled()

    const second = deferred<{ ok: boolean; version: number }>()
    const inFlight = setupController({ save: vi.fn().mockImplementation(() => second.promise) })
    inFlight.controller.prime(CONTEXT_A, 4)
    inFlight.controller.queue()
    const draining = inFlight.controller.flush()
    expect(inFlight.save).toHaveBeenCalledTimes(1)
    inFlight.controller.dispose()
    second.resolve({ ok: true, version: 5 })
    await draining
    expect(inFlight.controller.versionOf(CONTEXT_A)).toBe(4)
  })
})
