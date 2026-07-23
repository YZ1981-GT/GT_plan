/**
 * H2 披露 → disclosure_notes sync payload
 * - 上市：note_template_listed §五、23
 * - 国企：note_template_soe §八、23
 */
import {
  H2_DISCLOSURE_SHEET_NAME,
  H2_LISTED_SUBTABLE,
  H2_NOTE_SECTION,
  H2_SOE_SUBTABLE,
  isH2DisclosureApplicable,
  resolveH2CurrentStandard,
  type H2DisclosureVariant,
} from './h2NoteSectionMap'
import {
  listedDetailNet,
  listedDetailSubtotal,
  listedImpairmentEnd,
  listedImpairmentSubtotal,
  listedMaterialsNet,
  listedProjectCumPct,
  listedProjectEnd,
  listedProjectSubtotal,
  listedSummaryTotal,
  num,
  type ListedDetailRow,
  type ListedImpairmentRow,
  type ListedMaterialRow,
  type ListedMortgageRow,
  type ListedProjectRow,
  type ListedSummaryRow,
} from './h2ListedDisclosureModel'
import {
  soeCarrying,
  soeDetailSubtotal,
  soeImpairmentSubtotal,
  soeProjectCumPct,
  soeProjectEnd,
  soeProjectSubtotal,
  soeSummaryTotal,
  type SoeDetailRow,
  type SoeImpairmentRow,
  type SoeProjectRow,
  type SoeSummaryRow,
} from './h2SoeDisclosureModel'

import type { ColumnDef } from './disclosureColumnDefs'

export interface H2SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 H2TabDisclosure el-table-column（两级表头扁平合并） */
  columns?: Record<string, ColumnDef[]>
}

export interface H2ListedSyncSnapshot {
  summary: ListedSummaryRow[]
  detail: ListedDetailRow[]
  projects: ListedProjectRow[]
  impairment: ListedImpairmentRow[]
  materials: ListedMaterialRow[]
  mortgage: ListedMortgageRow[]
  noteImpairment: string
  noteFundSource: string
  noteMortgage: string
}

export interface H2SoeSyncSnapshot {
  summary: SoeSummaryRow[]
  detail: SoeDetailRow[]
  projects: SoeProjectRow[]
  impairment: SoeImpairmentRow[]
  noteImpairment: string
}

function nonEmptyLabel(label: string): boolean {
  return Boolean(String(label || '').trim())
}

export function buildH2ListedSubTableData(state: H2ListedSyncSnapshot): Record<string, Record<string, unknown>[]> {
  const sumTot = listedSummaryTotal(state.summary)
  const summaryRows: Record<string, unknown>[] = state.summary.map((r) => ({
    label: r.label,
    end_balance: num(r.endBalance),
    prior_balance: num(r.priorBalance),
  }))
  summaryRows.push({
    label: '合计',
    end_balance: sumTot.endBalance,
    prior_balance: sumTot.priorBalance,
    is_total: true,
  })

  const detailRows: Record<string, unknown>[] = state.detail
    .filter((r) => nonEmptyLabel(r.name))
    .map((r) => ({
      label: r.name,
      end_book: num(r.endBook),
      end_impairment: num(r.endImpairment),
      end_net: listedDetailNet(r.endBook, r.endImpairment),
      prior_book: num(r.priorBook),
      prior_impairment: num(r.priorImpairment),
      prior_net: listedDetailNet(r.priorBook, r.priorImpairment),
      // 附注模板简化列为期末/上年年末时用净值
      end_balance: listedDetailNet(r.endBook, r.endImpairment),
      prior_balance: listedDetailNet(r.priorBook, r.priorImpairment),
    }))
  const detTot = listedDetailSubtotal(state.detail)
  detailRows.push({
    label: '合计',
    end_book: detTot.endBook,
    end_impairment: detTot.endImpairment,
    end_net: detTot.endNet,
    prior_book: detTot.priorBook,
    prior_impairment: detTot.priorImpairment,
    prior_net: detTot.priorNet,
    end_balance: detTot.endNet,
    prior_balance: detTot.priorNet,
    is_total: true,
  })

  const moveRows: Record<string, unknown>[] = state.projects
    .filter((r) => nonEmptyLabel(r.name))
    .map((r) => ({
      label: r.name,
      begin_balance: num(r.beginBalance),
      increase: num(r.increase),
      transfer_to_fa: num(r.transferToFA),
      other_decrease: num(r.otherDecrease),
      interest_cap_accum: num(r.interestCapAccum),
      interest_cap_current: num(r.interestCapCurrent),
      interest_cap_rate: num(r.interestCapRate),
      end_balance: listedProjectEnd(r),
    }))
  const moveTot = listedProjectSubtotal(state.projects)
  moveRows.push({
    label: '合计',
    begin_balance: moveTot.beginBalance,
    increase: moveTot.increase,
    transfer_to_fa: moveTot.transferToFA,
    other_decrease: moveTot.otherDecrease,
    interest_cap_accum: moveTot.interestCapAccum,
    interest_cap_current: moveTot.interestCapCurrent,
    interest_cap_rate: null,
    end_balance: moveTot.endBalance,
    is_total: true,
  })

  const contRows: Record<string, unknown>[] = state.projects
    .filter((r) => nonEmptyLabel(r.name))
    .map((r) => ({
      label: r.name,
      budget: num(r.budget),
      cum_input_pct: listedProjectCumPct(r),
      progress: r.progress || '',
      fund_source: r.fundSource || '',
    }))
  contRows.push({
    label: '合计',
    budget: moveTot.budget,
    cum_input_pct: moveTot.cumInputPct,
    progress: '',
    fund_source: '',
    is_total: true,
  })

  const impRows: Record<string, unknown>[] = state.impairment
    .filter((r) => nonEmptyLabel(r.name))
    .map((r) => ({
      label: r.name,
      begin_balance: num(r.beginBalance),
      provision: num(r.provision),
      decrease: num(r.decrease),
      end_balance: listedImpairmentEnd(r),
    }))
  const impTot = listedImpairmentSubtotal(state.impairment)
  impRows.push({
    label: '合计',
    begin_balance: impTot.beginBalance,
    provision: impTot.provision,
    decrease: impTot.decrease,
    end_balance: impTot.endBalance,
    is_total: true,
  })

  const matNet = listedMaterialsNet(state.materials)
  const matRows: Record<string, unknown>[] = state.materials.map((r) => ({
    label: r.label,
    end_balance: r.isDeduction ? -num(r.endBalance) : num(r.endBalance),
    prior_balance: r.isDeduction ? -num(r.priorBalance) : num(r.priorBalance),
  }))
  matRows.push({
    label: '合计',
    end_balance: matNet.endBalance,
    prior_balance: matNet.priorBalance,
    is_total: true,
  })

  const mortRows: Record<string, unknown>[] = (state.mortgage || [])
    .filter((r) => nonEmptyLabel(r.name))
    .map((r) => ({
      label: r.name,
      amount: num(r.amount),
      end_balance: num(r.amount),
      description: r.description || '',
      remark: r.remark || '',
    }))
  if (mortRows.length) {
    const mortTotal = mortRows.reduce((s, r) => s + num(r.amount), 0)
    mortRows.push({
      label: '合计',
      amount: mortTotal,
      end_balance: mortTotal,
      description: '',
      remark: '',
      is_total: true,
    })
  }

  return {
    [H2_LISTED_SUBTABLE.summary]: summaryRows,
    [H2_LISTED_SUBTABLE.detail]: detailRows,
    [H2_LISTED_SUBTABLE.projectMovement]: moveRows,
    [H2_LISTED_SUBTABLE.projectCont]: contRows,
    [H2_LISTED_SUBTABLE.impairment]: impRows,
    [H2_LISTED_SUBTABLE.materials]: matRows,
    ...(mortRows.length ? { [H2_LISTED_SUBTABLE.restricted]: mortRows } : {}),
    _note_texts: [
      { section: 'listed-impairment', text: state.noteImpairment || '' },
      { section: 'listed-fund-source', text: state.noteFundSource || '' },
      { section: 'listed-mortgage', text: state.noteMortgage || '' },
    ] as unknown as Record<string, unknown>[],
  }
}

export function buildH2SoeSubTableData(state: H2SoeSyncSnapshot): Record<string, Record<string, unknown>[]> {
  const sumTot = soeSummaryTotal(state.summary)
  const summaryRows: Record<string, unknown>[] = state.summary.map((r) => ({
    label: r.label,
    end_book: num(r.endBook),
    end_impairment: num(r.endImpairment),
    end_carrying: soeCarrying(r.endBook, r.endImpairment),
    begin_book: num(r.beginBook),
    begin_impairment: num(r.beginImpairment),
    begin_carrying: soeCarrying(r.beginBook, r.beginImpairment),
    end_balance: soeCarrying(r.endBook, r.endImpairment),
    begin_balance: soeCarrying(r.beginBook, r.beginImpairment),
  }))
  summaryRows.push({
    label: '合计',
    end_book: sumTot.endBook,
    end_impairment: sumTot.endImpairment,
    end_carrying: sumTot.endCarrying,
    begin_book: sumTot.beginBook,
    begin_impairment: sumTot.beginImpairment,
    begin_carrying: sumTot.beginCarrying,
    end_balance: sumTot.endCarrying,
    begin_balance: sumTot.beginCarrying,
    is_total: true,
  })

  const detailRows: Record<string, unknown>[] = state.detail
    .filter((r) => nonEmptyLabel(r.name))
    .map((r) => ({
      label: r.name,
      end_book: num(r.endBook),
      end_impairment: num(r.endImpairment),
      end_carrying: soeCarrying(r.endBook, r.endImpairment),
      begin_book: num(r.beginBook),
      begin_impairment: num(r.beginImpairment),
      begin_carrying: soeCarrying(r.beginBook, r.beginImpairment),
      end_balance: soeCarrying(r.endBook, r.endImpairment),
      begin_balance: soeCarrying(r.beginBook, r.beginImpairment),
    }))
  const detTot = soeDetailSubtotal(state.detail)
  detailRows.push({
    label: '合计',
    end_book: detTot.endBook,
    end_impairment: detTot.endImpairment,
    end_carrying: detTot.endCarrying,
    begin_book: detTot.beginBook,
    begin_impairment: detTot.beginImpairment,
    begin_carrying: detTot.beginCarrying,
    end_balance: detTot.endCarrying,
    begin_balance: detTot.beginCarrying,
    is_total: true,
  })

  const projRows: Record<string, unknown>[] = state.projects
    .filter((r) => nonEmptyLabel(r.name))
    .map((r) => ({
      label: r.name,
      budget: num(r.budget),
      begin_balance: num(r.beginBalance),
      increase: num(r.increase),
      transfer_to_fa: num(r.transferToFA),
      other_decrease: num(r.otherDecrease),
      end_balance: soeProjectEnd(r),
      cum_input_pct: soeProjectCumPct(r),
      progress: r.progress || '',
      interest_cap_accum: num(r.interestCapAccum),
      interest_cap_current: num(r.interestCapCurrent),
      interest_cap_rate: num(r.interestCapRate),
      fund_source: r.fundSource || '',
    }))
  const pTot = soeProjectSubtotal(state.projects)
  projRows.push({
    label: '合计',
    budget: pTot.budget,
    begin_balance: pTot.beginBalance,
    increase: pTot.increase,
    transfer_to_fa: pTot.transferToFA,
    other_decrease: pTot.otherDecrease,
    end_balance: pTot.endBalance,
    cum_input_pct: pTot.cumInputPct,
    progress: '',
    interest_cap_accum: pTot.interestCapAccum,
    interest_cap_current: pTot.interestCapCurrent,
    interest_cap_rate: null,
    fund_source: '',
    is_total: true,
  })

  const impRows: Record<string, unknown>[] = state.impairment
    .filter((r) => nonEmptyLabel(r.name) || num(r.provisionAmount))
    .map((r) => ({
      label: r.name,
      provision_amount: num(r.provisionAmount),
      reason: r.reason || '',
    }))
  impRows.push({
    label: '合计',
    provision_amount: soeImpairmentSubtotal(state.impairment),
    reason: '',
    is_total: true,
  })

  return {
    [H2_SOE_SUBTABLE.summary]: summaryRows,
    [H2_SOE_SUBTABLE.detail]: detailRows,
    [H2_SOE_SUBTABLE.projectMovement]: projRows,
    [H2_SOE_SUBTABLE.impairment]: impRows,
    _note_texts: [
      { section: 'soe-impairment', text: state.noteImpairment || '' },
    ] as unknown as Record<string, unknown>[],
  }
}

// ─── 列头定义（label 取自 H2TabDisclosure el-table-column，两级表头扁平合并）───

const H2_LISTED_COLUMNS: Record<string, ColumnDef[]> = {
  [H2_LISTED_SUBTABLE.summary]: [
    { key: 'label', label: '项目', is_label: true },
    { key: 'end_balance', label: '期末余额', format: 'amount' },
    { key: 'prior_balance', label: '上年年末余额', format: 'amount' },
  ],
  [H2_LISTED_SUBTABLE.detail]: [
    { key: 'label', label: '项目', is_label: true },
    { key: 'end_book', label: '期末余额-账面余额', format: 'amount' },
    { key: 'end_impairment', label: '期末余额-减值准备', format: 'amount' },
    { key: 'end_net', label: '期末余额-账面净值', format: 'amount' },
    { key: 'prior_book', label: '上年年末余额-账面余额', format: 'amount' },
    { key: 'prior_impairment', label: '上年年末余额-减值准备', format: 'amount' },
    { key: 'prior_net', label: '上年年末余额-账面净值', format: 'amount' },
  ],
  [H2_LISTED_SUBTABLE.projectMovement]: [
    { key: 'label', label: '工程名称', is_label: true },
    { key: 'begin_balance', label: '期初余额', format: 'amount' },
    { key: 'increase', label: '本期增加', format: 'amount' },
    { key: 'transfer_to_fa', label: '转入固定资产', format: 'amount' },
    { key: 'other_decrease', label: '其他减少', format: 'amount' },
    { key: 'interest_cap_accum', label: '利息资本化累计金额', format: 'amount' },
    { key: 'interest_cap_current', label: '其中：本期利息资本化金额', format: 'amount' },
    { key: 'interest_cap_rate', label: '本期利息资本化率%' },
    { key: 'end_balance', label: '期末余额', format: 'amount' },
  ],
  [H2_LISTED_SUBTABLE.projectCont]: [
    { key: 'label', label: '工程名称', is_label: true },
    { key: 'budget', label: '预算数', format: 'amount' },
    { key: 'cum_input_pct', label: '工程累计投入占预算比例%' },
    { key: 'progress', label: '工程进度' },
    { key: 'fund_source', label: '资金来源' },
  ],
  [H2_LISTED_SUBTABLE.impairment]: [
    { key: 'label', label: '项目', is_label: true },
    { key: 'begin_balance', label: '期初余额', format: 'amount' },
    { key: 'provision', label: '本期计提', format: 'amount' },
    { key: 'decrease', label: '本期减少', format: 'amount' },
    { key: 'end_balance', label: '期末余额', format: 'amount' },
  ],
  [H2_LISTED_SUBTABLE.materials]: [
    { key: 'label', label: '项目', is_label: true },
    { key: 'end_balance', label: '期末余额', format: 'amount' },
    { key: 'prior_balance', label: '上年年末余额', format: 'amount' },
  ],
  [H2_LISTED_SUBTABLE.restricted]: [
    { key: 'label', label: '项目', is_label: true },
    { key: 'amount', label: '金额', format: 'amount' },
    { key: 'description', label: '说明' },
    { key: 'remark', label: '备注' },
  ],
}

const H2_SOE_TWO_LEVEL: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'end_book', label: '期末余额-账面余额', format: 'amount' },
  { key: 'end_impairment', label: '期末余额-减值准备', format: 'amount' },
  { key: 'end_carrying', label: '期末余额-账面价值', format: 'amount' },
  { key: 'begin_book', label: '期初余额-账面余额', format: 'amount' },
  { key: 'begin_impairment', label: '期初余额-减值准备', format: 'amount' },
  { key: 'begin_carrying', label: '期初余额-账面价值', format: 'amount' },
]

const H2_SOE_COLUMNS: Record<string, ColumnDef[]> = {
  [H2_SOE_SUBTABLE.summary]: H2_SOE_TWO_LEVEL,
  [H2_SOE_SUBTABLE.detail]: H2_SOE_TWO_LEVEL,
  [H2_SOE_SUBTABLE.projectMovement]: [
    { key: 'label', label: '项目名称', is_label: true },
    { key: 'budget', label: '预算数', format: 'amount' },
    { key: 'begin_balance', label: '期初余额', format: 'amount' },
    { key: 'increase', label: '本期增加', format: 'amount' },
    { key: 'transfer_to_fa', label: '本期转入固定资产金额', format: 'amount' },
    { key: 'other_decrease', label: '本期其他减少金额', format: 'amount' },
    { key: 'end_balance', label: '期末余额', format: 'amount' },
    { key: 'cum_input_pct', label: '工程累计投入占预算比例(%)' },
    { key: 'progress', label: '工程进度' },
    { key: 'interest_cap_accum', label: '利息资本化累计金额', format: 'amount' },
    { key: 'interest_cap_current', label: '其中：本期利息资本化金额', format: 'amount' },
    { key: 'interest_cap_rate', label: '本期利息资本化率(%)' },
    { key: 'fund_source', label: '资金来源' },
  ],
  [H2_SOE_SUBTABLE.impairment]: [
    { key: 'label', label: '项目', is_label: true },
    { key: 'provision_amount', label: '计提金额', format: 'amount' },
    { key: 'reason', label: '原因' },
  ],
}

export function buildH2ListedSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  state: H2ListedSyncSnapshot,
): H2SyncFromWorkpaperPayload[] {
  const variant: H2DisclosureVariant = 'listed'
  if (!isH2DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: H2_DISCLOSURE_SHEET_NAME.listed,
    section_id: H2_NOTE_SECTION.listed,
    current_standard: resolveH2CurrentStandard(variant, applicableStandards),
    sub_table_data: buildH2ListedSubTableData(state),
    columns: H2_LISTED_COLUMNS,
  }]
}

export function buildH2SoeSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  state: H2SoeSyncSnapshot,
): H2SyncFromWorkpaperPayload[] {
  const variant: H2DisclosureVariant = 'soe'
  if (!isH2DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: H2_DISCLOSURE_SHEET_NAME.soe,
    section_id: H2_NOTE_SECTION.soe,
    current_standard: resolveH2CurrentStandard(variant, applicableStandards),
    sub_table_data: buildH2SoeSubTableData(state),
    columns: H2_SOE_COLUMNS,
  }]
}
