/**
 * checklistPayload —— `checklist_responses` 双列载荷的唯一取列规则。
 *
 * spec: `.kiro/specs/n-cycle-sync-foundation-and-first-canary` Task 10
 * 共同判据: NC-34（契约字段双列映射：remark + conclusion）
 *
 * ═══ 为什么需要它 ═══════════════════════════════════════════════════════════
 *
 * N 域旧写法是 `item.remark ?? item.conclusion`。`??` 只兜 `null/undefined`，
 * 当 `remark === ''`（空串，后端常见）而载荷在 `conclusion` 时，返回的是 `''`
 * ⇒ **整表载荷被静默丢弃**，界面回落默认行，下一次保存还会把空表写回去。
 * 真库现算 N 域 3 行载荷 **全部**在 `conclusion`、`remark` 全空 —— 旧写法在这里
 * 丢的是 100%。
 *
 * 规则（design「契约字段语义」+ lane2/lane3 共同裁定「实际非空列优先」）：
 *   1. `*-review-session-*` 键是 AI 复核会话，**解析前**排除，不当业务载荷；
 *   2. 只有一列非空 ⇒ 取它（不看后缀）—— 防 `N1-5-rows` 这类后缀例外丢载荷；
 *   3. 两列都非空 ⇒ 按后缀判：`-rows`/`-entries` 取 remark，`-disclosure-*` 取 conclusion；
 *      都不匹配 ⇒ 记冲突（返回 `conflict: true`），调用方不得猜。
 */

/** AI 复核会话键标记 —— 这类键的载荷是会话记录，不是行表 JSON。 */
export const REVIEW_SESSION_MARKER = '-review-session-'

export type PayloadColumn = 'remark' | 'conclusion'

export interface PayloadPick {
  /** 取到的文本；无载荷时为空串 */
  text: string
  /** 取自哪一列；无载荷 / 被排除时为 null */
  column: PayloadColumn | null
  /** 两列都非空且后缀无法裁决 */
  conflict: boolean
  /** 因 AI 会话白名单被排除 */
  excluded: boolean
}

function nonEmpty(v: unknown): v is string | number {
  if (v === null || v === undefined) return false
  return String(v).trim() !== ''
}

export function isReviewSessionKey(itemId: string): boolean {
  return itemId.includes(REVIEW_SESSION_MARKER)
}

function columnBySuffix(itemId: string): PayloadColumn | null {
  if (/-(?:rows|entries)$/.test(itemId)) return 'remark'
  if (/-disclosure-/.test(itemId)) return 'conclusion'
  return null
}

/** 按规则从一条 response 里取载荷。 */
export function pickPayload(
  itemId: string,
  item: { remark?: unknown; conclusion?: unknown } | null | undefined,
): PayloadPick {
  if (isReviewSessionKey(itemId)) {
    return { text: '', column: null, conflict: false, excluded: true }
  }
  if (!item) return { text: '', column: null, conflict: false, excluded: false }
  const r = nonEmpty(item.remark)
  const c = nonEmpty(item.conclusion)
  if (r && !c) return { text: String(item.remark), column: 'remark', conflict: false, excluded: false }
  if (c && !r) return { text: String(item.conclusion), column: 'conclusion', conflict: false, excluded: false }
  if (!r && !c) return { text: '', column: null, conflict: false, excluded: false }
  const col = columnBySuffix(itemId)
  if (col === null) return { text: '', column: null, conflict: true, excluded: false }
  return { text: String(item[col]), column: col, conflict: false, excluded: false }
}

/** 取文本（冲突 / 排除 / 无载荷都返回空串）。 */
export function payloadText(
  itemId: string,
  item: { remark?: unknown; conclusion?: unknown } | null | undefined,
): string {
  return pickPayload(itemId, item).text
}

/** 取 JSON；解析失败返回原文（保留原文不覆盖），无载荷返回 null。 */
export function payloadJson(
  itemId: string,
  item: { remark?: unknown; conclusion?: unknown } | null | undefined,
): unknown {
  const text = payloadText(itemId, item)
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}
