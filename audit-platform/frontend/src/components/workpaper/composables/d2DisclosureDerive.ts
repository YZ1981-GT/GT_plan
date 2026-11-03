/**
 * D2 披露表逐项明细的「从底稿来源派生」——Tab 的「带入」按钮与离屏同步共用的唯一映射
 * （spec note-table-structure-formula-pull-closure R7）。
 *
 * 背景：单项计提 / 转回 / 核销 / 前五名四张表原先只有用户在披露 Tab 上点「从 D2-3 带入」「从 D2-11 带入」
 * 才会有行，离屏同步（`d2HeadlessDisclosure` → 附注刷新）拿到的是空表 ⇒ 附注里这四张表长期为空，而底稿
 * D2-3 / D2-5 / D2-11 明明已有数据。
 *
 * 口径：派生只在**用户没有录入行**时作为快照兜底（不落库、不覆盖用户录入）。派生规则与「带入」完全同一份实现，
 * 避免「Tab 带入的行」与「离屏推出去的行」两套口径来回打架（原先若只在离屏里调带入函数，用户删掉一行、下次
 * 刷新又会冒出来）。
 */
import type { D2IndividualRow, D2ReversalRow, D2Top5Row, D2WriteOffRow } from './useD2DisclosureNote'
// 与原「带入」用同一个 parseNum（`useD2FormulaEngine` 的 parseFloat 口径）：换成 shared 版会让 `12abc` 从 12 变 0
import { parseNum } from './useD2FormulaEngine'

/** 派生行不带 rowId：落库的行由「带入」补 id，快照不需要 id。 */
export type D2IndividualDerived = Omit<D2IndividualRow, 'rowId'>
export type D2ReversalDerived = Omit<D2ReversalRow, 'rowId'>
export type D2WriteOffDerived = Omit<D2WriteOffRow, 'rowId'>
export type D2Top5Derived = Omit<D2Top5Row, 'rowId'>

function rows(raw: unknown): Record<string, any>[] {
  return Array.isArray(raw) ? (raw as Record<string, any>[]).filter((r) => r && typeof r === 'object') : []
}

function text(value: unknown): string {
  return String(value ?? '').trim()
}

/** D2-3「按单项计提」子行（`D2-bd-individual-rows`）→ 披露③行：名称 + 双期坏账准备。 */
export function deriveIndividualRows(raw: unknown): D2IndividualDerived[] {
  return rows(raw)
    .filter((r) => r.isSubRow && text(r.label))
    .map((r) => ({
      name: text(r.label),
      // 账面余额两期都要人工填：D2-3 子行只给坏账准备（与「带入」口径一致）
      endAmount: 0,
      priorAmount: 0,
      provision: parseNum(r.currentAudited),
      priorProvision: parseNum(r.priorAudited),
      aging: '',
      basis: '',
    }))
}

/** D2-11 转回明细（`D2-writeoff-reversal-rows`）→ 披露⑥行。 */
export function deriveReversalRows(raw: unknown): D2ReversalDerived[] {
  return rows(raw)
    .filter((r) => text(r.debtorName) || parseNum(r.amount))
    .map((r) => ({
      companyName: text(r.debtorName),
      reversalReason: String(r.reason ?? ''),
      recoveryMethod: String(r.recoveryMethod ?? ''),
      originalBasis: String(r.originalBasis ?? ''),
      cumulativeProvision: parseNum(r.cumulativeProvision),
      amount: parseNum(r.amount),
    }))
}

/** D2-11 核销明细（`D2-writeoff-writeoff-rows`）→ 披露⑦行。 */
export function deriveWriteOffRows(raw: unknown): D2WriteOffDerived[] {
  return rows(raw)
    .filter((r) => text(r.debtorName) || parseNum(r.amount))
    .map((r) => ({
      companyName: text(r.debtorName),
      nature: String(r.receivableType ?? ''),
      amount: parseNum(r.amount),
      reason: String(r.reason ?? ''),
      procedure: String(r.approvalDoc ?? ''),
      relatedParty: String(r.isRelatedParty ?? ''),
    }))
}

/** D2-5 分析表「期末前十名」（`D2-analysis-top10`）→ 披露⑧前 5 名（合同资产与减值准备仍需手工）。 */
export function deriveTop5Rows(raw: unknown): D2Top5Derived[] {
  return rows(raw)
    .filter((r) => text(r.customerName))
    .sort((a, b) => parseNum(b.endBalance) - parseNum(a.endBalance))
    .slice(0, 5)
    .map((r) => ({
      companyName: text(r.customerName),
      arAmount: parseNum(r.endBalance),
      contractAssetAmount: 0,
      provision: 0,
    }))
}

/**
 * 派生行里「已有行没有的那些」（按单位名称去重；名称为空的行一律算新增，与原「带入」口径一致）。
 * ``nameOf`` 从两侧各自的行上取单位名称（披露行是 `companyName` / `name`）。
 */
export function missingByName<E, D>(
  existing: readonly E[],
  derived: readonly D[],
  nameOf: (row: E | D) => string,
): D[] {
  const seen = new Set((existing ?? []).map((r) => nameOf(r).trim()).filter(Boolean))
  const out: D[] = []
  for (const row of derived ?? []) {
    const name = nameOf(row).trim()
    if (name && seen.has(name)) continue
    if (name) seen.add(name)
    out.push(row)
  }
  return out
}
