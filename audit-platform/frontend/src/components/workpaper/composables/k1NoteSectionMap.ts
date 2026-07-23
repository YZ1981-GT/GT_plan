/**
 * K1 其他应收款披露表 ↔ 附注章节映射
 *
 * 权威：note_template_listed「五、8 其他应收款」/ note_template_soe「八、9 其他应收款」
 * G2/G3 应收利息/股利明细亦挂在同一附注章节下；K1 底稿同步「其他应收款项」相关子表。
 */
export type K1DisclosureVariant = 'listed' | 'soe'

export const K1_ACCOUNT_CODE = '1221'

export const K1_NOTE_SECTION = {
  listed: '五、8',
  soe: '八、9',
} as const satisfies Record<K1DisclosureVariant, string>

export const K1_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<K1DisclosureVariant, string>

/** 与 note_template_listed §五、8 tables[].name 对齐（K1 其他应收款项部分） */
export const K1_LISTED_SUBTABLE = {
  aging: '按账龄披露',
  nature: '按款项性质披露',
  stage1: '期末处于第一阶段的坏账准备',
  stage2: '期末处于第二阶段的坏账准备',
  stage3: '期末处于第三阶段的坏账准备',
  stageMovement: '本期计提、收回或转回的坏账准备情况',
  reversal: '本期转回或收回金额重要的坏账准备',
  writeoffSummary: '本期实际核销的其他应收款情况',
  writeoffDetail: '重要的其他应收款核销情况（逐项披露）',
  top5: '按欠款方归集的其他应收款期末余额前五名单位情况',
} as const

/** 与 note_template_soe §八、9 tables[].name 对齐（K1 其他应收款项部分） */
export const K1_SOE_SUBTABLE = {
  aging: '按账龄披露其他应收款项',
  methodEnd: '按坏账准备计提方法分类披露其他应收款项',
  methodPrior: '续：',
  individualDetail: '单项计提坏账准备的其他应收款项',
  portfolioOther: '采用余额百分比法或其他组合方法计提坏账准备的其他应收款项',
  eclMovement: '其他应收款项坏账准备计提情况',
  balanceMovement: '其他应收款项账面余额三阶段变动',
  reversal: '本期收回或转回金额重要的坏账准备',
  writeoff: '本期实际核销的其他应收款项',
  top5: '按欠款方归集的期末余额前五名的其他应收款项',
  govGrant: '涉及政府补助的应收款项',
  transfer: '因金融资产转移而终止确认的其他应收款',
} as const

/** 国企披露各区块编制提示（结构 vs 内容） */
export interface K1SectionGuideExt {
  id: string
  title: string
  structure: string
  source: string
  noteTarget: string
  sourceSheet: string
  sourceItemId?: string
  adjudicationKey?: 'receivable' | 'badDebt' | 'net' | 'portfolio' | 'none'
  portfolioLabel?: string
  portfolioRowKey?: string
}

export const K1_LISTED_SECTION_GUIDES: K1SectionGuideExt[] = [
  {
    id: 'aging',
    title: '按账龄披露',
    structure: '账龄段 + 小计 + 减坏账准备 + 合计',
    source: 'K1-2 明细账龄汇总',
    noteTarget: '五、8·按账龄披露',
    sourceSheet: '明细表K1-2',
    sourceItemId: 'K1-2-end-subtotal',
    adjudicationKey: 'receivable',
  },
  {
    id: 'nature',
    title: '按款项性质披露',
    structure: '性质行 + 账面余额/坏账/账面价值',
    source: 'K1-2 款项性质汇总',
    noteTarget: '五、8·按款项性质披露',
    sourceSheet: '明细表K1-2',
    adjudicationKey: 'receivable',
  },
  {
    id: 'ecl',
    title: 'ECL 三阶段坏账',
    structure: 'Stage1/2/3 + 合计',
    source: 'K1-3 三阶段转入转出',
    noteTarget: '五、8·坏账准备计提情况',
    sourceSheet: '坏账准备明细表K1-3',
    sourceItemId: 'K1-3-baddebt-rows',
    adjudicationKey: 'badDebt',
  },
  {
    id: 'reversal',
    title: '转回/收回',
    structure: '债务人 | 金额 | 原因',
    source: 'K1-9 转回检查表',
    noteTarget: '五、8·转回或收回',
    sourceSheet: '坏账准备转回(收回)核销检查表K1-9',
    sourceItemId: 'K1-9-writeoff',
    adjudicationKey: 'none',
  },
  {
    id: 'writeoff',
    title: '实际核销',
    structure: '债务人 | 性质 | 金额 | 程序',
    source: 'K1-9 核销检查表',
    noteTarget: '五、8·实际核销',
    sourceSheet: '坏账准备转回(收回)核销检查表K1-9',
    sourceItemId: 'K1-9-writeoff',
    adjudicationKey: 'none',
  },
  {
    id: 'top5',
    title: '前五名欠款方',
    structure: '单位 | 余额 | 账龄 | 占比',
    source: 'K1-2 / K1-5',
    noteTarget: '五、8·前五名',
    sourceSheet: '明细表K1-2',
    adjudicationKey: 'receivable',
  },
]

export const K1_SOE_SECTION_GUIDES: K1SectionGuideExt[] = [
  {
    id: 'aging',
    title: '按账龄列示',
    structure: '6段账龄 + 小计 + 减坏账准备 + 合计（期末/期初两列）',
    source: 'K1-2 明细账龄汇总；合计行与 K1-1 审定勾稽',
    noteTarget: '八、9·按账龄披露其他应收款项',
    sourceSheet: '明细表K1-2',
    adjudicationKey: 'receivable',
  },
  {
    id: 'method',
    title: '按计提方法分类',
    structure: '单项计提 / 组合计提 / 合计；含余额、比例、坏账准备、ECL率、账面价值',
    source: 'K1-3 坏账准备明细（单项子行 + 组合行）',
    noteTarget: '八、9·按坏账准备计提方法分类披露',
    sourceSheet: '坏账准备明细表K1-3',
    sourceItemId: 'K1-3-baddebt-rows',
    adjudicationKey: 'badDebt',
  },
  {
    id: 'individual',
    title: '单项计提明细',
    structure: '债务人 | 账面余额 | 坏账准备 | 预期信用损失率 | 计提理由',
    source: 'K1-3 单项评估子行；无单项时可留空',
    noteTarget: '八、9·单项计提坏账准备的其他应收款项',
    sourceSheet: '坏账准备明细表K1-3',
    adjudicationKey: 'portfolio',
    portfolioLabel: '单项计提',
    portfolioRowKey: 'r0',
  },
  {
    id: 'portfolioAging',
    title: '组合计提·账龄组合',
    structure: '各账龄段余额、比例、坏账准备（期末/期初对照）',
    source: 'K1-2 组合户账龄汇总（排除 K1-3 单项子行对应户）',
    noteTarget: '八、9·账龄组合（组合计提附表）',
    sourceSheet: '坏账准备测算K1-8',
    adjudicationKey: 'portfolio',
    portfolioLabel: '账龄组合',
    portfolioRowKey: 'r1',
  },
  {
    id: 'ecl',
    title: '坏账准备三阶段变动',
    structure: '期初→阶段间转移→计提/转回/转销/核销→期末（Stage1/2/3 + 合计）',
    source: 'K1-3 三阶段转入转出表',
    noteTarget: '八、9·其他应收款项坏账准备计提情况',
    sourceSheet: '坏账准备明细表K1-3',
    adjudicationKey: 'badDebt',
  },
  {
    id: 'balanceStage',
    title: '账面余额三阶段变动',
    structure: '期初→阶段间转移→本期新增/收回→期末（Stage1/2/3 + 合计）',
    source: 'K1-7 三阶段划分 + K1-2 期初余额自动汇总',
    noteTarget: '八、9·账面余额三阶段变动（Excel 77~87 行）',
    sourceSheet: '三阶段划分检查表K1-7',
    sourceItemId: 'K1-7-stage-rows',
    adjudicationKey: 'receivable',
  },
  {
    id: 'reversal',
    title: '转回/收回',
    structure: '债务人 | 转回金额 | 累计已计提 | 转回原因/方式',
    source: 'K1-9 转回检查表',
    noteTarget: '八、9·本期收回或转回',
    sourceSheet: '坏账准备转回(收回)核销检查表K1-9',
    sourceItemId: 'K1-9-writeoff',
    adjudicationKey: 'none',
  },
  {
    id: 'writeoff',
    title: '实际核销',
    structure: '债务人 | 款项性质 | 核销金额 | 原因 | 核销程序 | 是否关联交易',
    source: 'K1-9 核销检查表',
    noteTarget: '八、9·本期实际核销的其他应收款项',
    sourceSheet: '坏账准备转回(收回)核销检查表K1-9',
    sourceItemId: 'K1-9-writeoff',
    adjudicationKey: 'none',
  },
  {
    id: 'top5',
    title: '前五名欠款方',
    structure: '单位 | 性质 | 期末余额 | 账龄 | 占比% | 坏账准备',
    source: 'K1-2 按期末余额降序取前5；可与 K1-5 大额分析交叉核对',
    noteTarget: '八、9·前五名其他应收款项',
    sourceSheet: '明细表K1-2',
    adjudicationKey: 'receivable',
  },
  {
    id: 'govGrant',
    title: '政府补助应收',
    structure: '单位 | 补助项目 | 期末余额 | 账龄 | 预计收取时间/金额/依据',
    source: 'K1-2 款项性质含「政府补助」的明细行',
    noteTarget: '八、9·涉及政府补助的应收款项',
    sourceSheet: '明细表K1-2',
    adjudicationKey: 'none',
  },
  {
    id: 'transfer',
    title: '金融资产转移',
    structure: '终止确认：债务人/金额/损益；继续涉入：资产/负债金额',
    source: '人工录入（无标准源底稿时）',
    noteTarget: '八、9·转移终止确认及继续涉入',
    sourceSheet: '审定表K1-1',
    adjudicationKey: 'net',
  },
] as const

export function isK1ListedStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return x.includes('listed') || x.includes('上市') || x === 'listed_standalone' || x === 'listed_consolidated'
}

export function isK1SoeStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return (
    x.includes('soe')
    || x.includes('state_owned')
    || x.includes('国企')
    || x.includes('国有')
    || x === 'soe_standalone'
    || x === 'soe_consolidated'
  )
}

export function isK1DisclosureApplicable(
  variant: K1DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = applicableStandards ?? []
  if (list.length === 0) return true
  const hasListed = list.some(isK1ListedStandard)
  const hasSoe = list.some(isK1SoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveK1CurrentStandard(
  variant: K1DisclosureVariant,
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

export function resolveK1NoteSectionTarget(variant: K1DisclosureVariant): {
  sectionId: string
  chipValue: string
} {
  const sectionId = K1_NOTE_SECTION[variant]
  return { sectionId, chipValue: `Note:${sectionId}` }
}

export function isK1OtherReceivableNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、8' || s.startsWith('五、8')) return true
  if (s === '八、9' || s.startsWith('八、9')) return true
  if (s.includes('其他应收款')) return true
  return false
}
