/**
 * 候选前端代码身份 marker（spec platform-global-display-settings-closure 13A / AC-25）。
 *
 * `vite.config.ts` 在候选模式（进程环境含 `GT_EXPECTED_CANDIDATE_TREE_OID`）下经
 * `define` 注入 `__GT_CANDIDATE_TREE_EXPECTED__` / `__GT_CANDIDATE_TREE_ACTUAL__`，
 * 两者都由 Vite config 从**自身 cwd** 的 `git rev-parse HEAD^{tree}` 解析得到
 * （actual 由 Vite config 现算、expected 来自只读环境变量）。
 *
 * 普通开发模式不注入 ⇒ 这两个全局标识符在运行时不存在，本模块必须容忍缺失，
 * 不能因此抛 ReferenceError（共享 dev server 与 `start-dev.bat` 行为保持不变）。
 *
 * marker 写到 `<html data-gt-candidate-tree-*>`，供终验 Playwright 与后端
 * `/api/health` 的 `candidate_tree` / `X-GT-Candidate-Tree-*` header 三方对拍。
 */
import { TREE_OID_RE } from './treeOid'

export interface CandidateTreeMarker {
  expected: string
  actual: string
  /** 前端自算 actual 与只读 expected 是否逐字相等。 */
  matched: boolean
}

/** 读取 Vite `define` 注入的候选树身份；非候选模式返回 null（不抛错）。 */
export function readCandidateTreeIdentity(): CandidateTreeMarker | null {
  // 必须用 typeof 判存：普通模式下 Vite 不注入，直接引用会 ReferenceError。
  const expected = typeof __GT_CANDIDATE_TREE_EXPECTED__ === 'undefined'
    ? undefined
    : __GT_CANDIDATE_TREE_EXPECTED__
  const actual = typeof __GT_CANDIDATE_TREE_ACTUAL__ === 'undefined'
    ? undefined
    : __GT_CANDIDATE_TREE_ACTUAL__
  if (typeof expected !== 'string' || typeof actual !== 'string') return null
  if (!TREE_OID_RE.test(expected) || !TREE_OID_RE.test(actual)) return null
  return { expected, actual, matched: expected === actual }
}

/**
 * 把候选树身份写入 DOM marker。
 *
 * 只在候选模式写；普通模式返回 null 且不改 DOM。
 * 身份不一致时不在这里抛错（Vite config 已在启动期硬失败），
 * 但把 `data-gt-candidate-tree-matched="false"` 暴露给验收脚本，
 * 避免「marker 存在即认为一致」的假绿。
 */
export function installCandidateTreeMarker(
  root: HTMLElement | null = typeof document === 'undefined' ? null : document.documentElement,
): CandidateTreeMarker | null {
  const identity = readCandidateTreeIdentity()
  if (!identity || !root) return identity
  root.dataset.gtCandidateTreeExpected = identity.expected
  root.dataset.gtCandidateTreeActual = identity.actual
  root.dataset.gtCandidateTreeMatched = String(identity.matched)
  return identity
}
