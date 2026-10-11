/**
 * 统一桥的「失败归一」：把 HTTP / 本地异常收成 `WorkpaperSyncBridgeError`（三个互斥分桶）。
 *
 * 从 `useWorkpaperSyncBridge.ts` 原样搬出（行数门禁 whitelist 注释给的拆分方向：抽伴生模块）。
 * 本模块全是**无闭包**的纯函数与常量；桥 import 并 re-export，既有 import 路径一律不变。
 */
import {
  WorkpaperSyncContractError,
  WP_SYNC_STALE_IDENTITY_CODES,
  classifySyncFailure,
  type WorkpaperSyncFailureVerdict,
} from './workpaperSyncDto'
import { WP_BRIDGE_STATE_TEXT } from './workpaperSyncBridgeMachine'

// ═══════════════════════════════════════════════════════════════════════════
// 1. 失败归一
// ═══════════════════════════════════════════════════════════════════════════

/**
 * scope / 授权失败的**唯一**合成码。
 *
 * 服务端把「不存在 / 已 retire / 跨 scope / 无 visibility」四种原因压成同一个 404，
 * 响应体是纯字符串 `资源不存在或不可访问`，**没有** `error_code`。前端因此必须自己
 * 合成一个码才能分型，而这个码刻意**不区分**那四种原因 —— 区分开就等于泄露存在性。
 */
export const WP_BRIDGE_NON_DISCLOSURE_CODE = 'sync_scope_not_visible_or_forbidden'

/**
 * **没有任何服务端 `error_code`** 的失败（本地 flush/reload 钩子抛错、网络中断、超时、
 * 5xx 纯文本）的唯一合成码。
 *
 * 🔴 必须与 `WP_BRIDGE_NON_DISCLOSURE_CODE` 分开：两者共用一个码会让「统一 404 的
 * 存在性不泄露」与「本地钩子抛了个普通 Error」在 UI 上不可区分，而前者不可重试、
 * 后者恰恰是 AC 4.4 要求「保持 OO 并允许重试」的那一类。
 */
export const WP_BRIDGE_LOCAL_FAILURE_CODE = 'sync_step_failed_without_server_code'

/**
 * axios「请求被取消」判据（`utils/http.ts` 的请求去重层 `AbortController.abort()`）。
 *
 * 🔴 为什么要在桥里单独识别它、且**绝不**记进 `lastError`/`error` 态：
 * D4 整册的 40+ 张子 sheet **共用同一个 entryId**（`xlsx/gt-d4-operating-revenue`），
 * 于是 `read_store_projection` / `materialize` 在不同子 sheet 间是**同一个 URL**。
 * 用户切页签后再点「在线编辑」，http.ts 去重层会把上一发在飞的同 URL 请求 `abort()`
 * —— 这是**纯 UI 竞态**，不是同步失败：真正落库/授权/身份都没发生任何错误。
 *
 * 若把它当普通失败（`readWireError` 看不出它是 cancel：无 response、message 恰好是
 * `'canceled'`），就会弹出「同步失败: canceled」红色遮罩，而且因 `lastError` 是 sticky
 * （Property 48）永不消退。全仓其余保存路径（`useD4FormData`/`WpPopupMixedForm` 等
 * 十余处）都对 canceled 做了同款短路，唯独 sync 目录漏了这一处 —— 此判据补齐它。
 */
export function isRequestCanceled(error: unknown): boolean {
  const e = (error ?? {}) as { code?: unknown; name?: unknown; message?: unknown; __CANCEL__?: unknown }
  return (
    e.code === 'ERR_CANCELED' ||
    e.name === 'CanceledError' ||
    e.__CANCEL__ === true ||
    e.message === 'canceled'
  )
}

/** 合成码的中文文案：可诊断（说得出是 scope/授权面）但不透露对象是否存在。 */
const NON_DISCLOSURE_TEXT = '该同步对象不可访问：请确认项目/底稿/条目范围与当前权限'

/**
 * materialize「该底稿尚无已发布版本」的服务端码（`SubstrateNotPublishedError.error_code`）。
 *
 * 唯一触发按需首版的码（spec d2-online-edit-platform-closure R7）。值必须出现在生成的
 * `WP_SYNC_REJECTION_STATUS` 里 —— 由 `bridgeFirstPublication.spec.ts` 钉住，后端改名即红。
 */
export const SUBSTRATE_NOT_PUBLISHED_CODE = 'materialize_substrate_not_published'

/**
 * 服务端直取（`materialize-from-store`）判「该 entry 不是 store 型」的码 ⇒ 桥回落客户端路径。
 *
 * 只收这两个：其余 store 阶段拒绝（无契约 / 不在 manifest / 无 adapter）客户端路径同样会被拒，
 * 回落只会多打一次请求、把真实原因换成第二次失败。值必须等于后端
 * `StoreProjectionNotBackedError` / `StoreProjectionProviderNotAllowedError` 的 `error_code`
 * （`test_store_materialize.py` 读本文件钉住，后端改名即红）。
 */
export const SERVER_STORE_FALLBACK_CODES: ReadonlySet<string> = new Set([
  'entry_not_store_backed',
  'provider_module_not_allowed',
])

export interface WorkpaperSyncBridgeError {
  readonly stage: string
  readonly httpStatus: number | null
  readonly errorCode: string
  readonly message: string
  readonly verdict: WorkpaperSyncFailureVerdict
  readonly staleIdentity: boolean
}

interface WireErrorShape {
  response?: { status?: unknown; data?: unknown }
  code?: unknown
  message?: unknown
}

/** 从 axios 风格的异常里取 `(status, error_code, message)`。 */
export function readWireError(error: unknown): {
  status: number | null
  errorCode: string
  message: string
} {
  if (error instanceof WorkpaperSyncContractError) {
    return { status: null, errorCode: error.code, message: error.message }
  }
  const shape = (error ?? {}) as WireErrorShape
  const rawStatus = shape.response?.status
  const status = typeof rawStatus === 'number' && Number.isInteger(rawStatus) ? rawStatus : null
  const data = shape.response?.data as { detail?: unknown; message?: unknown } | undefined
  // 🔴 **平台真实响应信封是 `{code, message}`，不是 FastAPI 原生的 `{detail}`**。
  //
  // `backend/app/middleware/error_handler.http_exception_handler` 是全局注册的：
  //     content={"code": exc.status_code, "message": exc.detail}
  // ⇒ router 用 `HTTPException(detail={"error_code":…, "message":…})` 抛的 domain error，
  //   到前端是 **`data.message`** 里的对象，**根本没有 `data.detail` 键**。
  //   真栈实测原文：{"code":500,"message":{"error_code":"excel_extract_identity_carrier_missing",
  //                                       "message":"entry xlsx/gt-d4-operating-revenue: …"}}
  //
  // 此前这里只读 `data.detail` ⇒ `errorCode` 恒空 ⇒ **所有** sync domain error 都落第三桶
  // （`WP_BRIDGE_LOCAL_FAILURE_CODE` + `unregistered`），于是 `classifySyncFailure` 的全部
  // 分派（stale identity 三门 / 可重试 / 409·422·403 区分）在生产上从未生效，后端写的中文
  // 根因整段丢失（用户只看到 axios 的 `Request failed with status code 500`），且 500 被判
  // 可重试 ⇒ 对确定性失败无意义重试 3 次（真栈实测 materialize 500 ×3）。
  //
  // `detail` 仍优先：它更贴近 FastAPI 语义，也覆盖「绕过全局 handler 直接返回原生形状」的场景。
  // 判据：`__tests__/bridgeFailureRealEnvelope.spec.ts`（既有 22+ 条判据一律 mock `detail`，
  // 是个生产上不存在的形状 —— 全绿而生产失效，本仓库反复登记的「假绿第①源」）。
  const detail = data?.detail !== undefined ? data.detail : data?.message
  let errorCode = ''
  let message = typeof shape.message === 'string' ? shape.message : ''
  if (detail !== null && typeof detail === 'object' && !Array.isArray(detail)) {
    const wire = detail as Record<string, unknown>
    if (typeof wire.error_code === 'string') errorCode = wire.error_code.trim()
    if (typeof wire.message === 'string' && wire.message.trim() !== '') {
      message = wire.message
    }
  } else if (typeof detail === 'string' && detail.trim() !== '') {
    // 统一 404/403 的纯字符串 detail —— 逐字保留不能当 error_code 用。
    message = detail
  }
  return { status, errorCode, message }
}

/**
 * 归一成 `WorkpaperSyncBridgeError`。**三个互斥分桶，三个互不相同的码。**
 *
 * | 分桶 | 判据 | 码 | 可重试 |
 * |---|---|---|---|
 * | 业务失败 | 响应体带 `detail.error_code` | 服务端原码 | `classifySyncFailure` 裁决 |
 * | scope/授权 | 无码且 403/404（统一响应体是纯字符串） | `WP_BRIDGE_NON_DISCLOSURE_CODE` | 否 |
 * | 本地/传输 | 完全没有码（钩子抛错、断网、超时、5xx 纯文本） | `WP_BRIDGE_LOCAL_FAILURE_CODE` | 无响应或 500/503 时是 |
 *
 * 🔴 第三桶**不能**转交 `classifySyncFailure` —— 它对空 `error_code` 会抛
 * `failure_error_code_missing`。那条拒绝是给「服务端返回业务失败却漏了码」用的判据，
 * 拿它兜住本地钩子抛错会有两个后果：①原始异常被替换成一个看不懂的契约错误，
 * ②`lastError` 根本没来得及被记住，于是 Property 48 的粘性 error 直接失效。
 * 这条正是本任务写判据时打红抓到的真实缺陷。
 */
export function describeBridgeFailure(stage: string, error: unknown): WorkpaperSyncBridgeError {
  const wire = readWireError(error)
  if (wire.errorCode !== '') {
    const verdict = classifySyncFailure({ httpStatus: wire.status, errorCode: wire.errorCode })
    return {
      stage,
      httpStatus: wire.status,
      errorCode: wire.errorCode,
      message: wire.message || WP_BRIDGE_STATE_TEXT.error,
      verdict,
      staleIdentity: (WP_SYNC_STALE_IDENTITY_CODES as readonly string[]).includes(wire.errorCode),
    }
  }
  if (wire.status === 404 || wire.status === 403) {
    return {
      stage,
      httpStatus: wire.status,
      errorCode: WP_BRIDGE_NON_DISCLOSURE_CODE,
      message: NON_DISCLOSURE_TEXT,
      verdict: {
        httpStatus: wire.status,
        errorCode: WP_BRIDGE_NON_DISCLOSURE_CODE,
        canEnterEditing: false,
        retryableOperation: false,
        canForcesave: false,
        unregistered: false,
      },
      staleIdentity: false,
    }
  }
  // 无响应（本地/网络）或 5xx 纯文本：可重试面沿用 DTO 的登记规则（500/503），
  // 完全没有响应时按「可重试」处理 —— AC 4.4 明文要求超时/命令失败保持 OO 并允许重试。
  const retryable = wire.status === null || wire.status === 500 || wire.status === 503
  return {
    stage,
    httpStatus: wire.status,
    errorCode: WP_BRIDGE_LOCAL_FAILURE_CODE,
    message: wire.message || WP_BRIDGE_STATE_TEXT.error,
    verdict: {
      httpStatus: wire.status,
      errorCode: WP_BRIDGE_LOCAL_FAILURE_CODE,
      canEnterEditing: false,
      retryableOperation: retryable,
      canForcesave: false,
      unregistered: true,
    },
    staleIdentity: false,
  }
}
