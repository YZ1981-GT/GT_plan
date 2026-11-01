import { effectScope } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

const { error } = vi.hoisted(() => ({ error: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: { error } }))

import { runLegacyOnlyOfficeTransition } from '../legacyPendingWriteBarrier'
import {
  flushPendingWrites,
  pendingWriteBarrierActive,
  registerPendingFlusher,
} from '../pendingWrites'

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((done) => { resolve = done })
  return { promise, resolve }
}

const scopes: Array<ReturnType<typeof effectScope>> = []
function withFlusher(flusher: () => void | Promise<void>) {
  const scope = effectScope()
  scope.run(() => registerPendingFlusher(flusher))
  scopes.push(scope)
}

afterEach(async () => {
  for (const scope of scopes.splice(0)) scope.stop()
  error.mockReset()
  await flushPendingWrites().catch(() => undefined)
})

describe('legacy OnlyOffice 完整保存屏障', () => {
  it('flush 完成后 config/模式切换未完成时仍保持 active', async () => {
    const flush = vi.fn()
    const config = deferred()
    const transition = vi.fn(() => config.promise)
    withFlusher(flush)

    const result = runLegacyOnlyOfficeTransition(transition)
    expect(pendingWriteBarrierActive.value).toBe(true)
    await vi.waitFor(() => expect(transition).toHaveBeenCalledOnce())
    expect(flush).toHaveBeenCalledOnce()
    expect(pendingWriteBarrierActive.value).toBe(true)

    config.resolve()
    await expect(result).resolves.toBe(true)
    expect(pendingWriteBarrierActive.value).toBe(false)
    expect(error).not.toHaveBeenCalled()
  })

  it('写入失败不执行过渡，保持结构化模式并显示聚合后的中文失败原因', async () => {
    const transition = vi.fn()
    withFlusher(() => { throw new Error('子表保存失败') })
    await expect(runLegacyOnlyOfficeTransition(transition)).resolves.toBe(false)
    expect(transition).not.toHaveBeenCalled()
    expect(pendingWriteBarrierActive.value).toBe(false)
    expect(error).toHaveBeenCalledWith('切换在线编辑前有 1 项内容保存失败，请重试')
  })

  it('配置阶段抛错也释放 active，并把原错误交回调用方处理', async () => {
    await expect(runLegacyOnlyOfficeTransition(async () => {
      throw new Error('onlyoffice-config 失败')
    })).rejects.toThrow('onlyoffice-config 失败')
    expect(pendingWriteBarrierActive.value).toBe(false)
  })
})
