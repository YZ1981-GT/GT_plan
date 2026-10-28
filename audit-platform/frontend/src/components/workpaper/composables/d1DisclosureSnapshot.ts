/**
 * D1 应收票据披露表展开行与快照（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * 原先在 `D1TabDisclosure.vue` 里内联：分类展开行（上市含「其中：」与单项明细）、国企分类三行、国企组合计提账龄行、
 * 国企变动表行、上市变动行、说明文本加载与同步快照。抽成本模块的纯函数后 Tab（显示 / 勾稽面板 / 同步）与离屏
 * provider 调同一份计算 → 两条路径发出逐字节相同的载荷。入参 `d` = `useD1Disclosure` 的返回值。
 */
import { ratioOf } from './useD1FormulaEngine'
import type { DisclosureVariant, useD1Disclosure } from './useD1Disclosure'
import { D1_NOTE_TEXT_ORDER, type D1DisclosureSnapshot } from './d1NoteSectionMap'
import type { ChecklistResponse } from './useD1FormData'

export type D1DisclosureApi = ReturnType<typeof useD1Disclosure>

export type BadDebtDisplayRow = {
  rowKind: 'fixed' | 'hint' | 'individual' | 'summary'
  rowId: string
  label: string
  source?: 'single' | 'bank' | 'commercial'
  balance: number
  ratio: number
  provision: number
  lossRate: number
  bookValue: number
  basis?: string
}

/** 说明文本（`D1-disc-{变体}-note-{子节}`，空的不收）；`keys` = Tab 的文本域键集（与附注小节顺序同集，守卫钉住） */
export function readD1SectionNotes(
  responses: ReadonlyMap<string, ChecklistResponse>,
  variant: DisclosureVariant,
  keys: readonly string[] = D1_NOTE_TEXT_ORDER,
): Record<string, string> {
  const prefix = `D1-disc-${variant}-note-`
  const next: Record<string, string> = {}
  for (const key of keys) {
    const resp = responses.get(`${prefix}${key}`)
    if (resp?.remark) next[key] = resp.remark
  }
  return next
}

/** 上市分类展开行（单项 / 其中：/ 单项明细 / 组合 / 其中：/ 银承 / 商承 / 合计），比率按当前金额现算（F4-25 / F4-12） */
export function buildD1BadDebtDisplayRows(d: D1DisclosureApi, period: 'end' | 'prior'): BadDebtDisplayRow[] {
  const classRows = period === 'end' ? d.classEndRows.value : d.classPriorRows.value
  const total = period === 'end' ? d.classEndTotal.value : d.classPriorTotal.value
  const individuals = period === 'end' ? d.individualEndRows.value : d.individualPriorRows.value
  const single = classRows.find(r => r.rowId === `class-${period}-individual`)
  const bank = classRows.find(r => r.rowId === `class-${period}-portfolio-bank`)
  const commercial = classRows.find(r => r.rowId === `class-${period}-portfolio-commercial`)
  const comboBalance = (bank?.balance || 0) + (commercial?.balance || 0)
  const comboProvision = (bank?.provision || 0) + (commercial?.provision || 0)
  const comboBookValue = comboBalance - comboProvision
  const comboRatio = ratioOf(comboBalance, total.balance)
  const comboLossRate = ratioOf(comboProvision, comboBalance)

  return [
    {
      rowKind: 'fixed',
      rowId: `single-${period}`,
      label: '按单项计提坏账准备',
      source: 'single',
      balance: single?.balance || 0,
      // 比率按当前合计现算（F4-25 / F4-12），不透传可能过期的持久化值
      ratio: ratioOf(single?.balance || 0, total.balance),
      provision: single?.provision || 0,
      lossRate: ratioOf(single?.provision || 0, single?.balance || 0),
      bookValue: (single?.balance || 0) - (single?.provision || 0),
    },
    { rowKind: 'hint', rowId: `single-hint-${period}`, label: '其中：', balance: 0, ratio: 0, provision: 0, lossRate: 0, bookValue: 0 },
    ...individuals.map(row => ({
      rowKind: 'individual' as const,
      rowId: row.rowId,
      label: row.name || '',
      balance: row.balance,
      ratio: ratioOf(row.balance, total.balance),
      provision: row.provision,
      lossRate: row.lossRate,
      bookValue: row.balance - row.provision,
      basis: row.basis,
    })),
    {
      rowKind: 'fixed',
      rowId: `combo-${period}`,
      label: '按组合计提坏账准备',
      balance: comboBalance,
      ratio: comboRatio,
      provision: comboProvision,
      lossRate: comboLossRate,
      bookValue: comboBookValue,
    },
    { rowKind: 'hint', rowId: `combo-hint-${period}`, label: '其中：', balance: 0, ratio: 0, provision: 0, lossRate: 0, bookValue: 0 },
    {
      rowKind: 'fixed',
      rowId: `bank-${period}`,
      label: '银行承兑汇票',
      source: 'bank',
      balance: bank?.balance || 0,
      ratio: ratioOf(bank?.balance || 0, total.balance),
      provision: bank?.provision || 0,
      lossRate: ratioOf(bank?.provision || 0, bank?.balance || 0),
      bookValue: (bank?.balance || 0) - (bank?.provision || 0),
    },
    {
      rowKind: 'fixed',
      rowId: `commercial-${period}`,
      label: '商业承兑汇票',
      source: 'commercial',
      balance: commercial?.balance || 0,
      ratio: ratioOf(commercial?.balance || 0, total.balance),
      provision: commercial?.provision || 0,
      lossRate: ratioOf(commercial?.provision || 0, commercial?.balance || 0),
      bookValue: (commercial?.balance || 0) - (commercial?.provision || 0),
    },
    {
      rowKind: 'summary',
      rowId: `total-${period}`,
      label: '合计',
      balance: total.balance,
      ratio: total.ratio,
      provision: total.provision,
      lossRate: total.lossRate,
      bookValue: total.bookValue,
    },
  ]
}

/** 上市变动表唯一一行（缺省全零合计行） */
export function d1ListedMovementRow(d: D1DisclosureApi) {
  return d.movementRows.value[0] ?? {
    rowId: 'mv-total',
    priorBalance: 0,
    provision: 0,
    reversal: 0,
    writeOff: 0,
    transfer: 0,
    other: 0,
    endBalance: 0,
  }
}

/**
 * 国企分类表三行（单项 / 组合 / 合计）。
 *
 * 🔴 聚合行的比率必须按**聚合后的金额**重算：
 * 旧实现把银承与商承的 `ratio` 直接相加（两者分母是各自录入时点的合计）→ 实测
 * 「按组合计提坏账准备」行显示 162.50%（应 100.00%）；`lossRate` 还被硬编码为 0，
 * 附注里显示成 `-`。口径见预设 F4-25 / F4-12 / F4-11。
 */
export function buildD1SoeClassRows(d: D1DisclosureApi, period: 'end' | 'prior') {
  const rows = period === 'end' ? d.classEndRows.value : d.classPriorRows.value
  const total = period === 'end' ? d.classEndTotal.value : d.classPriorTotal.value
  const single = rows.find(r => r.rowId === `class-${period}-individual`)
  const bank = rows.find(r => r.rowId === `class-${period}-portfolio-bank`)
  const commercial = rows.find(r => r.rowId === `class-${period}-portfolio-commercial`)
  const comboBalance = (bank?.balance || 0) + (commercial?.balance || 0)
  const comboProvision = (bank?.provision || 0) + (commercial?.provision || 0)
  return [
    {
      rowId: `soe-${period}-single`, label: '按单项计提坏账准备',
      balance: single?.balance || 0,
      ratio: ratioOf(single?.balance || 0, total.balance),
      provision: single?.provision || 0,
      lossRate: ratioOf(single?.provision || 0, single?.balance || 0),
      bookValue: (single?.balance || 0) - (single?.provision || 0),
    },
    {
      rowId: `soe-${period}-portfolio`, label: '按组合计提坏账准备',
      balance: comboBalance,
      ratio: ratioOf(comboBalance, total.balance),
      provision: comboProvision,
      lossRate: ratioOf(comboProvision, comboBalance),
      bookValue: comboBalance - comboProvision,
    },
    {
      rowId: `soe-${period}-total`, label: '合计',
      balance: total.balance, ratio: total.ratio,
      provision: total.provision, lossRate: total.lossRate, bookValue: total.bookValue,
    },
  ]
}

// 国企组合计提表小计行名逐字取自源模板 A36/A39 与附注模板 八、4[4] 的 rows
// （带「小计：」后缀），改字面量会让同步后的附注行名与模板骨架不匹配。
const SOE_PORTFOLIO_SUBTOTAL = {
  commercial: '商业承兑汇票小计：',
  bank: '银行承兑汇票小计：',
} as const

/**
 * 国企「按组合计提坏账准备的应收票据」行集：商承小计 + 商承账龄明细 +
 * 银承小计 + 银承账龄明细 + 合计（顺序同源模板 A36~A42）。
 *
 * 小计取值口径：有账龄明细时用明细汇总，无明细时回落到分类表对应组合行（可直接录入）。
 * 所有损失率一律 `ratioOf(provision, balance)` 现算 —— 合计行原先硬编码 0。
 */
export function buildD1SoeAgingRows(d: D1DisclosureApi) {
  const classRowBalance = (kind: 'bank' | 'commercial', field: 'balance' | 'provision') =>
    d.classEndRows.value.find(r => r.rowId === `class-end-portfolio-${kind}`)?.[field] || 0

  const build = (kind: 'bank' | 'commercial') => {
    const detail = (kind === 'bank' ? d.bankPortfolioEndRows.value : d.commercialPortfolioEndRows.value)
      .map(r => ({ ...r, sourceType: kind }))
    const hasDetail = detail.length > 0
    const balance = hasDetail
      ? detail.reduce((s, r) => s + (r.balance || 0), 0)
      : classRowBalance(kind, 'balance')
    const provision = hasDetail
      ? detail.reduce((s, r) => s + (r.provision || 0), 0)
      : classRowBalance(kind, 'provision')
    return { detail, hasDetail, balance, provision }
  }

  const c = build('commercial')
  const b = build('bank')
  const detailRows = (g: ReturnType<typeof build>) => g.detail.map(r => ({
    rowKind: 'detail',
    rowId: r.rowId,
    sourceType: r.sourceType,
    name: r.drawerTypeOrAging || '',
    balance: r.balance || 0,
    provision: r.provision || 0,
    lossRate: ratioOf(r.provision || 0, r.balance || 0),
  }))
  const totalBalance = c.balance + b.balance
  const totalProvision = c.provision + b.provision

  return [
    {
      rowKind: 'subtotal', rowId: 'soe-commercial-subtotal', sourceType: 'commercial' as const,
      hasDetail: c.hasDetail, name: SOE_PORTFOLIO_SUBTOTAL.commercial,
      balance: c.balance, provision: c.provision, lossRate: ratioOf(c.provision, c.balance),
    },
    ...detailRows(c),
    {
      rowKind: 'subtotal', rowId: 'soe-bank-subtotal', sourceType: 'bank' as const,
      hasDetail: b.hasDetail, name: SOE_PORTFOLIO_SUBTOTAL.bank,
      balance: b.balance, provision: b.provision, lossRate: ratioOf(b.provision, b.balance),
    },
    ...detailRows(b),
    {
      rowKind: 'summary', rowId: 'soe-aging-total', sourceType: 'commercial' as const,
      name: '合计', balance: totalBalance, provision: totalProvision,
      lossRate: ratioOf(totalProvision, totalBalance),
    },
  ]
}

/**
 * 国企坏账变动表行集：单项 / 按组合 / 其中： / 明细… / 合计（顺序同源模板 A48~A52）。
 *
 * 预设 F4-20 要求「其中：」下方所有明细行之和 = 按组合计提行 → 有明细时按组合计提行
 * 改为**明细汇总（只读）**，从结构上保证勾稽成立；无明细时保持可直接录入。
 */
export function buildD1SoeMovementDisplayRows(d: D1DisclosureApi) {
  const movementRows = d.movementRows.value
  const individual = movementRows.find(r => r.label === '按单项计提') || movementRows[0]
  const portfolioRaw = movementRows.find(r => r.label === '按组合计提') || movementRows[1]
  const portfolio = d.hasMovementDetail.value
    ? { ...d.movementDetailTotal.value, rowId: portfolioRaw?.rowId || 'mv-portfolio' }
    : portfolioRaw
  // 合计行 = 单项 + 组合（F4-19），组合侧取上面已按明细汇总后的口径
  const sumCol = (k: 'priorBalance' | 'provision' | 'reversal' | 'writeOff' | 'transfer' | 'other' | 'endBalance') =>
    (individual?.[k] ?? 0) + (portfolio?.[k] ?? 0)
  const total = {
    rowId: 'mv-total',
    label: '合计',
    priorBalance: sumCol('priorBalance'),
    provision: sumCol('provision'),
    reversal: sumCol('reversal'),
    writeOff: sumCol('writeOff'),
    transfer: sumCol('transfer'),
    other: sumCol('other'),
    endBalance: sumCol('endBalance'),
  }
  return [
    { rowKind: 'data', rowId: individual?.rowId || 'mv-individual', label: '单项计提预期信用损失的应收票据', sourceRow: individual, readonlyRow: false },
    { rowKind: 'data', rowId: portfolio?.rowId || 'mv-portfolio', label: '按组合计提预期信用损失的应收票据', sourceRow: portfolio, readonlyRow: d.hasMovementDetail.value },
    { rowKind: 'hint', rowId: 'mv-hint', label: '其中：', sourceRow: null, readonlyRow: true },
    ...d.movementDetailRows.value.map(r => ({
      rowKind: 'detail' as const, rowId: r.rowId, label: r.label, sourceRow: r, readonlyRow: false,
    })),
    { rowKind: 'summary', rowId: total.rowId, label: '合计', sourceRow: total, readonlyRow: true },
  ]
}

/** 披露表 → `buildD1SyncPayload` 的快照（上市 14 张 / 国企 12 张表 + 各段说明），与 Tab 渲染同一批展开行。 */
export function buildD1DisclosureSnapshot(
  variant: DisclosureVariant,
  d: D1DisclosureApi,
  notes: Record<string, string>,
): D1DisclosureSnapshot {
  return {
    summaryRows: d.categorySummaryRows.value as any,
    summaryTotal: d.categorySummaryTotal.value as any,
    pledgedRows: d.pledgedRows.value as any,
    pledgedTotal: d.pledgedTotal.value as any,
    endorsedRows: d.endorsedRows.value as any,
    endorsedTotal: d.endorsedTotal.value as any,
    transferRows: d.transferRows.value as any,
    transferTotal: d.transferTotal.value as any,
    classEndRows: d.classEndRows.value as any,
    classPriorRows: d.classPriorRows.value as any,
    // 披露表实际渲染的分类展开行（上市版含「其中：」与单项明细行，与附注模板行结构一致）
    classDisplayEndRows: buildD1BadDebtDisplayRows(d, 'end') as any,
    classDisplayPriorRows: buildD1BadDebtDisplayRows(d, 'prior') as any,
    soeClassEndRows: buildD1SoeClassRows(d, 'end') as any,
    soeClassPriorRows: buildD1SoeClassRows(d, 'prior') as any,
    individualEndRows: d.individualEndRows.value as any,
    individualPriorRows: d.individualPriorRows.value as any,
    bankPortfolioEndRows: d.bankPortfolioEndRows.value as any,
    bankPortfolioPriorRows: d.bankPortfolioPriorRows.value as any,
    commercialPortfolioEndRows: d.commercialPortfolioEndRows.value as any,
    commercialPortfolioPriorRows: d.commercialPortfolioPriorRows.value as any,
    soePortfolioRows: buildD1SoeAgingRows(d).map((r: any) => ({
      name: r.name,
      balance: r.balance,
      provision: r.provision,
      lossRate: r.lossRate,
      isTotal: r.rowKind === 'summary',
    })),
    movementTotal: (variant === 'listed' ? d1ListedMovementRow(d) : d.movementTotal.value) as any,
    soeMovementRows: buildD1SoeMovementDisplayRows(d).map((r: any) => ({
      label: r.label,
      priorBalance: r.sourceRow?.priorBalance ?? 0,
      provision: r.sourceRow?.provision ?? 0,
      reversal: r.sourceRow?.reversal ?? 0,
      writeOff: r.sourceRow?.writeOff ?? 0,
      transfer: r.sourceRow?.transfer ?? 0,
      other: r.sourceRow?.other ?? 0,
      endBalance: r.sourceRow?.endBalance ?? 0,
    })),
    reversalRows: d.reversalDetailRows.value as any,
    reversalTotal: d.reversalDetailTotal.value as any,
    writeOffAmount: d.writeOffAmount.value,
    writeOffDetailRows: d.writeOffDetailRows.value as any,
    notes: { ...notes },
  }
}
