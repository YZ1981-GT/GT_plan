// Feature: zero-downtime-deployment, Component 4a
/**
 * 版本协商 composable。
 *
 * 首次锁定 localVersion，检测 serverVersion 漂移触发 updateAvailable。
 * ≤60s 轮询 /api/version 作兜底；任意情形不调 location.reload。
 */
import { ref, onMounted, onUnmounted } from 'vue'

// Module-level bridge for HTTP interceptor to push versions without importing Vue reactivity
export const versionBridge = {
  _callback: null as ((v: string) => void) | null,
  push(v: string) {
    if (this._callback) this._callback(v)
  },
}

export function useVersionCheck() {
  const localVersion = ref<string>('')
  const serverVersion = ref<string>('')
  const updateAvailable = ref(false)

  function recordServerVersion(v: string) {
    if (!v) return
    if (!localVersion.value) {
      localVersion.value = v // 首次锁定
    }
    serverVersion.value = v
    if (localVersion.value && v !== localVersion.value) {
      updateAvailable.value = true
    }
  }

  function dismiss() {
    updateAvailable.value = false
  }

  let timer: ReturnType<typeof setInterval> | undefined

  onMounted(() => {
    // 注册 bridge callback，使 http 拦截器可推送版本
    versionBridge._callback = recordServerVersion

    // ≤60s 轮询兜底
    timer = setInterval(async () => {
      try {
        const resp = await fetch('/api/version')
        if (resp.ok) {
          const data = await resp.json()
          // ResponseWrapperMiddleware 包装解信封
          const body = data?.data ?? data
          if (body?.git_commit) {
            recordServerVersion(body.git_commit)
          }
        }
      } catch {
        // 轮询失败不影响正常使用
      }
    }, 60_000)
  })

  onUnmounted(() => {
    if (timer) clearInterval(timer)
    versionBridge._callback = null
  })

  return { updateAvailable, localVersion, serverVersion, recordServerVersion, dismiss }
}
