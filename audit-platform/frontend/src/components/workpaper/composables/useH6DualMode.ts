/**
 * useH6DualMode — H6 固定资产清理 HTML ↔ OnlyOffice 双模式切换
 *
 * Spec: .kiro/specs/h6-asset-disposal-clearing/ Task 3.3
 * Requirements: 3.6
 *
 * - el-segmented 切换 结构化视图 / 在线编辑
 * - OO 健康检查（`health.data?.data?.healthy` 双层兼容）
 * - 切换前 autoSave
 * - localStorage 持久化 (per wpId)
 * - OO 不可用时降级为 HTML 视图
 * - Follow useH4DualMode pattern
 *
 * ═══ 🔴 @deprecated 生产已停用（H6 接桥后）═══════════════════════════════════
 *
 * `GtH6AssetDisposalClearing.vue` 已改用 `composables/useHSyncMode.ts`（统一四分支保存
 * 协议 + 真双向桥）。换掉本 composable 的两个理由：
 *   ① 它**不建桥** ⇒ OO 侧编辑回不到 HTML（假双向）；
 *   ② 它的 `isOoAvailable` 被宿主用在 `:disabled` 上，健康检查未就绪时整个切换器被锁死、
 *      点击被彻底忽略（D4 已实证的 bug ③）。
 *
 * 🔴 **本文件当前生产消费为 0，但先不删** —— 删除有三处守卫连带影响，需要一次独立的
 *    收敛动作（连同判据一起改），不能顺手做：
 *   · `test_h_foundation_hc_guards.py::test_use_h4_dual_mode_is_chained_across_four_entries`
 *     断言 `useH4DualMode` 恰有 **5 个**生产消费方，本文件是其中一个（它 import 了
 *     `useH4DualMode`）⇒ 删了变 4 个，判据红；
 *   · 同文件的 localStorage 判据把 `useH{2,3,4,6,8,9,10}DualMode.ts` 逐个列进
 *     「UI 偏好存储」清单（本文件的 `STORAGE_PREFIX = 'h6-dual-mode:'` 在列）⇒ 删了清单缺项；
 *   · `test_dual_mode_ui_preference_store_only_persists_a_mode_string` 遍历同一组 n。
 *
 *    上一轮把 `useH9FormData.ts` 当「零消费载体」删掉时，正是漏查了**测试消费方**
 *    （`hCycleAccountScope.spec.ts` 依赖它）⇒ 判据 ENOENT 打红。此处不重复那个错误。
 */
import { ref, onMounted, type Ref } from 'vue'

export type H6RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'h6-dual-mode:'

export interface UseH6DualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  /** 切换前自动保存回调 */
  autoSave?: () => Promise<void>
  /** 从 OO 切回 HTML 后 reload 数据 */
  reloadAll?: () => Promise<void>
}

export function useH6DualMode(options: UseH6DualModeOptions) {
  const { wpId, autoSave, reloadAll } = options

  const currentMode = ref<H6RenderMode>('html')
  const isOoAvailable = ref(false)
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

  function persistMode(mode: H6RenderMode): void {
    try {
      localStorage.setItem(STORAGE_PREFIX + wpId.value, mode)
    } catch { /* ignore */ }
  }

  /** OO 健康检查 — 双层兼容 health.data?.data?.healthy */
  async function checkOoHealth(): Promise<boolean> {
    checking.value = true
    try {
      const response = await fetch('/api/workpapers/onlyoffice/health')
      if (!response.ok) {
        isOoAvailable.value = false
        return false
      }
      const result = await response.json()
      // 双层兼容: result.data?.data?.healthy 或 result.data?.healthy 或 result.healthy
      const healthy = result.data?.data?.healthy ?? result.data?.healthy ?? result.healthy ?? false
      isOoAvailable.value = healthy
      return healthy
    } catch {
      isOoAvailable.value = false
      return false
    } finally {
      checking.value = false
    }
  }

  async function switchMode(target: H6RenderMode): Promise<void> {
    if (target === currentMode.value) return
    if (target === 'onlyoffice' && !isOoAvailable.value) return

    // autoSave before switching
    if (autoSave) {
      try { await autoSave() } catch { /* best effort */ }
    }

    if (target === 'onlyoffice') {
      currentMode.value = 'onlyoffice'
      persistMode('onlyoffice')
    } else {
      currentMode.value = 'html'
      persistMode('html')
      if (reloadAll) await reloadAll()
    }
  }

  function onModeChange(val: string | number | boolean): void {
    void switchMode(val as H6RenderMode)
  }

  onMounted(() => {
    loadPersistedMode()
    void checkOoHealth()
  })

  return {
    currentMode,
    isOoAvailable,
    checking,
    modeOptions,
    switchMode,
    onModeChange,
    checkOoHealth,
  }
}

export default useH6DualMode
