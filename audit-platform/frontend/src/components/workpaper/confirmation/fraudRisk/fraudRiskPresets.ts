/**
 * fraudRiskPresets.ts — D0-8 预置 19 条舞弊风险迹象 + tooltip 举例
 *
 * 来源：《审计准则问题解答第2号——函证》+ 致同通用审计程序模板
 * 跨循环复用：D0-8/E0-8/F0-8/K0-8 等共享同一预置常量
 */
import type { FraudRiskItem } from './fraudRiskTypes'

// ─── 19 条预置舞弊风险迹象 ──────────────────────────────────────────────────

export const PRESET_FRAUD_ITEMS: FraudRiskItem[] = [
  {
    seq: 1,
    description: '被审计单位管理层凌驾于内部控制之上',
    _preset: true,
  },
  {
    seq: 2,
    description: '被审计单位存在异常的关联方交易',
    _preset: true,
  },
  {
    seq: 3,
    description: '被审计单位近期频繁更换会计师事务所',
    _preset: true,
  },
  {
    seq: 4,
    description: '被审计单位管理层对被询证方施加不当影响或限制审计人员直接接触被询证方',
    _preset: true,
  },
  {
    seq: 5,
    description: '被询证方为被审计单位的关联方或存在重大利益关系的第三方',
    _preset: true,
  },
  {
    seq: 6,
    description: '被审计单位与被询证方之间的交易条款显著偏离市场惯例',
    _preset: true,
  },
  {
    seq: 7,
    description: '收到的回函存在明显的修改痕迹或可靠性存疑',
    _preset: true,
  },
  {
    seq: 8,
    description: '回函信息与被审计单位账面记录存在重大不一致且无合理解释',
    _preset: true,
  },
  {
    seq: 9,
    description: '被审计单位存在重大的期末异常交易（尤其是临近资产负债表日的大额交易）',
    _preset: true,
  },
  {
    seq: 10,
    description: '被询证方的注册信息、经营场所等与被审计单位有关人员存在关联',
    _preset: true,
  },
  {
    seq: 11,
    description: '被审计单位管理层拒绝或反对对特定交易对手方进行函证',
    _preset: true,
  },
  {
    seq: 12,
    description: '被审计单位存在收入确认方面的异常情况（如收入增长与现金流不匹配）',
    _preset: true,
  },
  {
    seq: 13,
    description: '被审计单位存在大量现金交易或非正常结算方式',
    _preset: true,
  },
  {
    seq: 14,
    description: '函证回函率异常偏高或偏低，或特定类别的函证全部未回函',
    tooltip_key: 'item_14_reply_rate',
    _preset: true,
  },
  {
    seq: 15,
    description: '被审计单位资金往来频繁但无明确商业实质',
    _preset: true,
  },
  {
    seq: 16,
    description: '被审计单位管理层存在重大个人财务困难或利益驱动',
    _preset: true,
  },
  {
    seq: 17,
    description: '函证程序中发现的差异未得到被审计单位管理层的合理解释',
    _preset: true,
  },
  {
    seq: 18,
    description: '被审计单位所处行业存在特殊的舞弊风险因素',
    tooltip_key: 'item_18_19_examples',
    _preset: true,
  },
  {
    seq: 19,
    description: '其他可能表明存在舞弊风险的情况',
    tooltip_key: 'item_18_19_examples',
    _preset: true,
  },
]

// ─── tooltip 举例文本（红框内容精确就近） ────────────────────────────────────

export const ITEM_TOOLTIPS_D08: Record<string, string> = {
  /** 第14条：回函率举例 */
  item_14_reply_rate: [
    '【举例】',
    '• 银行函证回函率通常应接近100%，若显著低于该水平需关注是否存在虚假银行账户',
    '• 债权人回函率通常较低（约30%-50%），但若特定科目回函率异常偏高（如接近100%）可能存在串通',
    '• 应收账款回函率因行业而异，但某一批次集中未回函时需评估是否因客户虚构',
    '• 关注是否存在通过控制回函过程来隐匿舞弊的行为',
  ].join('\n'),

  /** 第18-19条：行业特殊风险 + 其他情况举例 */
  item_18_19_examples: [
    '【举例】',
    '• 房地产行业：预售款（合同负债）确认时点操纵、关联方购房虚增收入',
    '• 贸易行业：循环贸易、空转、无商业实质的资金往来',
    '• 金融行业：复杂金融工具交易对手方可靠性、表外安排',
    '• 科技行业：知识产权交易虚假、无形资产关联交易',
    '• 制造业：跨期出入库、提前确认收入配合函证相符',
    '• 其他：管理层经历过类似舞弊事件、审计前科、媒体报道',
  ].join('\n'),
}

// ─── 编制说明 4 条（精确落位） ───────────────────────────────────────────────

export const GUIDANCE_NOTES_D08 = {
  /** ① 顶部说明 */
  top_note: '本表用于评价函证程序中是否存在舞弊风险迹象。审计人员应结合函证全过程（发函→跟函→回函→差异调节→替代程序）综合判断各项风险因素，并对存在舞弊风险迹象的事项制定针对性的应对措施。',
  /** ② 应对措施 placeholder */
  countermeasure_placeholder: '请描述针对该风险迹象的具体应对措施（如扩大样本范围/追加审计程序/与管理层沟通等）',
  /** ③ 索引列 tooltip */
  source_ref_tooltip: '填写支持性底稿的索引号（如 D0-1/D0-4/D0-7 等），可跳转查看相关底稿。',
  /** ④ 是=是 条件提示 */
  exist_yes_warning: '已识别舞弊风险迹象，请填写应对措施。如存在重大舞弊风险，应同步更新 B50 风险评估及总体应对方案。',
} as const
