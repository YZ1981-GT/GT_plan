/**
 * j1DisclosureDetailPull — J1 披露明细两表「从 J1-2 明细表带入」（纯函数）
 *
 * 背景（2026-07-30 复盘 P1）：源模板里披露表**每一行**都是对 J1-2 明细表的单元格引用
 * （上市 `A18='明细表J1-2 '!J13`、`A42='明细表J1-2 '!J38` …），但历史实现的
 * `pullFromSources()` 只覆盖汇总表 4~5 行 → 短期薪酬 12 行 + 设定提存 8 行全靠手打。
 *
 * ## 行名映射依据（全部取自源模板 Excel 公式，非猜测）
 *
 * J1-2 的项目清单比披露表更细，源模板用三种方式对应：
 *
 * | 披露行 | 源公式 | 本模块策略 |
 * |---|---|---|
 * | 工资、奖金、津贴和补贴 | `=J1-2!J13`（父行） | 精确匹配（其下「其中：」子项不重复带入） |
 * | 工伤保险费 / 生育保险费 | `=J1-2!J23` / `J24` | 精确匹配 |
 * | 其中：医疗保险费 | `=J1-2!J21+J22`（基本 + 补充医疗保险费） | 包含匹配聚合（披露名 ⊂ 明细名） |
 * | 工会经费和职工教育经费 | `=J1-2!J26+J27`（工会经费 + 职工教育经费） | 包含匹配聚合（明细名 ⊂ 披露名） |
 * | 其他短期薪酬（**仅国企**） | `=J1-2!J30+J31`（非货币性福利 + 其他短期薪酬） | `absorb` 显式别名 |
 *
 * 国企披露表**无**独立「非货币性福利」行（源模板把它并入「其他短期薪酬」），
 * 故国企侧必须传 `absorb`，否则该明细行会被当未匹配项追加成多余行。
 *
 * ## 三条防错约束
 *
 * 1. **两趟匹配**：先做全表精确匹配，再做包含聚合 —— 避免"先处理的行把后面行需要的
 *    明细项贪心吃掉"（单趟时行序会影响结果）。
 * 2. **包含匹配最短 3 字**：否则「其他」（2 字）会命中「其他短期薪酬」「其他长期职工福利」等。
 *    「其他」只走精确匹配 + **队列配对**（明细里两个「其他」按出现顺序配给披露里两个「其他」）。
 * 3. **未匹配的「其中：」子项一律跳过**：其金额已含在已匹配的父行里，追加会双算。
 *    只有未匹配且非零的**顶层**明细行才追加为新行（对齐 J1-7 的"未匹配追加"范式）。
 *
 * 金额口径 = **审定数**（未审 + 期初调整 / 账项调整），与
 * `aggregateDetailAuditedByCategory` 一致；期末由 `recalcDisclosureRow` 派生。
 *
 * spec: .kiro/specs/j1-disclosure-template-alignment/（复盘 P1-a）
 */
import { normalizeJ1Label } from './useJ1Adjudication'
import { recalcDisclosureRow, type J1DisclosureRow } from './j1DisclosureRowModel'

/** 包含匹配的最短披露行名长度（防「其他」这类 2 字词误吸） */
export const MIN_CONTAIN_LEN = 3

/** J1-2 明细行（只声明本模块读取的字段） */
export interface J1DetailPullRow {
  label?: unknown
  isSubItem?: unknown
  indent?: unknown
  unadjBegin?: unknown
  openingAdj?: unknown
  unadjIncrease?: unknown
  ajeIncrease?: unknown
  unadjDecrease?: unknown
  ajeDecrease?: unknown
}

export interface J1PullAmounts {
  begin: number
  increase: number
  decrease: number
}

export interface J1DetailPullOptions {
  /**
   * 变体专属别名：`披露行归一名 → 额外吸收的明细行归一名[]`。
   * 仅用于源模板公式明确合并的情形（国企「其他短期薪酬」吸收「非货币性福利」）。
   */
  absorb?: Readonly<Record<string, readonly string[]>>
}

export interface J1DetailPullResult {
  /** 命中并被覆盖的披露行数 */
  matched: number
  /** 未匹配而追加的顶层明细行数 */
  appended: number
  /** 未匹配且被跳过的「其中：」子项归一名（供 UI 如实提示，不臆造归属） */
  skippedSubItems: string[]
}

function num(v: unknown): number {
  const x = Number(v)
  return Number.isFinite(x) ? x : 0
}

/** 审定口径金额：未审 + 调整 */
export function auditedPullAmounts(r: J1DetailPullRow): J1PullAmounts {
  return {
    begin: num(r.unadjBegin) + num(r.openingAdj),
    increase: num(r.unadjIncrease) + num(r.ajeIncrease),
    decrease: num(r.unadjDecrease) + num(r.ajeDecrease),
  }
}

function isZero(a: J1PullAmounts): boolean {
  return a.begin === 0 && a.increase === 0 && a.decrease === 0
}

interface Candidate {
  key: string
  raw: string
  isSubItem: boolean
  amounts: J1PullAmounts
  used: boolean
}

function buildCandidates(detail: readonly J1DetailPullRow[]): Candidate[] {
  const out: Candidate[] = []
  for (const r of detail) {
    const raw = String(r.label ?? '').trim()
    const key = normalizeJ1Label(raw)
    if (!key) continue
    out.push({
      key,
      raw,
      isSubItem: Boolean(r.isSubItem) || num(r.indent) > 0,
      amounts: auditedPullAmounts(r),
      used: false,
    })
  }
  return out
}

function addInto(target: J1PullAmounts, src: J1PullAmounts): void {
  target.begin += src.begin
  target.increase += src.increase
  target.decrease += src.decrease
}

/** 精确匹配（队列配对：同名明细行按出现顺序配给同名披露行） */
function takeExact(candidates: Candidate[], key: string): Candidate | null {
  const hit = candidates.find((c) => !c.used && c.key === key)
  if (!hit) return null
  hit.used = true
  return hit
}

/** 包含聚合：披露名 ⊂ 明细名（医疗保险费 ← 基本/补充医疗保险费）或反向（工会经费和职工教育经费 ← 工会经费 + 职工教育经费） */
function takeContained(candidates: Candidate[], key: string): Candidate[] {
  if (key.length < MIN_CONTAIN_LEN) return []
  const hits = candidates.filter(
    (c) =>
      !c.used &&
      (c.key.includes(key) || (c.key.length >= MIN_CONTAIN_LEN && key.includes(c.key))),
  )
  for (const h of hits) h.used = true
  return hits
}

/**
 * 把 J1-2 明细表的审定数带入披露明细表（就地修改 `rows`）。
 *
 * 只覆盖匹配到的行；未匹配的披露行保持原值（不清零手工录入）。
 */
export function applyDetailPullToDisclosureRows(
  rows: J1DisclosureRow[],
  detail: readonly J1DetailPullRow[],
  options: J1DetailPullOptions = {},
): J1DetailPullResult {
  const candidates = buildCandidates(detail)
  const absorb = options.absorb ?? {}
  const targets = rows
    .map((row, index) => ({ row, index, key: normalizeJ1Label(row.label) }))
    .filter((t) => !t.row.isSubtotal && t.key)

  const picked = new Map<number, J1PullAmounts>()

  // ── 第 1 趟：精确匹配 + absorb 别名 ───────────────────────────────────
  for (const t of targets) {
    const hit = takeExact(candidates, t.key)
    if (!hit) continue
    const acc: J1PullAmounts = { ...hit.amounts }
    for (const alias of absorb[t.key] ?? []) {
      const extra = takeExact(candidates, normalizeJ1Label(alias))
      if (extra) addInto(acc, extra.amounts)
    }
    picked.set(t.index, acc)
  }

  // ── 第 2 趟：包含聚合（只处理第 1 趟未命中的披露行） ──────────────────
  for (const t of targets) {
    if (picked.has(t.index)) continue
    const hits = takeContained(candidates, t.key)
    if (hits.length === 0) continue
    const acc: J1PullAmounts = { begin: 0, increase: 0, decrease: 0 }
    for (const h of hits) addInto(acc, h.amounts)
    picked.set(t.index, acc)
  }

  for (const [index, amounts] of picked) {
    const row = rows[index]
    row.beginBalance = amounts.begin
    row.increase = amounts.increase
    row.decrease = amounts.decrease
    recalcDisclosureRow(row)
  }

  // ── 未匹配项：顶层非零行追加；「其中：」子项跳过（金额已含在父行，追加会双算） ──
  const category = rows.find((r) => r.category)?.category ?? ''
  const skippedSubItems: string[] = []
  let appended = 0
  let seq = 0
  for (const c of candidates) {
    if (c.used || isZero(c.amounts)) continue
    if (c.isSubItem) {
      skippedSubItems.push(c.raw || c.key)
      continue
    }
    seq += 1
    const row: J1DisclosureRow = {
      id: `pull-${category || 'row'}-${Date.now()}-${seq}`,
      label: c.raw,
      category,
      beginBalance: c.amounts.begin,
      increase: c.amounts.increase,
      decrease: c.amounts.decrease,
      endBalance: 0,
    }
    recalcDisclosureRow(row)
    rows.push(row)
    appended += 1
  }

  return { matched: picked.size, appended, skippedSubItems }
}

/**
 * 国企「其他短期薪酬」吸收「非货币性福利」（源模板 `B28='明细表J1-2 '!J30+J31`）。
 *
 * 上市披露表有独立「非货币性福利」行（`A32=J1-2!J30`）→ **不得**套用本别名。
 */
export const J1_SOE_SHORT_TERM_ABSORB: Readonly<Record<string, readonly string[]>> = {
  其他短期薪酬: ['非货币性福利'],
}
