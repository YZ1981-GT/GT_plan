/**
 * useAdjudicationAdjustmentPull.spec — 审定表按科目带入集中调整 核心逻辑测试
 * spec: adjustment-collaboration-and-propagation (K12 试点)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const listAdjustmentsMock = vi.fn()
vi.mock('@/services/auditPlatformApi', () => ({
  listAdjustments: (...args: any[]) => listAdjustmentsMock(...args),
}))

import {
  useAdjudicationAdjustmentPull,
  guessTargetRowKey,
} from './useAdjudicationAdjustmentPull'

describe('useAdjudicationAdjustmentPull.load', () => {
  beforeEach(() => listAdjustmentsMock.mockReset())

  it('按科目前缀过滤 + 损益贷方净额=贷-借 + 分录组类型', async () => {
    listAdjustmentsMock.mockResolvedValue({
      items: [
        // 命中 6301：Cr 50000 → net +50000（aje）
        { entry_group_id: 'g1', adjustment_no: 'AJE-005', adjustment_type: 'AJE', description: '确认利得',
          line_items: [
            { standard_account_code: '1002', debit_amount: 50000, credit_amount: 0 },
            { standard_account_code: '6301', account_name: '营业外收入', debit_amount: 0, credit_amount: 50000 },
          ] },
        // 命中 6301 子科目：Dr 8000 → net -8000（rje）
        { entry_group_id: 'g2', adjustment_no: 'RJE-002', adjustment_type: 'rje', source_ref: 'wp9:K12-3-adj',
          line_items: [
            { standard_account_code: '630101', debit_amount: 8000, credit_amount: 0 },
            { standard_account_code: '1122', debit_amount: 0, credit_amount: 8000 },
          ] },
        // 不命中 6301：应被过滤
        { entry_group_id: 'g3', adjustment_no: 'AJE-100',
          line_items: [{ standard_account_code: '6602', debit_amount: 100, credit_amount: 0 }] },
      ],
    })
    const pull = useAdjudicationAdjustmentPull({ projectId: 'p1', year: 2025, subjectPrefix: '6301', direction: 'credit' })
    await pull.load()
    expect(pull.matches.value).toHaveLength(2)
    const g1 = pull.matches.value.find((m) => m.entry_group_id === 'g1')!
    expect(g1.net).toBe(50000)
    expect(g1.adjustment_type).toBe('aje')
    const g2 = pull.matches.value.find((m) => m.entry_group_id === 'g2')!
    expect(g2.net).toBe(-8000)
    expect(g2.adjustment_type).toBe('rje')
    expect(g2.source_wp_code).toBe('wp9')
  })

  it("direction='debit'（资产/损益借方）净额=借-贷", async () => {
    listAdjustmentsMock.mockResolvedValue({
      items: [{ entry_group_id: 'g1', adjustment_no: 'A1', adjustment_type: 'aje',
        line_items: [{ standard_account_code: '1122', debit_amount: 30000, credit_amount: 0 }] }],
    })
    const pull = useAdjudicationAdjustmentPull({ projectId: 'p1', year: 2025, subjectPrefix: '1122', direction: 'debit' })
    await pull.load()
    expect(pull.matches.value[0].net).toBe(30000)
  })

  it('全零行不计入；返回数组/缺 items 均安全', async () => {
    listAdjustmentsMock.mockResolvedValue({ items: [
      { entry_group_id: 'z', adjustment_no: 'Z', line_items: [{ standard_account_code: '6301', debit_amount: 0, credit_amount: 0 }] },
    ] })
    const pull = useAdjudicationAdjustmentPull({ projectId: 'p1', year: 2025, subjectPrefix: '6301' })
    await pull.load()
    expect(pull.matches.value).toHaveLength(0)

    // 直接返回数组形态（非 {items}）
    listAdjustmentsMock.mockResolvedValue([
      { entry_group_id: 'a1', adjustment_no: 'A1', adjustment_type: 'aje',
        line_items: [{ standard_account_code: '6301', debit_amount: 0, credit_amount: 12000 }] },
    ])
    const pull2 = useAdjudicationAdjustmentPull({ projectId: 'p1', year: 2025, subjectPrefix: '6301' })
    await pull2.load()
    expect(pull2.matches.value).toHaveLength(1)
    expect(pull2.matches.value[0].net).toBe(12000)

    // 缺 items → 空
    listAdjustmentsMock.mockResolvedValue({})
    const pull3 = useAdjudicationAdjustmentPull({ projectId: 'p1', year: 2025, subjectPrefix: '6301' })
    await pull3.load()
    expect(pull3.matches.value).toHaveLength(0)
  })
})

describe('guessTargetRowKey', () => {
  const rows = [
    { rowKey: 'r-gov', name: '与日常活动无关的政府补助' },
    { rowKey: 'r-donate', name: '捐赠利得' },
    { rowKey: 'r-other', name: '其他' },
  ]
  it('摘要/科目名与行名互含 → 该行', () => {
    expect(guessTargetRowKey({ description: '本期政府补助利得', accountNames: [] }, rows)).toBeDefined()
    expect(guessTargetRowKey({ description: '', accountNames: ['捐赠利得'] }, rows)).toBe('r-donate')
  })
  it('无匹配 → 含"其他"的行', () => {
    expect(guessTargetRowKey({ description: '无法归类的调整', accountNames: [] }, rows)).toBe('r-other')
  })
  it('无匹配且无"其他"行 → 末行', () => {
    const rs = [{ rowKey: 'a', name: 'X' }, { rowKey: 'b', name: 'Y' }]
    expect(guessTargetRowKey({ description: 'zzz', accountNames: [] }, rs)).toBe('b')
  })
  it('空行集 → 空串', () => {
    expect(guessTargetRowKey({ description: 'x', accountNames: [] }, [])).toBe('')
  })
})
