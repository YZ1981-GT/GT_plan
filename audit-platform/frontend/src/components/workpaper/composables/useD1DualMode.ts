/**
 * useD1DualMode — D1 监盘核查组通用双模式切换 composable
 *
 * Spec: .kiro/specs/d1-inspection-check/
 * Task: 19.3
 *
 * 职责：
 * - 将 4 个 D1 Vue 组件（D1TabInventoryCount/D1TabRelatedPartyCheck/
 *   D1TabPledgeCheck/D1TabSamplingVouching）中重复的 HTML↔OnlyOffice
 *   双模式切换逻辑抽取为可复用模块
 * - 提供 editorMode/isOOMode/ooHealthy/modeOptions/ooSheetName reactive 状态
 * - 提供 checkOOHealth/switchMode 方法
 * - onMounted 自动执行健康检查
 *
 * Requirements: 20.3
 */
import { ref, computed, onMounted, type Ref } from 'vue'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface UseD1DualModeOptions {
  /** 底稿 ID（reactive） */
  wpId: Ref<string>
  /** 当前 sheet 中文名，用于 OO 组件的 sheet-name prop */
  sheetName: string
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * 通用双模式切换 composable
 *
 * @example
 * ```ts
 * const { editorMode, isOOMode, ooHealthy, modeOptions, ooSheetName, checkOOHealth, switchMode }
 *   = useD1DualMode({ wpId, sheetName: '应收票据监盘表D1-10' })
 * ```
 */
export function useD1DualMode(options: UseD1DualModeOptions) {
  const { wpId, sheetName } = options

  // ─── State ─────────────────────────────────────────────────────────────────

  const editorMode = ref<'html' | 'oo'>('html')
  const ooHealthy = ref(true)

  // ─── Computed ──────────────────────────────────────────────────────────────

  const modeOptions = computed(() => [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'oo', disabled: !ooHealthy.value },
  ])

  const isOOMode = computed(() => editorMode.value === 'oo')
  const ooSheetName = computed(() => sheetName)

  // ─── Methods ───────────────────────────────────────────────────────────────

  /**
   * 检查 OnlyOffice 服务健康状态
   * 健康则 ooHealthy=true，否则 false（禁用"在线编辑"选项）
   */
  async function checkOOHealth(): Promise<void> {
    try {
      const health = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
      ooHealthy.value = health.data?.data?.healthy ?? health.data?.healthy ?? false
    } catch {
      ooHealthy.value = false
    }
  }

  /**
   * 切换编辑模式
   * @param mode - 目标模式 'html' | 'oo'
   */
  function switchMode(mode: 'html' | 'oo'): void {
    editorMode.value = mode
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────────

  // 自动在 mount 时检查 OO 健康状态
  onMounted(checkOOHealth)

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    editorMode,
    ooHealthy,
    modeOptions,
    isOOMode,
    ooSheetName,
    checkOOHealth,
    switchMode,
  }
}

export default useD1DualMode
