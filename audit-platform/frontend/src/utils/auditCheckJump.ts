/**
 * 审计检查仪表盘 — 未通过项定位跳转 / 筛选 / 置顶排序 / 依赖图循环 纯函数
 * (audit-check-review-gate-hardening Task 3.3)
 *
 * 全部为无副作用纯函数，便于单测与自查（不依赖组件状态 / 网络 / 路由实例）。
 */

/** 项目级来源占位 wp_code（与后端 PROJECT_WP_CODE 一致，无归属单张底稿，不可跳转） */
export const PROJECT_WP_CODE = '__PROJECT__'

export type CheckFilterMode = 'all' | 'failed' | 'uncovered' | 'blocking'

/** 检查项（仅取跳转/筛选/排序需要的字段，超集兼容 summary 返回项） */
export interface JumpCheck {
  wp_id?: string | null
  wp_code?: string | null
  sheet_hint?: string | null
  passed?: boolean | null
  severity?: string
}

/** 检查项所属底稿行（父级 summary workpaper 行） */
export interface JumpWp {
  wp_id?: string | null
  wp_code?: string | null
}

/** 跳转目标：底稿 id + 可选 sheet 定位 */
export interface CheckJumpTarget {
  wpId: string
  sheet?: string
}

function nonEmpty(v: unknown): v is string {
  return typeof v === 'string' && v.trim().length > 0
}

/**
 * 解析 check 的底稿定位目标（可跳性判定 · Req6.1/6.2）。
 *
 * 规则（宁可不可点也不跳错）：
 * - 项目级来源（wp_code === '__PROJECT__'，如未更正错报/附注校验汇总）→ null（不可跳）
 * - 无法解析底稿 id（chk.wp_id 与父 wp.wp_id 均空）→ null（不可跳）
 * - 否则可跳：wpId 优先取 chk.wp_id，回退父 wp.wp_id；
 *   sheet 取 chk.sheet_hint（有则带 ?sheet=，无则只跳底稿不带 sheet，绝不静默失败/跳错底稿）
 */
export function resolveCheckJumpTarget(
  chk: JumpCheck,
  parentWp?: JumpWp,
): CheckJumpTarget | null {
  const wpCode = nonEmpty(chk.wp_code) ? chk.wp_code : parentWp?.wp_code
  if (wpCode === PROJECT_WP_CODE) return null

  const wpId = nonEmpty(chk.wp_id)
    ? chk.wp_id
    : nonEmpty(parentWp?.wp_id)
      ? (parentWp!.wp_id as string)
      : null
  if (!wpId) return null

  const sheet = nonEmpty(chk.sheet_hint) ? chk.sheet_hint.trim() : undefined
  return sheet ? { wpId, sheet } : { wpId }
}

/** 是否可跳（可跳性布尔便捷判定） */
export function isCheckJumpable(chk: JumpCheck, parentWp?: JumpWp): boolean {
  return resolveCheckJumpTarget(chk, parentWp) !== null
}

/** 不可跳时的原因提示文案（Req6.2：给出明确提示，不静默失败） */
export function jumpDisabledTooltip(chk: JumpCheck, parentWp?: JumpWp): string {
  const wpCode = nonEmpty(chk.wp_code) ? chk.wp_code : parentWp?.wp_code
  if (wpCode === PROJECT_WP_CODE) return '项目级检查，无对应底稿'
  return '无法定位到底稿'
}

/**
 * 筛选判定（Req6.3）。
 * - all: 全部
 * - failed: 仅未通过（passed === false）
 * - uncovered: 仅未覆盖（passed 为 null/undefined）
 * - blocking: 仅阻断（severity === 'blocking' 且 passed === false）
 */
export function matchesCheckFilter(chk: JumpCheck, mode: CheckFilterMode): boolean {
  switch (mode) {
    case 'failed':
      return chk.passed === false
    case 'uncovered':
      return chk.passed === null || chk.passed === undefined
    case 'blocking':
      return chk.severity === 'blocking' && chk.passed === false
    case 'all':
    default:
      return true
  }
}

/**
 * 默认排序优先级（Req6.3 · 未通过与阻断置顶）：
 * 阻断(blocking+failed) > 未通过(failed) > 未覆盖(null) > 通过(passed)；同级保持原序（稳定）。
 */
export function checkSortRank(chk: JumpCheck): number {
  if (chk.passed === false) return chk.severity === 'blocking' ? 0 : 1
  if (chk.passed === null || chk.passed === undefined) return 2
  return 3 // passed === true
}

/** 稳定排序：按优先级置顶，同级保持原始相对顺序 */
export function sortChecksByPriority<T extends JumpCheck>(checks: readonly T[]): T[] {
  return checks
    .map((c, i) => ({ c, i }))
    .sort((a, b) => {
      const r = checkSortRank(a.c) - checkSortRank(b.c)
      return r !== 0 ? r : a.i - b.i
    })
    .map(x => x.c)
}

/** 依赖图有效循环（D~N 语义，含 M；排除 OTHER/Q 等无 D~N 语义） */
export const GRAPH_VALID_CYCLES: readonly string[] = [
  'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N',
]

/**
 * 由实际有检查数据的循环动态生成依赖图循环列表（Req9.2）。
 * - 仅保留 GRAPH_VALID_CYCLES 中的循环，按其固定顺序排列
 * - 无任何匹配（如项目仅 OTHER）时回退完整 D~N 列表，保证依赖图可用
 */
export function deriveGraphCycles(cyclesPresent: Iterable<string>): string[] {
  const present = new Set(cyclesPresent)
  const list = GRAPH_VALID_CYCLES.filter(c => present.has(c))
  return list.length > 0 ? list : [...GRAPH_VALID_CYCLES]
}

/**
 * 选中循环的解析（默认取动态列表第一个；当前值不在列表则回退第一个 · Req9.2）。
 */
export function resolveSelectedGraphCycle(
  current: string,
  cycles: readonly string[],
): string {
  if (cycles.length === 0) return current
  return cycles.includes(current) ? current : cycles[0]
}
