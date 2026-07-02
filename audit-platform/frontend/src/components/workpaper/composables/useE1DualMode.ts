/**
 * useE1DualMode — 双模式切换(复用D1模式) composable
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 16b.1
 *
 * 职责：
 * - el-segmented 模式切换: 'structured' | 'online-edit'
 * - OnlyOffice 健康检查: GET /api/workpapers/onlyoffice/health
 *   双层.data兼容: response.data?.data?.healthy ?? response.data?.healthy
 * - 当 OO 不可用时: 禁用 online-edit 选项 + tooltip 提示
 *
 * Requirements: 13.1
 */
import { ref, computed, onMounted, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export type EditorMode = 'structured' | 'online-edit'

export interface UseE1DualModeOptions {
  wpId: Ref<string>
  defaultMode?: EditorMode
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useE1DualMode(options: UseE1DualModeOptions) {
  const { wpId, defaultMode = 'structured' } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const currentMode = ref<EditorMode>(defaultMode)
  const ooHealthy = ref<boolean | null>(null)  // null = checking
  const ooChecking = ref(false)

  // ─── OnlyOffice Health Check ───────────────────────────────────────────

  async function checkOoHealth(): Promise<void> {
    ooChecking.value = true
    try {
      const { default: http } = await import('@/utils/http')
      const response = await http.get('/api/workpapers/onlyoffice/health')
      // 双层.data兼容: ResponseWrapperMiddleware信封 {code,message,data:{healthy:true}}
      const healthy = (response as any).data?.data?.healthy ?? (response as any).data?.healthy ?? false
      ooHealthy.value = Boolean(healthy)
    } catch {
      ooHealthy.value = false
    } finally {
      ooChecking.value = false
    }
  }

  onMounted(() => { checkOoHealth() })

  // ─── Computed ──────────────────────────────────────────────────────────

  /** OO是否可用 */
  const isOoAvailable = computed(() => ooHealthy.value === true)

  /** 当前是否结构化模式 */
  const isStructured = computed(() => currentMode.value === 'structured')

  /** 当前是否在线编辑模式 */
  const isOnlineEdit = computed(() => currentMode.value === 'online-edit')

  /** 在线编辑禁用提示 */
  const ooDisabledTooltip = computed(() => {
    if (ooChecking.value) return '正在检查在线编辑服务...'
    if (!isOoAvailable.value) return '在线编辑服务不可用'
    return ''
  })

  // ─── Mode Switch ───────────────────────────────────────────────────────

  function switchMode(mode: EditorMode): void {
    if (mode === 'online-edit' && !isOoAvailable.value) return
    currentMode.value = mode
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    currentMode,
    ooHealthy,
    ooChecking,
    isOoAvailable,
    isStructured,
    isOnlineEdit,
    ooDisabledTooltip,
    switchMode,
    checkOoHealth,
  }
}
