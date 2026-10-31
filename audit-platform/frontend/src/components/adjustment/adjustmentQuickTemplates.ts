/**
 * 调整分录快捷模板（spec adjustment-hall-entry-review-closure 需求 1.4）。
 *
 * 模板只给科目与方向，金额由用户填。科目按「建议编码（且名称对得上）→ 名称精确 → 名称包含」在本项目科目里匹配，
 * 匹配不到的行保留模板科目名、科目留空让用户选（原先写死的 6601 资产减值损失、5001 主营业务收入、
 * 1503 一年内到期的非流动资产与现行准则科目表不符，选了就提交失败）。
 */
import type { AccountLike, EditableLine } from './adjustmentLineRules'

export interface QuickTemplateLine {
  /** 可接受的科目名称（第一个是展示用的标准名称） */
  names: string[]
  /** 建议编码（企业会计准则科目表）；本项目同编码科目的名称须对得上才采用 */
  codes: string[]
  side: 'debit' | 'credit'
}

export interface QuickTemplate {
  key: string
  type: 'aje' | 'rje'
  label: string
  description: string
  lines: QuickTemplateLine[]
}

const L = (side: 'debit' | 'credit', names: string[], codes: string[] = []): QuickTemplateLine => ({ side, names, codes })

export const QUICK_TEMPLATES: QuickTemplate[] = [
  { key: 'bad_debt', type: 'aje', label: '计提坏账准备', description: '按预期信用损失补提坏账准备',
    lines: [L('debit', ['信用减值损失'], ['6702']), L('credit', ['坏账准备'], ['1231'])] },
  { key: 'inventory_impairment', type: 'aje', label: '计提存货跌价准备', description: '按可变现净值补提存货跌价准备',
    lines: [L('debit', ['资产减值损失'], ['6701']), L('credit', ['存货跌价准备'], ['1471'])] },
  { key: 'depreciation', type: 'aje', label: '补提固定资产折旧', description: '补提固定资产折旧',
    lines: [L('debit', ['管理费用'], ['6602']), L('credit', ['累计折旧'], ['1602'])] },
  { key: 'amortization', type: 'aje', label: '补提无形资产摊销', description: '补提无形资产摊销',
    lines: [L('debit', ['管理费用'], ['6602']), L('credit', ['累计摊销'], ['1702'])] },
  { key: 'payroll_accrual', type: 'aje', label: '补提职工薪酬', description: '补提应付职工薪酬',
    lines: [L('debit', ['管理费用'], ['6602']), L('credit', ['应付职工薪酬'], ['2211'])] },
  { key: 'revenue_cutoff', type: 'aje', label: '冲回跨期确认的收入', description: '冲回不属于本期的营业收入（截止测试）',
    lines: [L('debit', ['主营业务收入', '营业收入'], ['6001']), L('credit', ['应收账款'], ['1122'])] },
  { key: 'income_tax', type: 'aje', label: '补提所得税', description: '补提当期所得税费用',
    lines: [L('debit', ['所得税费用'], ['6801']), L('credit', ['应交税费'], ['2221'])] },
  { key: 'rcl_receivable', type: 'rje', label: '应收 / 预收余额重分类', description: '应收账款贷方余额、预收（合同负债）借方余额重分类',
    lines: [L('debit', ['应收账款'], ['1122']), L('credit', ['合同负债', '预收账款', '预收款项'], ['2205', '2203'])] },
  { key: 'rcl_payable', type: 'rje', label: '应付 / 预付余额重分类', description: '应付账款借方余额、预付账款贷方余额重分类',
    lines: [L('debit', ['预付账款', '预付款项'], ['1123']), L('credit', ['应付账款'], ['2202'])] },
  { key: 'rcl_current_loan', type: 'rje', label: '一年内到期的长期借款', description: '一年内到期的长期借款重分类至流动负债',
    lines: [L('debit', ['长期借款'], ['2501']), L('credit', ['一年内到期的非流动负债'])] },
]

function nameFits(account: AccountLike, names: string[]): boolean {
  return names.some((n) => account.name === n || account.name.includes(n))
}

/** 模板行 → 本项目科目（规则见文件头）；找不到返回 null。 */
export function matchTemplateAccount(line: QuickTemplateLine, options: AccountLike[]): AccountLike | null {
  for (const code of line.codes) {
    const hit = options.find((o) => o.code === code)
    if (hit && nameFits(hit, line.names)) return hit
  }
  for (const name of line.names) {
    const exact = options.find((o) => o.name === name)
    if (exact) return exact
  }
  const partial = options.filter((o) => nameFits(o, line.names)).sort((a, b) => a.name.length - b.name.length)
  return partial[0] || null
}

/** 套用模板：返回类型、摘要、明细行（金额留空）与匹配不到的科目名。 */
export function applyQuickTemplate(tpl: QuickTemplate, options: AccountLike[]): {
  type: 'aje' | 'rje'; description: string; lines: EditableLine[]; unmatched: string[]
} {
  const unmatched: string[] = []
  const lines = tpl.lines.map((line): EditableLine => {
    const hit = matchTemplateAccount(line, options)
    if (!hit) unmatched.push(line.names[0])
    return {
      standard_account_code: hit?.code || '',
      account_name: hit?.name || line.names[0],
      debit_amount: undefined,
      credit_amount: undefined,
      side: line.side,
    }
  })
  return { type: tpl.type, description: tpl.description, lines, unmatched }
}
