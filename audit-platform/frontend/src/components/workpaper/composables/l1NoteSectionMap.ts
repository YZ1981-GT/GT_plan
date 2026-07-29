/**
 * l1NoteSectionMap — L1 短期借款 披露表↔附注模块 联动映射
 *
 * 权威来源 note_template_variant_matrix.json · duan_qi_jie_kuan：
 *   listed_standalone = 五、33
 *   soe_standalone    = 八、33
 *
 * 附注模板结构（五、33 / 八、33）：
 *   表1: 短期借款分类（项目/期末余额/上年年末余额|期初余额）
 *     固定4行: 信用借款/抵押借款/保证借款/质押借款 + 合计
 *   表2: 逾期借款情况（借款单位/期末余额/借款利率 [+ 上市: 逾期时间/逾期利率]）
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

// ─── 列定义 ──────────────────────────────────────────────────────────────────

/** 分类表列头（上市版: 期末余额/上年年末余额；国企版: 期末余额/期初余额） */
function buildCategoryColumns(variant: 'listed' | 'soe'): ColumnDef[] {
  return [
    { key: 'category', label: '项目', is_label: true },
    { key: 'endBalance', label: '期末余额' },
    { key: 'beginBalance', label: variant === 'listed' ? '上年年末余额' : '期初余额' },
  ]
}

/** 逾期借款表列头（上市版多逾期时间/逾期利率） */
function buildOverdueColumns(variant: 'listed' | 'soe'): ColumnDef[] {
  const cols: ColumnDef[] = [
    { key: 'borrower', label: '借款单位', is_label: true },
    { key: 'endBalance', label: '期末余额' },
    { key: 'rate', label: '借款利率(%)' },
  ]
  if (variant === 'listed') {
    cols.push(
      { key: 'overdueTime', label: '逾期时间' },
      { key: 'penaltyRate', label: '逾期利率(%)' },
    )
  }
  return cols
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

  const sub_table_data: Record<string, any> = {
    '短期借款分类': categoryTableRows,
  }

  if (overdueTableRows.length > 0) {
    sub_table_data['逾期借款情况'] = overdueTableRows
  }

  const columns: Record<string, ColumnDef[]> = {
    '短期借款分类': buildCategoryColumns(variant),
  }

  if (overdueTableRows.length > 0) {
    columns['逾期借款情况'] = buildOverdueColumns(variant)
  }

  // 说明文本
  const _note_texts = conclusionText
    ? [{ section: 'conclusion', title: '说明', text: conclusionText }]
    : []

  if (_note_texts.length > 0) {
    sub_table_data._note_texts = _note_texts
  }

  return { sub_table_data, columns }
}
