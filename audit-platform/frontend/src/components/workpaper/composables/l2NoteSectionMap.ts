/**
 * l2NoteSectionMap — L2 应付利息 披露表↔附注模块 联动映射
 *
 * 权威来源：
 * - `note_template_variant_matrix.json` · `qi_ta_ying_fu_kuan`（五、42 / 八、42）
 * - 源 xlsx `backend/wp_templates/L/L2 应付利息.xlsx` 的
 *   `附注披露（上市公司）信息` / `附注披露（国企）信息`
 * - 落点子表 = K3 章节（五、42 / 八、42）内的「应付利息」+「重要的逾期未付利息」
 *
 * 🔴 裁决 A（spec l-cycle-…completion R4）：该子表的写权从 K3 收敛到 L2。
 *    K3 侧改只读展示 + 引导跳转，buildK3SyncPayload 停止推送这两张表。
 *    L2 与 K3 在同一章节内表名零交集 → 走既有表级浅合并，不需要行级合并。
 *
 * spec: .kiro/specs/l-cycle-extraction-formula-and-disclosure-completion/ R4
 */
import { defineColumns, type ColumnDef } from './disclosureColumnDefs'

export type L2DisclosureVariant = 'listed' | 'soe'

export const L2_NOTE_SECTION = {
  listed: '五、42',
  soe: '八、42',
} as const satisfies Record<L2DisclosureVariant, string>

export const L2_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露（上市公司）信息',
  soe: '附注披露（国企）信息',
} as const satisfies Record<L2DisclosureVariant, string>

/** Listed 侧子表名（逐字取自附注模板 五、42 的 tables[].name） */
export const L2_LISTED_SUBTABLE = {
  interest: '应付利息',
  overdue: '重要的逾期未付利息',
} as const

/** Soe 侧子表名（与 listed 不同名，禁统一） */
export const L2_SOE_SUBTABLE = {
  interest: '应付利息',
  overdue: '重要的已逾期未支付的利息情况',
} as const

// ── 列定义（逐字对齐 note_template columns key）────────────────────────────

/** Listed 应付利息列 */
export function buildL2ListedInterestColumns(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'end_amount', label: '期末数', format: 'amount', align: 'right' },
    { key: 'prior_amount', label: '上年年末数', format: 'amount', align: 'right' },
  ])
}

/** Listed 逾期利息列 */
export function buildL2ListedOverdueColumns(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'overdue_amount', label: '逾期金额', format: 'amount', align: 'right' },
    { key: 'overdue_reason', label: '逾期原因', format: 'text' },
  ])
}

/** Soe 应付利息列 */
export function buildL2SoeInterestColumns(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'end_amount', label: '期末余额', format: 'amount', align: 'right' },
    { key: 'prior_amount', label: '期初余额', format: 'amount', align: 'right' },
  ])
}

/** Soe 逾期利息列 */
export function buildL2SoeOverdueColumns(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'overdue_amount', label: '逾期金额', format: 'amount', align: 'right' },
    { key: 'overdue_reason', label: '逾期原因', format: 'text' },
  ])
}

export function buildL2ListedColumns(): Record<string, ColumnDef[]> {
  return {
    [L2_LISTED_SUBTABLE.interest]: buildL2ListedInterestColumns(),
    [L2_LISTED_SUBTABLE.overdue]: buildL2ListedOverdueColumns(),
  }
}

export function buildL2SoeColumns(): Record<string, ColumnDef[]> {
  return {
    [L2_SOE_SUBTABLE.interest]: buildL2SoeInterestColumns(),
    [L2_SOE_SUBTABLE.overdue]: buildL2SoeOverdueColumns(),
  }
}

// ── 行集（两版不对称是源模板事实，不得对齐）──────────────────────────────────

/**
 * Listed 应付利息 7 行 —— 逐字取自 `note_template_listed.json` §五、42 的
 * `tables[].rows[].label`（已连库 repr 核实，含**反斜杠** `优先股\永续债`）。
 *
 * 🔴 listed 模板**无「其他」行**（soe 才有「其他利息」）⇒ 底稿侧 `useL2Disclosure`
 * 的第 7 行「其他」在 listed 推送时必须**丢弃**，否则附注表会多出一行。
 */
export const L2_LISTED_INTEREST_ROWS: readonly string[] = [
  '分期付息到期还本的长期借款利息',
  '企业债券利息',
  '短期借款应付利息',
  '划分为金融负债的优先股\\永续债利息',
  '其中：工具1',
  '工具2',
  '合计',
]

/** Soe 应付利息 6 行（无「其中：工具1/工具2」，有「其他利息」） */
export const L2_SOE_INTEREST_ROWS: readonly string[] = [
  '分期付息到期还本的长期借款利息',
  '企业债券利息',
  '短期借款应付利息',
  '划分为金融负债的优先股\\永续债利息',
  '其他利息',
  '合计',
]

/** 某变体的模板行标签集（推送时用于过滤模板不存在的行） */
function templateLabelSet(variant: L2DisclosureVariant): ReadonlySet<string> {
  return new Set(variant === 'listed' ? L2_LISTED_INTEREST_ROWS : L2_SOE_INTEREST_ROWS)
}

// ── Payload 构建 ─────────────────────────────────────────────────────────────

export interface L2InterestRow {
  label: string
  endAmount: number
  priorAmount: number
}

export interface L2OverdueRow {
  label: string
  overdueAmount: number
  overdueReason: string
}

export interface L2SyncPayload {
  note_section: string
  sheet_name: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  _sub_table_columns: Record<string, ColumnDef[]>
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * 底稿侧展示字面 → 附注模板行字面的归一化映射。
 *
 * 🔴 必需（2026-08-15 复盘实测）：`useL2Disclosure` 的行标签用**半角斜杠**
 * `划分为金融负债的优先股/永续债利息`，而附注模板 `八、42`/`五、42` 的
 * `rows[].label` 是**反斜杠** `划分为金融负债的优先股\永续债利息`（已连库 repr 核实）。
 * 不归一化则投影器按 label 匹配失败 ⇒ 附注侧新增一行而非填充既有行（表变 7 行）。
 * 同理 soe 模板第 5 行是「其他利息」而底稿侧是「其他」。
 *
 * 归一化只改**推送载荷**，不动 `useL2Disclosure` 的只读展示（那是源模板 UI 字面）。
 */
const LABEL_TO_TEMPLATE: Readonly<Record<string, string>> = {
  '划分为金融负债的优先股/永续债利息': '划分为金融负债的优先股\\永续债利息',
}

/** soe 侧额外映射：底稿「其他」→ 模板「其他利息」 */
const LABEL_TO_TEMPLATE_SOE: Readonly<Record<string, string>> = {
  ...LABEL_TO_TEMPLATE,
  其他: '其他利息',
}

function normalizeLabel(raw: string, variant: L2DisclosureVariant): string {
  const s = String(raw ?? '').trim()
  const table = variant === 'soe' ? LABEL_TO_TEMPLATE_SOE : LABEL_TO_TEMPLATE
  return table[s] ?? s
}

/**
 * 构建 L2 同步载荷。
 *
 * 🔴 只推自己负责的两张子表（应付利息 + 逾期利息），
 *    五、42/八、42 内其余子表（其他应付款/应付股利等）由 K3 负责、原样保留。
 *    不得声明 _removed_table_keys 指向 K3 的子表。
 */
export function buildL2SyncPayload(
  variant: L2DisclosureVariant,
  interestRows: readonly L2InterestRow[],
  overdueRows: readonly L2OverdueRow[],
): L2SyncPayload {
  const subtable = variant === 'listed' ? L2_LISTED_SUBTABLE : L2_SOE_SUBTABLE
  const columns = variant === 'listed' ? buildL2ListedColumns() : buildL2SoeColumns()

  // 归一化 label → 再按模板行集过滤（模板不存在的行不推，防附注表凭空多行）
  const allowed = templateLabelSet(variant)
  const interestData = interestRows
    .map((r) => ({
      label: normalizeLabel(String(r.label ?? ''), variant),
      end_amount: num(r.endAmount),
      prior_amount: num(r.priorAmount),
    }))
    .filter((r) => allowed.has(r.label))

  // 逾期表行标签是借款单位名（自由文本），不参与模板行匹配 ⇒ 不归一化
  const overdueData = overdueRows.map((r) => ({
    label: String(r.label ?? '').trim(),
    overdue_amount: num(r.overdueAmount),
    overdue_reason: String(r.overdueReason ?? '').trim(),
  }))

  const sub_table_data: Record<string, Record<string, unknown>[]> = {
    [subtable.interest]: interestData,
    [subtable.overdue]: overdueData,
  }

  return {
    note_section: L2_NOTE_SECTION[variant],
    sheet_name: L2_DISCLOSURE_SHEET_NAME[variant],
    sub_table_data,
    _sub_table_columns: columns,
  }
}
