/**
 * l1NoteSectionMap — L1 短期借款 披露表↔附注模块 联动映射
 *
 * 权威来源 note_template_variant_matrix.json · duan_qi_jie_kuan：
 *   listed_standalone = 五、33
 *   soe_standalone    = 八、33
 *
 * 附注模板结构（五、33 / 八、33，按底稿 L1 两张披露 sheet）：
 *   表1: 短期借款分类（上市: 项  目/期末余额/上年年末余额；国企: 借款类别/期末余额/期初余额）
 *     固定4行: 信用借款/抵押借款/保证借款/质押借款 + 合计
 *   表2: 上市「（2）逾期借款情况」: 借款单位/期末余额/借款利率/逾期时间/逾期利率；
 *        国企「已逾期未偿还的短期借款情况」: 债权单位/期末余额/借款利率
 *   说明: 审计核对结论
 *
 * 数据来源：
 *   分类表 → 从审定表 L1-1 各分类审定数自动派生（useL1DisclosureData.categoryRows）
 *   逾期表 → 审计师录入（useL1DisclosureData.overdueRows）
 *   说明   → 审计师录入 conclusionText
 */
import type { ColumnDef } from './disclosureColumnDefs'

// ─── 章节号常量 ──────────────────────────────────────────────────────────────

export const L1_NOTE_SECTION = {
  listed: '五、33',
  soe: '八、33',
} as const

export const L1_DISCLOSURE_SHEET_LISTED = '附注披露信息核对（上市公司）'
export const L1_DISCLOSURE_SHEET_SOE = '附注披露信息核对（国企）'

/** 子表名（逐字取附注模板 `tables[].name`；两版逾期表名不同） */
export const L1_SUBTABLE = {
  category: '短期借款分类',
  overdue: { listed: '（2）逾期借款情况', soe: '已逾期未偿还的短期借款情况' },
} as const

/**
 * 旧载荷推过、模板里不存在的表：随载荷带 `_removed_table_keys` 清掉库里的孤儿子表。
 * 改造前逾期表两版都推「逾期借款情况」（模板两版都没有这个表名）。
 */
export const L1_LEGACY_OBSOLETE_TABLES = ['逾期借款情况'] as const

// ─── 列定义 ──────────────────────────────────────────────────────────────────
//
// 口径实证见 spec `disclosure-columns-coverage-rollout` design §批 1 列头清查 §2/§3：
//   · 4 张表在源模板中**全是单行表头**（表头行无跨列合并 / consol `multi_header: null`
//     / 附注模版 md 仅 1 行 header）→ 标签列一律 `flat: true`，0 处 `group`。
//     不标 `flat` 时后端 `_infer_groups_from_headers` 会给上市逾期表凭空加「逾期」
//     父表头（逾期时间/逾期利率被并到假父表头下），实跑已复现。
//   · 🔴 表名与列名按底稿 L1 两张披露 sheet（= 附注模板 五、33 / 八、33，R8.4 批 9b-2 起「单体都按底稿
//     披露表格式」）：上市分类表标签列「项  目」（底稿 A7 双空格）、国企逾期表利率列「借款利率」（底稿 C16，
//     原按附注模版 md 写「借款利率（%）」）、两版逾期表名见 `L1_SUBTABLE`。

/** 分类表列头（上市: 项  目/期末余额/上年年末余额；国企: 借款类别/期末余额/期初余额） */
function buildCategoryColumns(variant: 'listed' | 'soe'): ColumnDef[] {
  return [
    { key: 'category', label: variant === 'listed' ? '项  目' : '借款类别', is_label: true, flat: true },
    { key: 'endBalance', label: '期末余额', format: 'amount' },
    { key: 'beginBalance', label: variant === 'listed' ? '上年年末余额' : '期初余额', format: 'amount' },
  ]
}

/** 逾期借款表列头（上市 5 列；国企 3 列，源 A16:C16 仅 3 列，禁凭空补录入列） */
function buildOverdueColumns(variant: 'listed' | 'soe'): ColumnDef[] {
  if (variant === 'soe') {
    return [
      { key: 'borrower', label: '债权单位', is_label: true, flat: true },
      { key: 'endBalance', label: '期末余额', format: 'amount' },
      { key: 'rate', label: '借款利率', format: 'percent' },
    ]
  }
  return [
    { key: 'borrower', label: '借款单位', is_label: true, flat: true },
    { key: 'endBalance', label: '期末余额', format: 'amount' },
    { key: 'rate', label: '借款利率', format: 'percent' },
    { key: 'overdueTime', label: '逾期时间', format: 'text' },
    { key: 'penaltyRate', label: '逾期利率', format: 'percent' },
  ]
}

export interface L1ColumnsOptions {
  /**
   * 逾期表是**条件推送**（`overdueRows` 全空时不进 `sub_table_data`）→
   * `columns` 必须成对：仅在该键进 `sub_table_data` 时才声明列头，
   * 否则破坏「columns 与 sub_table_data 键一一对应」（Property 1）。
   */
  includeOverdue?: boolean
}

function buildL1Columns(variant: 'listed' | 'soe', opts: L1ColumnsOptions): Record<string, ColumnDef[]> {
  const columns: Record<string, ColumnDef[]> = {
    [L1_SUBTABLE.category]: buildCategoryColumns(variant),
  }
  if (opts.includeOverdue) {
    columns[L1_SUBTABLE.overdue[variant]] = buildOverdueColumns(variant)
  }
  return columns
}

/** L1 上市（五、33）子表列头，键 = `sub_table_data` 数据键 */
export function buildL1ListedColumns(opts: L1ColumnsOptions = {}): Record<string, ColumnDef[]> {
  return buildL1Columns('listed', opts)
}

/** L1 国企（八、33）子表列头，键 = `sub_table_data` 数据键 */
export function buildL1SoeColumns(opts: L1ColumnsOptions = {}): Record<string, ColumnDef[]> {
  return buildL1Columns('soe', opts)
}

// ─── Payload 构建 ─────────────────────────────────────────────────────────────

export interface L1SyncPayloadOptions {
  variant: 'listed' | 'soe'
  categoryRows: Array<{ category: string; endBalance: number; beginBalance: number }>
  categoryTotal: { begin: number; end: number }
  overdueRows: Array<{ borrower: string; endBalance: number; rate: number; overdueTime?: string; penaltyRate?: number }>
  conclusionText: string
}

/**
 * 构建 L1 → 附注模块同步载荷
 * 用于 POST /api/projects/{pid}/disclosure-notes/sync-from-workpaper
 */
export function buildL1SyncPayload(opts: L1SyncPayloadOptions) {
  const { variant, categoryRows, categoryTotal, overdueRows, conclusionText } = opts

  // 分类表数据
  const categoryTableRows = [
    ...categoryRows.map(r => ({
      label: r.category,
      values: [r.endBalance, r.beginBalance],
    })),
    {
      label: '合  计',
      values: [categoryTotal.end, categoryTotal.begin],
      is_total: true,
    },
  ]

  // 逾期表数据
  const overdueTableRows = overdueRows
    .filter(r => r.borrower || r.endBalance)
    .map(r => {
      const values: (string | number)[] = [r.endBalance, r.rate]
      if (variant === 'listed') {
        values.push(r.overdueTime || '', r.penaltyRate || 0)
      }
      return { label: r.borrower, values }
    })

  const overdueTable = L1_SUBTABLE.overdue[variant]
  const sub_table_data: Record<string, any> = {
    [L1_SUBTABLE.category]: categoryTableRows,
  }

  if (overdueTableRows.length > 0) {
    sub_table_data[overdueTable] = overdueTableRows
  }
  // 清旧载荷的孤儿表；逾期表是「如无，删除」的条件表，本次没有逾期数据时连同上次推过的一起清掉
  sub_table_data._removed_table_keys = [
    ...L1_LEGACY_OBSOLETE_TABLES,
    ...(overdueTableRows.length > 0 ? [] : [overdueTable]),
  ]

  const columnsOpts: L1ColumnsOptions = { includeOverdue: overdueTableRows.length > 0 }
  const columns = variant === 'listed'
    ? buildL1ListedColumns(columnsOpts)
    : buildL1SoeColumns(columnsOpts)

  // 说明文本
  const _note_texts = conclusionText
    ? [{ section: 'conclusion', title: '说明', text: conclusionText }]
    : []

  if (_note_texts.length > 0) {
    sub_table_data._note_texts = _note_texts
  }

  return { sub_table_data, columns }
}
