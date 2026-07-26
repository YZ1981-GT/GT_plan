/**
 * H3 投资性房地产披露 ↔ 附注章节映射与 sync payload 构建
 *
 * 权威来源：note_template_variant_matrix.json · tou_zi_xing_fang_di_chan
 *   上市 → 五、21   国企 → 八、22
 *
 * 底稿 → 附注单向推送（sync_from_workpaper）：
 *  - sub_table_data 各子表 → 附注 table_data.sub_table_data
 *  - sub_table_data._note_texts → 附注 text_content
 *  - columns → _sub_table_columns（投影器产出表头）
 *
 * 成本模式 3 张表（原值/折旧摊销/减值准备变动）+
 * 公允价值模式 1 张表（公允价值变动）+
 * 说明文本若干。
 */
import type { ColumnDef } from './disclosureColumnDefs'

export type H3DisclosureVariant = 'listed' | 'soe'

export const H3_NOTE_SECTION = {
  listed: '五、21',
  soe: '八、22',
} as const satisfies Record<H3DisclosureVariant, string>

export const H3_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const satisfies Record<H3DisclosureVariant, string>

// ─── 列定义（对照致同源模板附注 投资性房地产 逐字取列头）─────────────────────

/** 成本模式 — 账面原值变动表 */
const COST_ORIGINAL_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'begin_balance', label: '期初余额', format: 'amount' },
  { key: 'increase', label: '本期增加金额', format: 'amount' },
  { key: 'decrease', label: '本期减少金额', format: 'amount' },
  { key: 'end_balance', label: '期末余额', format: 'amount' },
]

/** 成本模式 — 累计折旧和累计摊销变动表 */
const COST_DEP_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'begin_balance', label: '期初余额', format: 'amount' },
  { key: 'provision', label: '本期计提额', format: 'amount' },
  { key: 'decrease', label: '本期减少额', format: 'amount' },
  { key: 'end_balance', label: '期末余额', format: 'amount' },
]

/** 成本模式 — 减值准备变动表 */
const COST_IMPAIR_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'begin_balance', label: '期初余额', format: 'amount' },
  { key: 'provision', label: '本期计提额', format: 'amount' },
  { key: 'decrease', label: '本期减少额', format: 'amount' },
  { key: 'end_balance', label: '期末余额', format: 'amount' },
]

/** 公允价值模式 — 公允价值变动表 */
const FAIR_CHANGE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'begin_balance', label: '期初余额', format: 'amount' },
  { key: 'increase', label: '本期增加金额', format: 'amount' },
  { key: 'decrease', label: '本期减少金额', format: 'amount' },
  { key: 'fair_change', label: '公允价值变动', format: 'amount' },
  { key: 'end_balance', label: '期末余额', format: 'amount' },
]

// ─── 表名常量（对照模板 tables[].name 逐字）───────────────────────────────

const TABLE_NAMES = {
  listed: {
    costOriginal: '以成本模式计量的投资性房地产（账面原值）',
    costDep: '以成本模式计量的投资性房地产（累计折旧和累计摊销）',
    costImpair: '以成本模式计量的投资性房地产（减值准备）',
    fairChange: '以公允价值模式计量的投资性房地产',
  },
  soe: {
    costOriginal: '投资性房地产（账面原值）',
    costDep: '投资性房地产（累计折旧和累计摊销）',
    costImpair: '投资性房地产（减值准备）',
    fairChange: '投资性房地产（公允价值模式）',
  },
} as const

// ─── 辅助 ────────────────────────────────────────────────────────────────────

interface DisclosureNoteRow {
  category?: string
  beginBalance?: number
  increase?: number
  decrease?: number
  [k: string]: unknown
}

function buildTableRows(
  rows: DisclosureNoteRow[],
  mode: 'cost-original' | 'cost-dep' | 'cost-impair' | 'fair-change',
): Array<{ label: string; values: (number | null)[]; is_total?: boolean }> {
  const result: Array<{ label: string; values: (number | null)[]; is_total?: boolean }> = []
  let sumBegin = 0, sumInc = 0, sumDec = 0, sumEnd = 0, sumFair = 0

  for (const r of rows) {
    const label = r.category || ''
    const begin = Number(r.beginBalance) || 0
    const inc = Number(r.increase) || 0
    const dec = Number(r.decrease) || 0

    if (mode === 'fair-change') {
      const fairChange = Number((r as any).fairChange ?? (r as any).fair_change) || 0
      const end = begin + inc - dec + fairChange
      result.push({ label, values: [begin, inc, dec, fairChange, end] })
      sumBegin += begin; sumInc += inc; sumDec += dec; sumFair += fairChange; sumEnd += end
    } else if (mode === 'cost-dep' || mode === 'cost-impair') {
      const prov = Number((r as any).provision ?? r.increase) || 0
      const decAmt = Number(r.decrease) || 0
      const end = begin + prov - decAmt
      result.push({ label, values: [begin, prov, decAmt, end] })
      sumBegin += begin; sumInc += prov; sumDec += decAmt; sumEnd += end
    } else {
      // cost-original
      const end = begin + inc - dec
      result.push({ label, values: [begin, inc, dec, end] })
      sumBegin += begin; sumInc += inc; sumDec += dec; sumEnd += end
    }
  }

  // 合计行
  if (mode === 'fair-change') {
    result.push({ label: '合计', values: [sumBegin, sumInc, sumDec, sumFair, sumEnd], is_total: true })
  } else {
    result.push({ label: '合计', values: [sumBegin, sumInc, sumDec, sumEnd], is_total: true })
  }

  return result
}

// ─── buildH3SyncPayload ─────────────────────────────────────────────────────

export interface H3SyncPayloadOptions {
  variant: H3DisclosureVariant
  measurementModel: 'cost' | 'fair_value'
  /** 成本模式 — 原值变动表行（来自 getSectionRows('cost-original')） */
  costOriginalRows?: DisclosureNoteRow[]
  /** 成本模式 — 折旧表行 */
  costDepRows?: DisclosureNoteRow[]
  /** 成本模式 — 减值表行 */
  costImpairRows?: DisclosureNoteRow[]
  /** 公允价值模式 — 公允变动表行 */
  fairChangeRows?: DisclosureNoteRow[]
  /** 各 section 说明文本（key→text） */
  sectionTexts?: Record<string, string>
  /** 项目 ID */
  projectId: string
  /** 底稿 wp_id */
  wpId: string
}

/**
 * 构建 H3 投资性房地产底稿 → 附注模块的 sync payload。
 * 按当前计量模式只推对应表（成本→三表；公允→一表）。
 */
export function buildH3SyncPayload(opts: H3SyncPayloadOptions) {
  const { variant, measurementModel, sectionTexts = {} } = opts
  const names = TABLE_NAMES[variant]

  const sub_table_data: Record<string, unknown> = {}
  const columns: Record<string, ColumnDef[]> = {}

  if (measurementModel === 'cost') {
    // 成本模式三张表
    if (opts.costOriginalRows?.length) {
      const key = names.costOriginal
      sub_table_data[key] = buildTableRows(opts.costOriginalRows, 'cost-original')
      columns[key] = COST_ORIGINAL_COLUMNS
    }
    if (opts.costDepRows?.length) {
      const key = names.costDep
      sub_table_data[key] = buildTableRows(opts.costDepRows, 'cost-dep')
      columns[key] = COST_DEP_COLUMNS
    }
    if (opts.costImpairRows?.length) {
      const key = names.costImpair
      sub_table_data[key] = buildTableRows(opts.costImpairRows, 'cost-impair')
      columns[key] = COST_IMPAIR_COLUMNS
    }
  } else {
    // 公允价值模式一张表
    if (opts.fairChangeRows?.length) {
      const key = names.fairChange
      sub_table_data[key] = buildTableRows(opts.fairChangeRows, 'fair-change')
      columns[key] = FAIR_CHANGE_COLUMNS
    }
  }

  // 说明文本
  const noteTexts: Array<{ section: string; title: string; text: string }> = []
  const textEntries = Object.entries(sectionTexts).filter(([, v]) => v?.trim())
  for (const [key, text] of textEntries) {
    noteTexts.push({ section: key, title: key, text })
  }
  if (noteTexts.length) {
    sub_table_data._note_texts = noteTexts
  }

  return {
    wp_id: opts.wpId,
    sheet_name: H3_DISCLOSURE_SHEET_NAME[variant],
    section_id: H3_NOTE_SECTION[variant],
    current_standard: variant === 'listed' ? 'listed_standalone' : 'soe_standalone',
    sub_table_data,
    columns,
  }
}
