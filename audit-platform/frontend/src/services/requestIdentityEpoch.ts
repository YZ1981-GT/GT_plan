/**
 * 请求身份代际。
 *
 * 这不是 token 版本号：同一用户的 access token 自动刷新不能让正在重放的
 * 401 请求失效。它只在登录主体或会话边界明确切换时递增，用于让旧身份
 * 在途请求不能把结果交给新身份页面。
 */
let epoch = 0
const listeners = new Set<(next: number) => void>()

/** 当前逻辑身份代际。数值不含 token、用户 id 或其他敏感信息。 */
export function requestIdentityEpoch(): number {
  return epoch
}

/**
 * 推进登录会话边界，并同步通知在途订阅者。
 *
 * 调用方必须在替换本地 token / user 前调用；正常 refresh 与 token-updated
 * 广播属于同一会话，不能调用本函数。
 */
export function advanceRequestIdentityEpoch(): number {
  epoch += 1
  for (const listener of [...listeners]) listener(epoch)
  return epoch
}

/** 订阅身份切换；返回解除函数，避免每个 GET 订阅者泄漏监听器。 */
export function onRequestIdentityEpochChange(listener: (next: number) => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Vitest 专用：模块内存状态不跨用例泄漏。生产代码不应调用。 */
export function resetRequestIdentityEpochForTests(): void {
  epoch = 0
  listeners.clear()
}
