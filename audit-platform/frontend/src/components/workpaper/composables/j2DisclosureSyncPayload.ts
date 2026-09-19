/**
 * j2DisclosureSyncPayload — J2 长期应付职工薪酬/设定受益计划净资产 同步载荷构建器
 *
 * 子表名逐字取自 note_template JSON（listed 含尾冒号，soe 无尾冒号）。
 * 列 key 必须匹配组件 reactive 行对象的数据字段名。
 *
 * Spec: .kiro/specs/disclosure-sync-path-buildout/ (批6 J2)
 */

import { defineColumns, type ColumnDef } from './disclosureColumnDefs'
import {
  J2_NOTE_SECTION,
  J2_DISCLOSURE_SHEET_NAME,
  J2_NET_ASSET_NOTE_SECTION,
} from './j2NoteSectionMap'

// ── 子表名常量（逐字取自模板 tables[].name） ─────────────────────────────────

export const J2_LISTED_SUBTABLE = {
  summary: '长期应付职工薪酬',
  dbo: '设定受益计划义务现值：',
  asset: '计划资产：',
  net: '设定受益计划净负债（净资产）：',
  maturity: '未折现的离职后福利预计到期分析：',
  assetComp: '计划资产',
  assume: '精算假设',
  sens: '敏感性分析',
} as const

export const J2_SOE_SUBTABLE = {
  summary: '长期应付职工薪酬',
  change: '设定受益计划情况',
  maturity: '未折现的离职后福利预计到期分析',
  assetComp: '计划资产',
  assume: '精算假设',
  sens: '敏感性分析',
} as const

/**
 * 🔴 八、54 被删的两张上市结构误抄表 —— 同步载荷不再推送，且经
 * `_removed_table_keys` 清理存量孤儿子表。
 *
 * tables[2] `计划资产`（变动表 rows=9，与 tables[5] 构成表同名 → sub_table_data
 * 以表名为键必丢整表 → P0 三号），tables[3] `设定受益计划净负债（净资产）`（上市
 * 结构的独立三表，国企源模板是横向 7 列合一 = tables[1]）。
 */
export const J2_SOE_LEGACY_OBSOLETE_TABLES = [
  '计划资产：',                     // 旧名（变动表带尾冒号，与 J2_LISTED_SUBTABLE.asset 相同）
  '设定受益计划净负债（净资产）：',  // 旧名（listed 版带尾冒号）
  '设定受益计划义务现值',            // 曾用名（改名为 `设定受益计划情况` 前的 soe 版）
  '设定受益计划净负债（净资产）',    // soe 版无尾冒号
] as const

// ── Listed 列定义 ─────────────────────────────────────────────────────────────

function listedSummaryCols(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'end', label: '期末数', format: 'amount' },
    { key: 'begin', label: '期初数', format: 'amount' },
  ])
}

function listedDboCols(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'cur', label: '本期金额', format: 'amount' },
    { key: 'prior', label: '上期金额', format: 'amount' },
  ])
}

function listedMaturityCols(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'amount', label: '金额', format: 'amount' },
  ])
}

function listedAssetCompCols(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true },
    { key: 'end', label: '期末数', format: 'amount', group: '计划资产的公允价值' },
    { key: 'begin', label: '期初数', format: 'amount', group: '计划资产的公允价值' },
  ])
}

function listedAssumeCols(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'end', label: '期末数', format: 'percent' },
    { key: 'begin', label: '期初数', format: 'percent' },
  ])
}

function listedSensCols(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true },
    { key: 'delta', label: '假设的变动幅度', format: 'percent' },
    { key: 'up', label: '计划负债增加', format: 'amount', group: '对设定受益义务现值的影响' },
    { key: 'down', label: '计划负债减少', format: 'amount', group: '对设定受益义务现值的影响' },
  ])
}

/** Listed 全表列定义映射（按模板表名索引） */
export function buildJ2ListedColumns(): Record<string, ColumnDef[]> {
  return {
    [J2_LISTED_SUBTABLE.summary]: listedSummaryCols(),
    [J2_LISTED_SUBTABLE.dbo]: listedDboCols(),
    [J2_LISTED_SUBTABLE.asset]: listedDboCols(),
    [J2_LISTED_SUBTABLE.net]: listedDboCols(),
    [J2_LISTED_SUBTABLE.maturity]: listedMaturityCols(),
    [J2_LISTED_SUBTABLE.assetComp]: listedAssetCompCols(),
    [J2_LISTED_SUBTABLE.assume]: listedAssumeCols(),
    [J2_LISTED_SUBTABLE.sens]: listedSensCols(),
  }
}

// ── SOE 列定义 ────────────────────────────────────────────────────────────────

function soeSummaryCols(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'begin', label: '期初数', format: 'amount' },
    { key: 'increase', label: '本期增加', format: 'amount' },
    { key: 'decrease', label: '本期减少', format: 'amount' },
    { key: 'end', label: '期末数', format: 'amount' },
  ])
}

function soeChangeCols(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true },
    { key: 'dbo_cur', label: '本期金额', format: 'amount', group: '设定受益计划义务现值' },
    { key: 'dbo_prior', label: '上期金额', format: 'amount', group: '设定受益计划义务现值' },
    { key: 'asset_cur', label: '本期金额', format: 'amount', group: '计划资产的公允价值' },
    { key: 'asset_prior', label: '上期金额', format: 'amount', group: '计划资产的公允价值' },
    { key: 'net_cur', label: '本期金额', format: 'amount', group: '设定受益计划净负债（净资产）' },
    { key: 'net_prior', label: '上期金额', format: 'amount', group: '设定受益计划净负债（净资产）' },
  ])
}

function soeMaturityCols(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'amount', label: '金额', format: 'amount' },
  ])
}

function soeAssetCompCols(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true },
    { key: 'end', label: '期末数', format: 'amount', group: '计划资产的公允价值' },
    { key: 'begin', label: '期初数', format: 'amount', group: '计划资产的公允价值' },
  ])
}

function soeAssumeCols(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'end', label: '期末数', format: 'percent' },
    { key: 'begin', label: '期初数', format: 'percent' },
  ])
}

function soeSensCols(): ColumnDef[] {
  // 🔴 SOE says 计划负债减小 (not 计划负债减少)
  return defineColumns([
    { key: 'label', label: '项目', is_label: true },
    { key: 'delta', label: '假设的变动幅度', format: 'percent' },
    { key: 'up', label: '计划负债增加', format: 'amount', group: '对设定受益义务现值的影响' },
    { key: 'down', label: '计划负债减小', format: 'amount', group: '对设定受益义务现值的影响' },
  ])
}

/** SOE 全表列定义映射 */
export function buildJ2SoeColumns(): Record<string, ColumnDef[]> {
  return {
    [J2_SOE_SUBTABLE.summary]: soeSummaryCols(),
    [J2_SOE_SUBTABLE.change]: soeChangeCols(),
    [J2_SOE_SUBTABLE.maturity]: soeMaturityCols(),
    [J2_SOE_SUBTABLE.assetComp]: soeAssetCompCols(),
    [J2_SOE_SUBTABLE.assume]: soeAssumeCols(),
    [J2_SOE_SUBTABLE.sens]: soeSensCols(),
  }
}

// ── 载荷构建（组件调用，传 snapshot 进来） ───────────────────────────────────

export type J2Variant = 'listed' | 'soe'

/** 说明文本 title */
const NOTE_TEXT_TITLES: Record<string, string> = {
  noteTerm: '辞退福利/其他长期职工福利性质说明',
  noteDbp: '设定受益计划内容/风险/现金流量影响',
  noteSens: '敏感性分析方法说明',
}

interface J2ListedSnapshot {
  summaryRows: Array<{ key: string; label: string; end: number; begin: number }>
  dboRows: Array<{ key: string; label: string; cur: number; prior: number }>
  assetRows: Array<{ key: string; label: string; cur: number; prior: number }>
  netRows: Array<{ key: string; label: string; cur: number; prior: number }>
  maturityRows: Array<{ key: string; label: string; amount: number }>
  assetCompRows: Array<{ key: string; label: string; end: number; begin: number }>
  assumeRows: Array<{ key: string; label: string; end: number; begin: number }>
  sensRows: Array<{ key: string; label: string; delta: number; up: number; down: number }>
  noteTerm: string
  noteDbp: string
  noteSens: string
}

interface J2SoeSnapshot {
  summaryRows: Array<{ key: string; label: string; begin: number; increase: number; decrease: number }>
  /** Each changeRow has { key, label, dboCur, dboPrior, assetCur, assetPrior, netCur, netPrior } */
  changeRows: Array<{
    key: string; label: string
    dboCur: number; dboPrior: number
    assetCur: number; assetPrior: number
    netCur: number; netPrior: number
  }>
  maturityRows: Array<{ key: string; label: string; amount: number }>
  assetCompRows: Array<{ key: string; label: string; end: number; begin: number }>
  assumeRows: Array<{ key: string; label: string; end: number; begin: number }>
  sensRows: Array<{ key: string; label: string; delta: number; up: number; down: number }>
  noteTerm: string
  noteDbp: string
  noteSens: string
  /** 汇总表期末 = begin + increase - decrease */
  summaryEndFn: (row: { begin: number; increase: number; decrease: number }) => number
}

function buildNoteTexts(noteTerm: string, noteDbp: string, noteSens: string) {
  const texts: Array<{ section: string; title: string; text: string }> = []
  if (noteTerm) texts.push({ section: 'noteTerm', title: NOTE_TEXT_TITLES.noteTerm, text: noteTerm })
  if (noteDbp) texts.push({ section: 'noteDbp', title: NOTE_TEXT_TITLES.noteDbp, text: noteDbp })
  if (noteSens) texts.push({ section: 'noteSens', title: NOTE_TEXT_TITLES.noteSens, text: noteSens })
  return texts.length ? texts : undefined
}

function mapRows<R extends { label: string }>(
  rows: R[],
  mapper: (r: R) => Record<string, unknown>,
): Array<Record<string, unknown>> {
  return rows.map((r) => ({ label: r.label, ...mapper(r) }))
}

export function buildJ2ListedSyncPayload(snapshot: J2ListedSnapshot) {
  const sub_table_data: Record<string, unknown[]> = {
    [J2_LISTED_SUBTABLE.summary]: mapRows(snapshot.summaryRows, (r) => ({ end: r.end, begin: r.begin })),
    [J2_LISTED_SUBTABLE.dbo]: mapRows(snapshot.dboRows, (r) => ({ cur: r.cur, prior: r.prior })),
    [J2_LISTED_SUBTABLE.asset]: mapRows(snapshot.assetRows, (r) => ({ cur: r.cur, prior: r.prior })),
    [J2_LISTED_SUBTABLE.net]: mapRows(snapshot.netRows, (r) => ({ cur: r.cur, prior: r.prior })),
    [J2_LISTED_SUBTABLE.maturity]: mapRows(snapshot.maturityRows, (r) => ({ amount: r.amount })),
    [J2_LISTED_SUBTABLE.assetComp]: mapRows(snapshot.assetCompRows, (r) => ({ end: r.end, begin: r.begin })),
    [J2_LISTED_SUBTABLE.assume]: mapRows(snapshot.assumeRows, (r) => ({ end: r.end, begin: r.begin })),
    [J2_LISTED_SUBTABLE.sens]: mapRows(snapshot.sensRows, (r) => ({ delta: r.delta, up: r.up, down: r.down })),
  }

  const noteTexts = buildNoteTexts(snapshot.noteTerm, snapshot.noteDbp, snapshot.noteSens)
  if (noteTexts) {
    ;(sub_table_data as Record<string, unknown>)._note_texts = noteTexts
  }

  return {
    note_section: J2_NOTE_SECTION.listed,
    sheet_name: J2_DISCLOSURE_SHEET_NAME.listed,
    sub_table_data,
    _sub_table_columns: buildJ2ListedColumns(),
  }
}

export function buildJ2SoeSyncPayload(snapshot: J2SoeSnapshot) {
  const endFn = snapshot.summaryEndFn
  const sub_table_data: Record<string, unknown[]> = {
    [J2_SOE_SUBTABLE.summary]: snapshot.summaryRows.map((r) => ({
      label: r.label,
      begin: r.begin,
      increase: r.increase,
      decrease: r.decrease,
      end: endFn(r),
    })),
    [J2_SOE_SUBTABLE.change]: snapshot.changeRows.map((r) => ({
      label: r.label,
      dbo_cur: r.dboCur,
      dbo_prior: r.dboPrior,
      asset_cur: r.assetCur,
      asset_prior: r.assetPrior,
      net_cur: r.netCur,
      net_prior: r.netPrior,
    })),
    [J2_SOE_SUBTABLE.maturity]: mapRows(snapshot.maturityRows, (r) => ({ amount: r.amount })),
    [J2_SOE_SUBTABLE.assetComp]: mapRows(snapshot.assetCompRows, (r) => ({ end: r.end, begin: r.begin })),
    [J2_SOE_SUBTABLE.assume]: mapRows(snapshot.assumeRows, (r) => ({ end: r.end, begin: r.begin })),
    [J2_SOE_SUBTABLE.sens]: mapRows(snapshot.sensRows, (r) => ({ delta: r.delta, up: r.up, down: r.down })),
  }

  const noteTexts = buildNoteTexts(snapshot.noteTerm, snapshot.noteDbp, snapshot.noteSens)
  if (noteTexts) {
    ;(sub_table_data as Record<string, unknown>)._note_texts = noteTexts
  }

  return {
    note_section: J2_NOTE_SECTION.soe,
    sheet_name: J2_DISCLOSURE_SHEET_NAME.soe,
    sub_table_data,
    _sub_table_columns: buildJ2SoeColumns(),
    _removed_table_keys: [...J2_SOE_LEGACY_OBSOLETE_TABLES],
  }
}

// ── 净资产分支（五、17）列定义 ────────────────────────────────────────────────

export const J2_NET_ASSET_SUBTABLE = '设定受益计划净资产' as const

function netAssetColumns(): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'begin', label: '期初余额', format: 'amount' },
    { key: 'increase', label: '本期增加', format: 'amount' },
    { key: 'decrease', label: '本期减少', format: 'amount' },
    { key: 'end', label: '期末余额', format: 'amount' },
  ])
}

/**
 * 五、17 设定受益计划净资产：仅在上市侧净负债表期末为负（= 净资产）时推送。
 * variant_matrix: soe 侧为 null → 国企不推此章节。
 *
 * 行集从 Listed 汇总表中取 `dbp_net` 行的绝对值（净资产时期末为负数，取绝正显示）。
 */
export interface J2NetAssetSnapshot {
  /** 设定受益计划净资产余额（begin/increase/decrease/end，均取绝对值） */
  dbpNetRow: { begin: number; increase: number; decrease: number; end: number }
  /** 其他长期职工福利净资产（可选，不适用时传 null 或全 0 → 不推行） */
  otherLtRow?: { begin: number; increase: number; decrease: number; end: number } | null
}

export function buildJ2NetAssetPayload(snapshot: J2NetAssetSnapshot) {
  const rows: Array<Record<string, unknown>> = [
    {
      label: '设定受益计划净资产',
      begin: Math.abs(snapshot.dbpNetRow.begin),
      increase: Math.abs(snapshot.dbpNetRow.increase),
      decrease: Math.abs(snapshot.dbpNetRow.decrease),
      end: Math.abs(snapshot.dbpNetRow.end),
    },
  ]

  if (snapshot.otherLtRow) {
    const o = snapshot.otherLtRow
    const hasValue = o.begin !== 0 || o.increase !== 0 || o.decrease !== 0 || o.end !== 0
    if (hasValue) {
      rows.push({
        label: '符合设定受益计划条件的其他长期职工福利的净资产',
        begin: Math.abs(o.begin),
        increase: Math.abs(o.increase),
        decrease: Math.abs(o.decrease),
        end: Math.abs(o.end),
      })
    }
  }

  // 合计行
  const total = rows.reduce(
    (acc, r) => ({
      begin: acc.begin + (r.begin as number),
      increase: acc.increase + (r.increase as number),
      decrease: acc.decrease + (r.decrease as number),
      end: acc.end + (r.end as number),
    }),
    { begin: 0, increase: 0, decrease: 0, end: 0 },
  )
  rows.push({ label: '合计', is_total: true, ...total })

  const sub_table_data: Record<string, unknown> = {
    [J2_NET_ASSET_SUBTABLE]: rows,
  }

  return {
    note_section: J2_NET_ASSET_NOTE_SECTION.listed!,
    sheet_name: J2_DISCLOSURE_SHEET_NAME.listed,
    sub_table_data,
    _sub_table_columns: { [J2_NET_ASSET_SUBTABLE]: netAssetColumns() },
  }
}
