/**
 * visibilityAccess — 服务端可见性拒绝的前端统一处理助手
 *
 * Feature: procedure-delegation-visibility-isolation · Task 12（组件 C16 Frontend）。
 *  - Req 12.7：收到 External_Not_Found（HTTP 404）统一显示「资源不存在或不可访问」，
 *    不显示内部拒绝原因（not_found/cross_project/out_of_scope/... 一律不透出）。
 *  - 深链拒绝后必须清理已缓存的底稿名称/正文，绝不闪现缓存内容。
 *
 * 前端不是安全边界：这些助手只统一 UX，真正的授权判定由服务端 Wp_Bound_Gate 完成。
 */

/** 统一 External_Not_Found 文案（与 workpaperApi.EXTERNAL_NOT_FOUND_MESSAGE 一致）。 */
export const EXTERNAL_NOT_FOUND_MESSAGE = '资源不存在或不可访问'

/** 判定一个 axios 错误是否为服务端 External_Not_Found（HTTP 404）。 */
export function isExternalNotFound(err: any): boolean {
  return err?.response?.status === 404
}

/**
 * 深链定位参数（只用于在目标视图内定位，绝不作为授权依据）。
 * 服务端 gate 会独立判定；前端只负责把定位参数带过去。
 */
export interface DeepLinkLocator {
  wp?: string | null
  task_id?: string | null
  sheet_key?: string | null
  definition_key?: string | null
}

/**
 * 从深链定位参数构造 router query（过滤空值）。
 * 仅当存在 ``wp``（底稿已生成）时才应构造底稿深链——nullable wp 不定位（Req 12.9）。
 */
export function buildDeepLinkQuery(loc: DeepLinkLocator): Record<string, string> {
  const q: Record<string, string> = {}
  if (loc.wp) q.wp = loc.wp
  if (loc.task_id) q.task_id = loc.task_id
  if (loc.sheet_key) q.sheet_key = loc.sheet_key
  if (loc.definition_key) q.definition_key = loc.definition_key
  return q
}

/**
 * 深链目标被拒绝（404）时清理缓存并给出统一占位。
 *
 * @param clearCache 清理已缓存名称/正文的回调（视图自行实现，如置空 detail/name/rows）。
 * @returns 统一占位文案，供视图显示。
 */
export function handleDeepLinkRejection(clearCache: () => void): string {
  clearCache()
  return EXTERNAL_NOT_FOUND_MESSAGE
}
