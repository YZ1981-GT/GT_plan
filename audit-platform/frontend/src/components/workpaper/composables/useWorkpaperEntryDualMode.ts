/**
 * useWorkpaperEntryDualMode — 循环底稿入口 HTML ↔ OnlyOffice 双模式（D4/D5/D6/D7 共用）
 *
 * 各 cycle 通过 resolveOoSheetName 注入 sheet 名解析逻辑。
 */
import { ref, onMounted, type Ref } from 'vue'
import http from '@/utils/http'

export type WorkpaperRenderMode = 'html' | 'onlyoffice'

export function useWorkpaperEntryDualMode(options: {
  reloadAllResponses: () => Promise<void>
  resolveOoSheetName: () => string
}) {
  const { reloadAllResponses, resolveOoSheetName } = options

  const mode = ref<WorkpaperRenderMode>('html')
  const ooAvailable = ref(false)
  const checking = ref(false)

  async function checkOOHealth(): Promise<boolean> {
    checking.value = true
    try {
      // 🔴 该端点受 dedicated_wp_gate（router-level get_current_user）拦截：
      //    裸 fetch 无 Authorization 头 → 401 Not authenticated → ooAvailable 恒 false → "OO不可用"。
      //    必须用带鉴权的 http（axios 拦截器注入 Bearer token），认证通过后 gate 对无 wp_id 的
      //    /onlyoffice/health 静态路径 no-op 放行，端点正常返回 healthy。
      const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
      // 兼容 axios 原始响应 与 拦截器已解包信封 两种形态
      const result = (res as any)?.data?.data ?? (res as any)?.data ?? {}
      const healthy = result?.data?.healthy ?? result?.healthy ?? false
      ooAvailable.value = !!healthy
      return ooAvailable.value
    } catch {
      ooAvailable.value = false
      return false
    } finally {
      checking.value = false
    }
  }

  async function switchMode(target: WorkpaperRenderMode): Promise<void> {
    if (target === mode.value) return
    if (target === 'onlyoffice' && !ooAvailable.value) return
    if (target === 'onlyoffice') {
      mode.value = 'onlyoffice'
    } else {
      mode.value = 'html'
      await reloadAllResponses()
    }
  }

  onMounted(() => { void checkOOHealth() })

  return {
    mode,
    ooAvailable,
    checking,
    switchMode,
    checkOOHealth,
    resolveOoSheetName,
  }
}

export default useWorkpaperEntryDualMode
