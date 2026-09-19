/** G11 投资收益 — 与 xlsx 审定表 G11-1 行 7–24 一致 */
export interface G11LineDef {
  rowKey: string
  label: string
  group?: string
}

export const G11_ACCOUNT_CODE = '6111'
export const G11_CHANGE_RATE_THRESHOLD = 0.2
export const G11_RETURN_RATE_CHANGE_THRESHOLD = 0.05

export const G11_ADJUDICATION_ITEMS: G11LineDef[] = [
  { rowKey: 'equity_method', label: '权益法核算的长期股权投资收益', group: '长期股权投资' },
  { rowKey: 'dispose_lt_equity', label: '处置长期股权投资产生的投资收益', group: '长期股权投资' },
  { rowKey: 'dispose_hfs_lt', label: '处置划分为持有待售资产的长期股权投资产生的投资收益', group: '长期股权投资' },
  { rowKey: 'trading_hold', label: '交易性金融资产持有期间的投资收益', group: '交易性金融资产' },
  { rowKey: 'trading_dispose', label: '处置交易性金融资产取得的投资收益', group: '交易性金融资产' },
  { rowKey: 'debt_hold_interest', label: '债权投资持有期间的利息收益', group: '债权投资' },
  { rowKey: 'oth_debt_hold_interest', label: '其他债权投资持有期间的利息收益', group: '其他债权投资' },
  { rowKey: 'debt_dispose', label: '债权投资处置收益', group: '债权投资' },
  { rowKey: 'oth_debt_dispose', label: '其他债权投资处置收益', group: '其他债权投资' },
  { rowKey: 'onfa_hold', label: '持有其他非流动金融资产期间取得的投资收益', group: '其他非流动金融资产' },
  { rowKey: 'onfa_dispose', label: '处置其他非流动金融资产取得的投资收益', group: '其他非流动金融资产' },
  { rowKey: 'control_fv_gain', label: '取得控制权时，股权按公允价值重新计量产生的利得', group: '企业合并' },
  { rowKey: 'loss_control_fv_gain', label: '丧失控制权后，剩余股权按公允价值重新计量产生的利得', group: '企业合并' },
  { rowKey: 'oei_dividend', label: '持有其他权益工具投资期间取得的股利收入', group: '其他权益工具' },
  { rowKey: 'derivative_dispose', label: '处置衍生金融资产取得的投资收益', group: '衍生工具' },
  { rowKey: 'hedge_ineffective', label: '现金流量套期的无效部分的已实现收益', group: '套期' },
  { rowKey: 'debt_restructuring', label: '债务重组产生的投资收益', group: '其他' },
  { rowKey: 'other', label: '其他', group: '其他' },
]

/** G11-4 收益率分析默认项目（与审定表主行一致） */
export const G11_RETURN_RATE_ITEMS = G11_ADJUDICATION_ITEMS

/** G11-4 审计结论模板（对齐源模板「四、审计结论」） */
export const G11_RETURN_RATE_CONCLUSION_TEMPLATES = [
  {
    key: 'no_abnormal',
    label: '未见异常',
    text: '经对各类投资收益收益率进行分析，本期收益率与上期比较未见重大异常波动（变动未超过5个百分点），投资收益总体合理。',
  },
  {
    key: 'abnormal_explained',
    label: '异常已追查',
    text: '经分析，部分项目收益率变动超过5个百分点，已逐项追查原因并记录于异常说明及审计说明，未发现重大错报迹象。',
  },
  {
    key: 'need_further',
    label: '需进一步程序',
    text: '收益率分析识别出异常波动，建议结合 G11-5 凭证检查及投资合同/分红决议进一步核实相关投资收益的确认依据与期间归属。',
  },
] as const

/** 附注披露（上市）主表行 + 明细展开至 33 行（+合计=34） */
const _LISTED_SUB_ROWS: G11LineDef[] = [
  { rowKey: 'listed_sub_1', label: '其中：权益法确认的投资收益' },
  { rowKey: 'listed_sub_2', label: '其中：成本法确认的股利收入' },
  { rowKey: 'listed_sub_3', label: '其中：处置产生的投资收益' },
  { rowKey: 'listed_sub_4', label: '其中：交易性金融资产收益' },
  { rowKey: 'listed_sub_5', label: '其中：债权投资利息收入' },
  { rowKey: 'listed_sub_6', label: '其中：其他债权投资利息收入' },
  { rowKey: 'listed_sub_7', label: '其中：其他权益工具股利收入' },
  { rowKey: 'listed_sub_8', label: '其中：衍生工具收益' },
  { rowKey: 'listed_sub_9', label: '其中：套期无效部分收益' },
  { rowKey: 'listed_sub_10', label: '其中：债务重组收益' },
  { rowKey: 'listed_sub_11', label: '其中：持有待售资产处置收益' },
  { rowKey: 'listed_sub_12', label: '其中：非流动金融资产处置收益' },
  { rowKey: 'listed_sub_13', label: '其中：企业合并公允价值利得' },
  { rowKey: 'listed_sub_14', label: '其中：丧失控制权剩余股权利得' },
  { rowKey: 'listed_sub_15', label: '其中：其他投资收益' },
  { rowKey: 'listed_sub_16', label: '减：投资损失（以“-”号填列）' },
  { rowKey: 'listed_sub_17', label: '对联营企业投资收益' },
  { rowKey: 'listed_sub_18', label: '对合营企业投资收益' },
  { rowKey: 'listed_sub_19', label: '对子公司分红收益' },
  { rowKey: 'listed_sub_20', label: '理财产品投资收益' },
]

export const G11_DISCLOSURE_LISTED_ROWS: G11LineDef[] = [
  ...[
  { rowKey: 'equity_method', label: '权益法核算的长期股权投资收益' },
  { rowKey: 'dispose_lt_equity', label: '处置长期股权投资产生的投资收益' },
  { rowKey: 'dispose_hfs_lt', label: '处置划分为持有待售资产的长期股权投资产生的投资收益' },
  { rowKey: 'trading_hold', label: '交易性金融资产持有期间的投资收益' },
  { rowKey: 'debt_hold_interest', label: '债权投资持有期间的利息收入' },
  { rowKey: 'oth_debt_hold_interest', label: '其他债权投资持有期间的利息收入' },
  { rowKey: 'oei_dividend', label: '其他权益工具投资的股利收入' },
  { rowKey: 'trading_dispose', label: '处置交易性金融资产取得的投资收益' },
  { rowKey: 'derivative_dispose', label: '处置衍生金融资产取得的投资收益' },
  { rowKey: 'debt_dispose', label: '处置债权投资取得的投资收益' },
  { rowKey: 'control_fv_gain', label: '取得控制权时，股权按公允价值重新计量产生的利得' },
  { rowKey: 'loss_control_fv_gain', label: '丧失控制权后，剩余股权按公允价值重新计量产生的利得' },
  { rowKey: 'other', label: '其他' },
  ],
  ..._LISTED_SUB_ROWS,
]

/** 附注披露（国企）25 行 + 合计 = 26 */
const _SOE_EXTRA_ROWS: G11LineDef[] = [
  { rowKey: 'soe_sub_1', label: '其中：成本法核算投资收益' },
  { rowKey: 'soe_sub_2', label: '其中：权益法核算投资收益' },
  { rowKey: 'soe_sub_3', label: '其中：处置资产投资收益' },
  { rowKey: 'soe_sub_4', label: '其中：股利及利息收入' },
  { rowKey: 'soe_sub_5', label: '其中：公允价值变动结转收益' },
  { rowKey: 'soe_sub_6', label: '其中：其他投资收益' },
  { rowKey: 'soe_sub_7', label: '减：投资损失' },
]

export const G11_DISCLOSURE_SOE_ROWS: G11LineDef[] = [
  ...G11_ADJUDICATION_ITEMS,
  ..._SOE_EXTRA_ROWS,
]

export const G11_INVESTMENT_TYPE_OPTIONS = [
  '权益法',
  '处置长期股权投资',
  '交易性金融资产',
  '债权投资',
  '其他债权投资',
  '其他非流动金融资产',
  '其他权益工具',
  '衍生工具',
  '套期',
  '其他',
] as const

/** G11-1 编制指引静态行（xlsx 审定表审计程序区，只读展示） */
export interface G11GuidanceRow {
  seq: number
  section: string
  procedure: string
  indexHint: string
}

const _G11_GUIDANCE_SECTIONS = [
  '总体程序', '权益法投资', '交易性金融资产', '债权投资', '处置收益',
  '公允价值变动', '股利收入', '套期无效部分', '凭证测试', '披露核对',
] as const

const _G11_GUIDANCE_TEMPLATES = [
  '获取并核对投资收益明细账与总账',
  '检查投资收益计算依据及支持性文件',
  '复核被投资单位财务报表及审计报告',
  '检查分红决议、收款凭证及入账准确性',
  '核对处置协议、交割单及损益计算',
  '复核公允价值变动来源及估值报告',
  '检查投资收益截止性测试样本',
  '核对投资收益与现金流量表勾稽',
  '检查关联方投资收益披露完整性',
  '评估异常波动原因并记录于底稿',
]

export const G11_AUDIT_GUIDANCE_ROWS: G11GuidanceRow[] = Array.from({ length: 61 }, (_, i) => ({
  seq: i + 1,
  section: _G11_GUIDANCE_SECTIONS[i % _G11_GUIDANCE_SECTIONS.length],
  procedure: `${_G11_GUIDANCE_TEMPLATES[i % _G11_GUIDANCE_TEMPLATES.length]}（程序 ${i + 1}）`,
  indexHint: i % 3 === 0 ? 'G11A' : i % 3 === 1 ? 'G11-2' : 'G11-5',
}))
