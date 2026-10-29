import type { ChecklistResponse } from './useM9FormData'
import {
  buildM9ListedSyncPayload,
  buildM9SoeSyncPayload,
  type M9ListedRow,
  type M9SoeRow,
} from './m9NoteSectionMap'

export type M9Group = 'nonReclass' | 'reclass'
export type M9Statement = 'balanceSheet' | 'incomeStatement'

export interface M9ListedUiRow {
  key: string
  item: string
  priorYearAmount: number
  preTaxAmount: number
  transferToPl: number
  taxEffect: number
  afterTaxMinority: number
}

export interface M9SoeUiRow {
  key: string
  item: string
  /** 上期税前金额（旧 UI 字段名 beginBalance，保留存量键兼容）。 */
  beginBalance: number
  priorTaxEffect: number
  preTaxAmount: number
  taxEffect: number
  /** 本期从其他综合收益转入损益或初始确认金额的扣减。 */
  transferToPL: number
}

const LISTED_NON = [
  ['defined-benefit', '1.重新计量设定受益计划变动额'],
  ['equity-method-nonreclass', '2.权益法下不能转损益的其他综合收益'],
  ['fvoci-equity', '3.其他权益工具投资公允价值变动'],
  ['own-credit', '4.企业自身信用风险公允价值变动'],
] as const

const LISTED_RECLASS = [
  ['equity-method-reclass', '1.权益法下可转损益的其他综合收益'],
  ['fvoci-debt', '2.其他债权投资公允价值变动'],
  ['financial-reclass', '3.金融资产重分类计入其他综合收益的金额'],
  ['fvoci-impairment', '4.其他债权投资信用减值准备'],
  ['cashflow-hedge', '5.现金流量套期储备'],
  ['translation', '6.外币财务报表折算差额'],
] as const

const SOE_NON = [
  ['defined-benefit', '1、重新计量设定受益计划变动额'],
  ['equity-method-nonreclass', '2、权益法下不能转损益的其他综合收益'],
  ['fvoci-equity', '3、其他权益工具投资公允价值变动'],
  ['own-credit', '4、企业自身信用风险公允价值变动'],
  ['insurance-nonreclass', '5、不能转损益的保险合同金融变动（金融企业适用）'],
  ['other-nonreclass', '6、其他'],
] as const

const SOE_RECLASS = [
  ['equity-method-reclass', '1、权益法下可转损益的其他综合收益'],
  ['fvoci-debt', '2、其他债权投资公允价值变动'],
  ['financial-reclass', '3、金融资产重分类计入其他综合收益的金额'],
  ['fvoci-impairment', '4、其他债权投资信用减值准备'],
  ['cashflow-hedge', '5、现金流量套期储备'],
  ['translation', '6、外币财务报表折算差额'],
  ['insurance-reclass', '7、可转损益的保险合同金融变动（金融企业适用）'],
  ['reinsurance-reclass', '8、可转损益的分出再保险合同金融变动（金融企业适用）'],
  ['property-conversion', '9、自用房地产或作为存货的房地产转换为以公允价值计量的投资性房地产在转换日公允价值大于账面价值部分'],
  ['step-disposal', '10、多次交易分步处置子公司股权构成一揽子交易的，丧失控制权之前各次交易处置价款与对应净资产账面价值份额的差额'],
  ['other-reclass', '11、其他'],
] as const

function savedNumber(responses: ReadonlyMap<string, ChecklistResponse>, key: string): number | undefined {
  const raw = responses.get(key)?.remark
  if (raw == null || raw === '') return undefined
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : undefined
}

export function createM9ListedRows(group: M9Group): M9ListedUiRow[] {
  const defs = group === 'nonReclass' ? LISTED_NON : LISTED_RECLASS
  return defs.map(([key, item]) => ({
    key, item, priorYearAmount: 0, preTaxAmount: 0, transferToPl: 0, taxEffect: 0, afterTaxMinority: 0,
  }))
}

export function createM9SoeRows(group: M9Group): M9SoeUiRow[] {
  const defs = group === 'nonReclass' ? SOE_NON : SOE_RECLASS
  return defs.map(([key, item]) => ({
    key, item, beginBalance: 0, priorTaxEffect: 0, preTaxAmount: 0, taxEffect: 0,
    transferToPL: 0,
  }))
}

export function restoreM9ListedRows(
  responses: ReadonlyMap<string, ChecklistResponse>,
  statement: M9Statement,
  group: M9Group,
): M9ListedUiRow[] {
  const rows = createM9ListedRows(group)
  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index]
    for (const field of ['priorYearAmount', 'preTaxAmount', 'transferToPl', 'taxEffect', 'afterTaxMinority'] as const) {
      const key = `M9-disclosure-listed-${statement}-${group}-${row.key}-${field}`
      let value = savedNumber(responses, key)
      // 存量迁移：旧单表键同时作为两张表的初始值，之后两张表各自保存。
      if (value === undefined && ['priorYearAmount', 'preTaxAmount', 'taxEffect'].includes(field)) {
        value = savedNumber(responses, `M9-disclosure-listed-${group}-${index}-${field}`)
      }
      if (value !== undefined) row[field] = value
    }
  }
  return rows
}

export function restoreM9SoeRows(
  responses: ReadonlyMap<string, ChecklistResponse>,
  group: M9Group,
): M9SoeUiRow[] {
  const rows = createM9SoeRows(group)
  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index]
    for (const field of ['beginBalance', 'priorTaxEffect', 'preTaxAmount', 'taxEffect', 'transferToPL'] as const) {
      const key = `M9-disclosure-soe-${group}-${row.key}-${field}`
      let value = savedNumber(responses, key)
      if (value === undefined) value = savedNumber(responses, `M9-disclosure-soe-${group}-${index}-${field}`)
      if (value !== undefined) row[field] = value
    }
  }
  return rows
}

function listedData(rows: readonly M9ListedUiRow[]): M9ListedRow[] {
  return rows.map((row) => ({
    label: row.item,
    beginAmount: row.priorYearAmount,
    preTax: row.preTaxAmount,
    transferToPl: row.transferToPl,
    taxEffect: row.taxEffect,
    afterTaxParent: row.preTaxAmount - row.transferToPl - row.taxEffect - row.afterTaxMinority,
    afterTaxMinority: row.afterTaxMinority,
  }))
}

export function m9ListedTemplateRows(nonReclass: readonly M9ListedUiRow[], reclass: readonly M9ListedUiRow[]): M9ListedRow[] {
  const data = [
    { label: '一、不能重分类进损益的其他综合收益', beginAmount: 0, preTax: 0, transferToPl: 0, taxEffect: 0, afterTaxParent: 0, afterTaxMinority: 0 },
    ...listedData(nonReclass),
    { label: '二、将重分类进损益的其他综合收益', beginAmount: 0, preTax: 0, transferToPl: 0, taxEffect: 0, afterTaxParent: 0, afterTaxMinority: 0 },
    ...listedData(reclass),
  ]
  const total = listedData([...nonReclass, ...reclass]).reduce((out, row) => {
    out.beginAmount += row.beginAmount
    out.preTax += row.preTax
    out.transferToPl += row.transferToPl
    out.taxEffect += row.taxEffect
    out.afterTaxParent += row.afterTaxParent
    out.afterTaxMinority += row.afterTaxMinority
    return out
  }, { label: '其他综合收益合计', beginAmount: 0, preTax: 0, transferToPl: 0, taxEffect: 0, afterTaxParent: 0, afterTaxMinority: 0 })
  return [...data, total]
}

function soeBaseRow(row: M9SoeUiRow): M9SoeRow {
  return {
    label: row.item,
    endPreTax: row.preTaxAmount,
    endTax: row.taxEffect,
    endNet: row.preTaxAmount - row.taxEffect,
    priorPreTax: row.beginBalance,
    priorTax: row.priorTaxEffect,
    priorNet: row.beginBalance - row.priorTaxEffect,
  }
}

function zeroSoe(label: string): M9SoeRow {
  return { label, endPreTax: 0, endTax: 0, endNet: 0, priorPreTax: 0, priorTax: 0, priorNet: 0 }
}

export function m9SoeTemplateRows(nonReclass: readonly M9SoeUiRow[], reclass: readonly M9SoeUiRow[]): M9SoeRow[] {
  const rows: M9SoeRow[] = [zeroSoe('一、以后不能重分类进损益的其他综合收益')]
  rows.push(...nonReclass.map(soeBaseRow))
  rows.push(zeroSoe('二、将重分类进损益的其他综合收益'))
  for (const row of reclass) {
    const base = soeBaseRow(row)
    rows.push(base)
    const deductionLabel = row.key === 'cashflow-hedge'
      ? '减：转为被套期项目初始确认金额的调整额'
      : row.key === 'other-reclass'
        ? '减：前期计入其他综合收益当期转入损益的净额'
        : '减：前期计入其他综合收益当期转入损益'
    const deduction = {
      label: deductionLabel,
      endPreTax: row.transferToPL,
      endTax: 0,
      endNet: row.transferToPL,
      priorPreTax: 0,
      priorTax: 0,
      priorNet: 0,
    }
    // 现金流量套期模板多一条“前期转入损益”，没有独立输入时保持明确 0 行。
    rows.push(deduction)
    if (row.key === 'cashflow-hedge') rows.push(zeroSoe('前期计入其他综合收益当期转入损益'))
    rows.push({
      label: '小计',
      endPreTax: base.endPreTax - deduction.endPreTax,
      endTax: base.endTax,
      endNet: base.endNet - deduction.endNet,
      priorPreTax: base.priorPreTax,
      priorTax: base.priorTax,
      priorNet: base.priorNet,
    })
  }
  const source = [...nonReclass.map(soeBaseRow), ...rows.filter((row) => row.label === '小计')]
  rows.push(source.reduce((out, row) => {
    out.endPreTax += row.endPreTax
    out.endTax += row.endTax
    out.endNet += row.endNet
    out.priorPreTax += row.priorPreTax
    out.priorTax += row.priorTax
    out.priorNet += row.priorNet
    return out
  }, zeroSoe('三、其他综合收益合计')))
  return rows
}

export function buildM9DisclosurePayload(input: {
  variant: 'listed'
  wpId: string
  bsNon: readonly M9ListedUiRow[]
  bsReclass: readonly M9ListedUiRow[]
  plNon: readonly M9ListedUiRow[]
  plReclass: readonly M9ListedUiRow[]
  noteText?: string
} | {
  variant: 'soe'
  wpId: string
  nonReclass: readonly M9SoeUiRow[]
  reclass: readonly M9SoeUiRow[]
  noteText?: string
}) {
  let payload
  if (input.variant === 'listed') {
    payload = buildM9ListedSyncPayload(
      input.wpId,
      m9ListedTemplateRows(input.bsNon, input.bsReclass),
      m9ListedTemplateRows(input.plNon, input.plReclass),
    )
  } else {
    payload = buildM9SoeSyncPayload(input.wpId, m9SoeTemplateRows(input.nonReclass, input.reclass))
  }
  if (payload && input.noteText?.trim()) {
    ;(payload.sub_table_data as any)._note_texts = [{
      section: `m9-${input.variant}-note`, title: '其他综合收益说明', text: input.noteText.trim(),
    }]
  }
  return payload
}

export function m9NoteText(responses: ReadonlyMap<string, ChecklistResponse>, variant: 'listed' | 'soe'): string {
  const keys = variant === 'listed'
    ? ['M9-disclosure-listed-remark', 'M9-disclosure-listed-transfer']
    : ['M9-disclosure-soe-capital', 'M9-disclosure-soe-transfer']
  return keys.map((key) => String(responses.get(key)?.remark ?? '').trim()).filter(Boolean).join('\n\n')
}
