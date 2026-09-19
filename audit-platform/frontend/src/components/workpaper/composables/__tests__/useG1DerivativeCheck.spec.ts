import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  determineG1DerivativeId,
  createDefaultBQuestions,
  createDefaultCQuestions,
  useG1DerivativeCheck,
  G1_DERIVATIVE_ID_CHIP,
} from '../useG1DerivativeCheck'
import type { ChecklistResponse } from '../useF1FormData'

describe('determineG1DerivativeId', () => {
  it('未答完 → INCOMPLETE', () => {
    const b = createDefaultBQuestions()
    expect(determineG1DerivativeId(b, createDefaultCQuestions())).toBe('INCOMPLETE')
  })

  it('B 全部为否 → NONE（修正模板「任一否即无衍生」笔误）', () => {
    const b = createDefaultBQuestions().map((q) => ({ ...q, answer: false as boolean | null }))
    expect(determineG1DerivativeId(b, createDefaultCQuestions())).toBe('NONE')
  })

  it('B 任一为是且 C 未完成 → INCOMPLETE', () => {
    const b = createDefaultBQuestions().map((q) => ({
      ...q,
      answer: (q.id === 'b4') as boolean | null,
    }))
    expect(determineG1DerivativeId(b, createDefaultCQuestions())).toBe('INCOMPLETE')
  })

  it('B 有是 + C0=是 → EMBEDDED', () => {
    const b = createDefaultBQuestions().map((q) => ({
      ...q,
      answer: q.id === 'b1',
    }))
    const c = createDefaultCQuestions().map((q) => ({
      ...q,
      answer: true as boolean | null,
    }))
    expect(determineG1DerivativeId(b, c)).toBe('EMBEDDED')
    expect(G1_DERIVATIVE_ID_CHIP.EMBEDDED.label).toContain('嵌入')
  })

  it('B 有是 + C0=否 → STANDALONE', () => {
    const b = createDefaultBQuestions().map((q) => ({
      ...q,
      answer: q.id === 'b2',
    }))
    const c = createDefaultCQuestions().map((q) => ({
      ...q,
      answer: q.id === 'c0' ? false : true,
    }))
    expect(determineG1DerivativeId(b, c)).toBe('STANDALONE')
  })
})

describe('useG1DerivativeCheck', () => {
  it('嵌入衍生示例路径产出 EMBEDDED 结论', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>())
    const dc = useG1DerivativeCheck({
      allResponses,
      debouncedSave: (id, data) => {
        allResponses.value.set(id, {
          item_id: id,
          conclusion: data.conclusion ?? null,
          remark: data.remark ?? null,
        } as ChecklistResponse)
      },
      isReadonly: ref(false),
    })
    dc.applyEmbeddedDemo()
    expect(dc.idResult.value).toBe('EMBEDDED')
    expect(dc.showEmbeddedSection.value).toBe(true)
    expect(dc.cas22Hint.value).toBeTruthy()
    expect(allResponses.value.get('G1-14-id-result')?.remark).toBe('EMBEDDED')
  })

  it('兼容读取旧版清单行', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G1-14-rows', {
        item_id: 'G1-14-rows',
        conclusion: JSON.stringify([
          {
            id: '1',
            instrumentName: '利率互换',
            instrumentType: 'swap',
            notionalAmount: 1_000_000,
            counterparty: '银行A',
          },
        ]),
        remark: null,
      } as ChecklistResponse],
    ]))
    const dc = useG1DerivativeCheck({
      allResponses,
      debouncedSave: () => {},
      isReadonly: ref(false),
    })
    expect(dc.legacyRows.value).toHaveLength(1)
    expect(dc.legacyRows.value[0].instrumentName).toBe('利率互换')
    expect(dc.instrumentName.value).toBe('利率互换')
  })

  it('抽凭结果映射为凭证抽查行', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>())
    const dc = useG1DerivativeCheck({
      allResponses,
      debouncedSave: (id, data) => {
        allResponses.value.set(id, {
          item_id: id,
          conclusion: data.conclusion ?? null,
          remark: data.remark ?? null,
        } as ChecklistResponse)
      },
      isReadonly: ref(false),
    })
    const n = dc.applySamplingResults([
      {
        voucherNo: '记-001',
        voucherDate: '2025-12-01',
        summary: '买入国债',
        accountCode: '1501',
        accountName: '交易性金融资产',
        counterpartAccount: '1002',
        debitAmount: 1000,
        creditAmount: 0,
        checkResult: 'pass',
        abnormal: false,
      } as any,
    ], 'replace')
    expect(n).toBe(1)
    expect(dc.vouchers.value[0].voucherNo).toBe('记-001')
    expect(dc.vouchers.value[0].debitAmount).toBe(1000)
    expect(dc.vouchers.value[0].conclusion).toBe('未见异常')
  })

  it('从 G1-13 带入凭证行', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G1-13-rows', {
        item_id: 'G1-13-rows',
        conclusion: JSON.stringify([
          {
            voucherNo: '记-113',
            voucherDate: '2025-11-01',
            businessContent: 'G1-13 抽查',
            debitAccount: '1501',
            creditAccount: '1002',
            debitAmount: 500,
            creditAmount: 0,
            conclusion: '相符',
          },
        ]),
        remark: null,
      } as ChecklistResponse],
    ]))
    const dc = useG1DerivativeCheck({
      allResponses,
      debouncedSave: (id, data) => {
        allResponses.value.set(id, {
          item_id: id,
          conclusion: data.conclusion ?? null,
          remark: data.remark ?? null,
        } as ChecklistResponse)
      },
      isReadonly: ref(false),
    })
    const n = dc.syncVouchersFromG113()
    expect(n).toBe(1)
    expect(dc.vouchers.value[0].voucherNo).toBe('记-113')
    expect(dc.vouchers.value[0].businessContent).toBe('G1-13 抽查')
  })
})
