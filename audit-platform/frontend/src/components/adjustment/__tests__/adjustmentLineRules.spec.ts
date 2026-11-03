/**
 * 调整分录明细行规则（spec adjustment-hall-entry-review-closure 需求 1.2）—— 与后端 entry_rule_errors 同口径。
 * 后端文案见 backend/app/services/adjustment_entry_rules.py，这里逐条对齐。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  centsText, fillDifference, isBlankLine, lineRuleErrors, lineTotals, linesForSubmit, matchAccount, parsePastedLines, toCents,
  type EditableLine,
} from '../adjustmentLineRules'

const L = (code: string, debit?: number | null, credit?: number | null, name = ''): EditableLine =>
  ({ standard_account_code: code, account_name: name, debit_amount: debit, credit_amount: credit })
const OPTIONS = [
  { code: '1122', name: '应收账款' }, { code: '1231', name: '坏账准备' }, { code: '6702', name: '信用减值损失' },
  { code: '5602', name: '管理费用' }, { code: '6602', name: '管理费用' }, { code: '2241', name: '其他应付款' },
]

describe('toCents：按分四舍五入（与后端 ROUND_HALF_UP 一致）', () => {
  it.each([
    [null, 0], [undefined, 0], ['', 0], [0, 0], [100, 10000], ['1,234.56', 123456], ['¥ 10', 1000],
    ['1.005', 101], ['1.004', 100], [0.1 + 0.2, 30], ['-3.5', -350], ['.5', 50],
  ])('%s → %s 分', (input, cents) => {
    expect(toCents(input)).toBe(cents)
  })
  it.each(['abc', '1.2.3', '一百', Number.NaN, Number.POSITIVE_INFINITY])('%s 无法识别 → NaN', (input) => {
    expect(Number.isNaN(toCents(input))).toBe(true)
  })
  it('centsText 与后端 Decimal 文案一致', () => {
    expect([centsText(123456), centsText(5), centsText(-350), centsText(0)]).toEqual(['1234.56', '0.05', '-3.50', '0.00'])
  })
})

describe('lineRuleErrors', () => {
  it('平衡且非零 ⇒ 通过；没选科目且没填金额的空行跳过', () => {
    expect(lineRuleErrors([L('6702', 100), L(''), L('1231', null, 100)])).toEqual([])
    expect(isBlankLine(L(''))).toBe(true)
    expect(isBlankLine(L('', 0, 0))).toBe(true)
    expect(isBlankLine(L('1122'))).toBe(false)
  })

  it('全是空行 ⇒ 至少需要一行明细', () => {
    expect(lineRuleErrors([L(''), L('')])).toEqual(['至少需要一行明细'])
  })

  it('逐条规则与后端同文案，行号按界面行序', () => {
    const errors = lineRuleErrors([L('', 100), L('1231', -5), L('6702', 10, 10), L('1122', 0, 0)])
    expect(errors).toEqual([
      '第 1 行未选择科目',
      '第 2 行金额不能为负数（冲减请录入到相反方向）',
      '第 3 行借方和贷方不能同时填写',
      '第 4 行借贷金额均为 0',
      '借贷不平衡：借方合计 105.00，贷方合计 10.00，差额 95.00',
    ])
  })

  it('科目名在但没匹配上科目 ⇒ 点名让用户重新选择', () => {
    expect(lineRuleErrors([L('', 1, null, '不存在的科目'), L('1231', null, 1)]))
      .toEqual(['第 1 行科目「不存在的科目」不在本项目科目中，请重新选择'])
  })

  it('浮点尾差按分比较：0.1 + 0.2 借 = 0.3 贷 平衡', () => {
    expect(lineRuleErrors([L('6702', 0.1), L('6702', 0.2), L('1231', null, 0.3)])).toEqual([])
  })

  it('后端文案逐字对齐（防一边改了另一边没改）', () => {
    const backend = readFileSync(resolve(__dirname, '../../../../../../backend/app/services/adjustment_entry_rules.py'), 'utf8')
    for (const phrase of ['未选择科目', '金额不能为负数（冲减请录入到相反方向）', '借方和贷方不能同时填写', '借贷金额均为 0',
      '至少需要一行明细', '借贷合计为 0，没有需要调整的金额', '借贷不平衡：借方合计']) {
      expect(backend, phrase).toContain(phrase)
    }
  })
})

describe('提交与辅助', () => {
  it('linesForSubmit 丢空行、金额换回元、原样带回二级科目码', () => {
    const lines = [L('6702', 100.005), L(''), { ...L('1122', null, 100.01), detail_account_code: '112201' }]
    expect(linesForSubmit(lines)).toEqual([
      { standard_account_code: '6702', account_name: undefined, debit_amount: 100.01, credit_amount: 0 },
      { standard_account_code: '1122', account_name: undefined, debit_amount: 0, credit_amount: 100.01, detail_account_code: '112201' },
    ])
  })

  it('lineTotals 以分为单位', () => {
    expect(lineTotals([L('6702', 100), L('1231', null, 60)])).toEqual({ debit: 10000, credit: 6000, diff: 4000 })
  })

  it('差额补平：填进最后一个没填金额的行，不改已填金额；没有空行就新加一行', () => {
    const filled = fillDifference([L('6702', 100), L('1231', null, 60), L('1122')])
    expect(filled[2]).toMatchObject({ standard_account_code: '1122', credit_amount: 40 })
    expect(filled[1].credit_amount).toBe(60)
    const added = fillDifference([L('6702', null, 30), L('1231', null, 20)])
    expect(added).toHaveLength(3)
    expect(added[2]).toMatchObject({ standard_account_code: '', debit_amount: 50 })
    expect(lineRuleErrors(added)).toEqual(['第 3 行未选择科目'])
  })

  it('matchAccount：编码优先，再名称精确，再名称包含中最短的', () => {
    expect(matchAccount('6602', '', OPTIONS)?.code).toBe('6602')
    expect(matchAccount('', '管理费用', OPTIONS)?.code).toBe('5602')
    expect(matchAccount('', '应付款', OPTIONS)?.code).toBe('2241')
    expect(matchAccount('9999', '不存在', OPTIONS)).toBeNull()
  })

  it('parsePastedLines：制表符分隔，金额去千分位，识别不了的留空并提示', () => {
    const text = '6702\t信用减值损失\t1,000.00\t\t补提坏账\r\n\t坏账准备\t\t1000\n\n9999\t不存在\tabc\t\n'
    const { lines, summary, problems } = parsePastedLines(text, OPTIONS)
    expect(summary).toBe('补提坏账')
    expect(lines).toEqual([
      { standard_account_code: '6702', account_name: '信用减值损失', debit_amount: 1000, credit_amount: undefined },
      { standard_account_code: '1231', account_name: '坏账准备', debit_amount: undefined, credit_amount: 1000 },
      { standard_account_code: '', account_name: '不存在', debit_amount: undefined, credit_amount: undefined },
    ])
    expect(problems).toEqual(['第 3 行科目「不存在」不在本项目科目中，请选择', '第 3 行借方「abc」无法识别，已留空'])
  })
})
