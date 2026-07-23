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

export interface F2SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 F2 披露组件既有 el-table-column */
  columns?: Record<string, ColumnDef[]>
}

// ── 列头元数据：label 逐字取自 F2TabDisclosureListed/Soe 的 el-table-column（源对齐，禁止杜撰）──
// 两级表头（如「期末数 > 账面余额」）在扁平投影中合并为「期末账面余额」，保留源语义。

export function buildF2ListedColumns(): Record<string, ColumnDef[]> {
  return {
    存货分类: [
      { key: 'label', label: '存货种类', is_label: true },
      { key: 'end_gross', label: '期末账面余额', format: 'amount' },
      { key: 'end_impairment', label: '期末跌价准备/合同履约成本减值准备', format: 'amount' },
      { key: 'end_net', label: '期末账面价值', format: 'amount' },
      { key: 'prior_gross', label: '上年年末账面余额', format: 'amount' },
      { key: 'prior_impairment', label: '上年年末跌价准备/合同履约成本减值准备', format: 'amount' },
      { key: 'prior_net', label: '上年年末账面价值', format: 'amount' },
    ],
    存货跌价准备及合同履约成本减值准备: [
      { key: 'label', label: '存货种类', is_label: true },
      { key: 'opening', label: '期初余额', format: 'amount' },
      { key: 'increase_provision', label: '本期增加-计提', format: 'amount' },
      { key: 'increase_other', label: '本期增加-其他', format: 'amount' },
      { key: 'decrease_reversal', label: '本期减少-转回或转销', format: 'amount' },
      { key: 'decrease_other', label: '本期减少-其他', format: 'amount' },
      { key: 'ending', label: '期末余额', format: 'amount' },
    ],
    '存货跌价准备及合同履约成本减值准备（续）': [
      { key: 'label', label: '存货种类', is_label: true },
      { key: 'nrv_basis', label: '确定可变现净值/剩余对价与将要发生的成本的具体依据' },
      { key: 'reversal_reason', label: '本期转回或转销存货跌价准备/合同履约成本减值准备的原因' },
    ],
    按组合计提存货跌价准备: [
      { key: 'group_name', label: '组合', is_label: true },
      { key: 'balance', label: '账面余额-金额', format: 'amount' },
      { key: 'balance_pct', label: '账面余额-比例(%)', format: 'percent' },
      { key: 'impairment', label: '存货跌价准备-金额', format: 'amount' },
      { key: 'provision_standard', label: '存货跌价准备-计提标准' },
      { key: 'impairment_pct', label: '存货跌价准备-比例(%)', format: 'percent' },
      { key: 'net_value', label: '账面价值', format: 'amount' },
    ],
    '按组合计提存货跌价准备（续）': [
      { key: 'group_name', label: '组合', is_label: true },
      { key: 'balance', label: '账面余额-金额', format: 'amount' },
      { key: 'balance_pct', label: '账面余额-比例(%)', format: 'percent' },
      { key: 'impairment', label: '存货跌价准备-金额', format: 'amount' },
      { key: 'provision_standard', label: '存货跌价准备-计提标准' },
      { key: 'impairment_pct', label: '存货跌价准备-比例(%)', format: 'percent' },
      { key: 'net_value', label: '账面价值', format: 'amount' },
    ],
    开发成本: [
      { key: 'project_name', label: '项目名称', is_label: true },
      { key: 'start_date', label: '开工时间' },
      { key: 'expected_complete_date', label: '预计竣工时间' },
      { key: 'estimated_investment', label: '预计总投资', format: 'amount' },
      { key: 'end_balance', label: '期末数', format: 'amount' },
      { key: 'prior_balance', label: '上年年末数', format: 'amount' },
      { key: 'end_impairment', label: '期末跌价准备', format: 'amount' },
    ],
    开发产品: [
      { key: 'project_name', label: '项目名称', is_label: true },
      { key: 'complete_date', label: '竣工时间' },
      { key: 'opening', label: '期初余额', format: 'amount' },
      { key: 'increase', label: '本期增加', format: 'amount' },
      { key: 'decrease', label: '本期减少', format: 'amount' },
      { key: 'ending', label: '期末余额', format: 'amount' },
      { key: 'end_impairment', label: '期末跌价准备', format: 'amount' },
    ],
    周转房: [
      { key: 'project_name', label: '项目名称', is_label: true },
      { key: 'opening', label: '期初余额', format: 'amount' },
      { key: 'increase', label: '本期增加', format: 'amount' },
      { key: 'decrease', label: '本期减少', format: 'amount' },
      { key: 'ending', label: '期末余额', format: 'amount' },
    ],
  }
}

export function buildF2SoeColumns(): Record<string, ColumnDef[]> {
  return {
    存货分类: [
      { key: 'label', label: '项目', is_label: true },
      { key: 'end_gross', label: '期末账面余额', format: 'amount' },
      { key: 'end_impairment', label: '期末跌价准备/合同履约成本减值准备', format: 'amount' },
      { key: 'end_net', label: '期末账面价值', format: 'amount' },
      { key: 'prior_gross', label: '期初账面余额', format: 'amount' },
      { key: 'prior_impairment', label: '期初跌价准备/合同履约成本减值准备', format: 'amount' },
      { key: 'prior_net', label: '期初账面价值', format: 'amount' },
    ],
    存货跌价准备及合同履约成本减值准备: [
      { key: 'label', label: '存货种类', is_label: true },
      { key: 'opening', label: '期初数', format: 'amount' },
      { key: 'increase_provision', label: '本期增加-计提', format: 'amount' },
      { key: 'increase_other', label: '本期增加-其他', format: 'amount' },
      { key: 'decrease_reversal', label: '本期减少-转回', format: 'amount' },
      { key: 'decrease_writeoff', label: '本期减少-转销', format: 'amount' },
      { key: 'decrease_other', label: '本期减少-其他', format: 'amount' },
      { key: 'ending', label: '期末数', format: 'amount' },
    ],
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
  s4BorrowText: string
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
  noteCategory: string
  s3BorrowText: string
  s4AmortText: string
  noteText: string
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

export function buildF2ListedSubTableData(snap: F2ListedSyncSnapshot): Record<string, Record<string, unknown>[]> {
  return {
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
    按组合计提存货跌价准备: snap.s3EndRows.map((r) => ({
      group_name: r.groupName,
      balance: r.balance,
      balance_pct: r.balancePct,
      impairment: r.impairment,
      provision_standard: r.provisionStandard,
      impairment_pct: r.impairmentPct,
      net_value: r.netValue,
    })),
    '按组合计提存货跌价准备（续）': snap.s3PriorRows.map((r) => ({
      group_name: r.groupName,
      balance: r.balance,
      balance_pct: r.balancePct,
      impairment: r.impairment,
      provision_standard: r.provisionStandard,
      impairment_pct: r.impairmentPct,
      net_value: r.netValue,
    })),
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
    _note_texts: [
      { section: 'listed-note-category', text: snap.noteCategory },
      { section: 'listed-note-nrv', text: snap.noteNrv },
      { section: 'listed-note-provision', text: snap.noteProvision },
      { section: 'listed-note-borrow', text: snap.s4BorrowText },
      { section: 'listed-note-re', text: snap.noteRe },
    ],
  }
}

export function buildF2SoeSubTableData(snap: F2SoeSyncSnapshot): Record<string, Record<string, unknown>[]> {
  return {
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
    _note_texts: [
      { section: 'soe-note-category', text: snap.noteCategory },
      { section: 'soe-note-borrow', text: snap.s3BorrowText },
      { section: 'soe-note-amort', text: snap.s4AmortText },
      { section: 'soe-note', text: snap.noteText },
    ],
  }
}

export function buildF2SyncPayload(
  variant: F2DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  subTableData: Record<string, Record<string, unknown>[]>,
): F2SyncFromWorkpaperPayload | null {
  const target = resolveF2NoteSectionTarget(variant, applicableStandards)
  if (!target) return null
  // 防御：禁止一页 payload 携带对方章节
  const expected = F2_NOTE_SECTION[variant]
  if (target.sectionId !== expected) return null
  return {
    wp_id: wpId,
    sheet_name: F2_DISCLOSURE_SHEET_NAME[variant],
    section_id: target.sectionId,
    current_standard: resolveF2CurrentStandard(variant, applicableStandards),
    sub_table_data: subTableData,
    columns: variant === 'listed' ? buildF2ListedColumns() : buildF2SoeColumns(),
  }
}
