/**
 * 强制保存的**送达等待**与 202 回执**分流**（桥 `switchToHtml()` 的纯逻辑半边）。
 *
 * spec: oo-return-to-form-dead-end-and-save-speed · R1.2 / R1.3
 *
 * ═══ 为什么要等「送达」═══
 *
 * OnlyOffice 的 `onDocumentStateChange`：`true` = 当前用户正在编辑，`false` = 改动已送到文档
 * 编辑服务。强制保存（Command Service `forcesave`）只保存**文档服务已经收到的**改动 ⇒ 刚改完
 * 一格就点保存，改动还在路上时会拿到返回码 4（「无改动」）。以前前端把 4 一律当「冻结、留在
 * OO、请重试」，人被关在编辑器里（和平药房 D2 room g12 两次 `cs_error=4`）；现在按后端契约
 * 「直接放行离开」，那就必须先保证 4 是可信的 —— 发命令前等最近一次状态事件回到 `false`。
 *
 * ═══ 202 的四种去向 ═══
 *
 * | 回执 | 去向 |
 * |---|---|
 * | `dispatch_error` | 冻结（命令没出站，可重试） |
 * | 无回调 + `no_changes` + 已送达 | 放行离开（契约 error 4「直接放行离开；不得无限等 callback」） |
 * | 无回调 + `no_changes` + 未送达 | 冻结，`dirty` 保留（改动可能还在路上） |
 * | 无回调 + 其它终态 | 冻结，`dirty` 保留（会话不在线 / 配置故障 ≠ 没有改动） |
 * | 其余 | 照常进入等待回传 |
 */
import { describeBridgeFailure, type WorkpaperSyncBridgeError } from './workpaperSyncBridgeFailure'
import type { WorkpaperSyncForcesaveAccepted } from './workpaperSyncDto'

/** 发强制保存前等「改动已送达」的默认上限（毫秒）。实测 OO 编辑后约 1 s 内发 `false`。 */
export const FORCESAVE_DELIVERY_WAIT_MS = 3000

/** 无改动放行离开后给用户的提示（宿主显示；不是错误）。 */
export const FORCESAVE_NO_CHANGES_LEFT_NOTICE = '在线编辑里没有需要保存的改动，已回到表单'

export interface WorkpaperSyncDeliveryTracker {
  /** 记一次 `onDocumentStateChange` 的原始值。 */
  note(raw: boolean): void
  /** 是否有已编辑、尚未送达文档服务的改动。 */
  pending(): boolean
  /**
   * 等到改动送达（最近一次原始事件为 `false`）或超时。已送达 / 从未编辑 ⇒ 立即 `true`；
   * 超时或会话被重置 ⇒ `false`。
   */
  waitDelivered(timeoutMs: number): Promise<boolean>
  /** 会话结束：清掉待送达标记，并以 `false` 结算所有等待者。 */
  reset(): void
}

export function createDeliveryTracker(): WorkpaperSyncDeliveryTracker {
  let pendingDelivery = false
  let waiters: Array<(delivered: boolean) => void> = []

  function settle(delivered: boolean): void {
    const current = waiters
    waiters = []
    for (const resolve of current) resolve(delivered)
  }

  return {
    note(raw: boolean): void {
      pendingDelivery = raw === true
      if (!pendingDelivery) settle(true)
    },
    pending(): boolean {
      return pendingDelivery
    },
    waitDelivered(timeoutMs: number): Promise<boolean> {
      if (!pendingDelivery) return Promise.resolve(true)
      return new Promise<boolean>((resolve) => {
        let done = false
        const finish = (delivered: boolean): void => {
          if (done) return
          done = true
          clearTimeout(timer)
          resolve(delivered)
        }
        const timer = setTimeout(() => finish(false), Math.max(0, timeoutMs))
        waiters.push(finish)
      })
    },
    reset(): void {
      pendingDelivery = false
      settle(false)
    },
  }
}

export type WorkpaperSyncForcesaveRoute =
  | { readonly kind: 'track' }
  | { readonly kind: 'leave_no_changes' }
  | { readonly kind: 'frozen'; readonly error: WorkpaperSyncBridgeError }

function frozenError(code: string, message: string, status: number): WorkpaperSyncBridgeError {
  return describeBridgeFailure('forcesave_dispatch', {
    response: { status, data: { detail: { error_code: code, message } } },
  })
}

/** 202 回执 + 是否已确认送达 → 去向（见模块头的表）。 */
export function routeForcesaveAccepted(
  accepted: WorkpaperSyncForcesaveAccepted,
  input: { readonly delivered: boolean },
): WorkpaperSyncForcesaveRoute {
  if (accepted.dispatchError !== null) {
    // request 已冻结、shell 已建，但 Command Service 未受理 ⇒ 保持 OO 并允许重试（AC 4.4）。
    return {
      kind: 'frozen',
      error: frozenError(accepted.dispatchError, '强制保存命令未被受理', 502),
    }
  }
  if (accepted.callbackExpected !== false) return { kind: 'track' }
  if (accepted.csOutcome === 'no_changes') {
    if (input.delivered) return { kind: 'leave_no_changes' }
    return {
      kind: 'frozen',
      error: frozenError(
        'forcesave_no_changes_undelivered',
        forcesaveTerminalMessage('no_changes_undelivered', accepted.csError),
        409,
      ),
    }
  }
  return {
    kind: 'frozen',
    error: frozenError(
      `forcesave_${accepted.csOutcome ?? 'terminal_without_callback'}`,
      forcesaveTerminalMessage(accepted.csOutcome, accepted.csError),
      409,
    ),
  }
}

/** 无回调终态的人话文案（按 Command Service 语义分型，不压成一句）。 */
export function forcesaveTerminalMessage(outcome: string | null, code: number | null): string {
  const suffix = code === null ? '' : `（Command Service 返回码 ${code}）`
  switch (outcome) {
    case 'no_changes_undelivered':
      return `改动还在发送到文档服务，本次没有保存${suffix}。请稍候几秒再保存；单元格还在输入时先按回车确认。`
    case 'doc_not_online':
      return `编辑会话已不在线，无法保存${suffix}。请点「退出在线编辑」后重新进入，再保存。`
    case 'configuration_error':
      return `OnlyOffice 服务配置异常，保存命令无法执行${suffix}。请联系管理员检查 OnlyOffice 配置。`
    default:
      return `强制保存已终结且不会有回传${suffix}：${outcome ?? '未知原因'}。`
  }
}
