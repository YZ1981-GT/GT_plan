/**
 * G14 信用减值损失 — 固定行、科目映射与试算对账规则
 * 对齐致同 xlsx + CAS 22（含合同资产 ECL → 6702）
 */
export type G14CounterpartKind = 'allowance' | 'oci' | 'liability' | 'none'

export interface G14LineDef {
  rowKey: string
  label: string
  /** 对应科目列展示名 */
  provisionAccount: string
  /** 对方科目性质：FVOCI 进 OCI，财务担保进预计负债 */
  counterpartKind: G14CounterpartKind
  /** 试算取数科目前缀（按优先级） */
  tbPrefixes: string[]
  /** 试算科目名称关键字（同一前缀下消歧，如 1231 分明细） */
  tbNameHints: string[]
}

export const G14_LINE_ITEMS: G14LineDef[] = [
  {
    rowKey: 'notes',
    label: '应收票据坏账损失',
    provisionAccount: '应收票据坏账准备',
    counterpartKind: 'allowance',
    tbPrefixes: ['1231'],
    tbNameHints: ['应收票据', '票据'],
  },
  {
    rowKey: 'ar',
    label: '应收账款坏账损失',
    provisionAccount: '应收账款坏账准备',
    counterpartKind: 'allowance',
    tbPrefixes: ['1231'],
    tbNameHints: ['应收账款'],
  },
  {
    rowKey: 'rfin',
    label: '应收款项融资减值损失',
    provisionAccount: '应收款项融资减值准备',
    counterpartKind: 'allowance',
    tbPrefixes: ['1231', '1124'],
    tbNameHints: ['应收款项融资', '融资'],
  },
  {
    rowKey: 'othar',
    label: '其他应收款坏账损失',
    provisionAccount: '其他应收款坏账准备',
    counterpartKind: 'allowance',
    tbPrefixes: ['1231'],
    tbNameHints: ['其他应收'],
  },
  {
    rowKey: 'debt',
    label: '债权投资减值损失',
    provisionAccount: '债权投资减值准备',
    counterpartKind: 'allowance',
    tbPrefixes: ['1505', '1502'],
    tbNameHints: ['债权投资减值', '持有至到期'],
  },
  {
    rowKey: 'othdebt',
    label: '其他债权投资减值损失',
    provisionAccount: '其他综合收益-信用减值准备',
    counterpartKind: 'oci',
    tbPrefixes: ['1503', '4104'],
    tbNameHints: ['其他债权', '信用减值准备', 'FVOCI'],
  },
  {
    rowKey: 'ltar',
    label: '长期应收款坏账损失',
    provisionAccount: '长期应收款坏账准备',
    counterpartKind: 'allowance',
    tbPrefixes: ['1231', '1531', '1532'],
    tbNameHints: ['长期应收'],
  },
  {
    rowKey: 'ca',
    label: '合同资产减值损失',
    provisionAccount: '合同资产减值准备',
    counterpartKind: 'allowance',
    tbPrefixes: ['1142'],
    tbNameHints: ['合同资产减值', '合同资产'],
  },
  {
    rowKey: 'guarantee',
    label: '财务担保预计损失',
    provisionAccount: '预计负债',
    counterpartKind: 'liability',
    tbPrefixes: ['2801'],
    tbNameHints: ['财务担保', '贷款承诺', '担保'],
  },
  {
    rowKey: 'other',
    label: '其他',
    provisionAccount: '',
    counterpartKind: 'none',
    tbPrefixes: [],
    tbNameHints: [],
  },
]

export const G14_ACCOUNT_CODE = '6702'
/** 与 xlsx 编制说明一致：变动比例超过 30% 须说明主要原因 */
export const G14_CHANGE_RATE_THRESHOLD = 0.3
/**
 * 变动额绝对值阈值（元）：|变动额|≥该值亦须填写原因分析
 * （弥补「上期很小导致比率失真」或「上期为 0 无法算比率」）
 */
export const G14_CHANGE_AMOUNT_THRESHOLD = 100_000

/**
 * 编制范围说明（对齐 xlsx「编制说明【非打印内容】」CAS 22）
 */
export const G14_SCOPE_NOTE =
  '本科目反映按《企业会计准则第22号——金融工具确认和计量》（财会〔2017〕7号）计提的信用减值损失（含转回），涵盖以摊余成本计量的金融资产、FVOCI 债务工具、租赁应收款、合同资产及贷款承诺/财务担保合同等。'

/** 编制提示要点 */
export const G14_PREP_HINTS = [
  '本期数（未审/调整/审定）自 G14-2 明细自动汇总；上期数独立录入，用于本期与上期审定数比较。',
  '|变动率|>30% 或 |变动额|≥10万元 的行须填写「原因分析」；合计超阈值时审计说明须写明主要原因（负数为减少）。上期为 0 而本期有发生额时亦须说明。',
  '审定合计须与试算平衡表 6702 本期发生额一致（借方计提−贷方转回）；差异数≠0 须查明。',
  'G14-2：计入损益=计提−转回（转回正数）；期末=期初+计提−转回−转销+其他变动；核对列验证审定数=计入损益。',
  '合同资产减值按 CAS 22 ECL 计入信用减值损失（6702），对应科目 1142 合同资产减值准备；可用「取数对账」与试算期末勾稽。',
  '其他债权投资（FVOCI）减值对方科目为「其他综合收益-信用减值准备」，不是坏账准备贷方。',
  '资产负债表日按单项或组合计量预期信用损失（ECL）：差额确认损失或转回；企业可按内部核算设明细科目。',
  '「发布审定数」后经 EventBus 同步至附注披露；各减值来源与 D1/D2/D5/D6/F1/G4/G5 源科目 ECL 交叉核对。',
  'G14-3 调整分录可与中央调整分录模块双向同步：从模块拉取含 6702 的分录组，确认后推送未关联分录；账项净额按回写行写入 G14-2。',
] as const

/** G14-2 各行 ECL 交叉验证默认索引 */
export const G14_ECL_CROSS_REF: Record<string, string> = {
  notes: 'wp:D1-1',
  ar: 'wp:D2-1',
  rfin: 'wp:D5-1',
  othar: 'wp:F1-1',
  debt: 'wp:G4-1',
  othdebt: 'wp:G6-1',
  ltar: 'wp:G5-1',
  ca: 'wp:D6-1',
  guarantee: '',
  other: '',
}

/** 附注披露（上市）— 复用 G14-2 明细 rowKey */
export const G14_DISCLOSURE_LISTED_ROWS = G14_LINE_ITEMS

/** 附注披露（国企）— 坏账损失合并披露 */
export const G14_DISCLOSURE_SOE_ROWS = [
  { rowKey: 'bad_debt', label: '坏账损失' },
  { rowKey: 'debt', label: '债权投资减值损失' },
  { rowKey: 'othdebt', label: '其他债权投资减值损失' },
  { rowKey: 'other', label: '其他' },
] as const

/**
 * 国企「坏账损失」= 应收类 + 合同资产等坏账/减值源行（不含财务担保）
 */
export const G14_SOE_BAD_DEBT_SOURCES = [
  'notes', 'ar', 'rfin', 'othar', 'ltar', 'ca',
] as const

/** 国企「其他」行额外汇总源（财务担保预计损失等） */
export const G14_SOE_OTHER_EXTRA_SOURCES = ['guarantee'] as const

export const G14_DISCLOSURE_TEMPLATE_HINT =
  '信用减值损失（注：损失以“—”号填列，以下不存在的项目可以删除）'

export const G14_DISCLOSURE_FORMULA_MAP = [
  { field: '附注合计-本期', source: 'G14-1审定表', formula: 'SUM(currentAudited) = G14-adj-tb', account: '6702' },
  { field: '附注各行-本期', source: 'G14-2明细', formula: 'listed: 1:1; SOE: bad_debt=Σ应收/合同资产; other+=guarantee', account: '6702' },
  { field: '附注合计-上期', source: 'G14-adj-prior', formula: 'priorUnadj+priorAdj（无 priorAudited 时回算）', account: '6702' },
  { field: '同步附注', source: 'disclosure-notes', formula: '上市→三、信用减值损失；国企→八、73', account: '6702' },
  { field: 'ECL交叉验证', source: 'G14-2核对列', formula: '与 D1/D2/D5/D6/G4/G5/G6 索引联动', account: '-' },
  { field: '期末准备对账', source: 'trial_balance', formula: 'closingProvision ≈ TB(对应准备/OCI/预计负债)', account: '1231/1142/…' },
] as const

export function getG14LineDef(rowKey: string): G14LineDef | undefined {
  return G14_LINE_ITEMS.find((d) => d.rowKey === rowKey)
}

export function isG14OciCounterpart(rowKey: string): boolean {
  return getG14LineDef(rowKey)?.counterpartKind === 'oci'
}

export function g14CounterpartHint(rowKey: string): string {
  const kind = getG14LineDef(rowKey)?.counterpartKind
  if (kind === 'oci') {
    return 'FVOCI：对方计入其他综合收益-信用减值准备，而非坏账准备贷方'
  }
  if (kind === 'liability') {
    return '财务担保/贷款承诺：对方通常为预计负债（2801）'
  }
  return ''
}
