/**
 * useN1EntryDualMode — N1 入口级 HTML ↔ OnlyOffice 双模式
 *
 * 对齐 D4/D5/D6/D7 的入口级单一双模式架构（一个 sheet 一个切换，子组件不再各自切换），
 * 但健康检查用 **authed http.get**（携带 Bearer token），而非共享 useWorkpaperEntryDualMode
 * 的裸 fetch（裸 fetch 不带 Authorization → 401 → OO 永远不可用）。
 *
 * - checkOOHealth: GET /api/workpapers/onlyoffice/health（信封双层 .data 兼容）
 * - switchMode: 切 OO 前校验 ooAvailable；切回 html 时 reloadAllResponses 同步回写
 * - resolveOoSheetName: 由调用方注入（N1 直接用 GtWpRenderer 传入的真实全名 props.sheetName）
 */
import { ref, onMounted } from 'vue'
import http from '@/utils/http'

export type N1RenderMode = 'html' | 'onlyoffice'

export interface UseN1EntryDualModeOptions {
  reloadAllResponses: () => void | Promise<void>
  resolveOoSheetName: () => string
}

export function useN1EntryDualMode(options: UseN1EntryDualModeOptions) {
  const { reloadAllResponses, resolveOoSheetName } = options

  const mode = ref<N1RenderMode>('html')
  const ooAvailable = ref(false)
  const checking = ref(false)

  /** OnlyOffice 健康检查（authed；信封双层 .data 兼容） */
  async function checkOOHealth(): Promise<boolean> {
    checking.value = true
    try {
      const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
      const healthy = (res as any).data?.data?.healthy ?? (res as any).data?.healthy ?? false
      ooAvailable.value = Boolean(healthy)
      return ooAvailable.value
    } catch {
      ooAvailable.value = false
      return false
    } finally {
      checking.value = false
    }
  }

  async function switchMode(target: N1RenderMode): Promise<void> {
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

export default useN1EntryDualMode
