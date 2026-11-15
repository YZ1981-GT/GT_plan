/**
 * useG9DualMode — G9 HTML ↔ OnlyOffice 双模式
 * 比照 useF2DualMode / useG7DualMode：http 健康检查 + 取配置 + reloadAll
 *
 * 🔴 2026-11-15（spec 任务 2.8 第 ② 步）：取配置改走 `probeOnlyOfficeEntryConfig`
 * —— 它按服务端 readiness 决定走 room 协议还是回落旧式端点，不再由本文件自己拼
 * `/onlyoffice-config`。旧写法是 22 个 composable 各拼一份，后端 writer gate 的
 * `multi_resolver` 判据正是指向那条「优先级链没有单一来源」的路径。
 */
import { ref, onMounted, type Ref } from 'vue'
import http from '@/utils/http'
import { probeOnlyOfficeEntryConfig } from './onlyOfficeEntryConfig'
import { dualModeHtmlOoOptions } from './dualModeLabels'

export type G9RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'g9-dual-mode:'

export function useG9DualMode(options: {
  wpId: Ref<string>
  /** 项目 id —— 取配置要它才能问 entry-identity（缺它只能回落旧式端点）。 */
  projectId?: Ref<string>
  sheetName?: Ref<string>
  reloadAll?: () => Promise<void>
}) {
  const { wpId, projectId, sheetName, reloadAll } = options

  const currentMode = ref<G9RenderMode>('html')
  const isOoAvailable = ref(false)
  const ooConfig = ref<Record<string, any> | null>(null)
  const checking = ref(false)
  /** 不可切时的中文原因（来自唯一取配置入口；可切时为 null）。 */
  const unavailableReason = ref<string | null>(null)

  const modeOptions = dualModeHtmlOoOptions()

  function loadPersistedMode(): void {
    try {
      const saved = localStorage.getItem(STORAGE_PREFIX + wpId.value)
      if (saved === 'html' || saved === 'onlyoffice') currentMode.value = saved
    } catch { /* ignore */ }
  }

  function persistMode(mode: G9RenderMode): void {
    try {
      localStorage.setItem(STORAGE_PREFIX + wpId.value, mode)
    } catch { /* ignore */ }
  }

  async function checkOOHealth(): Promise<boolean> {
    checking.value = true
    try {
      const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
      const result = res.data?.data ?? res.data ?? {}
      const healthy = result.data?.healthy ?? result.healthy ?? false
      isOoAvailable.value = healthy
      return healthy
    } catch {
      isOoAvailable.value = false
      return false
    } finally {
      checking.value = false
    }
  }

  async function switchMode(target: G9RenderMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) return

    if (target === 'onlyoffice') {
      const sn = sheetName?.value || 'G9'
      // 取配置走唯一入口：room 就绪 ⇒ 判可切（由宿主走协同协议），否则回落旧式端点。
      const probe = await probeOnlyOfficeEntryConfig({
        projectId: projectId?.value,
        wpId: wpId.value,
        sheetName: sn,
      })
      if (!probe.available) {
        isOoAvailable.value = false
        if (probe.reason) unavailableReason.value = probe.reason
        return
      }
      ooConfig.value = probe.config
      currentMode.value = 'onlyoffice'
      persistMode('onlyoffice')
    } else {
      currentMode.value = 'html'
      ooConfig.value = null
      persistMode('html')
      if (reloadAll) await reloadAll()
    }
  }

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as G9RenderMode)
  }

  onMounted(() => {
    loadPersistedMode()
    void (async () => {
      let saved: string | null = null
      try {
        saved = localStorage.getItem(STORAGE_PREFIX + wpId.value)
      } catch { /* ignore */ }

      if (saved === 'onlyoffice') {
        const healthy = await checkOOHealth()
        if (healthy) {
          await switchMode('onlyoffice')
        } else {
          currentMode.value = 'html'
          persistMode('html')
        }
      } else {
        void checkOOHealth()
      }
    })()
  })

  return {
    currentMode,
    isOoAvailable,
    ooConfig,
    checking,
    /** 不可切时的中文原因（宿主可直接展示，不必自己翻译 reason code）。 */
    unavailableReason,
    modeOptions,
    switchMode,
    onModeChange,
    checkOOHealth,
  }
}

export default useG9DualMode
