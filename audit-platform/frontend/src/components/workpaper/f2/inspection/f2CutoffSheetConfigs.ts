/**
 * F2-29~32 存货（原材料/产成品）截止测试 — 对齐致同源模板四象限：
 *   入库×账→单 / 入库×单→账 / 出库×账→单 / 出库×单→账
 */
export type F2CutoffInvCategory = 'raw' | 'finished' | ''

export interface F2CutoffSheetConfig {
  sheetCode: string
  /** 短标题（工具栏） */
  title: string
  /** 完整底稿标题（对齐源模板，含原材料/产成品） */
  fullTitle: string
  direction: 'inbound' | 'outbound'
  /**
   * voucher_to_source = 记账凭证→原始凭证（存在/发生，防多记跨期）
   * source_to_voucher = 原始凭证→记账凭证（完整性，防漏记跨期）
   */
  trace: 'voucher_to_source' | 'source_to_voucher'
  /** @deprecated 兼容旧调用，等同 trace */
  testType: 'forward' | 'backward'
  /** 主原始凭证列名 */
  primaryDocLabel: string
  /** 是否显示质检报告列（入库表） */
  showInspect: boolean
  /** 其他单据列名（红字可选列） */
  otherDocLabel: string
  /** 审计过程要点（对齐源模板二、审计过程） */
  processSteps: string[]
  /** 页脚提示 */
  footerTips: string[]
}

/** 全量存货科目（1401~1411，不含1412跌价准备） */
export const F2_INVENTORY_ACCOUNT_CODES = '1401,1402,1403,1404,1405,1406,1407,1408,1409,1410,1411'

/** 原材料及相关（材料采购/在途/原材料/周转材料等） */
export const F2_CUTOFF_RAW_ACCOUNT_CODES = '1401,1402,1403,1404'

/** 产成品及相关（库存商品/发出商品） */
export const F2_CUTOFF_FINISHED_ACCOUNT_CODES = '1405,1406'

export const F2_CUTOFF_CATEGORY_OPTIONS: { value: F2CutoffInvCategory; label: string }[] = [
  { value: '', label: '全部类别' },
  { value: 'raw', label: '原材料' },
  { value: 'finished', label: '产成品' },
]

export function getF2CutoffAccountCodes(category: F2CutoffInvCategory = ''): string {
  if (category === 'raw') return F2_CUTOFF_RAW_ACCOUNT_CODES
  if (category === 'finished') return F2_CUTOFF_FINISHED_ACCOUNT_CODES
  return F2_INVENTORY_ACCOUNT_CODES
}

export function getF2CutoffSamplingParams(config: F2CutoffSheetConfig): {
  cutoffDirection: 'post_cutoff' | 'pre_cutoff'
  directionFilter: 'debit' | 'credit'
} {
  const directionFilter = config.direction === 'inbound' ? 'debit' : 'credit'
  // 凭证→单据：侧重截止日后入账样本；单据→凭证：侧重截止日前单据对应入账
  const cutoffDirection =
    config.trace === 'voucher_to_source' || config.testType === 'forward'
      ? 'post_cutoff'
      : 'pre_cutoff'
  return { cutoffDirection, directionFilter }
}

const SHARED_OBJECTIVES = [
  '资产负债表中记录的存货是存在的，并计入了正确的会计科目',
  '所有应记录的存货均已记录，且相关信息已得到恰当披露',
] as const

export const F2_CUTOFF_OBJECTIVES = [...SHARED_OBJECTIVES]

export const F2_CUTOFF_CONFIGS: Record<string, F2CutoffSheetConfig> = {
  'F2-29': {
    sheetCode: 'F2-29',
    title: '截止测试-入库(账→单)',
    fullTitle: '存货（原材料/产成品）截止测试-入库（从记账凭证至原始凭证）',
    direction: 'inbound',
    trace: 'voucher_to_source',
    testType: 'forward',
    primaryDocLabel: '入库单',
    showInspect: true,
    otherDocLabel: '送货单/发票',
    processSteps: [
      '从存货明细账借方选取截止日前后各 ___ 天、金额大于 ___ 元的样本，追查至入库单、质检报告等原始凭证，核对日期与金额。',
      '将入库单编号与监盘程序取得的截止信息交叉核对，关注是否冲突。',
    ],
    footerTips: [
      '应分别存货类别（如原材料、产成品）进行截止测试。',
      '本表测试存在/发生：账面入账是否有真实入库支持，识别提前入账或跨期。',
    ],
  },
  'F2-30': {
    sheetCode: 'F2-30',
    title: '截止测试-入库(单→账)',
    fullTitle: '存货（原材料/产成品）截止测试-入库（从原始凭证至记账凭证）',
    direction: 'inbound',
    trace: 'source_to_voucher',
    testType: 'backward',
    primaryDocLabel: '入库单',
    showInspect: true,
    otherDocLabel: '送货单/发票',
    processSteps: [
      '从入库记录中选取截止日前后各 ___ 天、金额大于 ___ 元的样本，与存货明细账借方勾稽，确认是否已入账且期间正确。',
      '核对入库单编号是否与监盘取得的截止信息不冲突。',
    ],
    footerTips: [
      '应分别存货类别（如原材料、产成品）进行截止测试。',
      '本表测试完整性：实物入库是否均已入账，识别推迟入账或漏记。',
    ],
  },
  'F2-31': {
    sheetCode: 'F2-31',
    title: '截止测试-出库(账→单)',
    fullTitle: '存货（原材料/产成品）截止测试-出库（从记账凭证至原始凭证）',
    direction: 'outbound',
    trace: 'voucher_to_source',
    testType: 'forward',
    primaryDocLabel: '出库单/领料单',
    showInspect: false,
    otherDocLabel: '运单/发运单',
    processSteps: [
      '从存货明细账贷方选取截止日前后各 ___ 天、金额大于 ___ 元的样本，追查至出库单、领料单、运单等，核对日期与金额。',
      '将出库单编号与监盘程序取得的截止信息交叉核对。',
      '产成品出库截止测试应与营业收入截止测试协调执行。',
    ],
    footerTips: [
      '应分别存货类别（如原材料、产成品）进行截止测试。',
      '若出库主要证据非出库单，应按实际证据调整本表栏目。',
      '发出商品未确认收入的，应结合收入确认时点评价期间归属。',
    ],
  },
  'F2-32': {
    sheetCode: 'F2-32',
    title: '截止测试-出库(单→账)',
    fullTitle: '存货（原材料/产成品）截止测试-出库（从原始凭证至记账凭证）',
    direction: 'outbound',
    trace: 'source_to_voucher',
    testType: 'backward',
    primaryDocLabel: '出库单/领料单',
    showInspect: false,
    otherDocLabel: '运单/发运单',
    processSteps: [
      '从出库/领料记录中选取截止日前后各 ___ 天、金额大于 ___ 元的样本，与存货明细账贷方勾稽，确认是否已入账且期间正确。',
      '核对出库单编号是否与监盘取得的截止信息不冲突，并与收入截止测试结果对照。',
    ],
    footerTips: [
      '应分别存货类别（如原材料、产成品）进行截止测试。',
      '以出库单为起点测试完整性；若实务以其他单据为主，应调整本表。',
      '产成品出库应与营业收入截止测试协调，关注发出未确认收入情形。',
    ],
  },
}

export function getF2CutoffConfig(code: string): F2CutoffSheetConfig | undefined {
  return F2_CUTOFF_CONFIGS[code]
}

/** 过程元数据字段（按 sheet 持久化） */
export const F2_CUTOFF_META_FIELDS = [
  'entityName',
  'cutoffDate',
  'sampleDaysBefore',
  'sampleDaysAfter',
  'amountThreshold',
  'processNote',
  'invCategory',
  'sampleWindowMode',
] as const
