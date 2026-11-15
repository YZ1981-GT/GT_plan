/**
 * Git tree OID 校验（spec platform-global-display-settings-closure 13A）。
 *
 * `vite.config.ts` 与前端运行时共用同一份形态判据：40 位小写十六进制。
 * 单独成模块是为了让 Vite config（Node 环境）与浏览器端都能 import，
 * 不把 git 调用或 DOM 逻辑带进任一侧。
 */
export const TREE_OID_RE = /^[0-9a-f]{40}$/

/** 判断字符串是否是合法 Git tree OID。 */
export function isTreeOid(value: unknown): value is string {
  return typeof value === 'string' && TREE_OID_RE.test(value)
}
