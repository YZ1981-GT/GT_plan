/**
 * D4（4）分解信息表 —— 动态类别列的稳定键分配与旧列迁移。
 *
 * 背景（本 spec Task 23，裁决门 A = ②旧值按列名迁移 + `legacy` 保留）
 * ================================================================
 *
 * 源模板 `附注披露信息（上市公司）` B46:I46 举例了四个行业（消费品 / 汽车 /
 * 能源 / 其他），而真实项目的业务板块由客户 `6001` 子科目决定（实证某项目为
 * 批发 / 零售 / 物流 / 物业与租赁 / 医疗收入 / 服务费及其他）⇒ 列必须动态。
 *
 * 列结构本身（`buildD4TransposeColumns`）与增删改名（`useD4Disclosure` 的
 * `addSection4Category` 等）**改造前已实现**，本模块只补两块真实缺口：
 *
 * 1. 🔴 **序号复用** —— 原 `nextD4CategoryKey` 取「**现有列表**最大 seq + 1」，
 *    删掉 `cat_4` 再新增又得 `cat_4`，而单元格键是 `{catKey}_{rowIdx}_{type}`
 *    ⇒ 历史 `cat_4_0_revenue` 会串到新列显示成别的行业的金额。
 *    正解 = **持久化单调计数器**（`seqCounter`），取 `max(现有最大, 计数器)+1`。
 *    与平台已登记的 H0 矩阵动态列同款结论。
 *
 * 2. **旧列迁移** —— 历史持久化的 `categories` 可能缺 `key`（更早版本按位置存），
 *    或存的是模板 seed 的 `cat0` / `cat1`（无下划线，见附注模板 JSON 的
 *    `cat0_revenue`）。迁移按**列名**匹配到当前板块，未匹配上的保留并标
 *    `isLegacy` 待人工归并，绝不静默丢弃已录数据。
 *
 * 🔴 键前缀保持 `cat_` 不改成 design.md 写的 `seg_`
 * -----------------------------------------------
 * `section4Cells` 的既有键形如 `cat_1_0_revenue`，改前缀等于让所有已录入的
 * 单元格失联（数据零丢失红线）。Property 24 的实质要求是「稳定键 + 不复用
 * 序号 + 不含中文」，与前缀字面无关。
 *
 * spec: d-cycle-four-table-extraction-and-disclosure-completion (Task 23)
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
 * Properties: 24, 25
 */

import { D4_DEFAULT_CATEGORIES, type D4TransposeCategory } from './d4DisclosureModel'

/** 稳定键前缀（与 `section4Cells` 既有键形态一致，不可改动）。 */
export const D4_SEGMENT_KEY_PREFIX = 'cat_'

/** 稳定键正则：`cat_` + 纯数字，不含中文。 */
export const D4_SEGMENT_KEY_RE = /^cat_\d+$/

/**
 * 待人工归并的旧列标记前缀。
 *
 * 迁移时无法匹配到当前板块的历史列保留为 `legacy` 列，label 前置该标记，
 * 审计师看到即知需要人工归并（而不是数据凭空消失）。
 */
export const D4_LEGACY_LABEL_MARK = '（待归并）'

/** 带迁移元信息的类别列。 */
export interface D4SegmentCategory extends D4TransposeCategory {
  /** 该列是否为「历史遗留、未匹配到当前板块」⇒ 待人工归并 */
  isLegacy?: boolean
}

/** 持久化的分解信息状态（`section4-rows` 的 remark JSON）。 */
export interface D4SegmentState {
  categories: D4SegmentCategory[]
  cells: Record<string, number | null>
  /**
   * 单调计数器：已分配过的最大 seq。
   *
   * 🔴 与 `categories` 里的最大 seq **不是**一回事 —— 删列后 categories 的
   * 最大值会回落，而本计数器只增不减，这正是「不复用已删序号」的保证。
   */
  seqCounter?: number
}

// ─────────────────────────────────────────────────────────────── 键分配

function seqOf(key: string): number {
  if (!D4_SEGMENT_KEY_RE.test(key)) return 0
  const n = Number(key.slice(D4_SEGMENT_KEY_PREFIX.length))
  return Number.isFinite(n) ? n : 0
}

/**
 * 分配下一个稳定键。
 *
 * @param categories - 当前列表（用于兼容「计数器缺失」的历史数据）
 * @param seqCounter - 持久化的单调计数器（历史数据可能没有，传 undefined）
 * @returns `{ key, seqCounter }` —— 调用方须把新的 seqCounter 一并持久化
 *
 * 🔴 取 `max(现有最大 seq, seqCounter) + 1`：
 *   - 只看 `categories` ⇒ 删列后复用已删序号（旧实现的缺陷）
 *   - 只看 `seqCounter` ⇒ 历史数据无该字段时从 1 开始，与既有列撞键
 */
export function allocateSegment(
  categories: readonly D4SegmentCategory[] | undefined,
  seqCounter?: number,
): { key: string; nextCounter: number } {
  let max = 0
  for (const c of categories ?? []) {
    const s = seqOf(c?.key ?? '')
    if (s > max) max = s
  }
  const counter = Number.isFinite(seqCounter as number) ? Number(seqCounter) : 0
  const next = Math.max(max, counter) + 1
  return { key: `${D4_SEGMENT_KEY_PREFIX}${next}`, nextCounter: next }
}

/**
 * 清理某板块列的全部单元格（键形如 `{key}_{rowIdx}_{revenue|cost}`）。
 *
 * 🔴 必须按 `{key}_` + **数字段** 精确匹配，不能裸 `startsWith(key + '_')` ——
 * 那样在 `cat_1` 与 `cat_10` 并存时，删 `cat_1` 会把 `cat_10_*` 一起误删
 * （`'cat_10_0_revenue'.startsWith('cat_1_')` 为 false，但反过来若 key 命名
 * 规则变化就会中招；此处按段解析，与命名规则解耦）。
 */
export function removeSegmentCells(
  cells: Record<string, number | null> | undefined,
  key: string,
): Record<string, number | null> {
  const out: Record<string, number | null> = {}
  for (const [k, v] of Object.entries(cells ?? {})) {
    // `cat_1_0_revenue` → segKey='cat_1'（前两段）, rest='0_revenue'
    const m = /^(cat_\d+)_(\d+)_(revenue|cost)$/.exec(k)
    if (m && m[1] === key) continue
    out[k] = v
  }
  return out
}

/**
 * 新增一个板块列（纯函数，不改入参）。
 *
 * @returns 新的 categories 与 seqCounter；label 为空时原样返回（拒绝无名列）
 */
export function appendSegment(
  state: D4SegmentState,
  label: string,
): D4SegmentState {
  const trimmed = (label ?? '').trim()
  if (!trimmed) return state
  const { key, nextCounter } = allocateSegment(state.categories, state.seqCounter)
  return {
    ...state,
    categories: [...(state.categories ?? []), { key, label: trimmed }],
    seqCounter: nextCounter,
  }
}

/**
 * 删除一个板块列，同时清理其单元格。
 *
 * 🔴 `seqCounter` **不回退** —— 否则下一次新增就会复用刚删掉的序号。
 */
export function removeSegment(state: D4SegmentState, key: string): D4SegmentState {
  const cats = (state.categories ?? []).filter((c) => c.key !== key)
  return { ...state, categories: cats, cells: removeSegmentCells(state.cells, key) }
}

// ─────────────────────────────────────────────────────────── 旧列迁移

/** 列名归一：去空白、全角括号转半角，仅用于匹配，不改写展示值。 */
function normalizeLabel(label: string): string {
  return (label ?? '')
    .replace(/\s+/g, '')
    .replace(/（/g, '(')
    .replace(/）/g, ')')
    .replace(new RegExp(D4_LEGACY_LABEL_MARK, 'g'), '')
    .trim()
}

export interface D4SegmentMigrationResult {
  state: D4SegmentState
  /** 按列名成功迁移的条数（旧 key → 新 key 的单元格搬移） */
  migrated: number
  /** 保留为 legacy 待人工归并的列 key */
  legacyKeys: string[]
  /** 本次迁移是否改变了状态（用于决定是否需要持久化） */
  changed: boolean
}

/**
 * 把历史持久化状态迁移到「本项目真实板块」上。
 *
 * 裁决门 A = ②：**旧值按列名匹配搬到新列，未匹配上的保留并标注待人工归并**。
 *
 * @param state - 历史持久化状态（可能无 seqCounter、可能是 seed 的 cat0 形态）
 * @param targetLabels - 本项目真实板块名（来自 `6001` 子科目；空数组 ⇒ 不迁移）
 *
 * 语义要点：
 * - 列名相同（归一后）⇒ 沿用**新分配的稳定键**并把该列全部单元格搬过去
 * - 目标板块在历史里没有 ⇒ 建空列（不填 0，`null` 表示未录入）
 * - 历史列在目标里没有 ⇒ **保留**，label 前置 `（待归并）`、标 `isLegacy`
 * - `targetLabels` 为空 ⇒ 原样返回（`changed=false`），避免误清空
 */
export function migrateSegments(
  state: D4SegmentState,
  targetLabels: readonly string[],
): D4SegmentMigrationResult {
  const oldCats = state.categories ?? []
  const oldCells = state.cells ?? {}

  if (!targetLabels || targetLabels.length === 0) {
    return { state, migrated: 0, legacyKeys: [], changed: false }
  }

  // 历史列按归一后的 label 建索引（同名取第一个，后续同名进 legacy）
  const byLabel = new Map<string, D4SegmentCategory>()
  const consumed = new Set<string>()
  for (const c of oldCats) {
    const norm = normalizeLabel(c?.label ?? '')
    if (!norm || byLabel.has(norm)) continue
    byLabel.set(norm, c)
  }

  let counter = Number.isFinite(state.seqCounter as number)
    ? Number(state.seqCounter)
    : 0
  for (const c of oldCats) {
    const s = seqOf(c?.key ?? '')
    if (s > counter) counter = s
  }

  const nextCats: D4SegmentCategory[] = []
  const nextCells: Record<string, number | null> = {}
  let migrated = 0

  for (const label of targetLabels) {
    const trimmed = (label ?? '').trim()
    if (!trimmed) continue

    const hit = byLabel.get(normalizeLabel(trimmed))
    const hitKeyIsStable = !!hit && seqOf(hit.key ?? '') > 0

    // 🔴 幂等的关键：命中且历史 key 已是合法稳定键 ⇒ **复用原 key**，不再分配新号。
    //   否则「对已迁移结果再迁一次」会给同一 label 反复换 key（cat_2 → cat_3 → …），
    //   而 `section4Cells` 的键内嵌 catKey ⇒ 每次迁移都在搬同一份数据、seqCounter
    //   无界增长，且外部若缓存过列 key 就会失联。
    let key: string
    if (hit && hitKeyIsStable && !consumed.has(hit.key)) {
      key = hit.key
    } else {
      counter += 1
      key = `${D4_SEGMENT_KEY_PREFIX}${counter}`
    }
    nextCats.push({ key, label: trimmed })

    if (hit && !consumed.has(hit.key)) {
      consumed.add(hit.key)
      const oldPrefix = `${hit.key}_`
      for (const [k, v] of Object.entries(oldCells)) {
        if (!k.startsWith(oldPrefix)) continue
        nextCells[`${key}_${k.slice(oldPrefix.length)}`] = v
        migrated += 1
      }
    }
  }

  // 未被消费的历史列 → legacy 保留（数据零丢失）
  const legacyKeys: string[] = []
  for (const c of oldCats) {
    if (!c?.key || consumed.has(c.key)) continue
    counter += 1
    const key = `${D4_SEGMENT_KEY_PREFIX}${counter}`
    const rawLabel = (c.label ?? '').trim() || c.key
    const label = rawLabel.startsWith(D4_LEGACY_LABEL_MARK)
      ? rawLabel
      : `${D4_LEGACY_LABEL_MARK}${rawLabel}`
    nextCats.push({ key, label, isLegacy: true })
    legacyKeys.push(key)

    const oldPrefix = `${c.key}_`
    for (const [k, v] of Object.entries(oldCells)) {
      if (!k.startsWith(oldPrefix)) continue
      nextCells[`${key}_${k.slice(oldPrefix.length)}`] = v
    }
  }

  const next: D4SegmentState = {
    categories: nextCats,
    cells: nextCells,
    seqCounter: counter,
  }
  const changed =
    JSON.stringify(next.categories) !== JSON.stringify(oldCats) ||
    JSON.stringify(next.cells) !== JSON.stringify(oldCells) ||
    next.seqCounter !== state.seqCounter

  return { state: next, migrated, legacyKeys, changed }
}

/**
 * 反序列化持久化状态（容错 + 补齐 key 与 seqCounter）。
 *
 * 历史数据三种形态都要认：
 * - 完整（`{categories, cells, seqCounter}`）
 * - 缺 `seqCounter`（本任务之前的版本）
 * - `categories[].key` 缺失或非 `cat_\d+`（更早版本 / 模板 seed 的 `cat0`）
 */
export function parseSegmentState(raw: unknown): D4SegmentState {
  const empty: D4SegmentState = {
    categories: [...D4_DEFAULT_CATEGORIES],
    cells: {},
    seqCounter: D4_DEFAULT_CATEGORIES.length,
  }
  if (raw == null || raw === '') return empty

  let data: any = raw
  if (typeof raw === 'string') {
    try {
      data = JSON.parse(raw)
    } catch {
      return empty
    }
  }
  if (!data || typeof data !== 'object') return empty

  const rawCats = Array.isArray(data.categories) ? data.categories : []
  if (rawCats.length === 0) return empty

  // 补齐 / 规整 key（保留原 key 里的合法 seq，非法的重新分配）
  let counter = Number.isFinite(data.seqCounter) ? Number(data.seqCounter) : 0
  const seen = new Set<string>()
  const cats: D4SegmentCategory[] = []
  const remap = new Map<string, string>()
  for (const c of rawCats) {
    const label = String(c?.label ?? '').trim()
    let key = String(c?.key ?? '')
    if (!D4_SEGMENT_KEY_RE.test(key) || seen.has(key)) {
      const alloc = allocateSegment(cats, counter)
      if (key) remap.set(key, alloc.key)
      key = alloc.key
      counter = alloc.nextCounter
    } else {
      const s = seqOf(key)
      if (s > counter) counter = s
    }
    seen.add(key)
    cats.push(c?.isLegacy ? { key, label, isLegacy: true } : { key, label })
  }

  const rawCells =
    data.cells && typeof data.cells === 'object' ? data.cells : {}
  const cells: Record<string, number | null> = {}
  for (const [k, v] of Object.entries(rawCells as Record<string, unknown>)) {
    let outKey = k
    for (const [from, to] of remap) {
      if (k.startsWith(`${from}_`)) {
        outKey = `${to}_${k.slice(from.length + 1)}`
        break
      }
    }
    cells[outKey] = v == null ? null : Number(v)
  }

  return { categories: cats, cells, seqCounter: counter }
}

// ═══════════════════════════════════════════════════════════════════════════
// §2 行集 —— 与源模板逐行对齐（Task 31）
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 源模板（4）表行集实证（openpyxl 直读 `D4-1至D4-4 … .xlsx`）：
 *
 * 上市 `附注披露信息（上市公司）` R48~R56 / 国企 `附注披露信息（国企）` R41~R49，
 * **两版逐行同构**：
 *
 * | 行 | 上市 | 国企 | 形态 |
 * |---|---|---|---|
 * | 主营业务 | R48 `=SUM(B49:B51)` | R41 `=SUM(B42:B44)` | 派生小计（只读） |
 * | 其中：在某一时点确认 | R49 | R42 | 可录入 |
 * | 　　　在某一时段确认 | R50 | R43 | 可录入 |
 * | （空可扩行） | R51 | R44 | 可录入，**在小计 SUM 范围内** |
 * | 其他业务 | R52 `=SUM(B53:B55)` | R45 `=SUM(B46:B48)` | 派生小计（只读） |
 * | 其中：在某一时点确认 | R53 | R46 | 可录入 |
 * | 　　　在某一时段确认 | R54 | R47 | 可录入 |
 * | 　　　租赁收入 | R55 | R48 | 可录入 |
 * | 合　计 | R56 `=B52+B48` | R49 `=B45+B41` | 派生总计（只读） |
 *
 * 🔴 改造前 `D4_TRANSPOSE_CHECK_ITEMS` 只有 3 项（时点 / 时段 / 租赁收入），
 * 丢了两个业务父行、空可扩行与合计行 —— 而「时点/时段」在源模板里**各出现两次**
 * （主营业务下 + 其他业务下），旧模型无法表达归属。
 */
export type D4SegmentRowKind = 'subtotal' | 'detail' | 'expandable' | 'total'

export interface D4SegmentRowDef {
  /** 稳定行键（进单元格键，禁用中文与序号） */
  key: string
  /** 行标签（逐字取自源模板，含缩进空格） */
  label: string
  kind: D4SegmentRowKind
  /** `subtotal` 行的被加项行键；`total` 行的被加项为两个 subtotal */
  children?: readonly string[]
}

export const D4_SEGMENT_ROWS: readonly D4SegmentRowDef[] = [
  {
    key: 'main',
    label: '主营业务',
    kind: 'subtotal',
    children: ['main_point', 'main_period', 'main_ext'],
  },
  { key: 'main_point', label: '其中：在某一时点确认', kind: 'detail' },
  { key: 'main_period', label: '      在某一时段确认', kind: 'detail' },
  { key: 'main_ext', label: '', kind: 'expandable' },
  {
    key: 'other',
    label: '其他业务',
    kind: 'subtotal',
    children: ['other_point', 'other_period', 'other_lease'],
  },
  { key: 'other_point', label: '其中：在某一时点确认', kind: 'detail' },
  { key: 'other_period', label: '      在某一时段确认', kind: 'detail' },
  { key: 'other_lease', label: '      租赁收入', kind: 'detail' },
  { key: 'total', label: '合  计', kind: 'total', children: ['main', 'other'] },
] as const

/** 可录入行键（`detail` + `expandable`）。 */
export const D4_SEGMENT_INPUT_ROW_KEYS: readonly string[] = D4_SEGMENT_ROWS.filter(
  (r) => r.kind === 'detail' || r.kind === 'expandable',
).map((r) => r.key)

/**
 * 该行是否只读（派生行：`subtotal` 小计 / `total` 合计）。
 *
 * 🔴 只读语义的**唯一判据是 `kind`**，`D4SegmentRowDef` 上没有 `readonly` 字段。
 * 组件模板曾直接写 `row.readonly`（恒 `undefined` ⇒ falsy）⇒ 父行与合计行
 * 既不加粗也**没被禁用**，用户可以直接改写派生格、把「小计 = Σ 明细」的勾稽改坏，
 * 而 `get_diagnostics` / vitest / Vite transform 四层全绿（2026-08-07 浏览器实测抓出）。
 * 故此处提供派生函数作单一真源，模板与守卫共用。
 */
export function isSegmentRowReadonly(row: Pick<D4SegmentRowDef, 'kind'>): boolean {
  return row.kind === 'subtotal' || row.kind === 'total'
}

/** 单元格键：`{catKey}_{rowKey}_{revenue|cost}`。 */
export function segmentCellKey(
  catKey: string,
  rowKey: string,
  type: 'revenue' | 'cost',
): string {
  return `${catKey}_${rowKey}_${type}`
}

/**
 * 派生某（类别, 行）的值。
 *
 * - `detail` / `expandable` ⇒ 直接取录入值
 * - `subtotal` ⇒ 其 children 的和
 * - `total` ⇒ 两个 subtotal 的和（等价于全部可录入行之和）
 *
 * 🔴 三态：全部被加项都未录入 ⇒ 返 `null`（不是 0），与平台「余额为 0 ≠ 未录入」一致。
 */
export function deriveSegmentCell(
  cells: Record<string, number | null> | undefined,
  catKey: string,
  rowKey: string,
  type: 'revenue' | 'cost',
): number | null {
  const def = D4_SEGMENT_ROWS.find((r) => r.key === rowKey)
  if (!def) return null
  const src = cells ?? {}

  if (def.kind === 'detail' || def.kind === 'expandable') {
    const v = src[segmentCellKey(catKey, rowKey, type)]
    return v == null ? null : Number(v)
  }

  let sum: number | null = null
  for (const child of def.children ?? []) {
    const v = deriveSegmentCell(src, catKey, child, type)
    if (v != null) sum = (sum ?? 0) + v
  }
  return sum
}

/**
 * 派生某行在所有类别下的横向合计。
 *
 * ⚠️ 源模板**没有**横向合计列（改造前 `buildD4TransposeColumns` 自造了
 * `total_revenue`/`total_cost` 两列）。本函数只供**底稿 UI 内部核对**使用，
 * **不得**进入推送给附注的列定义。
 */
export function segmentRowAcrossCategories(
  cells: Record<string, number | null> | undefined,
  categories: readonly D4SegmentCategory[] | undefined,
  rowKey: string,
  type: 'revenue' | 'cost',
): number | null {
  let sum: number | null = null
  for (const c of categories ?? []) {
    const v = deriveSegmentCell(cells, c.key, rowKey, type)
    if (v != null) sum = (sum ?? 0) + v
  }
  return sum
}

// ────────────────────────────────────────────── 单元格键迁移（rowIdx → rowKey）

/**
 * 旧 `rowIdx` → 新 `rowKey` 的迁移表。
 *
 * 改造前的行集是 `['在某一时点确认', '在某一时段确认', '租赁收入']`（rowIdx 0/1/2），
 * 单元格键形如 `cat_1_0_revenue`。新行集里「时点/时段」各有两处（主营业务下与
 * 其他业务下），旧数据**无法确定归属** ⇒ 按以下推断迁移：
 *
 * - `0`（在某一时点确认）→ `main_point`
 * - `1`（在某一时段确认）→ `main_period`
 * - `2`（租赁收入）→ `other_lease` —— **确定**，源模板里租赁收入只在其他业务下
 *
 * 前两项归主营业务是**推断**（多数项目主营占绝大部分），迁移后由审计师复核。
 * 🔴 绝不丢弃：无法映射的旧键一律原样保留（下游按 `D4_SEGMENT_ROWS` 取值时忽略，
 * 但数据仍在库里，可人工找回）。
 */
export const D4_LEGACY_ROW_INDEX_MAP: Readonly<Record<string, string>> = {
  '0': 'main_point',
  '1': 'main_period',
  '2': 'other_lease',
}

export interface D4CellKeyMigrationResult {
  cells: Record<string, number | null>
  /** 成功迁移的键数 */
  migrated: number
  /** 原样保留（未识别）的键 */
  kept: string[]
  changed: boolean
}

/**
 * 把 `{catKey}_{rowIdx}_{type}` 形态的旧单元格键迁移成 `{catKey}_{rowKey}_{type}`。
 *
 * 幂等：已是 rowKey 形态的键原样通过。
 */
export function migrateSegmentCellKeys(
  cells: Record<string, number | null> | undefined,
): D4CellKeyMigrationResult {
  const src = cells ?? {}
  const out: Record<string, number | null> = {}
  const kept: string[] = []
  let migrated = 0

  const validRowKeys = new Set(D4_SEGMENT_ROWS.map((r) => r.key))
  const parse = (k: string) => /^(cat_\d+)_([^_]+(?:_[^_]+)*)_(revenue|cost)$/.exec(k)

  // 🔴 必须两趟：第一趟落「已是 rowKey 形态」的键，第二趟迁移旧键并**累加**。
  //    单趟按 Object.entries 顺序处理时，若新键排在旧键之后，`out[k] = v` 会
  //    覆盖掉刚累加进去的值（守卫的「累加而非覆盖」用例正是它打红的）。
  for (const [k, v] of Object.entries(src)) {
    const m = parse(k)
    if (!m) {
      kept.push(k)
      out[k] = v
      continue
    }
    if (validRowKeys.has(m[2])) out[k] = v
  }

  for (const [k, v] of Object.entries(src)) {
    const m = parse(k)
    if (!m || validRowKeys.has(m[2])) continue
    const [, catKey, rowPart, type] = m
    const mapped = D4_LEGACY_ROW_INDEX_MAP[rowPart]
    if (!mapped) {
      kept.push(k)
      out[k] = v
      continue
    }
    const nk = segmentCellKey(catKey, mapped, type as 'revenue' | 'cost')
    const prev = out[nk]
    out[nk] = prev == null ? v : Number(prev) + Number(v ?? 0)
    migrated += 1
  }

  const changed = JSON.stringify(out) !== JSON.stringify(src)
  return { cells: out, migrated, kept, changed }
}
