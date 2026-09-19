/**
 * H9 租赁负债披露表 ↔ 附注章节冻结映射
 *
 * 权威来源：
 * - note_template_listed「五、47」租赁负债（表名：租赁负债）
 * - note_template_soe「八、52」租赁负债（表名：租赁负债）
 * - 源 xlsx「附注披露信息（上市公司/国企）」
 */
export type H9DisclosureVariant = 'listed' | 'soe'

export const H9_NOTE_SECTION = {
  listed: '五、47',
  soe: '八、52',
} as const satisfies Record<H9DisclosureVariant, string>

export const H9_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<H9DisclosureVariant, string>

/** 与 note_template tables[].name 一致 */
export const H9_LISTED_SUBTABLE = {
  main: '租赁负债',
} as const

export const H9_SOE_SUBTABLE = {
  main: '租赁负债',
} as const

export function isListedStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return x.includes('listed') || x.includes('上市') || x === 'listed_standalone' || x === 'listed_consolidated'
}

export function isSoeStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return (
    x.includes('soe')
    || x.includes('state_owned')
    || x.includes('国企')
    || x.includes('国有')
    || x === 'cass'
    || x === 'cas'
    || x === 'soe_standalone'
    || x === 'soe_consolidated'
  )
}

export function isH9DisclosureApplicable(
  variant: H9DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = (applicableStandards || []).map((s) => String(s).trim()).filter(Boolean)
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveH9CurrentStandard(
  variant: H9DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): string {
  const list = (applicableStandards || []).map((s) => String(s).toLowerCase())
  if (variant === 'listed') {
    if (list.some((s) => s === 'listed_consolidated' || (s.includes('listed') && s.includes('consol')))) {
      return 'listed_consolidated'
    }
    return 'listed_standalone'
  }
  if (list.some((s) => s === 'soe_consolidated' || (s.includes('soe') && s.includes('consol')))) {
    return 'soe_consolidated'
  }
  return 'soe_standalone'
}

export function isH9LeaseLiabilityNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、47' || s.startsWith('五、47')) return true
  if (s === '八、52' || s.startsWith('八、52')) return true
  if (s === '租赁负债' || (s.includes('租赁负债') && !s.includes('使用权'))) return true
  return false
}

/** 源模板 CAS21 编制提示（作 placeholder，勿写入 v-model） */
export const H9_LISTED_GUIDANCE = {
  interest:
    '2025年计提的租赁负债利息费用金额为XX万元，计入财务费用-利息支出金额为XX万元，计入固定资产金额为XX万元。',
  tips: [
    '承租人根据《企业会计准则第21号——租赁》所确认的租赁负债发生的利息费用适用借款费用准则。使用权资产于租赁期开始日便达到预定可使用状态，租赁负债相关利息费用不应资本化计入使用权资产。租赁期开始日后，租赁负债可视同企业的一般借款。',
    '承租人向出租人支付的租金等款项中包含应缴纳的增值税的，相关增值税税额不属于租赁付款额的范畴，不应纳入租赁负债和使用权资产的计量。',
    '出租人为确保承租人履行合同相关义务收取租赁保证金的，该租赁保证金不属于出租人的租赁收款额和承租人的租赁付款额，出租人和承租人应当分别将其作为单独的负债和资产进行会计处理。',
  ],
} as const

export const H9_SOE_GUIDANCE = {
  tips: H9_LISTED_GUIDANCE.tips,
} as const
