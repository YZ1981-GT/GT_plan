/**
 * useK11DualMode — K11 资产减值损失 HTML ↔ OnlyOffice 双模式切换
 *
 * Spec: .kiro/specs/k11-asset-impairment-loss/
 * Task: 1.1（P0 双模式对齐 D4/F2 七月十日"拉取成功"范式）
 *
 * 关键：切 OnlyOffice 前**预拉 onlyoffice-config（带 project_id）**，
 *      config 拉取成功才置 currentMode='onlyoffice'（"拉取成功才可以"），失败回退 html。
 * - el-segmented 切换 结构化视图(html) / 在线编辑(onlyoffice)
 * - OO 健康检查（`/workpapers/onlyoffice/health` 双层兼容 + 带鉴权 http）
 * - localStorage 持久化 (per wpId)
 * - 单 sheet config 失败不全局禁用（isOoAvailable 由 health 决定）
 */
import { ref, onMounted, type Ref } from 'vue'
import http from '@/utils/http'

export type K11RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'k11-dual-mode:'

export interface UseK11DualModeOptions {
  wpId: Ref<string>
  /** 当前 sheet 的真实 xlsx 名称（用于拉取 onlyoffice-config） */
  sheetName?: Ref<string>
  /** 项目 id（onlyoffice-config 必填 query 参，缺失会 422） */
  projectId?: Ref<string>
  /** 从 OO 切回 HTML 后 reload 数据 */
  reloadAll?: () => Promise<void>
}

export function useK11DualMode(options: UseK11DualModeOptions) {
  const { wpId, sheetName, projectId, reloadAll } = options

  const currentMode = ref<K11RenderMode>('html')
  /** OO 服务是否健康（health 检查） */
  const isOoAvailable = ref(false)
  /** 当前 sheet 的 onlyoffice-config 是否已拉取成功（"拉取成功"tag 依据） */
  const ooConfigReady = ref(false)
  /** config 拉取中 */
  const fetchingConfig = ref(false)
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

  function persistMode(mode: K11RenderMode): void {
    try {
      localStorage.setItem(STORAGE_PREFIX + wpId.value, mode)
    } catch { /* ignore */ }
  }

  /**
   * OO 健康检查 — GET /workpapers/onlyoffice/health（带鉴权 http + 双层信封兼容）
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
   * 切换模式
   * - 切 onlyoffice：先预拉当前 sheet 的 onlyoffice-config（带 project_id），
   *   **拉取成功才切**，失败保持 html 并提示。
   * - 切回 html：清 config + reloadAll 刷新数据。
   */
  async function switchMode(target: K11RenderMode): Promise<void> {
    if (target === currentMode.value) return

    if (target === 'onlyoffice') {
      if (!isOoAvailable.value) return
      const sn = sheetName?.value || ''
      if (!sn) return
      fetchingConfig.value = true
      ooConfigReady.value = false
      try {
        const params: Record<string, any> = {}
        if (projectId?.value) params.project_id = projectId.value
        const res = await http.get(
          `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(sn)}/onlyoffice-config`,
          { params, _silent: true } as any,
        )
        const payload = res.data?.data ?? res.data
        if (!payload) throw new Error('empty onlyoffice-config')
        // config 拉取成功 → 允许进入在线编辑
        ooConfigReady.value = true
        currentMode.value = 'onlyoffice'
        persistMode('onlyoffice')
      } catch {
        // config 拉取失败 → 保持结构化视图（不全局禁用 OO 服务）
        ooConfigReady.value = false
        currentMode.value = 'html'
      } finally {
        fetchingConfig.value = false
      }
    } else {
      currentMode.value = 'html'
      ooConfigReady.value = false
      persistMode('html')
      if (reloadAll) await reloadAll()
    }
  }

  /** el-segmented @change 回调 */
  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as K11RenderMode)
  }

  onMounted(() => {
    loadPersistedMode()
    // 结构化视图为主：后台轻量健康探测，不阻塞首屏，也不自动切 OO
    void checkOoHealth().then((healthy) => {
      // 若持久化偏好是 OO 且健康，尝试预拉 config 恢复在线编辑
      if (healthy && currentMode.value === 'onlyoffice') {
        currentMode.value = 'html' // 先回退，交由 switchMode 校验 config
        void switchMode('onlyoffice')
      }
    })
  })

  return {
    currentMode,
    isOoAvailable,
    ooConfigReady,
    fetchingConfig,
    checking,
    modeOptions,
    switchMode,
    onModeChange,
    checkOoHealth,
  }
}

export default useK11DualMode
