/**
 * useTraceEntry — 统一溯源入口 composable
 *
 * Feature: platform-global-hardening
 * Requirements: 8.3
 *
 * 收敛 ReportTracePanel 与 GtIndexChip 两套溯源入口为单一 TraceDrawer 入口。
 * 任何模块（底稿 tab / 报表 / 试算表 / 附注）调用 openTrace(addr, value) 即可
 * 打开溯源抽屉，展示完整链路。
 */
import { ref, readonly } from 'vue'

export interface TraceEntryState {
  /** 抽屉是否可见 */
  visible: boolean
  /** 目标地址（addr_id、科目代码、坐标等） */
  targetAddr: string
  /** 目标金额 */
  targetValue: number | null
  /** 项目 ID（从调用点传入或从路由解析） */
  projectId: string
}

// ─── 模块级单例状态 ───
const state = ref<TraceEntryState>({
  visible: false,
  targetAddr: '',
  targetValue: null,
  projectId: '',
})

/**
 * 打开溯源抽屉
 *
 * @param addr - 目标地址（addr_id 或坐标，如 "1122" / "D2-1!B5"）
 * @param value - 目标金额（可选）
 * @param projectId - 项目 ID（可选，未传时使用上次设置的值）
 */
export function openTrace(
  addr: string,
  value?: number | null,
  projectId?: string,
): void {
  state.value = {
    visible: true,
    targetAddr: addr,
    targetValue: value ?? null,
    projectId: projectId || state.value.projectId,
  }
}

/**
 * 关闭溯源抽屉
 */
export function closeTrace(): void {
  state.value.visible = false
}

/**
 * 设置项目 ID（一般在主入口初始化时调用）
 */
export function setTraceProjectId(projectId: string): void {
  state.value.projectId = projectId
}

/**
 * useTraceEntry — 统一溯源入口 hook
 *
 * 在 App.vue 或 layout 层使用此 hook 绑定 TraceDrawer 的 props；
 * 在底稿 tab / GtIndexChip / ReportTracePanel 中直接调用 openTrace(addr, value)。
 *
 * @example
 * ```vue
 * // Layout 层（绑定 TraceDrawer）
 * const { state, setVisible } = useTraceEntry()
 * <TraceDrawer
 *   v-model:visible="state.visible"
 *   :target-addr="state.targetAddr"
 *   :target-value="state.targetValue"
 *   :project-id="state.projectId"
 * />
 *
 * // 消费端（底稿 tab / 报表组件）
 * import { openTrace } from '@/components/trace/useTraceEntry'
 * openTrace('1122', 50000)
 * ```
 */
export function useTraceEntry() {
  return {
    /** 只读溯源状态 */
    state: readonly(state),
    /** 打开溯源抽屉 */
    openTrace,
    /** 关闭溯源抽屉 */
    closeTrace,
    /** 设置项目 ID */
    setTraceProjectId,
    /** 用于 v-model 绑定（TraceDrawer visible） */
    setVisible(val: boolean) {
      state.value.visible = val
    },
  }
}
