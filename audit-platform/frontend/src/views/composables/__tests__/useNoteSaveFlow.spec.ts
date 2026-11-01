import { effectScope, nextTick, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { useNoteSaveFlow } from '../useNoteSaveFlow'

function deferred() {
  let resolve!: () => void
  let reject!: (error: Error) => void
  const promise = new Promise<void>((ok, fail) => { resolve = ok; reject = fail })
  return { promise, resolve, reject }
}

describe('useNoteSaveFlow', () => {
  it('手工/自动保存分别传 keepEditing=false/true，并只在成功后回调', async () => {
    const id = ref('n1')
    const save = vi.fn().mockResolvedValue(undefined)
    const onSaved = vi.fn()
    const flow = useNoteSaveFlow({ currentNoteId: () => id.value, save, onSaved })
    expect(await flow.saveCurrentNote({ auto: false })).toBe(true)
    expect(save).toHaveBeenLastCalledWith({ keepEditing: false })
    expect(onSaved).toHaveBeenLastCalledWith(false)
    expect(await flow.saveCurrentNote({ auto: true })).toBe(true)
    expect(save).toHaveBeenLastCalledWith({ keepEditing: true })
    expect(onSaved).toHaveBeenLastCalledWith(true)
    expect(flow.saveStatus.value).toBe('saved')
  })

  it('保存失败返回 false 并保持错误状态，不调用成功回调', async () => {
    const onSaved = vi.fn()
    const flow = useNoteSaveFlow({
      currentNoteId: () => 'n1',
      save: vi.fn().mockRejectedValue(new Error('boom')),
      onSaved,
    })
    expect(await flow.saveCurrentNote()).toBe(false)
    expect(flow.saveStatus.value).toBe('error')
    expect(onSaved).not.toHaveBeenCalled()
  })

  it('保存中切章：旧请求完成后不把新章节标为已保存、不触发跳转回调', async () => {
    const id = ref('n1')
    const pending = deferred()
    const onSaved = vi.fn()
    const flow = useNoteSaveFlow({ currentNoteId: () => id.value, save: () => pending.promise, onSaved })
    const saving = flow.saveCurrentNote()
    expect(flow.saveStatus.value).toBe('saving')
    id.value = 'n2'
    pending.resolve()
    expect(await saving).toBe(true)
    expect(flow.saveStatus.value).toBe('idle')
    expect(onSaved).not.toHaveBeenCalled()
  })

  it('宿主作用域销毁时清理“已保存”复位定时器', async () => {
    vi.useFakeTimers()
    const scope = effectScope()
    const flow = scope.run(() => useNoteSaveFlow({ currentNoteId: () => 'n1', save: async () => {} }))!
    await flow.saveCurrentNote()
    expect(flow.saveStatus.value).toBe('saved')
    scope.stop()
    vi.runAllTimers()
    await nextTick()
    expect(flow.saveStatus.value).toBe('saved')
    vi.useRealTimers()
  })
})
