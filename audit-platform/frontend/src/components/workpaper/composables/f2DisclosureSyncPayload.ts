/**
 * F2 披露 → disclosure_notes sync payload 构建
 * 子表名对齐 note_template_listed §五、9 / note_template_soe §八、10
 */
import type { F2DisclosureVariant } from './f2NoteSectionMap'
import {
  F2_DISCLOSURE_SHEET_NAME,
  F2_NOTE_SECTION,
  resolveF2CurrentStandard,
  resolveF2NoteSectionTarget,
} from './f2NoteSectionMap'

import type { ColumnDef } from './disclosureColumnDefs'
import { DR_COL_LABELS, type DrSyncRow } from './f2DataResourceInventory'

/**
 * 「确认为存货的数据资源」列头（上市/国企共用，逐字取自附注模版）。
 * 该表为三段式明细，无两级表头。
 */
function buildDataResourceColumns(): ColumnDef[] {
  return [
    // flat：源模版为单行表头，抑制前缀推断
    { key: 'label', label: '项目', is_label: true, flat: true },
    { key: 'purchased', label: DR_COL_LABELS.purchased, format: 'amount' },
    { key: 'self_processed', label: DR_COL_LABELS.selfProcessed, format: 'amount' },
    { key: 'other', label: DR_COL_LABELS.other, format: 'amount' },
    { key: 'total', label: DR_COL_LABELS.total, format: 'amount' },
  ]
}

/**
 * 同步载荷的 `sub_table_data`：数据键 → 行数组；`_` 前缀键为元数据。
 *
 * 索引签名保留行数组形态（消费方与测试直接按 `sub['存货分类'][0].label` 取值），
 * `_removed_table_keys`（`string[]`）经 `withMeta` 单点断言写入。
 */
export type F2SubTableData = Record<string, Record<string, unknown>[]>

/** 元数据键单点写入（唯一需要断言的地方，避免全链路降级成 `unknown`） */
function withMeta(
  tables: Record<string, Record<string, unknown>[]>,
  meta: { _note_texts?: F2NoteTextRow[]; _removed_table_keys?: string[] },
): F2SubTableData {
  return { ...tables, ...meta } as unknown as F2SubTableData
}

export interface F2SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  /** 数据键为行数组；`_` 前缀键为元数据（`_note_texts` / `_removed_table_keys`） */
  sub_table_data: F2SubTableData
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 F2 披露组件既有 el-table-column */
  columns?: Record<string, ColumnDef[]>
}

// ── 列头元数据：label 逐字取自 F2TabDisclosureListed/Soe 的 el-table-column（源对齐，禁止杜撰）──
// 两级表头（如「期末数 > 账面余额」）在扁平投影中合并为「期末账面余额」，保留源语义。

/** (3) 按组合计提：期末 / 上年年末两表列结构相同（源模板 R49-R61） */
function buildPortfolioColumns(): ColumnDef[] {
  return [
    { key: 'group_name', label: '组合', is_label: true },
    { key: 'balance', label: '金额', group: '账面余额', format: 'amount' },
    { key: 'balance_pct', label: '比例(%)', group: '账面余额', format: 'percent' },
    { key: 'impairment', label: '金额', group: '存货跌价准备', format: 'amount' },
    { key: 'provision_standard', label: '计提标准', group: '存货跌价准备' },
    { key: 'impairment_pct', label: '比例(%)', group: '存货跌价准备', format: 'percent' },
    { key: 'net_value', label: '账面价值', format: 'amount' },
  ]
}

/**
 * 上市三表的标签列头 = 源 xlsx A8/A22/A35「存货种类」。
 *
 * 🔴 曾误写为「项目」（与 F2TabDisclosureListed 的 el-table-column 及源模板都不一致），
 * 同步后附注表头显示「项目」。平台契约：同步 `columns[0].label` 必须 === 模板
 * `headers[0]`，两处已一起改（`fix_note_inventory_structure.LISTED_LABEL_HEADER`）。
 */
export const F2_LISTED_LABEL_HEADER = '存货种类'

/**
 * (3) 计提方式二选一（源模板 R47~R61「按组合」与其后「或：…各库龄组合…」为互斥两组）。
 *
 * 表名逐字对齐 note_template_listed §五、9 的 `tables[].name`。
 */
export type F2ListedS3Mode = 'portfolio' | 'aging'

export const F2_PORTFOLIO_TABLES = {
  portfolio: {
    end: '按组合计提存货跌价准备',
    prior: '按组合计提存货跌价准备（续）',
  },
  aging: {
    end: '按库龄组合计提存货跌价准备',
    prior: '按库龄组合计提存货跌价准备（续）',
  },
} as const satisfies Record<F2ListedS3Mode, { end: string; prior: string }>

/** 未选中的那一组 → `_removed_table_keys`（后端跳过本次推送键，不会误删） */
export function f2ObsoletePortfolioTables(mode: F2ListedS3Mode): string[] {
  const other = mode === 'portfolio' ? F2_PORTFOLIO_TABLES.aging : F2_PORTFOLIO_TABLES.portfolio
  return [other.end, other.prior]
}

/**
 * 上市列头。`mode` 决定 (3) 推送哪一组表名，与 `buildF2ListedSubTableData` 同源，
 * 保证 `columns` 键集合 === `sub_table_data` 数据键集合。
 *
 * 默认参数为 `'portfolio'` —— 平台覆盖率 sweep 会以空入参调用本函数，
 * 必须仍返回非空列头（否则触发「列头为空」守卫）。
 */
export function buildF2ListedColumns(
  mode: F2ListedS3Mode = 'portfolio',
): Record<string, ColumnDef[]> {
  return {
    // 两级表头：期末余额{账面余额,跌价准备,账面价值} / 上年年末余额{同}
    存货分类: [
      { key: 'label', label: F2_LISTED_LABEL_HEADER, is_label: true },
      { key: 'end_gross', label: '账面余额', group: '期末余额', format: 'amount' },
      { key: 'end_impairment', label: '跌价准备/合同履约成本减值准备', group: '期末余额', format: 'amount' },
      { key: 'end_net', label: '账面价值', group: '期末余额', format: 'amount' },
      { key: 'prior_gross', label: '账面余额', group: '上年年末余额', format: 'amount' },
      { key: 'prior_impairment', label: '跌价准备/合同履约成本减值准备', group: '上年年末余额', format: 'amount' },
      { key: 'prior_net', label: '账面价值', group: '上年年末余额', format: 'amount' },
    ],
    // 两级表头：本期增加{计提,其他} / 本期减少{转回或转销,其他}；期初/期末为无分组列
    存货跌价准备及合同履约成本减值准备: [
      { key: 'label', label: F2_LISTED_LABEL_HEADER, is_label: true },
      { key: 'opening', label: '期初余额', format: 'amount' },
      { key: 'increase_provision', label: '计提', group: '本期增加', format: 'amount' },
      { key: 'increase_other', label: '其他', group: '本期增加', format: 'amount' },
      { key: 'decrease_reversal', label: '转回或转销', group: '本期减少', format: 'amount' },
      { key: 'decrease_other', label: '其他', group: '本期减少', format: 'amount' },
      { key: 'ending', label: '期末余额', format: 'amount' },
    ],
    '存货跌价准备及合同履约成本减值准备（续）': [
      // flat：源模板 B35/C35 为单行表头（与模板 JSON 的 columns 保持一致）
      { key: 'label', label: F2_LISTED_LABEL_HEADER, is_label: true, flat: true },
      { key: 'nrv_basis', label: '确定可变现净值/剩余对价与将要发生的成本的具体依据' },
      { key: 'reversal_reason', label: '本期转回或转销存货跌价准备/合同履约成本减值准备的原因' },
    ],
    // 库龄组合与按组合列结构完全相同（源模板同形），按 mode 二选一
    [F2_PORTFOLIO_TABLES[mode].end]: buildPortfolioColumns(),
    [F2_PORTFOLIO_TABLES[mode].prior]: buildPortfolioColumns(),
    // (5)~(7) 房企附表为单级表头（源模板 R67/R75/R84）→ flat 抑制前缀推断，
    // 否则「本期增加/本期减少」会被反猜出一个源模板不存在的「本期」父表头
    开发成本: [
      { key: 'project_name', label: '项目名称', is_label: true, flat: true },
      { key: 'start_date', label: '开工时间' },
      { key: 'expected_complete_date', label: '预计竣工时间' },
      { key: 'estimated_investment', label: '预计总投资', format: 'amount' },
      { key: 'end_balance', label: '期末数', format: 'amount' },
      { key: 'prior_balance', label: '上年年末数', format: 'amount' },
      { key: 'end_impairment', label: '期末跌价准备', format: 'amount' },
    ],
    开发产品: [
      { key: 'project_name', label: '项目名称', is_label: true, flat: true },
      { key: 'complete_date', label: '竣工时间' },
      { key: 'opening', label: '期初余额', format: 'amount' },
      { key: 'increase', label: '本期增加', format: 'amount' },
      { key: 'decrease', label: '本期减少', format: 'amount' },
      { key: 'ending', label: '期末余额', format: 'amount' },
      { key: 'end_impairment', label: '期末跌价准备', format: 'amount' },
    ],
    周转房: [
      { key: 'project_name', label: '项目名称', is_label: true, flat: true },
      { key: 'opening', label: '期初余额', format: 'amount' },
      { key: 'increase', label: '本期增加', format: 'amount' },
      { key: 'decrease', label: '本期减少', format: 'amount' },
      { key: 'ending', label: '期末余额', format: 'amount' },
    ],
    确认为存货的数据资源: buildDataResourceColumns(),
  }
}

export function buildF2SoeColumns(): Record<string, ColumnDef[]> {
  return {
    // 两级表头：期末数{账面余额,跌价准备,账面价值} / 期初数{同}（国企用「期末数/期初数」）
    存货分类: [
      { key: 'label', label: '项目', is_label: true },
      { key: 'end_gross', label: '账面余额', group: '期末数', format: 'amount' },
      { key: 'end_impairment', label: '跌价准备/合同履约成本减值准备', group: '期末数', format: 'amount' },
      { key: 'end_net', label: '账面价值', group: '期末数', format: 'amount' },
      { key: 'prior_gross', label: '账面余额', group: '期初数', format: 'amount' },
      { key: 'prior_impairment', label: '跌价准备/合同履约成本减值准备', group: '期初数', format: 'amount' },
      { key: 'prior_net', label: '账面价值', group: '期初数', format: 'amount' },
    ],
    // 两级表头：本期增加{计提,其他} / 本期减少{转回,转销,其他}——国企转回与转销分列
    存货跌价准备及合同履约成本减值准备: [
      { key: 'label', label: '存货种类', is_label: true },
      { key: 'opening', label: '期初数', format: 'amount' },
      { key: 'increase_provision', label: '计提', group: '本期增加', format: 'amount' },
      { key: 'increase_other', label: '其他', group: '本期增加', format: 'amount' },
      { key: 'decrease_reversal', label: '转回', group: '本期减少', format: 'amount' },
      { key: 'decrease_writeoff', label: '转销', group: '本期减少', format: 'amount' },
      { key: 'decrease_other', label: '其他', group: '本期减少', format: 'amount' },
      { key: 'ending', label: '期末数', format: 'amount' },
    ],
    确认为存货的数据资源: buildDataResourceColumns(),
  }
}

export interface F2ListedSyncSnapshot {
  section1Rows: Array<{
    rowKey: string
    label: string
    endGross: number
    endImpairment: number
    endNet: number
    priorGross: number
    priorImpairment: number
    priorNet: number
  }>
  section1Total: {
    label: string
    endGross: number
    endImpairment: number
    endNet: number
    priorGross: number
    priorImpairment: number
    priorNet: number
  }
  section2Rows: Array<{
    rowKey: string
    label: string
    opening: number
    incProvision: number
    incOther: number
    decReversal: number
    decOther: number
    ending: number
  }>
  section2Total: {
    label: string
    opening: number
    incProvision: number
    incOther: number
    decReversal: number
    decOther: number
    ending: number
  }
  section2QualRows: Array<{
    rowKey: string
    label: string
    nrvBasis: string
    reversalReason: string
  }>
  s3EndRows: Array<{
    groupName: string
    balance: number
    balancePct: number
    impairment: number
    provisionStandard: string
    impairmentPct: number
    netValue: number
  }>
  s3PriorRows: Array<{
    groupName: string
    balance: number
    balancePct: number
    impairment: number
    provisionStandard: string
    impairmentPct: number
    netValue: number
  }>
  /** (3) 计提方式：决定推送「按组合」还是「按库龄组合」两表 */
  s3Mode: F2ListedS3Mode
  s4BorrowText: string
  /** (4) 合同履约成本本期摊销说明（源：附注模版「（说明合同履约成本本期摊销金额。）」） */
  s4AmortText: string
  s5Rows: Array<{
    projectName: string
    startDate: string
    expectedCompleteDate: string
    estimatedInvestment: number
    endBalance: number
    priorBalance: number
    endImpairment: number
  }>
  s6Rows: Array<{
    projectName: string
    completeDate: string
    opening: number
    increase: number
    decrease: number
    ending: number
    endImpairment: number
  }>
  s7Rows: Array<{
    projectName: string
    opening: number
    increase: number
    decrease: number
    ending: number
  }>
  /** (8) 确认为存货的数据资源（21 行三段式） */
  s8DataResourceRows: DrSyncRow[]
  noteCategory: string
  noteNrv: string
  noteProvision: string
  noteRe: string
}

export interface F2SoeSyncSnapshot {
  section1Rows: Array<{
    rowKey: string
    label: string
    kind: string
    endGross: number
    endImpairment: number
    endNet: number
    priorGross: number
    priorImpairment: number
    priorNet: number
  }>
  section1Total: {
    label: string
    endGross: number
    endImpairment: number
    endNet: number
    priorGross: number
    priorImpairment: number
    priorNet: number
  }
  section2Rows: Array<{
    rowKey: string
    label: string
    opening: number
    incProvision: number
    incOther: number
    decReversal: number
    decWriteOff: number
    decOther: number
    ending: number
  }>
  section2Total: {
    label: string
    opening: number
    incProvision: number
    incOther: number
    decReversal: number
    decWriteOff: number
    decOther: number
    ending: number
  }
  /** (5) 确认为存货的数据资源（21 行三段式） */
  s5DataResourceRows: DrSyncRow[]
  noteCategory: string
  /** (1) 土地储备说明（源模板 r23 注：面积 / 本期增加 / 期末余额） */
  landNote: string
  s3BorrowText: string
  s4AmortText: string
  noteText: string
}

export interface F2NoteTextRow {
  section: string
  title: string
  text: string
}

/**
 * 说明文本 → `_note_texts`（后端 `_format_note_texts` 渲染成 `【title】\n正文`）。
 *
 * 🔴 `title` 必填中文：缺省时后端会用 `section` 兜底，附注正文里出现
 * `【listed-note-category】` 这类英文键（违反 UI 全中文化）。空文本直接丢弃。
 */
export function buildF2NoteTexts(
  entries: ReadonlyArray<readonly [section: string, title: string, text: string]>,
): F2NoteTextRow[] {
  const out: F2NoteTextRow[] = []
  for (const [section, title, text] of entries) {
    const body = String(text ?? '').trim()
    if (!body) continue
    out.push({ section, title, text: body })
  }
  return out
}

function classRow(r: F2ListedSyncSnapshot['section1Rows'][number] | F2ListedSyncSnapshot['section1Total']) {
  return {
    label: r.label,
    end_gross: r.endGross,
    end_impairment: r.endImpairment,
    end_net: r.endNet,
    prior_gross: r.priorGross,
    prior_impairment: r.priorImpairment,
    prior_net: r.priorNet,
  }
}

function portfolioRow(r: F2ListedSyncSnapshot['s3EndRows'][number]): Record<string, unknown> {
  return {
    group_name: r.groupName,
    balance: r.balance,
    balance_pct: r.balancePct,
    impairment: r.impairment,
    provision_standard: r.provisionStandard,
    impairment_pct: r.impairmentPct,
    net_value: r.netValue,
  }
}

export function buildF2ListedSubTableData(snap: F2ListedSyncSnapshot): F2SubTableData {
  const s3Mode: F2ListedS3Mode = snap.s3Mode === 'aging' ? 'aging' : 'portfolio'
  const s3Tables = F2_PORTFOLIO_TABLES[s3Mode]
  const tables: Record<string, Record<string, unknown>[]> = {
    存货分类: [
      ...snap.section1Rows.map(classRow),
      { ...classRow(snap.section1Total), is_total: true },
    ],
    存货跌价准备及合同履约成本减值准备: [
      ...snap.section2Rows.map((r) => ({
        label: r.label,
        opening: r.opening,
        increase_provision: r.incProvision,
        increase_other: r.incOther,
        decrease_reversal: r.decReversal,
        decrease_other: r.decOther,
        ending: r.ending,
      })),
      {
        label: snap.section2Total.label,
        opening: snap.section2Total.opening,
        increase_provision: snap.section2Total.incProvision,
        increase_other: snap.section2Total.incOther,
        decrease_reversal: snap.section2Total.decReversal,
        decrease_other: snap.section2Total.decOther,
        ending: snap.section2Total.ending,
        is_total: true,
      },
    ],
    '存货跌价准备及合同履约成本减值准备（续）': snap.section2QualRows.map((r) => ({
      label: r.label,
      nrv_basis: r.nrvBasis,
      reversal_reason: r.reversalReason,
    })),
    [s3Tables.end]: snap.s3EndRows.map(portfolioRow),
    [s3Tables.prior]: snap.s3PriorRows.map(portfolioRow),
    开发成本: snap.s5Rows.map((r) => ({
      project_name: r.projectName,
      start_date: r.startDate,
      expected_complete_date: r.expectedCompleteDate,
      estimated_investment: r.estimatedInvestment,
      end_balance: r.endBalance,
      prior_balance: r.priorBalance,
      end_impairment: r.endImpairment,
    })),
    开发产品: snap.s6Rows.map((r) => ({
      project_name: r.projectName,
      complete_date: r.completeDate,
      opening: r.opening,
      increase: r.increase,
      decrease: r.decrease,
      ending: r.ending,
      end_impairment: r.endImpairment,
    })),
    周转房: snap.s7Rows.map((r) => ({
      project_name: r.projectName,
      opening: r.opening,
      increase: r.increase,
      decrease: r.decrease,
      ending: r.ending,
    })),
    // 容错残缺快照：缺该子表时推空数组而非抛错（同步链路不因单表缺失整体失败）
    确认为存货的数据资源: (snap.s8DataResourceRows ?? []).map((r) => ({ ...r })),
  }
  return withMeta(tables, {
    _note_texts: buildF2NoteTexts([
      ['listed-note-category', '存货分类说明', snap.noteCategory],
      ['listed-note-nrv', '可变现净值确定依据', snap.noteNrv],
      ['listed-note-provision', '跌价准备计提政策说明', snap.noteProvision],
      ['listed-note-borrow', '存货期末余额中含有借款费用资本化金额的说明', snap.s4BorrowText],
      ['listed-note-amort', '合同履约成本本期摊销金额的说明', snap.s4AmortText],
      ['listed-note-re', '房地产开发企业披露说明', snap.noteRe],
    ]),
    // 二选一：未采用的那一组从附注删除（源模板「或：」关系）。
    // `_drop_removed_tables` 会跳过本次推送键，故不会自删。
    _removed_table_keys: f2ObsoletePortfolioTables(s3Mode),
  })
}

export function buildF2SoeSubTableData(snap: F2SoeSyncSnapshot): F2SubTableData {
  const tables: Record<string, Record<string, unknown>[]> = {
    存货分类: [
      ...snap.section1Rows.map((r) => ({
        label: r.label,
        kind: r.kind,
        end_gross: r.endGross,
        end_impairment: r.endImpairment,
        end_net: r.endNet,
        prior_gross: r.priorGross,
        prior_impairment: r.priorImpairment,
        prior_net: r.priorNet,
      })),
      {
        label: snap.section1Total.label,
        end_gross: snap.section1Total.endGross,
        end_impairment: snap.section1Total.endImpairment,
        end_net: snap.section1Total.endNet,
        prior_gross: snap.section1Total.priorGross,
        prior_impairment: snap.section1Total.priorImpairment,
        prior_net: snap.section1Total.priorNet,
        is_total: true,
      },
    ],
    存货跌价准备及合同履约成本减值准备: [
      ...snap.section2Rows.map((r) => ({
        label: r.label,
        opening: r.opening,
        increase_provision: r.incProvision,
        increase_other: r.incOther,
        decrease_reversal: r.decReversal,
        decrease_writeoff: r.decWriteOff,
        decrease_other: r.decOther,
        ending: r.ending,
      })),
      {
        label: snap.section2Total.label,
        opening: snap.section2Total.opening,
        increase_provision: snap.section2Total.incProvision,
        increase_other: snap.section2Total.incOther,
        decrease_reversal: snap.section2Total.decReversal,
        decrease_writeoff: snap.section2Total.decWriteOff,
        decrease_other: snap.section2Total.decOther,
        ending: snap.section2Total.ending,
        is_total: true,
      },
    ],
    // 容错残缺快照：缺该子表时推空数组而非抛错
    确认为存货的数据资源: (snap.s5DataResourceRows ?? []).map((r) => ({ ...r })),
  }
  return withMeta(tables, {
    _note_texts: buildF2NoteTexts([
      // 🔴 `soe-note-land` 曾整条缺失：底稿有「土地储备说明」输入框 + AI 辅助，
      // 但快照没这字段 → 填了永远回流不到附注（源模板 r23 注要求披露）。
      ['soe-note-land', '土地储备说明', snap.landNote],
      ['soe-note-category', '存货分类说明', snap.noteCategory],
      ['soe-note-borrow', '借款费用资本化', snap.s3BorrowText],
      ['soe-note-amort', '合同履约成本本期摊销金额的说明', snap.s4AmortText],
      ['soe-note', '其他附注说明', snap.noteText],
    ]),
  })
}

export function buildF2SyncPayload(
  variant: F2DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  subTableData: F2SubTableData,
): F2SyncFromWorkpaperPayload | null {
  const target = resolveF2NoteSectionTarget(variant, applicableStandards)
  if (!target) return null
  // 防御：禁止一页 payload 携带对方章节
  const expected = F2_NOTE_SECTION[variant]
  if (target.sectionId !== expected) return null
  // (3) 计提方式：列头必须与 sub_table_data 推的那一组表名一致，否则出孤儿列头
  const s3Mode: F2ListedS3Mode = F2_PORTFOLIO_TABLES.aging.end in subTableData
    ? 'aging'
    : 'portfolio'
  return {
    wp_id: wpId,
    sheet_name: F2_DISCLOSURE_SHEET_NAME[variant],
    section_id: target.sectionId,
    current_standard: resolveF2CurrentStandard(variant, applicableStandards),
    sub_table_data: subTableData,
    columns: variant === 'listed' ? buildF2ListedColumns(s3Mode) : buildF2SoeColumns(),
  }
}
