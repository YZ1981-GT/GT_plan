/**
 * J1-6 计提情况检查表 —— 短期薪酬区行身份（与 OnlyOffice 侧模板行身份对齐）
 *
 * 🔴 短期薪酬区（`J1-6-short-term`）是**模板预置骨架行**：19 行固定、Tab 内无增删/排序操作。
 * 其行身份必须与 OO 侧一致 —— 模板 `计提情况检查表J1-6` R17:R35 经 instrumentation 盖的是
 * `GTROW-J16S-{行号4位}`。若 HTML 自铸 `acr-*`，两侧身份不相交，OO 物化会把 HTML 19 行当新行
 * 插在骨架之后（真 OO 往返实测 38 行、第二分区整体下移）。
 *
 * 真 OO 往返守卫：backend/scripts/e2e/verify_j1_oo94_roundtrip.py
 * 后端身份真源：phase5_j1_06_accrual_check（TEMPLATE_ID_J106='J16S'，FIRST_DATA_ROW_J106=17）
 */
import skeleton from './j1AccrualSkeleton.json'

export const SHORT_TERM_TEMPLATE_ID = skeleton.templateId
export const SHORT_TERM_TEMPLATE_FIRST_ROW = skeleton.firstRow
export const SHORT_TERM_SKELETON_ROWS: ReadonlyArray<Readonly<{ label: string; indent: number }>> = skeleton.rows
const TEMPLATE_ROW_ID_PREFIX = `GTROW-${SHORT_TERM_TEMPLATE_ID}-`

/** 第 index 条骨架行（0 起）对应的模板行身份。 */
export function shortTermTemplateRowId(index: number): string {
  if (!Number.isInteger(index) || index < 0) throw new RangeError(`非法骨架行下标 ${index}`)
  const row = String(SHORT_TERM_TEMPLATE_FIRST_ROW + index).padStart(4, '0')
  return `${TEMPLATE_ROW_ID_PREFIX}${row}`
}

/** 仅接受本表、本位置的精确模板身份；任意 `GTROW-*` 前缀不构成合法性。 */
export function isExpectedTemplateRowId(id: unknown, index: number): boolean {
  return typeof id === 'string' && id === shortTermTemplateRowId(index)
}

/**
 * 历史载荷兼容：旧版用 `acr-*` 自铸身份。该区 19 行固定且无增删/排序 ⇒ 数组下标与骨架行一一对应，
 * 可**一次性**换绑到模板行身份。只在行数恰为骨架行数时做，否则原样返回（不猜）；已是模板身份的行不动。
 * 返回新数组，不改入参。
 */
export function bindShortTermTemplateIds<T extends { id: string }>(rows: T[], skeletonCount: number): T[] {
  if (rows.length !== skeletonCount) return rows
  if (rows.every((r, i) => isExpectedTemplateRowId(r.id, i))) return rows
  return rows.map((r, i) => (
    isExpectedTemplateRowId(r.id, i) ? r : { ...r, id: shortTermTemplateRowId(i) }
  ))
}

/**
 * Excel `ROUND(x, 2)` 同口径（四舍五入、远离零）。模板 `G=ROUND(D*F,2)` / `I=G-H`，
 * HTML 派生值必须同口径，否则两侧显示值差分位。先按 1e-9 修正二进制误差（如 1.005*100=100.4999…）。
 */
export function roundHalfAwayFromZero2(x: number): number {
  if (!Number.isFinite(x)) return 0
  const sign = x < 0 ? -1 : 1
  return (sign * Math.round(Math.abs(x) * 100 + 1e-9)) / 100
}

/** 与模板 G=ROUND(D*F,2)、I=G-H 完全同号。 */
export function calculateAccrualAmounts(baseAmount: number, rate: number, actual: number) {
  const estimated = roundHalfAwayFromZero2(baseAmount * rate)
  const diff = roundHalfAwayFromZero2(estimated - actual)
  return { estimated, diff }
}
