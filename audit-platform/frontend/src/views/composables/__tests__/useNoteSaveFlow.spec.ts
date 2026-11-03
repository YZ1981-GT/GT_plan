/** useNoteSaveFlow：附注一次保存的状态与收尾（spec platform-performance-user-experience-closure 任务 30）。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useNoteSaveFlow } from '../useNoteSaveFlow'

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

function setup(noteId: { value: string | undefined } = { value: 'n1' }) {
  const save = vi.fn<(opts: { keepEditing: boolean }) => Promise<boolean>>()
  const onSaved = vi.fn<(auto: boolean) => void>()
  const flow = useNoteSaveFlow({ currentNoteId: () => noteId.value, save, onSaved })
  return { ...flow, save, onSaved, noteId }
}

describe('useNoteSaveFlow', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('本章保存成功：saving → saved → 3 秒后 idle；收尾带上是否定时保存', async () => {
    const s = setup()
    const pending = deferred<boolean>()
    s.save.mockReturnValueOnce(pending.promise)

    const run = s.saveCurrentNote({ auto: true })
    expect(s.saveStatus.value).toBe('saving')
    expect(s.save).toHaveBeenCalledWith({ keepEditing: true })
    pending.resolve(true)

    await expect(run).resolves.toBe(true)
    expect(s.onSaved).toHaveBeenCalledWith(true)
    expect(s.saveStatus.value).toBe('saved')
    vi.advanceTimersByTime(3000)
    expect(s.saveStatus.value).toBe('idle')
  })

  it('手工保存：keepEditing=false，收尾收到 auto=false', async () => {
    const s = setup()
    s.save.mockResolvedValueOnce(true)
    await expect(s.saveCurrentNote({ auto: false })).resolves.toBe(true)
    expect(s.save).toHaveBeenCalledWith({ keepEditing: false })
    expect(s.onSaved).toHaveBeenCalledWith(false)
  })

  it('save 返回 false：标记失败、不收尾、返回 false（调用方保留 dirty）', async () => {
    const s = setup()
    s.save.mockResolvedValueOnce(false)
    await expect(s.saveCurrentNote({ auto: true })).resolves.toBe(false)
    expect(s.saveStatus.value).toBe('error')
    expect(s.onSaved).not.toHaveBeenCalled()
  })

  it('save 抛错（网络失败 / 版本冲突）：标记失败并返回 false，不向外抛', async () => {
    const s = setup()
    s.save.mockRejectedValueOnce(new Error('network'))
    await expect(s.saveCurrentNote({ auto: false })).resolves.toBe(false)
    expect(s.saveStatus.value).toBe('error')
    expect(s.onSaved).not.toHaveBeenCalled()
  })

  it('保存期间切了章：旧章算保存成功，但不清新章撤销记录、不跳章，状态回 idle', async () => {
    const s = setup()
    const pending = deferred<boolean>()
    s.save.mockReturnValueOnce(pending.promise)
    const run = s.saveCurrentNote({ auto: false })
    s.noteId.value = 'n2'
    pending.resolve(true)

    await expect(run).resolves.toBe(true)
    expect(s.onSaved).not.toHaveBeenCalled()
    expect(s.saveStatus.value).toBe('idle')
  })

  it('收尾抛错：按失败处理（与原内联实现同口径）', async () => {
    const s = setup()
    s.save.mockResolvedValueOnce(true)
    s.onSaved.mockImplementationOnce(() => { throw new Error('history') })
    await expect(s.saveCurrentNote({ auto: true })).resolves.toBe(false)
    expect(s.saveStatus.value).toBe('error')
  })

  it('没有当前章节：不发保存，返回 false', async () => {
    const s = setup({ value: undefined })
    await expect(s.saveCurrentNote({ auto: true })).resolves.toBe(false)
    expect(s.save).not.toHaveBeenCalled()
    expect(s.saveStatus.value).toBe('idle')
  })
})
