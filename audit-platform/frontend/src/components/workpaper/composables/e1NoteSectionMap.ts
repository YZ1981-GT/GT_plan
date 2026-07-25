/**
 * E1 货币资金披露 ↔ 附注章节冻结映射与 sync payload 构建
 *
 * 权威来源：note_template_listed.json 五、1 / note_template_soe.json 八、1「货币资金」
 * （sheet 结构见 E1 底稿「附注披露信息(上市公司)/(国企)」披露表）。
 *
 * 底稿 → 附注单向推送（sync_from_workpaper）：
 *  - sub_table_data 各子表 → 附注 table_data.sub_table_data（读时投影为 _tables 渲染）
 *  - sub_table_data._note_texts → 附注 text_content（文本框内容与披露表保持一致）
 *  - columns → _sub_table_columns（投影器据此产出扁平表头，附注模块渲染）
 *
 * 表结构对齐附注模板（附注模块 el-table 仅支持单级表头，故不推送外币多级表头表；
 * 外币信息按模板归属附注五、81 外币货币性项目，不落 五、1/八、1）：
 *  - listed 五、1：单表「货币资金」（项目/期末余额/上年年末余额）
 *  - soe 八、1：主表「货币资金」（项目/期末余额/期初余额）+「受限制的货币资金明细」
 */
import type { ColumnDef } from './disclosureColumnDefs'

export type E1DisclosureVariant = 'listed' | 'soe'

export const E1_NOTE_SECTION = {
  listed: '五、1',
  soe: '八、1',
} as const satisfies Record<E1DisclosureVariant, string>

// 底稿披露 sheet 真实 tab 名（半角括号，见 workpaper_sheet_classification wp_code=E1）。
// 用真实 sheet 名而非合成标识，使附注「打开同步底稿」(_last_sync_sheet) 反向跳转也能精确定位。
export const E1_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息(上市公司)',
  soe: '附注披露信息(国企)',
} as const satisfies Record<E1DisclosureVariant, string>

export function resolveE1CurrentStandard(
  variant: E1DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): string {
  const list = (applicableStandards || []).map((s) => String(s).toLowerCase())
  if (variant === 'listed') {
    if (list.some((s) => s === 'listed_consolidated' || (s.includes('listed') && s.includes('consol')))) {
      return 'listed_consolidated'
    }
    return 'listed_standalone'
  }
  if (list.some((s) => s === 'soe_consolidated' || (s.includes('soe') && s.includes('consol')))) {
    return 'soe_consolidated'
  }
  return 'soe_standalone'
}

const AMT = 'amount' as const
const TXT = 'text' as const

// ─── 列头元数据（逐字取自附注模板 五、1/八、1 + E1TabDisclosure 披露表列）──────
// listed 主表：项目/期末余额/上年年末余额（模板 五、1 headers）
const MAIN_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'end_amount', label: '期末余额', format: AMT },
  { key: 'prior_amount', label: '上年年末余额', format: AMT },
]
// soe 主表：项目/期末余额/期初余额（模板 八、1 headers）
const MAIN_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'end_amount', label: '期末余额', format: AMT },
  { key: 'prior_amount', label: '期初余额', format: AMT },
]
// soe 受限表：项目/期末余额/期初余额 + 受限原因（原因为审计师录入的真实披露内容，非杜撰）
const RESTRICTED_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'end_amount', label: '期末余额', format: AMT },
  { key: 'prior_amount', label: '期初余额', format: AMT },
  { key: 'reason', label: '受限原因', format: TXT },
]

// ─── 快照行类型（组件层传入，字段与 E1TabDisclosure 行接口对齐）───────────────
export interface E1MainRowLike {
  key: string
  label: string
  endingAmount: number
  openingAmount: number
}
export interface E1RestrictedRowLike {
  item: string
  openingAmount: number
  endingAmount: number
  reason: string
}

export interface E1DisclosureSnapshot {
  /** 主披露表行（含合计/其中：存放境外，label 直接来自披露表） */
  mainRows: E1MainRowLike[]
  /** 受限制货币资金明细（仅 soe），可空 */
  restrictedRows?: E1RestrictedRowLike[]
  /** 披露说明文本（文本框内容），与披露表保持一致后同步到附注 text_content */
  noteText: string
}

export interface E1SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)

/** 主表行 key → 是否合计行（合计标 is_total 供投影器识别加粗）。 */
function isTotalKey(key: string): boolean {
  return key === 'total'
}

/**
 * 构建 E1 → 附注 sync-from-workpaper 载荷。
 * listed：单表「货币资金」；soe：主表「货币资金」+「受限制的货币资金明细」。
 */
export function buildE1SyncPayload(
  variant: E1DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snapshot: E1DisclosureSnapshot,
): E1SyncPayload {
  const mainRow = (r: E1MainRowLike) => ({
    label: r.label,
    end_amount: num(r.endingAmount),
    prior_amount: num(r.openingAmount),
    ...(isTotalKey(r.key) ? { is_total: true } : {}),
  })

  const subTableData: Record<string, unknown> = {
    货币资金: snapshot.mainRows.map(mainRow),
    _note_texts: buildNoteTexts(variant, snapshot.noteText),
  }

  const columns: Record<string, ColumnDef[]> = {
    货币资金: variant === 'soe' ? MAIN_COLUMNS_SOE : MAIN_COLUMNS_LISTED,
  }

  if (variant === 'soe') {
    const restricted = snapshot.restrictedRows ?? []
    const endTotal = restricted.reduce((s, r) => s + num(r.endingAmount), 0)
    const openTotal = restricted.reduce((s, r) => s + num(r.openingAmount), 0)
    subTableData['受限制的货币资金明细'] = [
      ...restricted.map((r) => ({
        label: r.item,
        end_amount: num(r.endingAmount),
        prior_amount: num(r.openingAmount),
        reason: String(r.reason ?? ''),
      })),
      { label: '合计', end_amount: endTotal, prior_amount: openTotal, reason: '', is_total: true },
    ]
    columns['受限制的货币资金明细'] = RESTRICTED_COLUMNS
  }

  return {
    wp_id: wpId,
    sheet_name: E1_DISCLOSURE_SHEET_NAME[variant],
    section_id: E1_NOTE_SECTION[variant],
    current_standard: resolveE1CurrentStandard(variant, applicableStandards),
    sub_table_data: subTableData,
    columns,
  }
}

/** 披露说明 → _note_texts（仅非空），保证附注 text_content 与披露表文本框一致。 */
export function buildNoteTexts(
  variant: E1DisclosureVariant,
  noteText: string,
): Array<{ section: string; title: string; text: string }> {
  const text = String(noteText ?? '').trim()
  if (!text) return []
  return [{ section: `${variant}-note`, title: '货币资金说明', text }]
}
