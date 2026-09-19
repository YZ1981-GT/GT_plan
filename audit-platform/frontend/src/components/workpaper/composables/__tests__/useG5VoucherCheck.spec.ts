/**
 * useG5VoucherCheck — G5-12 凭证检查 composable 单测
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useG5VoucherCheck, G5_VOUCHER_CHECK_LABELS } from '../useG5VoucherCheck'

describe('useG5VoucherCheck', () => {
  it('五项核对标签与源模板一致', () => {
    expect(G5_VOUCHER_CHECK_LABELS).toHaveLength(5)
    expect(G5_VOUCHER_CHECK_LABELS[3]).toContain('初始成本')
    expect(G5_VOUCHER_CHECK_LABELS[4]).toContain('交易对手')
  })

  it('检查比例在账面为 0 时返回 null（避免 DIV/0）', () => {
    const map = ref(new Map())
    const vc = useG5VoucherCheck({ allResponses: map as any })
    vc.addOccurrenceRow()
    vc.occurrenceRows.value[0].debitAmount = 1000
    expect(vc.checkRatios.value.find((r) => r.direction === '本期借方')?.ratio).toBeNull()
    vc.criteria.value.bookDebitOccurrence = 10000
    expect(vc.checkRatios.value.find((r) => r.direction === '本期借方')?.ratio).toBeCloseTo(0.1)
  })

  it('迁移旧版 check1..check7 扁平行', () => {
    const legacy = [
      {
        id: '1',
        summary: '分期收款',
        amount: 500,
        voucherDate: '2025-03-01',
        voucherNo: '记-10',
        check1: '✓',
        check2: '✓',
        check3: '✗',
        check4: '',
        check5: '',
        isAbnormal: '是',
      },
    ]
    const map = ref(
      new Map([['G5-12-rows', { item_id: 'G5-12-rows', remark: JSON.stringify(legacy) }]]),
    )
    const vc = useG5VoucherCheck({ allResponses: map as any })
    vc.load()
    expect(vc.occurrenceRows.value).toHaveLength(1)
    expect(vc.occurrenceRows.value[0].businessContent).toBe('分期收款')
    expect(vc.occurrenceRows.value[0].checks[0]).toBe(true)
    expect(vc.occurrenceRows.value[0].checks[2]).toBe(false)
    expect(vc.occurrenceRows.value[0].abnormal).toBe(true)
  })

  it('抽凭回填去重凭证号', () => {
    const vc = useG5VoucherCheck()
    vc.fillFromSamples('occurrence', [
      { voucherNo: 'A1', summary: '一', debitAmount: 1 },
      { voucherNo: 'A1', summary: '重复', debitAmount: 2 },
      { voucherNo: 'A2', summary: '二', creditAmount: 3 },
    ])
    expect(vc.occurrenceRows.value).toHaveLength(2)
  })

  it('从 G5-2 行汇总账面发生额', () => {
    const vc = useG5VoucherCheck()
    const r = vc.applyFromBalanceRows([
      { debtorName: '甲', debitOccurrence: 100, creditOccurrence: 20, isRelatedParty: true },
      { debtorName: '乙', debitOccurrence: 50, creditOccurrence: 0, isRelatedParty: false },
    ])
    expect(r.filled).toBe(true)
    expect(r.debit).toBe(150)
    expect(r.credit).toBe(20)
    expect(vc.criteria.value.bookDebitOccurrence).toBe(150)
    expect(vc.criteria.value.specificSample).toContain('甲')
  })

  it('异常草稿含推送标记文案', () => {
    const vc = useG5VoucherCheck()
    vc.addOccurrenceRow()
    vc.occurrenceRows.value[0].voucherNo = '记-99'
    vc.occurrenceRows.value[0].abnormal = true
    vc.occurrenceRows.value[0].remark = '初始成本错误'
    const drafts = vc.buildAbnormalAdjDrafts()
    expect(drafts).toHaveLength(1)
    expect(drafts[0].remark).toContain('来自G5-12凭证检查')
    expect(drafts[0].description).toContain('记-99')
  })
})
