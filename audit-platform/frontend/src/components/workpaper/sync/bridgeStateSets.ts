/**
 * 桥的**状态集合**（纯数据）。从 `useWorkpaperSyncBridge.ts` 迁出，桥原样 re-export，
 * 既有 import 路径不变。
 *
 * spec: oo-return-to-form-dead-end-and-save-speed · R1.4 / R1.5
 */
import type { WorkpaperSyncBridgeState } from './workpaperSyncBridgeMachine'

/**
 * AC 4.8 的阻断集：这些状态下关闭/刷新/路由离开必须提示用户。
 *
 * 🔴 `applied` **在**集合里：结构化回写已完成但 HTML 还没按 result revision 重载，
 * 此刻离开会让用户下次看到旧 revision 并以为回写丢了（Property 14）。
 * `oo_editing` **不在**集合里 —— 它靠 `dirty` 单独判定，否则打开编辑器就永远走不掉。
 *
 * 🔴 `forcesave_frozen` **不在**集合里（2026-10-24 移出）：冻结态的 request 要么已就地终结
 * （Command Service 无回调终态），要么从未被受理（`dispatch_error`），没有任何东西在飞。
 * 放在集合里的后果是真栈实测的死路：`leaveBlockReason` 恒非空 ⇒ 未改动也离不开、
 * 工具栏「同步中…」常亮、关页弹「离开此网站」—— 而界面让用户「再重新保存」只会再拿一次
 * 返回码 4（和平药房 D2 room g12 两次 `cs_error=4`）。冻结态有没有未保存的东西由 `dirty` 判。
 */
export const WP_BRIDGE_IN_FLIGHT_STATES: readonly WorkpaperSyncBridgeState[] = [
  'flushing',
  'committing',
  'materializing',
  'oo_loading',
  'descriptor_mounted',
  'confirming_descriptor',
  'forcesave_requesting',
  'forcesave_accepted',
  'waiting_application',
  'incoming_durable',
  'application_bound',
  'merging',
  'rematerializing',
  'conflict',
  'refresh_required',
  'applied',
  'recovery_claiming',
  // 🔴 后台合并两态**刻意不在**集合里（R4.3）：文件已在服务端耐久、合并由服务端照常完成，
  //    关页 / 切页不该弹「离开此网站」。
]

/**
 * 可以交给后台合并的状态（R4）：文件已在服务端耐久，之后的合并不再需要编辑器。
 * `waiting_application` 不在内 —— OnlyOffice 还没把文件交回来，关编辑器可能丢改动。
 */
export const WP_BRIDGE_BACKGROUND_MERGE_SOURCE_STATES: readonly WorkpaperSyncBridgeState[] = [
  'incoming_durable',
  'application_bound',
  'merging',
  'rematerializing',
]

/** 后台合并的两态（mode=html）：前者表单只读等结果，后者表单可用、横幅给原因与出口。 */
export const WP_BRIDGE_BACKGROUND_MERGE_STATES: readonly WorkpaperSyncBridgeState[] = [
  'merging_in_background',
  'background_merge_failed',
]

/**
 * 可以（重新）发强制保存命令的状态集合。
 *
 * 🔴 `forcesave_frozen` 必须在内，否则「允许重试」只是说法：转换表里
 * `forcesave_frozen --forcesave_started--> forcesave_requesting` 本来就在（design
 * §retryOperation「重试只重发命令，不重新冻结 request」），但 `canForcesave` 只认
 * `oo_editing` ⇒ 宿主的保存按钮 `:disabled="!canForcesave"` 永久灰掉。
 *
 * `forcesaveUnlocked` 仍是硬前提（在 `canForcesave` 里与本集合取合），没拿到
 * confirm-descriptor 成功响应之前一律不放行。
 */
export const WP_BRIDGE_FORCESAVE_READY_STATES: readonly WorkpaperSyncBridgeState[] = [
  'oo_editing',
  'forcesave_frozen',
]

/**
 * 在线编辑里「等用户动作、不会自己推进」的状态 —— 宿主据此显示「退出在线编辑」。
 *
 * 每一个都必须在转换表里接受 `reset`（判据逐条核对），否则按钮亮起后点了就抛。
 * 冲突 / 恢复待认领的裁决面板生产零挂载，退出是这些状态当前唯一的出口；
 * `conflict` / `refresh_required` 仍在 in-flight 集合里（关页要提示），退出须用户确认。
 */
export const WP_BRIDGE_EXIT_STATES: readonly WorkpaperSyncBridgeState[] = [
  'forcesave_frozen',
  'error',
  'conflict',
  'refresh_required',
  'close_authorization_stale',
  'recovery_pending',
  'duplicate',
  'recovery_download_only',
  'close_recovery_required',
]

/**
 * 编辑器可直接操作（不盖遮罩）的状态。
 *
 * 冻结态必须在内：它的提示让用户在编辑器里按回车确认单元格后再保存，遮罩挡着就做不到
 * （截图形态：红字说「请在编辑器内先点一下」，整块编辑区却是灰的、点不进去）。
 */
export const WP_BRIDGE_UNMASKED_STATES: readonly WorkpaperSyncBridgeState[] = [
  'oo_editing',
  'forcesave_frozen',
]
