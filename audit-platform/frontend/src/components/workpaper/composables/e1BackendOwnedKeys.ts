/**
 * E1 后端独占键（公式推送引擎是唯一写入方）—— 前端只在内存里算、**不保存**。
 *
 * spec: chain-closure-phase2-formula-push-engine · design §四「键归属」 · 需求 4.5
 *
 * - `E1-adj-tb-amount-{ending,opening}`：试算平衡表数（试算表审定数，系统值）
 * - `E1-adj-total-{1001,1002,1012}[-opening]`：三科目审定合计（派生）
 * - `E1-adj-slot-{finance_co,accrued,digital}[-opening]`：披露主表语义槽（派生）
 *
 * 🔴 若前端照旧把这些键随 `flushSave` 回写，用户打开底稿期间后台推送了新值，
 *    随后一次普通保存就会用内存里的旧值覆盖它 —— 两个写入方来回覆盖（一个单元格只能有一个写入方）。
 * 用户可编辑的 `E1-adj-{itemKey}-{field}` / `-note` 照常保存（不在本集合内）。
 */
const BACKEND_OWNED = [
  /^E1-adj-tb-amount-(ending|opening)$/,
  /^E1-adj-total-(1001|1002|1012)(-opening)?$/,
  /^E1-adj-slot-(finance_co|accrued|digital)(-opening)?$/,
] as const

export function isE1BackendOwnedKey(itemId: string): boolean {
  return BACKEND_OWNED.some((re) => re.test(itemId))
}

/** 审定表防抖保存要提交的条目：`E1-adj-` 前缀、且不是后端独占键。 */
export function e1AdjudicationSaveItemIds(itemIds: Iterable<string>): string[] {
  return [...itemIds].filter((id) => id.startsWith('E1-adj-') && !isE1BackendOwnedKey(id))
}
