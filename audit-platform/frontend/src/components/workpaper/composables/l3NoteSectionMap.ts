/**
 * l3NoteSectionMap — L3 长期借款 披露表↔附注模块 联动映射
 *
 * 权威来源 note_template_variant_matrix.json · chang_qi_jie_kuan：
 *   listed_standalone = 五、45
 *   soe_standalone    = 八、49
 *
 * 附注模板结构（R8.4 批 9b-2 按底稿 L3 两张披露 sheet）：
 *   表1: 长期借款 —— 一行表头，两列同名「利率区间」
 *     上市 五、45: 项  目/期末余额/利率区间/上年年末余额/利率区间
 *     国企 八、49: 借款类别/期末余额/利率区间/期初余额/利率区间
 *     固定行: 质押/抵押/保证/信用借款 + 小计 − 减一年内到期 = 合计
 *   表2: 一年内到期的长期借款
 *     国企 八、45「（1）一年内到期的长期借款」: 借款类别/期末余额/期初余额（独立章节）
 *     上市在 五、43「一年内到期的非流动负债」里，与应付债券、长期应付款等共用一节 ⇒ 不推（同 L5）：
 *       附注按已推送的表投影，只推一张会让该节其余模板表从附注里消失
 *   说明: 审计结论
 */
import type { ColumnDef } from './disclosureColumnDefs'

/**
 * 章节号（嵌套形态 = 一个循环推多个章节，`gen_note_wp_sync_registry.py` 据此登记
 * `listed_sections` / `soe_sections`，同 G1 / G10）。
 */
export const L3_NOTE_SECTION = {
  listed: { main: '五、45' },
  soe: { main: '八、49', within1y: '八、45' },
} as const

export const L3_DISCLOSURE_SHEET_LISTED = '附注披露信息核对（上市公司）'
export const L3_DISCLOSURE_SHEET_SOE = '附注披露信息核对（国企）'

/** 子表名（逐字取附注模板 `tables[].name`） */
export const L3_SUBTABLE = {
  main: '长期借款',
  /** 国企 八、45 唯一一张表 */
  within1ySoe: '（1）一年内到期的长期借款',
} as const

/**
 * 旧载荷推过、模板里不存在的表：随载荷带 `_removed_table_keys` 清掉库里的孤儿子表。
 * 改造前「一年内到期的长期借款」随长期借款一起推进 五、45 / 八、49（模板这两节都没有这张表）。
 */
export const L3_LEGACY_OBSOLETE_TABLES = ['一年内到期的长期借款'] as const

// ─── 列定义 ──────────────────────────────────────────────────────────────────
//
// 🔴 按底稿 L3 两张披露 sheet（一行表头、无合并格；上市 A7:E7、国企 A8:E8）：
//   · 两列同名「利率区间」照抄（加期别前缀即杜撰），靠 key 区分 `endRate` / `priorRate`；
//   · 国企原取「附注模版 4 列」（借款类别/期末余额/期初余额/期末利率期间（%）、丢期初利率），
//     与底稿 5 列不符 ⇒ 改按底稿，与模板 八、49 同列（R8.4 批 9b-2）；
//   · 标签列头逐字等于模板 `headers[0]`（上市「项  目」双空格，与底稿 A7 同）。

function buildClassificationColumns(variant: 'listed' | 'soe'): ColumnDef[] {
  const listed = variant === 'listed'
  return [
    { key: 'label', label: listed ? '项  目' : '借款类别', is_label: true, flat: true },
    { key: 'endAmount', label: '期末余额', format: 'amount' },
    { key: 'endRate', label: '利率区间', format: 'text' },
    { key: 'priorAmount', label: listed ? '上年年末余额' : '期初余额', format: 'amount' },
    { key: 'priorRate', label: '利率区间', format: 'text' },
  ]
}

/** 国企 八、45「（1）一年内到期的长期借款」列定义 */
export function buildL3Within1ySoeColumns(): Record<string, ColumnDef[]> {
  return {
    [L3_SUBTABLE.within1ySoe]: [
      { key: 'label', label: '借款类别', is_label: true, flat: true },
      { key: 'endAmount', label: '期末余额', format: 'amount' },
      { key: 'priorAmount', label: '期初余额', format: 'amount' },
    ],
  }
}

/** L3 上市（五、45）子表列头，键 = `sub_table_data` 数据键 */
export function buildL3ListedColumns(): Record<string, ColumnDef[]> {
  return { [L3_SUBTABLE.main]: buildClassificationColumns('listed') }
}

/** L3 国企（八、49）子表列头，键 = `sub_table_data` 数据键 */
export function buildL3SoeColumns(): Record<string, ColumnDef[]> {
  return { [L3_SUBTABLE.main]: buildClassificationColumns('soe') }
}

export interface L3SyncPayloadOptions {
  variant: 'listed' | 'soe'
  classificationRows: Array<{ label: string; endAmount: number; priorAmount: number; isTotal?: boolean; isSubtotal?: boolean; isDeduction?: boolean; rowKey?: string }>
  currentPortionRows: Array<{ label: string; endAmount: number; priorAmount: number; isTotal?: boolean }>
  rateRange: (rowKey: string, period: 'end' | 'prior') => string
  propertyNote: string
  conclusion: string
}

/** 推到附注的一节（`sync-batch-from-workpaper` 的一个 item） */
export interface L3SyncItem {
  section_id: string
  sub_table_data: Record<string, any>
  columns: Record<string, ColumnDef[]>
}

/**
 * 构建同步载荷：上市 1 节（五、45），国企 2 节（八、49 长期借款 + 八、45 一年内到期的长期借款）。
 * 主表节带 `_removed_table_keys` 清掉旧载荷推进来的孤儿子表。
 */
export function buildL3SyncPayload(opts: L3SyncPayloadOptions): L3SyncItem[] {
  const { variant, classificationRows, currentPortionRows, rateRange, propertyNote, conclusion } = opts

  // values 与 buildClassificationColumns(variant) 的非标签列同序（两版同为
  // 期末余额 / 利率区间(end) / 上年年末余额|期初余额 / 利率区间(prior)）
  const classRows = classificationRows.map(r => ({
    label: r.label,
    values: [r.endAmount, rateRange(r.rowKey || '', 'end'), r.priorAmount, rateRange(r.rowKey || '', 'prior')],
    ...(r.isTotal ? { is_total: true } : {}),
  }))

  const main: Record<string, any> = {
    [L3_SUBTABLE.main]: classRows,
    _removed_table_keys: [...L3_LEGACY_OBSOLETE_TABLES],
  }
  const _note_texts: Array<{ section: string; title: string; text: string }> = []
  if (propertyNote) _note_texts.push({ section: 'property', title: '抵押质押说明', text: propertyNote })
  if (conclusion) _note_texts.push({ section: 'conclusion', title: '审计结论', text: conclusion })
  if (_note_texts.length > 0) main._note_texts = _note_texts

  if (variant === 'listed') {
    return [{ section_id: L3_NOTE_SECTION.listed.main, sub_table_data: main, columns: buildL3ListedColumns() }]
  }
  const within1y = currentPortionRows.map(r => ({
    label: r.label,
    values: [r.endAmount, r.priorAmount],
    ...(r.isTotal ? { is_total: true } : {}),
  }))
  return [
    { section_id: L3_NOTE_SECTION.soe.main, sub_table_data: main, columns: buildL3SoeColumns() },
    {
      section_id: L3_NOTE_SECTION.soe.within1y,
      sub_table_data: { [L3_SUBTABLE.within1ySoe]: within1y },
      columns: buildL3Within1ySoeColumns(),
    },
  ]
}
