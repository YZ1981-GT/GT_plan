/**
 * useA13MisstatementBridge — normalizeMisstatementPushPayload 单元测试
 *
 * 锁定 a13:push-misstatement 四种 payload 形态的归一化行为，
 * 保证全平台 ~35 个底稿的"推送错报至A13"按钮都能正确落库。
 */
import { describe, it, expect } from 'vitest'
import { normalizeMisstatementPushPayload } from '@/composables/useA13MisstatementBridge'

describe('normalizeMisstatementPushPayload', () => {
  it('形态A：{ items: [...] } 借贷取绝对值较大者', () => {
    const drafts = normalizeMisstatementPushPayload({
      items: [
        { wpCode: 'D4', description: '收入跨期', accountName: '营业收入', debitAmount: 0, creditAmount: 5000, indexRef: 'D4-17' },
        { wpCode: 'D4', description: '多计收入', accountName: '营业收入', debitAmount: 3000, creditAmount: 0 },
      ],
    })
    expect(drafts).toHaveLength(2)
    expect(drafts[0]).toMatchObject({ wpCode: 'D4', amount: 5000, accountName: '营业收入' })
    expect(drafts[0].description).toContain('收入跨期')
    expect(drafts[0].description).toContain('D4-17')
    expect(drafts[1].amount).toBe(3000)
  })

  it('形态B：{ wpCode, accountCode, entries: [...] } 顶层科目下沉到行', () => {
    const drafts = normalizeMisstatementPushPayload({
      wpCode: 'K9',
      accountCode: '6602',
      accountName: '管理费用',
      entries: [
        { description: '费用跨期', debitAmount: 1200, creditAmount: 0, indexRef: 'K9-3' },
      ],
      ajeTotal: 1200,
      rjeTotal: 0,
    })
    expect(drafts).toHaveLength(1)
    expect(drafts[0]).toMatchObject({ wpCode: 'K9', accountCode: '6602', accountName: '管理费用', amount: 1200 })
  })

  it('形态C：{ wpCode, accountCode, source, items:[{voucherNo, amount}] } 凭证号入描述', () => {
    const drafts = normalizeMisstatementPushPayload({
      wpCode: 'I2',
      accountCode: '1301',
      source: 'I2-3',
      items: [
        { voucherNo: '记-123', amount: 8000, description: '截止跨期', indexRef: 'I2-13' },
      ],
      timestamp: Date.now(),
    })
    expect(drafts).toHaveLength(1)
    expect(drafts[0].wpCode).toBe('I2')
    expect(drafts[0].accountCode).toBe('1301')
    expect(drafts[0].amount).toBe(8000)
    expect(drafts[0].description).toContain('记-123')
    expect(drafts[0].description).toContain('I2-13')
  })

  it('形态D：扁平单行 { wpCode, accountCode, amount, description }', () => {
    const drafts = normalizeMisstatementPushPayload({
      wpCode: 'K13',
      accountCode: '6711',
      amount: 4500,
      description: '税前扣除性存疑支出',
    })
    expect(drafts).toHaveLength(1)
    expect(drafts[0]).toMatchObject({ wpCode: 'K13', accountCode: '6711', amount: 4500 })
    expect(drafts[0].description).toContain('税前扣除性存疑支出')
  })

  it('金额 ≤0 的行不生成错报（错报汇总必须有金额）', () => {
    const drafts = normalizeMisstatementPushPayload({
      items: [
        { wpCode: 'D2', description: '零额行', debitAmount: 0, creditAmount: 0 },
        { wpCode: 'D2', description: '有效行', debitAmount: 100, creditAmount: 0 },
      ],
    })
    expect(drafts).toHaveLength(1)
    expect(drafts[0].description).toContain('有效行')
  })

  it('缺描述时回退默认文案', () => {
    const drafts = normalizeMisstatementPushPayload({ wpCode: 'E1', amount: 200 })
    expect(drafts).toHaveLength(1)
    expect(drafts[0].description).toBe('底稿推送错报')
  })

  it('snake_case 别名兼容（debit_amount/wp_code/account_code）', () => {
    const drafts = normalizeMisstatementPushPayload({
      items: [{ wp_code: 'H1', account_code: '1601', description: '折旧调整', debit_amount: 700, credit_amount: 0 }],
    })
    expect(drafts[0]).toMatchObject({ wpCode: 'H1', accountCode: '1601', amount: 700 })
  })

  it('非法/空 payload 返回空数组', () => {
    expect(normalizeMisstatementPushPayload(null)).toEqual([])
    expect(normalizeMisstatementPushPayload(undefined)).toEqual([])
    expect(normalizeMisstatementPushPayload('bad' as any)).toEqual([])
    expect(normalizeMisstatementPushPayload({})).toEqual([])
  })
})
