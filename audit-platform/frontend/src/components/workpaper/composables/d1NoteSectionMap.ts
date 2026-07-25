/**
 * D1 应收票据披露 ↔ 附注章节冻结映射与 sync payload 构建
 *
 * 权威来源：note_template_listed.json 五、4 / note_template_soe.json 八、4「应收票据」
 * （sheet 结构见 D1 底稿「附注披露信息（上市公司）/（国企）」披露表）。
 *
 * 底稿 → 附注单向推送（sync_from_workpaper）：
 *  - sub_table_data 各子表 → 附注 table_data.sub_table_data（读时投影为 _tables 渲染）
 *  - sub_table_data._note_texts → 附注 text_content（文本框内容与披露表保持一致）
 *  - columns → _sub_table_columns（投影器据此产出扁平表头，附注模块渲染）
 */
import type { ColumnDef } from './disclosureColumnDefs'

export type D1DisclosureVariant = 'listed' | 'soe'

export const D1_NOTE_SECTION = {
  listed: '五、4',
  soe: '八、4',
} as const satisfies Record<D1DisclosureVariant, string>

export const D1_DISCLOSURE_SHEET_NAME = {
  listed: 'D1-note-listed',
  soe: 'D1-note-soe',
} as const satisfies Record<D1DisclosureVariant, string>

export function resolveD1CurrentStandard(
  variant: D1DisclosureVariant,
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

// ─── 列头元数据（逐字取自 D1TabDisclosure el-table-column / 披露表源结构）──────
const AMT = 'amount' as const
const PCT = 'percent' as const

const SUMMARY_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '票据种类', is_label: true },
  { key: 'end_balance', label: '期末账面余额', format: AMT },
  { key: 'end_provision', label: '期末坏账准备', format: AMT },
  { key: 'end_book_value', label: '期末账面价值', format: AMT },
  { key: 'prior_balance', label: '上年末账面余额', format: AMT },
  { key: 'prior_provision', label: '上年末坏账准备', format: AMT },
  { key: 'prior_book_value', label: '上年末账面价值', format: AMT },
]
const PLEDGED_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '种类', is_label: true },
  { key: 'pledged_amount', label: '期末已质押金额', format: AMT },
]
const ENDORSED_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '种类', is_label: true },
  { key: 'derecognized', label: '期末终止确认金额', format: AMT },
  { key: 'not_derecognized', label: '期末未终止确认金额', format: AMT },
]
const TRANSFER_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '种类', is_label: true },
  { key: 'transfer_amount', label: '期末转应收账款金额', format: AMT },
]
const CLASS_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '类别', is_label: true },
  { key: 'balance', label: '金额', format: AMT },
  { key: 'ratio', label: '比例(%)', format: PCT },
  { key: 'provision', label: '坏账准备', format: AMT },
  { key: 'loss_rate', label: '预期信用损失率(%)', format: PCT },
  { key: 'book_value', label: '账面价值', format: AMT },
]
const WRITEOFF_DETAIL_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '单位名称', is_label: true },
  { key: 'note_type', label: '应收票据性质', format: 'text' },
  { key: 'amount', label: '核销金额', format: AMT },
  { key: 'reason', label: '核销原因', format: 'text' },
  { key: 'procedure', label: '履行的核销程序', format: 'text' },
  { key: 'related', label: '款项是否由关联交易产生', format: 'text' },
]

// ─── 快照行类型（组件层传入，字段与 useD1Disclosure 行接口对齐）───────────────
export interface D1SummaryRowLike { category: string; endBalance: number; endProvision: number; endBookValue: number; priorBalance: number; priorProvision: number; priorBookValue: number }
export interface D1PledgedRowLike { category: string; pledgedAmount: number }
export interface D1EndorsedRowLike { category: string; derecognizedAmount: number; notDerecognizedAmount: number }
export interface D1TransferRowLike { category: string; transferAmount: number }
export interface D1ClassRowLike { label: string; balance: number; ratio: number; provision: number; lossRate: number; bookValue: number }
export interface D1WriteOffDetailRowLike { companyName: string; noteType: string; amount: number; reason: string; procedure: string; relatedPartyFlag: string }

export interface D1DisclosureSnapshot {
  summaryRows: D1SummaryRowLike[]
  summaryTotal: D1SummaryRowLike
  pledgedRows: D1PledgedRowLike[]
  pledgedTotal: D1PledgedRowLike
  endorsedRows: D1EndorsedRowLike[]
  endorsedTotal: D1EndorsedRowLike
  transferRows: D1TransferRowLike[]
  transferTotal: D1TransferRowLike
  classEndRows: D1ClassRowLike[]
  classPriorRows: D1ClassRowLike[]
  writeOffAmount: number
  writeOffDetailRows: D1WriteOffDetailRowLike[]
  /** 各子节说明文本（文本框内容），与披露表保持一致后同步到附注 text_content */
  notes: Record<string, string>
}

export interface D1SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)

/** 主表名（listed=应收票据 / soe=应收票据分类） */
function summaryTableName(variant: D1DisclosureVariant): string {
  return variant === 'soe' ? '应收票据分类' : '应收票据'
}

/**
 * 构建 D1 → 附注 sync-from-workpaper 载荷。
 * 覆盖披露表主要表格 + 全部子节说明文本（_note_texts）。
 */
export function buildD1SyncPayload(
  variant: D1DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snapshot: D1DisclosureSnapshot,
): D1SyncPayload {
  const mainName = summaryTableName(variant)

  const summaryRow = (r: D1SummaryRowLike, isTotal = false) => ({
    label: r.category,
    end_balance: num(r.endBalance),
    end_provision: num(r.endProvision),
    end_book_value: num(r.endBookValue),
    prior_balance: num(r.priorBalance),
    prior_provision: num(r.priorProvision),
    prior_book_value: num(r.priorBookValue),
    ...(isTotal ? { is_total: true } : {}),
  })
  const classRow = (r: D1ClassRowLike) => ({
    label: r.label,
    balance: num(r.balance),
    ratio: num(r.ratio),
    provision: num(r.provision),
    loss_rate: num(r.lossRate),
    book_value: num(r.bookValue),
    ...(r.label === '合计' ? { is_total: true } : {}),
  })

  const subTableData: Record<string, unknown> = {
    [mainName]: [
      ...snapshot.summaryRows.map((r) => summaryRow(r)),
      summaryRow(snapshot.summaryTotal, true),
    ],
    期末已质押的应收票据: [
      ...snapshot.pledgedRows.map((r) => ({ label: r.category, pledged_amount: num(r.pledgedAmount) })),
      { label: snapshot.pledgedTotal.category || '合计', pledged_amount: num(snapshot.pledgedTotal.pledgedAmount), is_total: true },
    ],
    期末已背书或贴现但尚未到期的应收票据: [
      ...snapshot.endorsedRows.map((r) => ({ label: r.category, derecognized: num(r.derecognizedAmount), not_derecognized: num(r.notDerecognizedAmount) })),
      { label: snapshot.endorsedTotal.category || '合计', derecognized: num(snapshot.endorsedTotal.derecognizedAmount), not_derecognized: num(snapshot.endorsedTotal.notDerecognizedAmount), is_total: true },
    ],
    期末因出票人未履约而将其转应收账款的票据: [
      ...snapshot.transferRows.map((r) => ({ label: r.category, transfer_amount: num(r.transferAmount) })),
      { label: snapshot.transferTotal.category || '合计', transfer_amount: num(snapshot.transferTotal.transferAmount), is_total: true },
    ],
    '按坏账计提方法分类（期末余额）': snapshot.classEndRows.map(classRow),
    '按坏账计提方法分类（上年年末余额）': snapshot.classPriorRows.map(classRow),
    本期实际核销的应收票据情况: [
      { label: '实际核销的应收票据', amount: num(snapshot.writeOffAmount) },
      ...snapshot.writeOffDetailRows.map((r) => ({
        label: r.companyName, note_type: r.noteType, amount: num(r.amount),
        reason: r.reason, procedure: r.procedure, related: r.relatedPartyFlag,
      })),
    ],
    _note_texts: buildNoteTexts(snapshot.notes),
  }

  const columns: Record<string, ColumnDef[]> = {
    [mainName]: SUMMARY_COLUMNS,
    期末已质押的应收票据: PLEDGED_COLUMNS,
    期末已背书或贴现但尚未到期的应收票据: ENDORSED_COLUMNS,
    期末因出票人未履约而将其转应收账款的票据: TRANSFER_COLUMNS,
    '按坏账计提方法分类（期末余额）': CLASS_COLUMNS,
    '按坏账计提方法分类（上年年末余额）': CLASS_COLUMNS,
    本期实际核销的应收票据情况: WRITEOFF_DETAIL_COLUMNS,
  }

  return {
    wp_id: wpId,
    sheet_name: D1_DISCLOSURE_SHEET_NAME[variant],
    section_id: D1_NOTE_SECTION[variant],
    current_standard: resolveD1CurrentStandard(variant, applicableStandards),
    sub_table_data: subTableData,
    columns,
  }
}

const NOTE_TITLES: Record<string, string> = {
  top: '应收票据说明',
  pledged: '已质押应收票据说明',
  endorsed: '已背书或贴现应收票据说明',
  badDebtClass: '坏账准备计提说明',
  writeOff: '应收票据核销说明',
}

/** 各子节说明 → _note_texts（仅非空），保证附注 text_content 与披露表文本框一致。 */
export function buildNoteTexts(notes: Record<string, string>): Array<{ section: string; title: string; text: string }> {
  const order = ['top', 'pledged', 'endorsed', 'badDebtClass', 'writeOff']
  const out: Array<{ section: string; title: string; text: string }> = []
  for (const key of order) {
    const text = String(notes?.[key] ?? '').trim()
    if (text) out.push({ section: `note-${key}`, title: NOTE_TITLES[key] ?? key, text })
  }
  return out
}
