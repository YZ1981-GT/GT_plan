/**
 * useB60DualMode — B60 结构化视图 ↔ OnlyOffice 双模式（比照 useF2DualMode / useD4DualMode）
 *
 * 关键：切到 OnlyOffice 前必须先 GET onlyoffice-config「拉取成功」才切换并显示，
 * 拉取失败则回退结构化视图 + isOoAvailable=false（对齐 D4 双模式铁律）。
 *
 * 可同时用于 B60 主底稿（sheetName='B60'）与 8 个 docx-inline 子底稿（各自 wpId+sheetName）。
 *
 * Spec: b60-strategy-rework（直接修复）
 */
import { ref, computed, onMounted, type Ref } from 'vue'
import http from '@/utils/http'

export type B60RenderMode = 'structured' | 'onlyoffice'

const STORAGE_PREFIX = 'b60-dual-mode:'

export interface UseB60DualModeOptions {
  /** 承载 OnlyOffice 文档的底稿 wp_id */
  wpId: Ref<string>
  /** OnlyOffice sheet 名（主底稿传 'B60'，子底稿传各自 wp_code） */
  sheetName: Ref<string>
  /** 结构化视图标签（主底稿用 '章节编辑'，子底稿用 '结构化视图'） */
  structuredLabel?: string
  /** 切回结构化视图时的刷新回调 */
  reloadStructured?: () => void | Promise<void>
  /** 切到 OnlyOffice 前的 flush 回调（如章节编辑的待保存内容） */
  flushBeforeOnline?: () => void | Promise<void>
}

export function useB60DualMode(options: UseB60DualModeOptions) {
  const { wpId, sheetName, structuredLabel = '结构化视图', reloadStructured, flushBeforeOnline } = options

  const currentMode = ref<B60RenderMode>('structured')
  const isOoAvailable = ref(false)
  /** 已成功拉取的 OnlyOffice 配置（非空即代表「拉取成功」） */
  const ooConfig = ref<Record<string, any> | null>(null)
  const checking = ref(false)
  const switching = ref(false)

  const modeOptions = computed(() => [
    { label: structuredLabel, value: 'structured' as const },
    { label: '在线编辑', value: 'onlyoffice' as const, disabled: !isOoAvailable.value },
  ])

  function _key(): string {
    return STORAGE_PREFIX + wpId.value + ':' + sheetName.value
  }

  function loadPersistedMode(): void {
    try {
      const saved = localStorage.getItem(_key())
      if (saved === 'structured' || saved === 'onlyoffice') currentMode.value = saved
    } catch { /* ignore */ }
  }

  function persistMode(mode: B60RenderMode): void {
    try {
      localStorage.setItem(_key(), mode)
    } catch { /* ignore */ }
  }

  /** OnlyOffice 服务健康探测（不阻塞首屏，静默） */
  async function checkOOHealth(): Promise<boolean> {
    checking.value = true
    try {
      const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
      const result = res.data?.data ?? res.data ?? {}
      const healthy = result.data?.healthy ?? result.healthy ?? false
      isOoAvailable.value = !!healthy
      return !!healthy
    } catch {
      isOoAvailable.value = false
      return false
    } finally {
      checking.value = false
    }
  }

  /**
   * 切换模式。切到 OnlyOffice 时先预拉 onlyoffice-config，
   * 「拉取成功」（config 非空）才真正切换并显示；失败则回退结构化视图。
   */
  async function switchMode(target: B60RenderMode): Promise<void> {
    if (target === currentMode.value || switching.value) return

    if (target === 'onlyoffice') {
      switching.value = true
      try {
        if (flushBeforeOnline) await flushBeforeOnline()
        const sn = sheetName.value || 'B60'
        const res = await http.get(
          `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(sn)}/onlyoffice-config`,
          { _silent: true } as any,
        )
        const result = res.data?.data ?? res.data ?? {}
        const config = result.data || result
        // 「拉取成功」判定：必须拿到非空配置
        if (config && (config.config || config.token !== undefined || config.onlyoffice_url)) {
          ooConfig.value = config
          isOoAvailable.value = true
          currentMode.value = 'onlyoffice'
          persistMode('onlyoffice')
        } else {
          // 拉取到空配置 → 视为不可用，保持结构化视图
          isOoAvailable.value = false
          ooConfig.value = null
        }
      } catch {
        // 拉取失败 → 回退结构化视图 + 标记不可用
        isOoAvailable.value = false
        ooConfig.value = null
      } finally {
        switching.value = false
      }
    } else {
      currentMode.value = 'structured'
      ooConfig.value = null
      persistMode('structured')
      if (reloadStructured) await reloadStructured()
    }
  }

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as B60RenderMode)
  }

  onMounted(() => {
    loadPersistedMode()
    void (async () => {
      let saved: string | null = null
      try { saved = localStorage.getItem(_key()) } catch { /* ignore */ }

      if (saved === 'onlyoffice') {
        const healthy = await checkOOHealth()
        if (healthy) {
          await switchMode('onlyoffice')
        } else {
          currentMode.value = 'structured'
          persistMode('structured')
        }
      } else {
        // 结构化视图：后台轻量探测，失败不影响渲染
        void checkOOHealth()
      }
    })()
  })

  return {
    currentMode,
    isOoAvailable,
    ooConfig,
    checking,
    switching,
    modeOptions,
    switchMode,
    onModeChange,
    checkOOHealth,
  }
}

export default useB60DualMode
