import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import { pendingWriteBarrierActive } from '../pendingWrites'
import { useGRenderModeSwitch, type GRenderMode } from '../useGRenderModeSwitch'
import type { WorkpaperSyncBridge } from '../useWorkpaperSyncBridge'

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((done) => { resolve = done })
  return { promise, resolve }
}

function fakeBridge(): WorkpaperSyncBridge {
  return {
    mode: ref('html'),
    state: ref('html_idle'),
    dirty: ref(false),
    canForcesave: ref(false),
  } as unknown as WorkpaperSyncBridge
}

describe('useGRenderModeSwitch legacy 完整屏障', () => {
  it('显式进入 OO 时，legacy 配置未完成前一直冻结且保持 HTML', async () => {
    const config = deferred()
    const currentMode = ref<GRenderMode>('html')
    const onModeChange = vi.fn(async (target: unknown) => {
      await config.promise
      currentMode.value = target as GRenderMode
    })
    const mode = useGRenderModeSwitch({
      bridge: fakeBridge(),
      legacy: { currentMode, onModeChange },
      isManagedSheet: ref(false),
      editorHostRef: ref(null),
    })

    const switching = mode.switchRenderMode('onlyoffice')
    expect(pendingWriteBarrierActive.value).toBe(true)
    expect(mode.renderMode.value).toBe('html')
    await vi.waitFor(() => expect(onModeChange).toHaveBeenCalledOnce())
    expect(pendingWriteBarrierActive.value).toBe(true)

    config.resolve()
    await switching
    expect(mode.renderMode.value).toBe('onlyoffice')
    expect(pendingWriteBarrierActive.value).toBe(false)
  })

  it('mounted 直接恢复 OO 会同步拦回 HTML，再经健康检查和完整屏障恢复', async () => {
    const config = deferred()
    const currentMode = ref<GRenderMode>('html')
    const onModeChange = vi.fn(async () => {
      await config.promise
      currentMode.value = 'onlyoffice'
    })
    const checkOOHealth = vi.fn(async () => true)
    const mode = useGRenderModeSwitch({
      bridge: fakeBridge(),
      legacy: { currentMode, onModeChange, checkOOHealth },
      isManagedSheet: ref(false),
      editorHostRef: ref(null),
    })

    currentMode.value = 'onlyoffice'
    expect(mode.renderMode.value).toBe('html')
    expect(pendingWriteBarrierActive.value).toBe(true)
    await vi.waitFor(() => expect(onModeChange).toHaveBeenCalledOnce())
    expect(checkOOHealth).toHaveBeenCalledOnce()

    config.resolve()
    await vi.waitFor(() => expect(mode.renderMode.value).toBe('onlyoffice'))
    expect(pendingWriteBarrierActive.value).toBe(false)
  })

  it('受管 sheet 的 legacy 偏好先延后，转入非受管 sheet 时才受保护地恢复', async () => {
    const currentMode = ref<GRenderMode>('html')
    const managed = ref(true)
    const onModeChange = vi.fn(async () => { currentMode.value = 'onlyoffice' })
    const mode = useGRenderModeSwitch({
      bridge: fakeBridge(),
      legacy: { currentMode, onModeChange, checkOOHealth: async () => true },
      isManagedSheet: managed,
      editorHostRef: ref(null),
    })

    currentMode.value = 'onlyoffice'
    expect(currentMode.value).toBe('html')
    expect(onModeChange).not.toHaveBeenCalled()

    managed.value = false
    expect(pendingWriteBarrierActive.value).toBe(true)
    await vi.waitFor(() => expect(mode.renderMode.value).toBe('onlyoffice'))
    expect(pendingWriteBarrierActive.value).toBe(false)
  })
})
