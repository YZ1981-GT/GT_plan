/**
 * useK10DualMode — K10 其他收益 HTML ↔ OnlyOffice 双模式（比照 useD4DualMode / useF2DualMode）
 *
 * D4 范式核心："拉取成功才可以切在线编辑"：
 * - onMounted: health 轻量探测（http 带鉴权），失败不阻塞首屏
 * - switchMode('onlyoffice'): 先 GET onlyoffice-config，**拉取成功**才 currentMode='onlyoffice'；
 *   拉取失败则回退 html + isOoAvailable=false（绝不在 config 未就绪时切到 OO）
 * - 提供 ooConfig 供上层展示"拉取成功"状态
 *
 * Spec: K10 复盘 P0-1（双模式对齐 D4/F2）
 */
import { ref, onMounted, type Ref } from 'vue'
import http from '@/utils/http'

export type K10RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'k10-dual-mode:'

export interface UseK10DualModeOptions {
  wpId: Ref<string>
  /** 项目ID —— onlyoffice-config 端点必填 query 参数（缺失会 422） */
  projectId?: Ref<string>
  sheetName?: Ref<string>
  /** 从 OO 切回 HTML 后 reload 数据 */
  reloadAll?: () => Promise<void>
}

export function useK10DualMode(options: UseK10DualModeOptions) {
  const { wpId, projectId, sheetName, reloadAll } = options

  const currentMode = ref<K10RenderMode>('html')
  const isOoAvailable = ref(false)
  /** onlyoffice-config 拉取结果；非空表示"拉取成功" */
  const ooConfig = ref<Record<string, any> | null>(null)
  const checking = ref(false)

  const modeOptions = [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice' },
  ]

  function loadPersistedMode(): void {
    try {
      const saved = localStorage.getItem(STORAGE_PREFIX + wpId.value)
      if (saved === 'html' || saved === 'onlyoffice') currentMode.value = saved
    } catch { /* ignore */ }
  }

  function persistMode(mode: K10RenderMode): void {
    try {
      localStorage.setItem(STORAGE_PREFIX + wpId.value, mode)
    } catch { /* ignore */ }
  }

  /**
   * OO 健康检查 — GET /api/workpapers/onlyoffice/health（http 带鉴权 + 双层兼容）
   */
  async function checkOoHealth(): Promise<boolean> {
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

  /**
   * 切换模式。
   * - 切到 onlyoffice：先 GET onlyoffice-config，**拉取成功**才切；失败回退 html。
   * - 切回 html：清 config + reloadAll 刷新结构化数据。
   */
  async function switchMode(target: K10RenderMode): Promise<void> {
    if (target === currentMode.value) return

    if (target === 'onlyoffice') {
      if (!isOoAvailable.value) {
        const healthy = await checkOoHealth()
        if (!healthy) return
      }
      const sn = sheetName?.value || 'K10'
      try {
        const res = await http.get(
          `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(sn)}/onlyoffice-config`,
          { params: projectId?.value ? { project_id: projectId.value } : {}, _silent: true } as any,
        )
        const result = res.data?.data ?? res.data ?? {}
        ooConfig.value = result.data || result
        // 拉取成功才切
        currentMode.value = 'onlyoffice'
        persistMode('onlyoffice')
      } catch {
        // 该 sheet 拉取失败（如合成"底稿目录"无 OO 底稿）：不切、保持结构化。
        // 不置 isOoAvailable=false —— 单个 sheet 失败不应全局禁用在线编辑（其它数据 sheet 仍可用）。
        ooConfig.value = null
        currentMode.value = 'html'
        persistMode('html')
        try {
          const { ElMessage } = await import('element-plus')
          ElMessage.warning('该表暂不支持在线编辑（OnlyOffice 底稿拉取失败），已保持结构化视图')
        } catch { /* ignore */ }
      }
    } else {
      currentMode.value = 'html'
      ooConfig.value = null
      persistMode('html')
      if (reloadAll) await reloadAll()
    }
  }

  /** el-segmented @change 回调 */
  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as K10RenderMode)
  }

  onMounted(() => {
    loadPersistedMode()
    void (async () => {
      let saved: string | null = null
      try { saved = localStorage.getItem(STORAGE_PREFIX + wpId.value) } catch { /* ignore */ }
      if (saved === 'onlyoffice') {
        const healthy = await checkOoHealth()
        if (healthy) {
          await switchMode('onlyoffice')
        } else {
          currentMode.value = 'html'
          persistMode('html')
        }
      } else {
        // 结构化视图：后台轻量探测，失败不影响渲染
        void checkOoHealth()
      }
    })()
  })

  return {
    currentMode,
    isOoAvailable,
    ooConfig,
    checking,
    modeOptions,
    switchMode,
    onModeChange,
    checkOoHealth,
  }
}

export default useK10DualMode
