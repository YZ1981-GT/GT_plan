/**
 * e0SummaryLowerZone.ts — E0-1 下区四块固定文字单一真源
 *
 * 源模板：`函证结果汇总表E0-1` R27~R38（逐格 openpyxl 直读实证）
 *
 * 四块：一、函证情况（矩阵，内容由 e0SummaryMatrix 提供）/ 二、样本选择 /
 * 三、审计说明 / 四、审计结论 + 提示区
 *
 * 设计约束（e0-confirmation-completion §0, R3.7~3.11）：
 * - 跨格合并：O30+O31 / V32+V33 须合并渲染（否则界面出现半句话）
 * - V32 的源模板笔误「本函证证」原样保留（守卫按原文断言）
 * - 「二、样本选择」的零余额/注销账户判定逻辑归 send-list spec 的 R16，
 *   本文件 SHALL NOT 含判定条件（Property 27）
 */

export interface E0LowerZoneText {
  block: 'sample_selection' | 'audit_note' | 'conclusion' | 'tips'
  key: string
  /** 逐字源模板文字；跨两行的已在此合并 */
  text: string
  /** 源模板锚点，多格合并时用 '+' 连接 */
  anchor: string
  /** true = 只读方法论上下文；false = 该段下方有录入位置 */
  readonly: boolean
}

/**
 * E0-1 下区固定文字（逐字取自源 xlsx，守卫用 openpyxl 交叉比对）。
 * 矩阵块（一、函证情况）不在此列（由 e0SummaryMatrix 驱动）。
 */
export const E0_LOWER_ZONE_TEXTS: readonly E0LowerZoneText[] = [
  // ── 二、样本选择 ──────────────────────────────────────────────────────
  {
    block: 'sample_selection',
    key: 'scope_all',
    text: '所有银行账户全部函证（包括零余额账户和在本期内注销的账户）。',
    anchor: 'O28',
    readonly: true,
  },
  {
    block: 'sample_selection',
    key: 'scope_reason',
    text: '如果存在未函证的银行账户应记录不执行函证程序的理由。',
    anchor: 'O29',
    readonly: true,
  },
  {
    block: 'sample_selection',
    key: 'scope_exception',
    // O30+O31 合并（一句话被源模板拆成两格）
    text: '审计准则规定的可以不执行银行函证程序的理由是：银行存款、借款及与金融机构往来的其他重要信息对财务报表不重要且与之相关的重大错报风险很低。',
    anchor: 'O30+O31',
    readonly: true,
  },

  // ── 三、审计说明 ──────────────────────────────────────────────────────
  {
    block: 'audit_note',
    key: 'note_control',
    text: '1.对询证函保持的控制的说明',
    anchor: 'V28',
    readonly: false, // 每条下方有录入位置
  },
  {
    block: 'audit_note',
    key: 'note_mismatch',
    text: '2.针对不符事项的程序',
    anchor: 'V30',
    readonly: false,
  },
  {
    block: 'audit_note',
    key: 'note_other_info',
    // V32+V33 合并（一句话被源模板拆成两格）
    // V32 含源模板笔误「本函证证」—— 原样保留
    text: '3.如果银行回函中存在未函证的其他信息（如XX账号未包含在本函证证中，具体信息另函回复等），应考虑未函证信息的影响，并考虑实施进一步审计程序',
    anchor: 'V32+V33',
    readonly: false,
  },

  // ── 四、审计结论 ──────────────────────────────────────────────────────
  {
    block: 'conclusion',
    key: 'conclusion',
    text: '四、审计结论',
    anchor: 'V34',
    readonly: false, // 录入位置
  },

  // ── 提示 ──────────────────────────────────────────────────────────────
  {
    block: 'tips',
    key: 'tips_title',
    text: '提示：对收到的回函重点检查：',
    anchor: 'A37',
    readonly: true,
  },
  {
    block: 'tips',
    key: 'tips_body',
    // A38（合并区 A38:N38），四条以 \n 分隔
    text: '1.确认与发出的询证函是否为同一份、是否为原件；\n2.核实回函快递物流信息、对比回函印章是否与被询证着名称一致、加盖印章和签名是否清晰可辨认等；必要时进一步与被审计单位持有的其他文件进行核对或亲自前往被询证者进行核实；\n3.关注回函中是否包含免责或其他限制性条款；\n4.检查函证信息是否相符，对回函不符的询证函事项查明原因确定是否存在错报，考虑是否存在舞弊的可能性。',
    anchor: 'A38',
    readonly: true,
  },
]

/** 下区四块锚点标题（供渲染组件分段） */
export const E0_LOWER_ZONE_BLOCKS = {
  matrix: { anchor: 'C27', title: '一、函证情况' },
  sample_selection: { anchor: 'O27', title: '二、样本选择' },
  audit_note: { anchor: 'V27', title: '三、审计说明' },
  conclusion: { anchor: 'V34', title: '四、审计结论' },
} as const

/** 按 block 分组获取文字 */
export function getTextsForBlock(block: E0LowerZoneText['block']): readonly E0LowerZoneText[] {
  return E0_LOWER_ZONE_TEXTS.filter((t) => t.block === block)
}

/** 「未函证账户的理由」持久化 key */
export const E0_UNFUNDED_REASON_KEY = 'E0-1-lower-unfunded-reason'

/** 三条审计说明的持久化 key 前缀 */
export const E0_AUDIT_NOTE_KEY_PREFIX = 'E0-1-lower-audit-note-'

/** 审计结论持久化 key */
export const E0_CONCLUSION_KEY = 'E0-1-lower-conclusion'
