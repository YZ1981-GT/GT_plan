/**
 * 追踪窗口到点 / 重试之后，宿主「刷新状态」读到的 operation 快照 → 一句中文与「能否重试」
 * （spec writeback-followup-issue-closure R3.5）。
 *
 * 为什么不喂回桥：超时后桥落 sticky `error`（Property 48），状态机在 `error` 上不接受
 * `operation_observed`。快照因此只读、只在宿主上展示；回表单 / 重新进入仍走页面原有路径。
 *
 * 纯函数、不碰请求面（宿主边界：两个宿主文件都不 import HTTP）。
 */
import type { WorkpaperSyncOperationSnapshot } from './workpaperSyncDto'

export interface WorkpaperSyncOperationFollowUp {
  /** 快照的 operation 状态；取快照本身失败时为 `unavailable`。 */
  readonly state: WorkpaperSyncOperationSnapshot['state'] | 'unavailable'
  readonly message: string
}

const ASK_AGAIN = '请稍后再点「刷新状态」。'
const START_OVER = '请刷新页面后重新进入在线编辑再保存。'

/** 取快照本身失败（网络 / 服务暂不可用）时的展示。 */
export const OPERATION_FOLLOW_UP_UNAVAILABLE: WorkpaperSyncOperationFollowUp = Object.freeze({
  state: 'unavailable',
  message: `暂时取不到服务器上的回写状态，${ASK_AGAIN}`,
})

/**
 * 服务端会接受普通重试：operation 已关联回写任务（incoming 已 durable）且停在 `error`。
 * 「已关联」即 primary（`classifyOperationShape`：applicationId 非空 ⇔ primary）。
 * 重试从已保存的文件重跑 apply，不再向文档服务器发保存命令。
 */
export function snapshotIsRetryable(snapshot: WorkpaperSyncOperationSnapshot): boolean {
  return snapshot.state === 'error' && snapshot.applicationId !== null
}

function failureReason(snapshot: WorkpaperSyncOperationSnapshot): string {
  // 中文措辞由后端单源词表给（`applicationErrorMessage`），查不到登记时只回码本身。
  if (snapshot.applicationErrorMessage) return snapshot.applicationErrorMessage
  const code = snapshot.applicationErrorCode ?? snapshot.errorCode
  return code ? `错误码 ${code}` : '原因未知'
}

/** 穷尽 `WP_SYNC_OPERATION_STATES`：后端新增状态时这里编译失败，必须显式裁决。 */
export function describeOperationFollowUp(
  snapshot: WorkpaperSyncOperationSnapshot,
): WorkpaperSyncOperationFollowUp {
  const revision = snapshot.resultRevision == null ? '' : `（第 ${snapshot.resultRevision} 版）`
  const state = snapshot.state
  switch (state) {
    case 'created':
    case 'command_pending':
    case 'accepted':
    case 'waiting_application':
      return { state, message: `服务器还没收到 OnlyOffice 回传的文件，${ASK_AGAIN}` }
    case 'application_bound':
    case 'extracting':
    case 'merging':
    case 'rematerializing':
    case 'applying':
      return { state, message: `服务器正在回写这次保存，${ASK_AGAIN}` }
    case 'applied':
      return { state, message: `服务器已完成回写${revision}。请刷新页面查看最新内容。` }
    case 'refresh_required':
    case 'superseded':
      return {
        state,
        message: `服务器已合并${revision}，在线编辑里的文档需要重新打开。请刷新页面后再进入在线编辑。`,
      }
    case 'conflict': {
      const count = snapshot.conflictCount ? ` ${snapshot.conflictCount} 处` : ''
      return { state, message: `回写发现${count}冲突，需要逐项裁决。请刷新页面后按提示处理。` }
    }
    case 'duplicate':
      return { state, message: '这次保存已并入同一份回写任务。请刷新页面查看结果。' }
    case 'error':
      return {
        state,
        message: snapshotIsRetryable(snapshot)
          ? `回写失败：${failureReason(snapshot)}。可点「重试回写」用已保存的文件重新回写。`
          : `回写失败：${failureReason(snapshot)}。${START_OVER}`,
      }
    case 'rejected':
      return { state, message: `服务器拒绝了这次保存。${START_OVER}` }
    case 'authorization_stale':
      return { state, message: `发起保存的编辑者已失去编辑资格，这次保存没有落地。${START_OVER}` }
    default: {
      const unhandled: never = state
      return { state: 'unavailable', message: `服务器返回了未知状态 ${String(unhandled)}。${START_OVER}` }
    }
  }
}
