/**
 * K7 递延收益 披露 ↔ 附注章节映射与 sync payload 构建
 *
 * 权威来源：note_template_variant_matrix.json di_yan_shou_yi
 *   listed: 五、51 / soe: 八、56 ／ account_code: 2401
 *
 * 列头口径实证见 spec `disclosure-columns-coverage-rollout`
 * design §批 2 列头清查 §8：
 *   · 两版源模板均为**单行表头**（上市 A7:F7 / 国企 A7:E7 零跨列合并）→ 标签列标
 *     `flat: true`。🔴 **必须标**：不标时后端 `_infer_groups_from_headers` 会把
 *     `本期增加`/`本期减少` 归到凭空的「本期」父表头下（实跑已复现）。
 *     校验预设 F51-3「期初 + 本期增加 − 本期减少 = 期末（每行独立）」证实这 4 个
 *     金额列是**并列值列**而非「本期」下的子列。
 *   · label 逐字取自附注模版（`上市报表附注.md` L4948 / `国企报表附注.md` L3972）
 *     + `note_template_{listed,soe}.json` 五、51 / 八、56 `headers[]`。
 *     国企标签列源 xlsx A7 = `项目/类别` → 冲突，取附注口径 `项目`。
 *   · 🔴 变体列集不同（T4）：上市 5 个值列（末列 `形成原因`）／国企 4 个值列
 *     —— 国企源 xlsx 只 5 列、附注模版只 5 列、note headers 只 5 项，且底稿国企
 *     `DisclosureRow` **连 `reason` 字段都没有** → `values` 必须按变体分支。
 *   · 底稿两张 UI 表（与资产相关 / 与收益相关）列集相同、附注只有 1 张表 →
 *     两表行拼成一个列表推送（现状做法正确，保留）。
 *   · 国企 表2「其中：递延收益-政府补助情况」（10 列，预设 F51-4/5/7/7a~7d）
 *     底稿已补录入区块（`K7TabDisclosureSoe` 政府补助明细表）→ **条件表**语义：
 *     源模板红字「仅披露金额重大的政府补助项目」→ 有行才推；无行时不推空表
 *     （`_source=workpaper` 下推空表会整表覆盖模板骨架）**且进 `_removed_table_keys`**，
 *     否则用户删空所有行后附注会永久残留上次推送的过时数据（孤儿表）。
 *     ⚠️ 与 K3「应付利息/应付股利」不同 —— 那两张**压根没有录入区块**，
 *     不属本载荷所有，故只跳过、不 removed。
 */
import type { ColumnDef } from './disclosureColumnDefs'

export type K7DisclosureVariant = 'listed' | 'soe'

export const K7_NOTE_SECTION = {
  listed: '五、51',
  soe: '八、56',
} as const satisfies Record<K7DisclosureVariant, string>

/**
 * 同步载荷 `sheet_name` = 源 xlsx 真实中文 tab 名（逐字，实测 `wb.sheetnames`）。
 * ⚠️ 国企版写的是「**国有企业**」而非「国企」，源模板即如此。
 */
export const K7_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const satisfies Record<K7DisclosureVariant, string>

/**
 * 附注子表名，逐字 = `note_template_*.json` 五、51 / 八、56 的 `tables[].name`
 *
 * 🔴 `grantDetail` **只存在于国企版**（八、56 表2）→ 变体化清单见
 * `K7_LISTED_SUBTABLE` / `K7_SOE_SUBTABLE`，契约测试必须按变体传，
 * 否则上市侧 P1 会因模板无该表而红。
 */
export const K7_SUBTABLE = {
  deferredIncome: '递延收益',
  grantDetail: '其中：递延收益-政府补助情况',
} as const

/** 上市（五、51）只有主表 */
export const K7_LISTED_SUBTABLE = {
  deferredIncome: K7_SUBTABLE.deferredIncome,
} as const

/** 国企（八、56）主表 + 政府补助明细表 */
export const K7_SOE_SUBTABLE = {
  deferredIncome: K7_SUBTABLE.deferredIncome,
  grantDetail: K7_SUBTABLE.grantDetail,
} as const

// ─── 列定义 ──────────────────────────────────────────────────────────────────

/** 递延收益变动表列头（上市 6 列含 `形成原因`；国企 5 列） */
function buildDeferredIncomeColumns(variant: K7DisclosureVariant): ColumnDef[] {
  const cols: ColumnDef[] = [
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'begin_amount', label: '期初余额', format: 'amount' },
    { key: 'increase', label: '本期增加', format: 'amount' },
    { key: 'decrease', label: '本期减少', format: 'amount' },
    { key: 'end_amount', label: '期末余额', format: 'amount' },
  ]
  if (variant === 'listed') {
    cols.push({ key: 'reason', label: '形成原因', format: 'text' })
  }
  return cols
}

/**
 * 国企 表2「其中：递延收益-政府补助情况」列头（10 列，单行表头 → 标签列标 `flat`）。
 * label / key 逐字取自 `note_template_soe.json` 八、56 `tables[1]`（模板侧为真源，
 * 平台铁律：列键对齐既有模板/映射，不反向改模板）。
 */
function buildGrantDetailColumns(): ColumnDef[] {
  return [
    { key: 'grant_item', label: '补助项目', is_label: true, flat: true },
    { key: 'begin_amount', label: '期初余额', format: 'amount' },
    { key: 'new_grant', label: '本期新增补助金额', format: 'amount' },
    { key: 'to_pl', label: '本期计入损益金额', format: 'amount' },
    { key: 'pl_line_item', label: '本期计入损益的列报项目', format: 'text' },
    { key: 'refund', label: '本期返还的金额', format: 'amount' },
    { key: 'other_change', label: '其他变动', format: 'amount' },
    { key: 'end_amount', label: '期末余额', format: 'amount' },
    { key: 'grant_kind', label: '与资产相关/与收益相关', format: 'text' },
    { key: 'refund_reason', label: '本期返还的原因', format: 'text' },
  ]
}

/** K7 上市（五、51）子表列头，键 = `sub_table_data` 数据键 */
export function buildK7ListedColumns(): Record<string, ColumnDef[]> {
  return { [K7_SUBTABLE.deferredIncome]: buildDeferredIncomeColumns('listed') }
}

/**
 * K7 国企（八、56）子表列头，键 = `sub_table_data` 数据键
 *
 * `includeGrant` 默认 true（覆盖率 sweep 空入参调用须返回完整列集 + 契约 P1 要求
 * 两张表都有列定义）；载荷侧无政府补助明细行时再剔除该键。
 */
export function buildK7SoeColumns(
  opts: { includeGrant?: boolean } = {},
): Record<string, ColumnDef[]> {
  const { includeGrant = true } = opts
  const cols: Record<string, ColumnDef[]> = {
    [K7_SUBTABLE.deferredIncome]: buildDeferredIncomeColumns('soe'),
  }
  if (includeGrant) cols[K7_SUBTABLE.grantDetail] = buildGrantDetailColumns()
  return cols
}

// ─── Payload 构建 ─────────────────────────────────────────────────────────────

export interface K7DisclosureRow {
  /** 补助项目（底稿 `assetRelatedRows`/`incomeRelatedRows` 的 `project`） */
  project: string
  beginBalance: number
  increase: number
  decrease: number
  /** 形成原因 —— **仅上市版底稿有此字段、附注也仅上市版有此列** */
  reason?: string
}

/**
 * 国企 表2「其中：递延收益-政府补助情况」行（仅国企版）。
 *
 * 期末余额为派生列，不接受入参（勾稽：期初 + 新增 − 计入损益 − 返还 − 其他变动）。
 */
export interface K7GrantDetailRow {
  grantItem: string
  beginBalance: number
  newGrant: number
  toPl: number
  plLineItem?: string
  refund: number
  otherChange: number
  grantKind?: string
  refundReason?: string
}

/** F51-7a~7d：期末余额 = 期初 + 本期新增 − 本期计入损益 − 本期返还 − 其他变动 */
export function grantDetailEndAmount(r: K7GrantDetailRow): number {
  return num(r.beginBalance) + num(r.newGrant) - num(r.toPl) - num(r.refund) - num(r.otherChange)
}

export interface K7SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

function resolveCurrentStandard(variant: K7DisclosureVariant): string {
  return variant === 'listed' ? 'listed_standalone' : 'soe_standalone'
}

function num(v: number | undefined | null): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0
}

export function buildK7SyncPayload(
  variant: K7DisclosureVariant,
  wpId: string,
  rows: readonly K7DisclosureRow[],
  narrativeText: string,
  /** 国企 表2 政府补助明细行（上市版无该表，传了也忽略） */
  grantRows: readonly K7GrantDetailRow[] = [],
): K7SyncPayload {
  // values 必须与 buildDeferredIncomeColumns(variant) 的非标签列 **同序同长**
  const toValues = (
    begin: number,
    increase: number,
    decrease: number,
    end: number,
    reason: string,
  ): Array<string | number> => variant === 'listed'
    ? [begin, increase, decrease, end, reason]
    : [begin, increase, decrease, end]

  const dataRows = rows.map(r => {
    const begin = num(r.beginBalance)
    const increase = num(r.increase)
    const decrease = num(r.decrease)
    // F51-3：期初 + 本期增加 − 本期减少 = 期末（底稿公式列）
    return {
      label: r.project || '',
      values: toValues(begin, increase, decrease, begin + increase - decrease, r.reason || ''),
    }
  })

  const totalBegin = rows.reduce((s, r) => s + num(r.beginBalance), 0)
  const totalIncrease = rows.reduce((s, r) => s + num(r.increase), 0)
  const totalDecrease = rows.reduce((s, r) => s + num(r.decrease), 0)

  const tableRows = [
    ...dataRows,
    {
      label: '合计',
      values: toValues(
        totalBegin,
        totalIncrease,
        totalDecrease,
        totalBegin + totalIncrease - totalDecrease,
        '',
      ),
      is_total: true,
    },
  ]

  const sub: Record<string, unknown> = {}
  sub[K7_SUBTABLE.deferredIncome] = tableRows

  // ── 国企 表2 政府补助明细（条件表：有行才推，无行则显式 removed 清理历史推送）
  const grants = variant === 'soe'
    ? grantRows.filter(g => (g.grantItem || '').trim() || grantDetailEndAmount(g) !== 0
      || num(g.beginBalance) || num(g.newGrant) || num(g.toPl) || num(g.refund) || num(g.otherChange))
    : []
  if (grants.length > 0) {
    const grantRowObjs = grants.map(g => ({
      grant_item: g.grantItem || '',
      begin_amount: num(g.beginBalance),
      new_grant: num(g.newGrant),
      to_pl: num(g.toPl),
      pl_line_item: g.plLineItem || '',
      refund: num(g.refund),
      other_change: num(g.otherChange),
      end_amount: grantDetailEndAmount(g),
      grant_kind: g.grantKind || '',
      refund_reason: g.refundReason || '',
    }))
    const sum = (pick: (g: K7GrantDetailRow) => number): number =>
      grants.reduce((s, g) => s + num(pick(g)), 0)
    sub[K7_SUBTABLE.grantDetail] = [
      ...grantRowObjs,
      {
        grant_item: '合计',
        begin_amount: sum(g => g.beginBalance),
        new_grant: sum(g => g.newGrant),
        to_pl: sum(g => g.toPl),
        pl_line_item: '',
        refund: sum(g => g.refund),
        other_change: sum(g => g.otherChange),
        end_amount: sum(grantDetailEndAmount),
        grant_kind: '',
        refund_reason: '',
        is_total: true,
      },
    ]
  } else if (variant === 'soe') {
    // 条件表关闭：清掉上次推送，避免附注永久残留过时明细
    sub._removed_table_keys = [K7_SUBTABLE.grantDetail]
  }

  // 叙述正文必须挂 sub_table_data 内（后端 `_extract_note_texts(sub_table_data)` 只认这里）
  if (narrativeText.trim()) {
    sub._note_texts = [{
      section: 'note-deferred-revenue',
      title: '递延收益说明',
      text: narrativeText.trim(),
    }]
  }

  const columns = variant === 'listed'
    ? buildK7ListedColumns()
    : buildK7SoeColumns({ includeGrant: grants.length > 0 })

  return {
    wp_id: wpId,
    sheet_name: K7_DISCLOSURE_SHEET_NAME[variant],
    section_id: K7_NOTE_SECTION[variant],
    current_standard: resolveCurrentStandard(variant),
    sub_table_data: sub,
    columns,
  }
}
