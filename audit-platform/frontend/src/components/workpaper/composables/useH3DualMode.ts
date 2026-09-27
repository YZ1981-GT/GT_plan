/**
 * useH3DualMode — H3 投资性房地产 HTML ↔ OnlyOffice 双模式切换
 *
 * Spec: .kiro/specs/h3-investment-property/ Task 6.2
 * Requirements: 16.1-16.2
 *
 * - el-segmented 切换 HTML / OnlyOffice
 * - OO 健康检查（`health.data?.data?.healthy` 双层兼容）
 * - 切换前 autoSave
 * - localStorage 持久化 (per wpId)
 * - Follow useH1DualMode / useH2DualMode pattern
 *
 * ═══ 🔴 @deprecated 生产已停用（H3 接桥后）═══════════════════════════════════
 *
 * `GtH3InvestmentProperty.vue` 已改用 `composables/useHSyncMode.ts`（统一四分支保存
 * 协议 + 真双向桥）。换掉本 composable 的两个理由与 H2/H4/H6/H8 同：
 *   ① 它**不建桥** ⇒ OO 侧编辑回不到 HTML（假双向）；
 *   ② 宿主原本用它的 `isOoAvailable` 做 `:disabled`，健康检查未就绪时整个切换器被锁死、
 *      点击被彻底忽略（D4 已实证的 bug ③）。
 *
 * 🔴 H3 接桥还多做一件前几条没有的事：**变体轴归一**。`明细表（成本模式）H3-2` 与
 * `明细表（公允价值模式）H3-2` 是两张各有独立持久化键的受管表，宿主用
 * `h3SyncCode` 把 `currentSheet` 按计量模式归一到 `H3-2-cost` / `H3-2-fair`
 * 两个短码 —— 本 composable 完全没有这个概念（它只认 wpId + sheetName）。
 *
 * 🔴 **本文件当前生产与测试消费均为 0，但先不删**（与 `useH2DualMode` / `useH6DualMode`
 *    同一处置）：`test_h_foundation_hc_guards.py` 的 localStorage 判据把
 *    `useH{2,3,4,6,8,9,10}DualMode.ts` 逐个列进「UI 偏好存储」清单，本文件的
 *    `STORAGE_PREFIX` 在列 ⇒ 删了清单缺项；删除需要一次独立的收敛动作连同判据一起改。
 *    「零消费」结论是按值 grep（`split_real_importers('useH3DualMode')`）现算的：
 *    real=[]，命中只剩注释（宿主里那段说明 + `useH4DualMode.ts` 的 pattern 引用）。
 */
import { ref, onMounted, type Ref } from 'vue'

export type H3RenderMode = 'html' | 'onlyoffice'

const STORAGE_PREFIX = 'h3-dual-mode:'

export interface UseH3DualModeOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  /** 切换前自动保存回调 */
  autoSave?: () => Promise<void>
  /** 从 OO 切回 HTML 后 reload 数据 */
  reloadAll?: () => Promise<void>
}

export function useH3DualMode(options: UseH3DualModeOptions) {
  const { wpId, autoSave, reloadAll } = options

  const currentMode = ref<H3RenderMode>('html')
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

  function persistMode(mode: H3RenderMode): void {
    try {
      localStorage.setItem(STORAGE_PREFIX + wpId.value, mode)
    } catch { /* ignore */ }
  }

  /** OO 健康检查 — 双层兼容 health.data?.data?.healthy */
  async function checkOOHealth(): Promise<boolean> {
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

  async function switchMode(target: H3RenderMode): Promise<void> {
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
    void switchMode(val as H3RenderMode)
  }

  onMounted(() => {
    loadPersistedMode()
    void checkOOHealth()
  })

  return {
    currentMode,
    isOoAvailable,
    checking,
    modeOptions,
    switchMode,
    onModeChange,
    checkOOHealth,
  }
}

export default useH3DualMode
