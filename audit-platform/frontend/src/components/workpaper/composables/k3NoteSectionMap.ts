/**
 * K3 其他应付款 披露 ↔ 附注章节映射与 sync payload 构建
 *
 * 权威来源（实证 2026-07-30）：
 * - 源 xlsx `backend/wp_templates/K/K3 其他应付款.xlsx` 的 `附注披露信息(上市公司)` /
 *   `附注披露信息(国企)`（**两版都是半角括号，源模板即如此，勿"修正"为全角**）：
 *   三段结构 —— ①主表「应付利息 / 应付股利 / 其他应付款」三行汇总（引 `=B17`/`=C17`）
 *   ②「（1）其他应付款（按款项性质列示）」引 `'审定表K3-1'!I8:I10 / E8:E10`
 *   ③「其中，账龄超过1年的重要其他应付款」引 `'长期挂账检查表K3-5'`。
 * - `note_template_listed.json` §五、42（**7 表**）/ `note_template_soe.json` §八、42（**6 表**）
 *   是交付物权威：主表 + 应付利息 + 逾期未付利息 + 应付股利 [+ 超1年未付股利（仅上市）]
 *   + 按款项性质列示 + 账龄超1年重要款项。
 *
 * 🔴 改造前只推主表 1 张，其余 6/5 张表在附注侧永远为空。
 * 🔴 上市表 7、国企表 6 的模板名原是泄漏名 `项  目` / md 消歧名 `其他应付款（表6）`，
 *   已由 `fix_note_k_liability_structure.py` 正名，旧键经 `_removed_table_keys` 清理。
 *
 * account_code: 2241
 *
 * spec: .kiro/specs/k-cycle-disclosure-alignment/ Task 7
 */
import { defineColumns, type ColumnDef } from './disclosureColumnDefs'

export type K3DisclosureVariant = 'listed' | 'soe'

export const K3_NOTE_SECTION = {
  listed: '五、42',
  soe: '八、42',
} as const satisfies Record<K3DisclosureVariant, string>

/** 源 xlsx 真实 tab 名 —— **半角括号**，源模板即如此，不要统一成全角 */
export const K3_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息(上市公司)',
  soe: '附注披露信息(国企)',
} as const satisfies Record<K3DisclosureVariant, string>

/** 附注子表名，逐字 = `note_template_listed.json` §五、42 的 `tables[].name` */
export const K3_LISTED_SUBTABLE = {
  summary: '其他应付款',
  interest: '应付利息',
  interestOverdue: '重要的逾期未付利息',
  dividend: '应付股利',
  dividendOverdue: '重要的超过1年未支付的应付股利',
  byNature: '其他应付款（按款项性质列示）',
  agingOver1y: '其中，账龄超过1年的重要其他应付款',
} as const

/** 附注子表名，逐字 = `note_template_soe.json` §八、42 的 `tables[].name` */
export const K3_SOE_SUBTABLE = {
  summary: '其他应付款',
  interest: '应付利息',
  interestOverdue: '重要的已逾期未支付的利息情况',
  dividend: '应付股利',
  byNature: '按款项性质列示',
  agingOver1y: '账龄超过1年的重要其他应付款项',
} as const

/** 模板改名前的旧表名（表头首格泄漏 / md 消歧产物），须从附注侧清理 */
export const K3_LEGACY_OBSOLETE_TABLES = {
  listed: ['项  目'] as readonly string[],
  soe: ['其他应付款（表6）'] as readonly string[],
} as const

// ── 模板固定行（逐字取自 note_template）──────────────────────────────────────

export const K3_SUMMARY_ROWS = {
  listed: ['应付利息', '应付股利', '其他应付款'] as readonly string[],
  soe: ['应付利息', '应付股利', '其他应付款项'] as readonly string[],
} as const

export const K3_INTEREST_ROWS = {
  listed: [
    '分期付息到期还本的长期借款利息',
    '企业债券利息',
    '短期借款应付利息',
    '划分为金融负债的优先股\\永续债利息',
    '其中：工具1',
    '工具2',
  ] as readonly string[],
  soe: [
    '分期付息到期还本的长期借款利息',
    '企业债券利息',
    '短期借款应付利息',
    '划分为金融负债的优先股\\永续债利息',
    '其他利息',
  ] as readonly string[],
} as const

export const K3_DIVIDEND_ROWS = {
  listed: [
    '普通股股利',
    '划分为权益工具的优先股\\永续债股利',
    '其中：工具1',
    '工具2',
  ] as readonly string[],
  soe: ['普通股股利', '划分为权益工具的优先股\\永续债股利', '其他'] as readonly string[],
} as const

export const K3_BY_NATURE_ROWS = {
  listed: ['押金', '质保金'] as readonly string[],
  soe: ['应付往来款', '应付保证金及押金'] as readonly string[],
} as const

export const K3_TOTAL_LABEL = '合计'

// ── 列定义 ───────────────────────────────────────────────────────────────────

function twoPeriod(labelHead: string, priorHead: string): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: labelHead, is_label: true, flat: true },
    { key: 'end_amount', label: '期末余额', format: 'amount', align: 'right' },
    { key: 'prior_amount', label: priorHead, format: 'amount', align: 'right' },
  ])
}

function overdueInterest(labelHead: string): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: labelHead, is_label: true, flat: true },
    { key: 'overdue_amount', label: '逾期金额', format: 'amount', align: 'right' },
    { key: 'overdue_reason', label: '逾期原因', format: 'text' },
  ])
}

function agingOver1y(labelHead: string, amountHead: string, reasonHead: string): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: labelHead, is_label: true, flat: true },
    { key: 'end_amount', label: amountHead, format: 'amount', align: 'right' },
    { key: 'unpaid_reason', label: reasonHead, format: 'text' },
  ])
}

/** 上市 §五、42 七张表列头（列键与模板 seed 同形） */
export function buildK3ListedColumns(): Record<string, ColumnDef[]> {
  const T = K3_LISTED_SUBTABLE
  return {
    [T.summary]: twoPeriod('项目', '上年年末余额'),
    [T.interest]: twoPeriod('项目', '上年年末余额'),
    [T.interestOverdue]: overdueInterest('借款单位'),
    [T.dividend]: twoPeriod('项目（或股东名称）', '上年年末余额'),
    [T.dividendOverdue]: defineColumns([
      { key: 'label', label: '股东名称', is_label: true, flat: true },
      { key: 'dividend_amount', label: '应付股利金额', format: 'amount', align: 'right' },
      { key: 'unpaid_reason', label: '未支付原因', format: 'text' },
    ]),
    [T.byNature]: twoPeriod('项目', '上年年末余额'),
    // 第 2 列列头以附注模版为准（源 xlsx 作「金额」）
    [T.agingOver1y]: agingOver1y('项目', '期末余额', '未偿还或未结转的原因'),
  }
}

/** 国企 §八、42 六张表列头 */
export function buildK3SoeColumns(): Record<string, ColumnDef[]> {
  const T = K3_SOE_SUBTABLE
  return {
    [T.summary]: twoPeriod('类别', '期初余额'),
    [T.interest]: twoPeriod('项目', '期初余额'),
    [T.interestOverdue]: overdueInterest('债权单位'),
    [T.dividend]: twoPeriod('项目', '期初余额'),
    [T.byNature]: twoPeriod('项目', '期初余额'),
    [T.agingOver1y]: agingOver1y('债权单位名称', '期末余额', '未偿还原因'),
  }
}

// ── 快照 → 载荷 ──────────────────────────────────────────────────────────────

/** 两期金额行（主表 / 应付利息 / 应付股利 / 按款项性质列示 共用） */
export interface K3DisclosureRow {
  project: string
  endAmount: number
  priorAmount: number
}

/** 逾期未付利息行 */
export interface K3OverdueInterestRow {
  unit: string
  amount: number
  reason?: string
}

/** 超过 1 年未支付的应付股利行（仅上市） */
export interface K3OverdueDividendRow {
  shareholder: string
  amount: number
  reason?: string
}

/** 账龄超过 1 年的重要其他应付款行 */
export interface K3AgingOver1yRow {
  name: string
  endAmount: number
  reason?: string
}

export interface K3DisclosureSnapshot {
  /** 按款项性质列示明细（主表「其他应付款」行由本表合计派生） */
  byNature: readonly K3DisclosureRow[]
  interest?: readonly K3DisclosureRow[]
  dividend?: readonly K3DisclosureRow[]
  interestOverdue?: readonly K3OverdueInterestRow[]
  /** 仅上市 */
  dividendOverdue?: readonly K3OverdueDividendRow[]
  agingOver1y?: readonly K3AgingOver1yRow[]
  narrativeText?: string
}

export interface K3SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 去空白后判定合计/小计（源模板写「合 计」，`startsWith('合计')` 会漏判） */
function isTotalLabel(v: unknown): boolean {
  const n = String(v ?? '').replace(/[\s\u3000]/g, '')
  return n === '合计' || n === '小计'
}

function twoPeriodRows(rows: readonly K3DisclosureRow[]): Array<Record<string, unknown>> {
  const data = rows
    .filter(r => String(r?.project ?? '').trim() && !isTotalLabel(r.project))
    .map(r => ({
      label: String(r.project).trim(),
      end_amount: num(r.endAmount),
      prior_amount: num(r.priorAmount),
    }))
  return [
    ...data,
    {
      label: K3_TOTAL_LABEL,
      end_amount: data.reduce((s, r) => s + num(r.end_amount), 0),
      prior_amount: data.reduce((s, r) => s + num(r.prior_amount), 0),
      is_total: true,
    },
  ]
}

function sumEnd(rows: Array<Record<string, unknown>>): number {
  const total = rows.find(r => r.is_total)
  return num(total?.end_amount)
}

function sumPrior(rows: Array<Record<string, unknown>>): number {
  const total = rows.find(r => r.is_total)
  return num(total?.prior_amount)
}

function resolveCurrentStandard(variant: K3DisclosureVariant): string {
  return variant === 'listed' ? 'listed_standalone' : 'soe_standalone'
}

/**
 * 构建同步载荷。
 *
 * - 主表三行由分表合计派生（应付利息 / 应付股利 / 其他应付款 = 按款项性质列示合计），
 *   与源模板 `=B17`/`=C17` 的取数关系一致。
 * - 逾期利息 / 超1年未付股利 / 账龄超1年 三张是**条件表**：无行则不推，
 *   表名进 `_removed_table_keys`（源模板「不存在的项目请删除」）。
 */
export function buildK3SyncPayload(
  variant: K3DisclosureVariant,
  wpId: string,
  snapshot: K3DisclosureSnapshot,
): K3SyncPayload {
  const isListed = variant === 'listed'
  const T = isListed ? K3_LISTED_SUBTABLE : K3_SOE_SUBTABLE
  const columns = isListed ? buildK3ListedColumns() : buildK3SoeColumns()

  const byNatureRows = twoPeriodRows(snapshot.byNature ?? [])
  const interestRows = twoPeriodRows(snapshot.interest ?? [])
  const dividendRows = twoPeriodRows(snapshot.dividend ?? [])

  const summaryLabels = K3_SUMMARY_ROWS[variant]
  const summaryRows: Array<Record<string, unknown>> = [
    { label: summaryLabels[0], end_amount: sumEnd(interestRows), prior_amount: sumPrior(interestRows) },
    { label: summaryLabels[1], end_amount: sumEnd(dividendRows), prior_amount: sumPrior(dividendRows) },
    { label: summaryLabels[2], end_amount: sumEnd(byNatureRows), prior_amount: sumPrior(byNatureRows) },
  ]
  summaryRows.push({
    label: K3_TOTAL_LABEL,
    end_amount: summaryRows.reduce((s, r) => s + num(r.end_amount), 0),
    prior_amount: summaryRows.reduce((s, r) => s + num(r.prior_amount), 0),
    is_total: true,
  })

  const sub: Record<string, unknown> = {
    [T.summary]: summaryRows,
    [T.byNature]: byNatureRows,
  }

  const removed: string[] = [...K3_LEGACY_OBSOLETE_TABLES[variant]]

  // 🔴 应付利息 / 应付股利：底稿尚无对应录入区块（见 spec Task 8）。
  // 未提供行时**不推送**（而非推一张只有合计 0 的空表）—— `_source=workpaper` 下
  // 投影器只渲染推来的 sub_table_data、不与模板 `_tables` 合并，推空表会把模板
  // 骨架行整表覆盖掉。也不进 `_removed_table_keys`：它们是模板正式表，只是暂未接线。
  if ((snapshot.interest ?? []).length > 0) {
    sub[T.interest] = interestRows
  } else {
    delete columns[T.interest]
  }
  if ((snapshot.dividend ?? []).length > 0) {
    sub[T.dividend] = dividendRows
  } else {
    delete columns[T.dividend]
  }

  const overdueInterestRows = (snapshot.interestOverdue ?? []).filter(
    r => String(r?.unit ?? '').trim() || num(r?.amount),
  )
  if (overdueInterestRows.length > 0) {
    sub[T.interestOverdue] = overdueInterestRows.map(r => ({
      label: String(r.unit ?? '').trim(),
      overdue_amount: num(r.amount),
      overdue_reason: r.reason ?? '',
    }))
  } else {
    removed.push(T.interestOverdue)
    delete columns[T.interestOverdue]
  }

  if (isListed) {
    const listedT = K3_LISTED_SUBTABLE
    const overdueDividendRows = (snapshot.dividendOverdue ?? []).filter(
      r => String(r?.shareholder ?? '').trim() || num(r?.amount),
    )
    if (overdueDividendRows.length > 0) {
      sub[listedT.dividendOverdue] = overdueDividendRows.map(r => ({
        label: String(r.shareholder ?? '').trim(),
        dividend_amount: num(r.amount),
        unpaid_reason: r.reason ?? '',
      }))
    } else {
      removed.push(listedT.dividendOverdue)
      delete columns[listedT.dividendOverdue]
    }
  }

  const agingRows = (snapshot.agingOver1y ?? []).filter(
    r => String(r?.name ?? '').trim() || num(r?.endAmount),
  )
  if (agingRows.length > 0) {
    sub[T.agingOver1y] = agingRows.map(r => ({
      label: String(r.name ?? '').trim(),
      end_amount: num(r.endAmount),
      unpaid_reason: r.reason ?? '',
    }))
  } else {
    removed.push(T.agingOver1y)
    delete columns[T.agingOver1y]
  }

  const narrative = String(snapshot.narrativeText ?? '').trim()
  if (narrative) {
    sub._note_texts = [{ section: 'k3-note', title: '其他应付款说明', text: narrative }]
  }

  const pushed = new Set(Object.keys(sub))
  const removedFinal = removed.filter(n => n && !pushed.has(n))
  if (removedFinal.length > 0) sub._removed_table_keys = removedFinal

  return {
    wp_id: wpId,
    sheet_name: K3_DISCLOSURE_SHEET_NAME[variant],
    section_id: K3_NOTE_SECTION[variant],
    current_standard: resolveCurrentStandard(variant),
    sub_table_data: sub,
    columns,
  }
}
