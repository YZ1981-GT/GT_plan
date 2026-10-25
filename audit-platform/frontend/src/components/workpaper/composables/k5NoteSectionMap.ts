/**
 * K5 预计负债 披露 ↔ 附注章节映射与 sync payload 构建
 *
 * 权威来源：note_template_variant_matrix.json yu_ji_fu_zhai
 *   listed: 五、50 / soe: 八、55 ／ account_code: 2701
 *
 * 列头口径实证见 spec `disclosure-columns-coverage-rollout`
 * design §批 2 列头清查 §4（上市）/ §5（国企）：
 *   · 两版源模板均为**单行表头**（A6:D6 零跨列合并）→ 标签列标 `flat: true`、0 处 `group`。
 *   · label 逐字取自附注模版（`上市报表附注.md` L4930 / `国企报表附注.md` L3952）
 *     + `note_template_{listed,soe}.json` 五、50 / 八、55 `headers[]` + consol 五-50-1 / 五-55-1。
 *     源 xlsx 的 `期末数`/`期初数` 按「附注是交付物」取附注模版的 `期末余额`/`上年年末余额|期初余额`。
 *   · 校验预设 F50-1/2/3：只有 2 个数值列 + 合计行，**无变动表** → 底稿 roll-forward 的
 *     `本期增加`/`本期减少` 不进附注列（只进 `_note_texts` 叙述）。
 *   · 两版都是 4 列（末列 `形成原因`）：单体附注按底稿披露表格式（R8.4 批 9b-2，2026-10-24）。国企原为 3 列
 *     （随附注模版把形成原因降为表下注文字），而国企源 xlsx D6 就是 `形成原因`（取明细表 K5-2「预计负债计提原因」）。
 *     上市取披露页「变动说明」，国企取披露页「确认依据」（同一来源：每个预计负债项目的计提原因）。
 */
import type { ColumnDef } from './disclosureColumnDefs'

export type K5DisclosureVariant = 'listed' | 'soe'

export const K5_NOTE_SECTION = {
  listed: '五、50',
  soe: '八、55',
} as const satisfies Record<K5DisclosureVariant, string>

/**
 * 同步载荷 `sheet_name` = 源 xlsx 真实中文 tab 名（逐字，实测 `wb.sheetnames`）。
 * ⚠️ 上市版是**前全角后半角**括号 `（上市公司)`，源模板即如此，不要"修正"。
 */
export const K5_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司)',
  soe: '附注披露信息（国企）',
} as const satisfies Record<K5DisclosureVariant, string>

/** 附注子表名，逐字 = `note_template_*.json` 五、50 / 八、55 的 `tables[0].name` */
export const K5_SUBTABLE = {
  provision: '预计负债',
} as const

// ─── 列定义 ──────────────────────────────────────────────────────────────────

/** 预计负债表列头（两版 4 列含 `形成原因`，只有期初列名不同） */
function buildProvisionColumns(variant: K5DisclosureVariant): ColumnDef[] {
  return [
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'end_amount', label: '期末余额', format: 'amount' },
    { key: 'prior_amount', label: variant === 'listed' ? '上年年末余额' : '期初余额', format: 'amount' },
    { key: 'reason', label: '形成原因', format: 'text' },
  ]
}

function buildK5Columns(variant: K5DisclosureVariant): Record<string, ColumnDef[]> {
  return { [K5_SUBTABLE.provision]: buildProvisionColumns(variant) }
}

/** K5 上市（五、50）子表列头，键 = `sub_table_data` 数据键 */
export function buildK5ListedColumns(): Record<string, ColumnDef[]> {
  return buildK5Columns('listed')
}

/** K5 国企（八、55）子表列头，键 = `sub_table_data` 数据键 */
export function buildK5SoeColumns(): Record<string, ColumnDef[]> {
  return buildK5Columns('soe')
}

// ─── Payload 构建 ─────────────────────────────────────────────────────────────

export interface K5DisclosureRow {
  /** 类别（底稿 `provisionTable[].category`）→ 附注标签列 */
  project: string
  /** 期末余额 */
  endAmount: number
  /** 上年年末余额 / 期初余额 */
  priorAmount: number
  /** 形成原因（上市取披露页「变动说明」`remark`，国企取「确认依据」`basis`） */
  reason?: string
}

export interface K5SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

function resolveCurrentStandard(variant: K5DisclosureVariant): string {
  return variant === 'listed' ? 'listed_standalone' : 'soe_standalone'
}

function num(v: number | undefined | null): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0
}

export function buildK5SyncPayload(
  variant: K5DisclosureVariant,
  wpId: string,
  rows: readonly K5DisclosureRow[],
  narrativeText: string,
): K5SyncPayload {
  // values 必须与 buildProvisionColumns(variant) 的非标签列 **同序同长**
  const toValues = (endAmount: number, priorAmount: number, reason: string): Array<string | number> =>
    [endAmount, priorAmount, reason]

  const tableRows = [
    ...rows.map(r => ({
      label: r.project || '',
      values: toValues(num(r.endAmount), num(r.priorAmount), r.reason || ''),
    })),
    {
      label: '合计',
      values: toValues(
        rows.reduce((s, r) => s + num(r.endAmount), 0),
        rows.reduce((s, r) => s + num(r.priorAmount), 0),
        '',
      ),
      is_total: true,
    },
  ]

  const sub: Record<string, unknown> = {}
  sub[K5_SUBTABLE.provision] = tableRows

  // 叙述正文必须挂 sub_table_data 内（后端 `_extract_note_texts(sub_table_data)` 只认这里）
  if (narrativeText.trim()) {
    sub._note_texts = [{
      section: 'note-provisions',
      title: '预计负债说明',
      text: narrativeText.trim(),
    }]
  }

  const columns = variant === 'listed' ? buildK5ListedColumns() : buildK5SoeColumns()

  return {
    wp_id: wpId,
    sheet_name: K5_DISCLOSURE_SHEET_NAME[variant],
    section_id: K5_NOTE_SECTION[variant],
    current_standard: resolveCurrentStandard(variant),
    sub_table_data: sub,
    columns,
  }
}
