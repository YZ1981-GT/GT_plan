/**
 * 桥的「离开」伴生：退出在线编辑（R1.5）与离开前确认（R1.6）。从 `useWorkpaperSyncBridge.ts`
 * 迁出（桥行数门），桥原样放进返回值，宿主 / 测试的调用方式不变。
 *
 * spec: oo-return-to-form-dead-end-and-save-speed · R1.5 / R1.6
 *
 * ═══ 离开前确认（R1.6）═══
 *
 * 单元格正在输入、还没按回车时，`onDocumentStateChange` 不会报 `true` ⇒ 桥认为没有改动，
 * 「保存并回到表单模式」/「结构化视图」走 clean close，输入的内容静默丢失。宿主因此可以登记一个
 * 确认函数（实现见 `editorLeaveConfirm.ts`，用 OnlyOffice 的 `requestClose()`），clean close
 * 发 leave 之前先问它：`close` 放行，`stay`（用户在编辑器的提示里选了「取消」）则拒绝离开。
 * 没登记 ⇒ 照旧放行。确认函数必须保证一定会给出结论（「任何结论都不得重新挡住离开」）。
 */
import { computed, type Ref } from 'vue'

import { WP_BRIDGE_EXIT_STATES } from './bridgeStateSets'
import type { WorkpaperSyncBridgeMode, WorkpaperSyncBridgeState } from './workpaperSyncBridgeMachine'

export type WorkpaperSyncLeaveVerdict = 'close' | 'stay'
/** 能当场判定就同步返回（不给离开路径多加一跳异步），要等编辑器答复才返回 Promise。 */
export type WorkpaperSyncLeaveConfirmer = () =>
  | WorkpaperSyncLeaveVerdict
  | Promise<WorkpaperSyncLeaveVerdict>

/** clean close 因用户选择继续编辑而被拒的码（调用方据此不当失败显示）。 */
export const BRIDGE_LEAVE_KEPT_CODE = 'bridge_clean_close_editor_kept'

/** 是不是「用户选择继续编辑」的拒绝（宿主 / 视图开关据此不显示失败）。 */
export function isLeaveKeptRefusal(error: unknown): boolean {
  return (error as { code?: unknown } | null)?.code === BRIDGE_LEAVE_KEPT_CODE
}

/** 离开前确认的登记位。 */
export function createLeaveConfirmerSlot() {
  let current: WorkpaperSyncLeaveConfirmer | null = null
  return {
    /** 登记；返回只注销自己那一个的函数（先卸载的宿主不会注销后挂载的那个）。 */
    set(fn: WorkpaperSyncLeaveConfirmer): () => void {
      current = fn
      return () => {
        if (current === fn) current = null
      }
    },
    /** 是否放行。没登记 ⇒ 放行（同步）。 */
    allows(): boolean | Promise<boolean> {
      const verdict = current === null ? 'close' : current()
      return typeof verdict === 'string'
        ? verdict === 'close'
        : verdict.then((v) => v === 'close')
    },
  }
}

export interface BridgeExitContext {
  readonly mode: Ref<WorkpaperSyncBridgeMode>
  readonly state: Ref<WorkpaperSyncBridgeState>
  /** 尽力释放 lease（送真实 dirty，失败不抛）。 */
  bestEffortLeave(): Promise<void>
  reloadHtml(minimumRevision: number): Promise<void>
  reset(): void
  refuse(code: string, message: string): never
}

/**
 * 「退出在线编辑」：只在 mode=oo 且状态属于 `WP_BRIDGE_EXIT_STATES` 时可用（宿主据 `canExit` 显示按钮）。
 * 有改动时的确认归宿主；这里尽力释放 lease（服务端拒绝即按过期处理）、尽力重载表单（服务端可能已
 * 合并过），再 `reset` 回 html_idle。两步失败都不阻断退出。
 */
export function createBridgeExit(ctx: BridgeExitContext) {
  const canExit = computed(
    () => ctx.mode.value === 'oo' && WP_BRIDGE_EXIT_STATES.includes(ctx.state.value),
  )
  async function exitOnlineEdit(): Promise<void> {
    if (!canExit.value) {
      ctx.refuse('bridge_exit_not_available', `state=${ctx.state.value} 不提供退出在线编辑`)
    }
    await ctx.bestEffortLeave()
    try {
      await ctx.reloadHtml(0)
    } catch {
      // 表单按已加载的数据显示；不阻断退出。
    }
    ctx.reset()
  }
  return { canExit, exitOnlineEdit }
}
