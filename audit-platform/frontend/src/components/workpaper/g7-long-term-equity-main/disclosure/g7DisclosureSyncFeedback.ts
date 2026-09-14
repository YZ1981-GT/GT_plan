/**
 * G7 披露同步的**错误反馈**（上市 / 国企两个 Tab 共用的单一真源）。
 *
 * 🔴 立项理由（2026-08-12 浏览器实测）：两个 Tab 的 `syncToDisclosureNotes()` 原先用
 * **一个 `try` 包住整条链** + 裸 `catch {}`：
 *
 *     try { persist → 构载荷 → api.post → 回写同步基线 → persist → 派发事件 → success }
 *     catch { ElMessage.warning('同步附注失败，请检查国企附注章节映射后重试') }
 *
 * 实测形态：点一次同步，页面上 `已同步 128 行到 14 个附注章节` 与
 * `同步附注失败，请检查国企附注章节映射后重试` **同时出现**，而 postgres 实况是
 * 13 个章节全部写入、`八、18` 落 10 张子表 ⇒ 那条失败提示是**误报**。
 *
 * 两重危害：
 * 1. **指向完全错误的原因**（「检查附注章节映射」）—— 章节映射没问题，真实异常被吞掉了，
 *    审计师无从排查；
 * 2. **诱使重复点击** —— 数据其实已落地，重复同步是无谓的写库。
 *
 * 修法（本模块 + 两个 Tab 的调用处）：
 * - 把链拆成 **① 真同步**（`api.post` 及其之前）与 **② 成功后的收尾**（基线回写 /
 *   persist / 派发事件）两段各自 try；
 * - ① 失败 ⇒ 附注确实没落地，报错并带**真实原因**（HTTP 状态 + 后端 detail）；
 * - ② 失败 ⇒ 附注**已落地**，绝不能报「同步失败」，改为「已同步 …；但基线回写失败」
 *   并说明后果（下次删表/改名可能在附注残留过时明细）；
 * - 两段都 `console.error` 原始异常（fail-open 吞异常是平台记过的最贵一类缺陷）。
 */

/** 后端错误信封的可能形态（`ResponseWrapperMiddleware` 包 `{code,message,data}`）。 */
interface ApiErrorLike {
  message?: unknown
  response?: {
    status?: unknown
    data?: {
      detail?: unknown
      message?: unknown
    }
  }
}

/**
 * 把异常提炼成**可排查**的一行原因：优先后端 `detail` / `message`，再退 HTTP 状态，
 * 最后退 `Error.message`；全都没有才给「未知错误」。
 *
 * 🔴 不返回空串 —— 空串会让调用处拼出「同步附注失败：」这种断尾提示，
 * 与原来的裸 catch 一样无从排查。
 */
export function describeSyncError(err: unknown): string {
  const e = (err ?? {}) as ApiErrorLike
  const detail = e.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail.trim()
  const backendMsg = e.response?.data?.message
  if (typeof backendMsg === 'string' && backendMsg.trim()) return backendMsg.trim()
  const status = e.response?.status
  if (status !== undefined && status !== null && String(status).trim()) {
    return `HTTP ${status}`
  }
  const msg = e.message
  if (typeof msg === 'string' && msg.trim()) return msg.trim()
  return '未知错误（详见浏览器控制台）'
}

/**
 * 「同步已落地、但收尾失败」的提示文案。
 *
 * @param okText 成功文案（已同步 N 行到 M 个章节…），必须原样带上 —— 用户要知道数据**已落地**。
 * @param err 收尾阶段的异常。
 */
export function describeSyncTailFailure(okText: string, err: unknown): string {
  return (
    `${okText}；但同步基线回写失败（${describeSyncError(err)}）——` +
    '附注数据**已落地、无需重试**；后果是下次在本底稿删表/改名时，' +
    '附注可能残留过时明细，届时重新点一次「同步到附注模块」即可。'
  )
}
