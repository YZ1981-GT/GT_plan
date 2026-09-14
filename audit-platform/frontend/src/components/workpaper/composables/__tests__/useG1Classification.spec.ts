/**
 * G1-9 分类适当性检查 — 对齐 Excel 矩阵 + 明细同步契约测试
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  classifyBasisLabel,
  emptyClassificationRow,
  hasFvtplBasis,
  useG1Classification,
} from '../useG1Classification'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

describe('G1-9 classification basis', () => {
  it('交易性任一情形即具备依据', () => {
    const row = emptyClassificationRow('1', 1)
    expect(hasFvtplBasis(row)).toBe(false)
    row.tradingNearTermSale = 'yes'
    expect(hasFvtplBasis(row)).toBe(true)
    expect(classifyBasisLabel(row)).toContain('交易性')
  })

  it('债务非SPPI 与 指定消除错配', () => {
    const row = emptyClassificationRow('2', 2)
    row.debtSppiFail = 'yes'
    expect(classifyBasisLabel(row)).toContain('未通过SPPI')
    row.debtSppiFail = ''
    row.designatedMismatch = 'yes'
    expect(classifyBasisLabel(row)).toContain('初始指定')
  })

  it('其他说明也可作为依据', () => {
    const row = emptyClassificationRow('3', 3)
    row.other = '结构性存款挂钩指数'
    expect(hasFvtplBasis(row)).toBe(true)
  })
})

describe('applyFromBusinessModel', () => {
  it('将 G1-8 问卷映射到交易性三列', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G1-8-model-result', {
        item_id: 'G1-8-model-result',
        remark: 'OTHER',
        conclusion: '属于其他业务模式',
      } as ChecklistResponse],
      ['G1-8-questionnaire', {
        item_id: 'G1-8-questionnaire',
        remark: JSON.stringify([
          { id: 'q2_1', answer: true },
          { id: 'q2_2', answer: false },
          { id: 'q2_3', answer: true },
        ]),
        conclusion: null,
      } as ChecklistResponse],
      ['G1-9-rows', {
        item_id: 'G1-9-rows',
        conclusion: JSON.stringify([
          { ...emptyClassificationRow('r1', 1), investItem: '股票A', closingBookValue: 100 },
        ]),
        remark: null,
      } as ChecklistResponse],
    ]))

    const cls = useG1Classification({
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

    const n = cls.applyFromBusinessModel()
    expect(n).toBe(1)
    expect(cls.rows.value[0].tradingNearTermSale).toBe('yes')
    expect(cls.rows.value[0].tradingDerivative).toBe('yes')
    expect(cls.rows.value[0].indexRef).toBe('G1-8')
    expect(cls.rows.value[0].other).toContain('G1-8结论')
  })

  it('从 G1-10 SPPI FAIL 写入 debtSppiFail', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G1-10-rows', {
        item_id: 'G1-10-rows',
        conclusion: JSON.stringify({
          version: 2,
          bondRows: [{ investItem: '债券X', conclusion: 'FAIL' }],
          wealthStep1: [],
          wealthStep2: [],
          perpetualRows: [],
          convertibleRows: [],
          projectRows: [],
          absRows: [],
        }),
        remark: null,
      } as ChecklistResponse],
      ['G1-9-rows', {
        item_id: 'G1-9-rows',
        conclusion: JSON.stringify([
          { ...emptyClassificationRow('r1', 1), investItem: '债券X', closingBookValue: 200 },
        ]),
        remark: null,
      } as ChecklistResponse],
    ]))

    const cls = useG1Classification({
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

    const n = cls.applyFromSppi()
    expect(n).toBe(1)
    expect(cls.rows.value[0].debtSppiFail).toBe('yes')
    expect(cls.rows.value[0].other).toContain('G1-10 SPPI：FAIL')
  })
})
