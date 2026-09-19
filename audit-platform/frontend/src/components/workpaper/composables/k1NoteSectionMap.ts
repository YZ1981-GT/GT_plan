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

/**
 * 同步载荷 `sheet_name` = 源 xlsx 真实中文 tab 名（逐字，openpyxl 实测 `wb.sheetnames`）。
 *
 * 🔴 上市侧是**前半角后全角**括号 `(上市公司）`，源模板 `K1 其他应收款.xlsx` 即如此。
 * 原先写成全角全角 → 附注「打开同步底稿」的 `?sheet=` 精确匹配落空。
 * `disclosureSheetNameRegistry.spec.ts` 只比对「常量 ↔ registry（由常量生成）」，
 * **查不出与 xlsx 的漂移** → 守卫改用 openpyxl 直读（`test_note_k_sheet_names.py`）。
 */
export const K1_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息(上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<K1DisclosureVariant, string>

/**
 * 附注合计行字面（**按本章节实证取值**，禁止全局硬套）。
 *
 * K1 两版模板与源 xlsx 都是**无空格**的「合计」/「小计」（对比 D2/F1 的「合 计」）；
 * 唯二例外是国企 §八、9 的「由金融资产转移而终止确认的其他应收款项」与
 * 「涉及政府补助的应收款项」用了双空格「合  计」（源 xlsx A115 / A130 即如此），
 * 以及国企账龄表的「小  计」/「合  计」（源 xlsx A13/A15）。
 * 故合计行字面必须**逐表**取，不能只留一个全局常量。
 */
export const K1_NOTE_TOTAL_LABEL = '合计'
export const K1_NOTE_TOTAL_LABEL_WIDE = '合  计'
export const K1_NOTE_SUBTOTAL_LABEL_WIDE = '小  计'

/**
 * 与 note_template_listed §五、8 tables[].name **逐字**对齐（K1 其他应收款项部分）。
 * 契约测试见 `__tests__/k1NoteSubtableContract.spec.ts`——改名前先改附注模板。
 *
 * 🔴 `govGrant` / `transfer` / `continuedInvolvement` 三张表 2026-07-31 补入：
 * 源 xlsx 上市披露 sheet 的 ⑧`A136:E141` / ⑨`A146:D150` / ⑩`A153:B159` 明确列在
 * 其他应收款披露内，国企 §八、9 也一直有对应三表 —— 上市侧模板却整张缺失（两版不对称），
 * 底稿早已收集 `govGrantRows`/`transferRows`/`continuedInvolvementRows` 却无处推送。
 * 已由 `fix_note_k_complex_structure.py` 补入模板（`insert=True`）。
 */
export const K1_LISTED_SUBTABLE = {
  /**
   * 汇总表「其他应收款」（源 xlsx `A5:C20` 首表，行 = 应收利息/应收股利/其他应收款/合计）。
   * 该表同时承载 G2（应收利息）/ G3（应收股利）/ K1（其他应收款）三个底稿的推送 ——
   * K1 只在 `fs_reconciliation` 有值时推送（条件表语义），无值不推且不进
   * `_removed_table_keys`（可能由 G2/G3 承载，越权删会打断对方）。
   */
  summary: '其他应收款',
  aging: '按账龄披露',
  nature: '按款项性质披露',
  stage1: '期末处于第一阶段的坏账准备',
  stage2: '期末处于第二阶段的坏账准备',
  stage3: '期末处于第三阶段的坏账准备',
  priorStage1: '上年年末处于第一阶段的坏账准备',
  priorStage2: '上年年末处于第二阶段的坏账准备',
  priorStage3: '上年年末处于第三阶段的坏账准备',
  stageMovement: '本期计提、收回或转回的坏账准备情况',
  reversal: '本期转回或收回金额重要的坏账准备',
  writeoffSummary: '本期实际核销的其他应收款情况',
  writeoffDetail: '重要的其他应收款核销情况（逐项披露）',
  top5: '按欠款方归集的其他应收款期末余额前五名单位情况',
  govGrant: '应收政府补助情况',
  transfer: '因金融资产转移而终止确认的其他应收款情况',
  continuedInvolvement: '转移其他应收款且继续涉入形成的资产、负债的金额',
} as const

/** 与 note_template_soe §八、9 tables[].name **逐字**对齐（K1 其他应收款项部分） */
export const K1_SOE_SUBTABLE = {
  /** 同上市侧 `K1_LISTED_SUBTABLE.summary`，源 xlsx 国企侧首表也叫「其他应收款」。 */
  summary: '其他应收款',
  aging: '按账龄披露其他应收款项',
  methodEnd: '按坏账准备计提方法分类披露其他应收款项',
  /**
   * 🔴 原为**裸续表名** `续：`（源 xlsx A27 就是这两个字）——裸续表名跨章节撞键，
   * 且附注 TAB 只显示「续：」看不出续的是哪张表。已由
   * `fix_note_k_complex_structure.py` 正名，改这里必须与模板同步（否则立刻孤儿表）。
   */
  methodPrior: '按坏账准备计提方法分类披露其他应收款项（续：期初余额）',
  individualDetail: '单项计提坏账准备的其他应收款项',
  portfolioAging: '账龄组合',
  portfolioOther: '采用余额百分比法或其他组合方法计提坏账准备的其他应收款项',
  eclMovement: '其他应收款项坏账准备计提情况',
  balanceMovement: '其他应收款项账面余额变动',
  reversal: '收回或转回的坏账准备',
  writeoff: '本期实际核销的其他应收款项',
  top5: '按欠款方归集的期末余额前五名的其他应收款项',
  govGrant: '涉及政府补助的应收款项',
  transfer: '由金融资产转移而终止确认的其他应收款项',
  continuedInvolvement: '其他应收款项转移继续涉入形成的资产、负债的金额',
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
  {
    id: 'priorEcl',
    title: '上年年末 ECL 三阶段',
    structure: 'Stage1/2/3 快照（上年年末）+ 合计',
    source: 'K1-3 上年审定列 / 上期归档底稿',
    noteTarget: '五、8·上年年末处于第一/二/三阶段的坏账准备',
    sourceSheet: '坏账准备明细表K1-3',
    sourceItemId: 'K1-3-baddebt-rows',
    adjudicationKey: 'none',
  },
  {
    id: 'movement',
    title: '坏账准备三阶段变动',
    structure: '期初→阶段迁移→计提/转回/转销/核销→期末',
    source: 'K1-3 三阶段转入转出表',
    noteTarget: '五、8·本期计提、收回或转回的坏账准备情况',
    sourceSheet: '坏账准备明细表K1-3',
    sourceItemId: 'K1-3-baddebt-rows',
    adjudicationKey: 'badDebt',
  },
  {
    id: 'fundCentralization',
    title: '资金集中管理',
    structure: '金额 + 文字（解释15号）',
    source: '人工判断；需考虑非经营性资金占用专项说明',
    noteTarget: '五、8·资金集中管理（文字）',
    sourceSheet: '审定表K1-1',
    adjudicationKey: 'none',
  },
  {
    id: 'govGrant',
    title: '应收政府补助',
    structure: '发文单位 | 补助项目 | 期末余额 | 账龄 | 预计收取时间/金额/依据',
    source: 'K1-2 款项性质含「政府补助」的明细行',
    noteTarget: '附注「计入其他应收款的政府补助」（不在 五、8）',
    sourceSheet: '明细表K1-2',
    adjudicationKey: 'none',
  },
  {
    id: 'transfer',
    title: '转移终止确认 / 继续涉入',
    structure: '终止确认：项目/方式/金额/损益；继续涉入：资产、负债分项',
    source: '人工录入（金融资产转移合同）',
    noteTarget: '附注 §七 金融工具·因转移而终止确认的金融资产（不在 五、8）',
    sourceSheet: '审定表K1-1',
    adjudicationKey: 'none',
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
    noteTarget: '八、9·账龄组合',
    sourceSheet: '坏账准备测算K1-8',
    adjudicationKey: 'portfolio',
    portfolioLabel: '账龄组合',
    portfolioRowKey: 'r1',
  },
  {
    id: 'portfolioOther',
    title: '组合计提·其他组合',
    structure: '组合名称 | 账面余额 | 计提比例(%) | 坏账准备（期末/期初对照）',
    source: '人工设定组合（余额百分比法等）；坏账准备由计提比例派生',
    noteTarget: '八、9·采用余额百分比法或其他组合方法计提坏账准备的其他应收款项',
    sourceSheet: '坏账准备测算K1-8',
    adjudicationKey: 'none',
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
    structure: '债务人 | 转回或收回金额 | 转回或收回前累计已计提坏账准备金额 | 原因、方式',
    source: 'K1-9 转回检查表（accumProvision → 累计已计提）',
    noteTarget: '八、9·收回或转回的坏账准备',
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
    title: '金融资产转移终止确认',
    structure: '债务人名称 | 终止确认金额 | 与终止确认相关的利得或损失（损失以「-」填列）',
    source: '人工录入（金融资产转移合同）',
    noteTarget: '八、9·由金融资产转移而终止确认的其他应收款项',
    sourceSheet: '审定表K1-1',
    adjudicationKey: 'net',
  },
  {
    id: 'continuedInvolvement',
    title: '转移继续涉入形成的资产、负债',
    structure: '资产：/资产小计；负债：/负债小计 + 说明（转移方式/关系/风险）',
    source: '人工录入（证券化、保理等）',
    noteTarget: '八、9·其他应收款项转移继续涉入形成的资产、负债的金额',
    sourceSheet: '审定表K1-1',
    adjudicationKey: 'none',
  },
  {
    id: 'balanceChangeNote',
    title: '说明：账面余额显著变动 / 计提依据',
    structure: '两段文字（源模板 R88 / R89）',
    source: '人工撰写（可 AI 辅助），随同步写入附注文字',
    noteTarget: '八、9·文字段落',
    sourceSheet: '坏账准备明细表K1-3',
    adjudicationKey: 'none',
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
