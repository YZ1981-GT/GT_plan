/**
 * e0RestrictedToE1.spec.ts — E0-3/E0-6 受限联动测试（Property 13/22）
 */
import { describe, it, expect } from 'vitest'
import {
  collectE03Restricted,
  collectE06Restricted,
  planE1RestrictedMerge,
  pendingE06Decisions,
  type E0RestrictedCandidate,
  type E1RestrictedRowLike,
} from '../e0RestrictedToE1'

describe('collectE03Restricted', () => {
  it('只收集受限行（O 列 ≠ 否且非空）', () => {
    const rows = [
      { '银行账号': '6001001', '开户银行': '工行', '账户余额（原币）': 100000, '是否存在冻结、担保或其他使用限制（如是，请注明）': '是', '索引号': 'CF-01' },
      { '银行账号': '6001002', '开户银行': '建行', '账户余额（原币）': 200000, '是否存在冻结、担保或其他使用限制（如是，请注明）': '否', '索引号': 'CF-02' },
      { '银行账号': '6001003', '开户银行': '招行', '账户余额（原币）': 300000, '是否存在冻结、担保或其他使用限制（如是，请注明）': '定期存单质押', '索引号': 'CF-03' },
      { '银行账号': '', '开户银行': '农行', '账户余额（原币）': 50000, '是否存在冻结、担保或其他使用限制（如是，请注明）': '是' },
    ]
    const result = collectE03Restricted(rows)
    expect(result.length).toBe(2) // 工行 + 招行（农行缺账号被跳过）
    expect(result[0].accountNo).toBe('6001001')
    expect(result[0].reason).toBe('') // 「是」无具体说明
    expect(result[1].accountNo).toBe('6001003')
    expect(result[1].reason).toBe('定期存单质押')
  })

  it('无受限行 → 空数组', () => {
    const rows = [
      { '银行账号': '6001001', '开户银行': '工行', '账户余额（原币）': 100000, '是否存在冻结、担保或其他使用限制（如是，请注明）': '否' },
    ]
    expect(collectE03Restricted(rows)).toEqual([])
  })
})

describe('collectE06Restricted', () => {
  it('只收集受限行（K 列 = 是/具体说明）', () => {
    const rows = [
      { '产品名称': '金华结构性存款A', '开户行名称及收件人': '工行', '产品净值': 1000000, '是否被用于担保或存在其他使用限制': '是', '索引号': 'CF-10' },
      { '产品名称': '金华理财B', '开户行名称及收件人': '建行', '产品净值': 500000, '是否被用于担保或存在其他使用限制': '否', '索引号': 'CF-11' },
    ]
    const result = collectE06Restricted(rows)
    expect(result.length).toBe(1)
    expect(result[0].source).toBe('E0-6')
    expect(result[0].accountNo).toBe('金华结构性存款A') // 产品名称 = accountNo
    expect(result[0].bankName).toBe('工行')
    expect(result[0].accountingTarget).toBeUndefined() // 待用户裁决
  })
})

describe('planE1RestrictedMerge', () => {
  const candidates: E0RestrictedCandidate[] = [
    { source: 'E0-3', accountNo: 'ACC-001', bankName: '工行', amount: 100000, reason: '冻结' },
    { source: 'E0-3', accountNo: 'ACC-002', bankName: '建行', amount: 200000, reason: '质押' },
    { source: 'E0-3', accountNo: 'ACC-003', bankName: '招行', amount: 300000, reason: '担保' },
  ]

  it('Property 13: E1 侧已有同账号行 SHALL NOT 被静默覆盖（进 conflicts）', () => {
    const existing: E1RestrictedRowLike[] = [
      { accountNo: 'ACC-002', amount: 180000 }, // 金额不同 → conflict
    ]
    const plan = planE1RestrictedMerge(candidates, existing)
    expect(plan.conflicts.length).toBe(1)
    expect(plan.conflicts[0].candidate.accountNo).toBe('ACC-002')
    expect(plan.conflicts[0].existing.amount).toBe(180000)
    expect(plan.additions.length).toBe(2) // ACC-001, ACC-003
  })

  it('Property 13: 无受限行 → 空 additions', () => {
    const plan = planE1RestrictedMerge([], [])
    expect(plan.additions).toEqual([])
    expect(plan.conflicts).toEqual([])
    expect(plan.skipped).toEqual([])
  })

  it('Property 13: 联动 SHALL NOT 产生任何对 E0-3 的写入（纯函数无副作用）', () => {
    const original = JSON.parse(JSON.stringify(candidates))
    planE1RestrictedMerge(candidates, [])
    expect(candidates).toEqual(original) // 输入未被修改
  })

  it('金额相同 → skipped（幂等）', () => {
    const existing: E1RestrictedRowLike[] = [
      { accountNo: 'ACC-001', amount: 100000 },
    ]
    const plan = planE1RestrictedMerge(candidates, existing)
    expect(plan.skipped.length).toBe(1)
    expect(plan.skipped[0].accountNo).toBe('ACC-001')
  })

  it('Property 22: E0-6 受限行未指定 accountingTarget → 不进任何分类', () => {
    const e06: E0RestrictedCandidate[] = [
      { source: 'E0-6', accountNo: '金华理财A', bankName: '工行', amount: 500000, reason: '质押', accountingTarget: undefined },
    ]
    const plan = planE1RestrictedMerge(e06, [])
    // 未指定落点不进 additions
    expect(plan.additions).toEqual([])
    expect(plan.conflicts).toEqual([])
    expect(plan.skipped).toEqual([])
  })

  it('Property 22: E0-6 指定 accountingTarget 后正常进 additions', () => {
    const e06: E0RestrictedCandidate[] = [
      { source: 'E0-6', accountNo: '金华理财A', bankName: '工行', amount: 500000, reason: '质押', accountingTarget: 'other_monetary' },
    ]
    const plan = planE1RestrictedMerge(e06, [])
    expect(plan.additions.length).toBe(1)
  })
})

describe('pendingE06Decisions', () => {
  it('只返回 E0-6 且 accountingTarget 未设置的行', () => {
    const candidates: E0RestrictedCandidate[] = [
      { source: 'E0-3', accountNo: 'A', bankName: '', amount: 0, reason: '' },
      { source: 'E0-6', accountNo: 'B', bankName: '', amount: 0, reason: '', accountingTarget: undefined },
      { source: 'E0-6', accountNo: 'C', bankName: '', amount: 0, reason: '', accountingTarget: 'other_monetary' },
    ]
    const pending = pendingE06Decisions(candidates)
    expect(pending.length).toBe(1)
    expect(pending[0].accountNo).toBe('B')
  })
})
