/**
 * G11 投资收益 — 分项回写匹配（摘要/附注 → G11-1/G11-2 rowKey）
 */
import { G11_ACCOUNT_CODE, G11_ADJUDICATION_ITEMS } from './g11Constants'

export const G11_ADJ_WRITEBACK_DEFAULT_ROW = 'other'

export const G11_ADJUDICATION_WRITEBACK_OPTIONS = G11_ADJUDICATION_ITEMS.map((d) => ({
  rowKey: d.rowKey,
  label: d.label,
  group: d.group,
}))

/** 常用对方科目（投资收益调整） */
export const G11_ADJ_ACCOUNT_OPTIONS: { code: string; name: string }[] = [
  { code: G11_ACCOUNT_CODE, name: '投资收益' },
  { code: '1511', name: '长期股权投资' },
  { code: '1501', name: '交易性金融资产' },
  { code: '1503', name: '其他权益工具投资' },
  { code: '1504', name: '其他非流动金融资产' },
  { code: '1502', name: '债权投资' },
  { code: '1505', name: '其他债权投资' },
  { code: '1131', name: '应收股利' },
  { code: '1132', name: '应收利息' },
  { code: '6101', name: '公允价值变动损益' },
  { code: '1002', name: '银行存款' },
  { code: '4104', name: '利润分配—未分配利润' },
]

const KEYWORD_RULES: Array<{ rowKey: string; pattern: RegExp }> = [
  { rowKey: 'equity_method', pattern: /权益法|联营|合营/ },
  { rowKey: 'dispose_lt_equity', pattern: /处置.*长期股权|长期股权.*处置/ },
  { rowKey: 'dispose_hfs_lt', pattern: /持有待售.*长期股权|长期股权.*持有待售/ },
  { rowKey: 'trading_hold', pattern: /交易性金融资产.*持有|持有.*交易性|理财.*收益/ },
  { rowKey: 'trading_dispose', pattern: /处置.*交易性|交易性.*处置/ },
  { rowKey: 'debt_hold_interest', pattern: /债权投资.*利息|持有.*债权投资/ },
  { rowKey: 'oth_debt_hold_interest', pattern: /其他债权.*利息|持有.*其他债权/ },
  { rowKey: 'debt_dispose', pattern: /处置.*债权投资|债权投资.*处置/ },
  { rowKey: 'oth_debt_dispose', pattern: /处置.*其他债权|其他债权.*处置/ },
  { rowKey: 'onfa_hold', pattern: /其他非流动金融资产.*持有|持有.*其他非流动/ },
  { rowKey: 'onfa_dispose', pattern: /处置.*其他非流动|其他非流动.*处置/ },
  { rowKey: 'control_fv_gain', pattern: /取得控制权|合并日.*公允/ },
  { rowKey: 'loss_control_fv_gain', pattern: /丧失控制权|剩余股权.*公允/ },
  { rowKey: 'oei_dividend', pattern: /其他权益工具.*股利|股利收入/ },
  { rowKey: 'derivative_dispose', pattern: /衍生.*处置|处置.*衍生/ },
  { rowKey: 'hedge_ineffective', pattern: /套期.*无效|现金流量套期/ },
  { rowKey: 'debt_restructuring', pattern: /债务重组/ },
]

export function isG11AccountCode(code: string | null | undefined): boolean {
  const c = String(code ?? '').trim()
  return !!c && (c === G11_ACCOUNT_CODE || c.startsWith(G11_ACCOUNT_CODE))
}

export function inferG11AdjudicationRowKey(input: {
  adjudicationRowKey?: string
  description?: string
  summary?: string
  noteItem?: string
  remark?: string
  itemName?: string
  accountName?: string
}): string {
  const explicit = String(input.adjudicationRowKey ?? '').trim()
  if (explicit && G11_ADJUDICATION_ITEMS.some((d) => d.rowKey === explicit)) return explicit

  const text = [
    input.description,
    input.summary,
    input.noteItem,
    input.remark,
    input.itemName,
    input.accountName,
  ].map((s) => String(s ?? '')).join(' ')

  for (const def of G11_ADJUDICATION_ITEMS) {
    if (def.rowKey === 'other') continue
    if (text.includes(def.label) || text.includes(def.label.slice(0, 8))) return def.rowKey
  }
  for (const rule of KEYWORD_RULES) {
    if (rule.pattern.test(text)) return rule.rowKey
  }
  return G11_ADJ_WRITEBACK_DEFAULT_ROW
}
