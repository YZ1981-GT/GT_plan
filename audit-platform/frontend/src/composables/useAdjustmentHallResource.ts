import { ref, type Ref } from 'vue'

export type AdjustmentResourceStatus = 'idle' | 'loading' | 'success' | 'error'

export interface AdjustmentHallResource<T> {
  data: Ref<T>
  status: Ref<AdjustmentResourceStatus>
  error: Ref<string>
  lastSuccessAt: Ref<number | null>
  requestEpoch: Ref<number>
  load: (loader: () => Promise<T>, errorMessage: string) => Promise<boolean>
  reset: () => void
}

function isCancelled(error: unknown): boolean {
  const value = error as { code?: string; name?: string; message?: string } | null
  return value?.code === 'ERR_CANCELED'
    || value?.name === 'CanceledError'
    || value?.message === 'canceled'
}

/**
 * 调整大厅读资源状态。上下文签名与资源自身 epoch 双重校验，晚到响应不能覆盖新上下文或更新请求。
 */
export function useAdjustmentHallResource<T>(
  initial: () => T,
  contextKey: () => string,
): AdjustmentHallResource<T> {
  const data = ref(initial()) as Ref<T>
  const status = ref<AdjustmentResourceStatus>('idle')
  const error = ref('')
  const lastSuccessAt = ref<number | null>(null)
  const requestEpoch = ref(0)

  async function load(loader: () => Promise<T>, errorMessage: string): Promise<boolean> {
    const contextSnapshot = contextKey()
    const epoch = ++requestEpoch.value
    status.value = 'loading'
    error.value = ''
    try {
      const result = await loader()
      if (epoch !== requestEpoch.value || contextSnapshot !== contextKey()) return false
      data.value = result
      status.value = 'success'
      lastSuccessAt.value = Date.now()
      return true
    } catch (cause) {
      if (epoch !== requestEpoch.value || contextSnapshot !== contextKey()) return false
      if (isCancelled(cause)) {
        status.value = lastSuccessAt.value == null ? 'idle' : 'success'
        return false
      }
      status.value = 'error'
      error.value = errorMessage
      return false
    }
  }

  function reset(): void {
    requestEpoch.value += 1
    data.value = initial()
    status.value = 'idle'
    error.value = ''
    lastSuccessAt.value = null
  }

  return { data, status, error, lastSuccessAt, requestEpoch, load, reset }
}
