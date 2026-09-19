import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useG13Detail } from '../useG13Detail'
import {
  calcFairValueFromParts,
  isBsFvReconciled,
  isPlReconciled,
} from '../useG13FormulaEngine'
import type { ChecklistResponse } from '../useF1FormData'

describe('useG13Detail totalRow', () => {
  it('合计行 currentAudited 为明细审定数之和', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G13-detail-rows', {
        remark: JSON.stringify([
          {
            rowId: 'r1',
            seq: 1,
            instrumentName: '工具A',
            belongAccount: 'G1',
            currentUnadjusted: 500,
            adjustment: 20,
          },
          {
            rowId: 'r2',
            seq: 2,
            instrumentName: '工具B',
            belongAccount: 'G9',
            currentUnadjusted: 300,
            adjustment: 0,
          },
        ]),
      } as ChecklistResponse],
    ]))

    const detail = useG13Detail({
      allResponses,
      debouncedSave: () => {},
      isReadonly: ref(false),
    })

    expect(detail.totalRow.value.currentAudited).toBe(820)
    expect(detail.grandTotalAudited.value).toBe(820)
    expect(detail.totalRow.value.instrumentName).toBe('合计')
  })

  it('ensureBelongRow 无匹配时自动建占位行', () => {
    const saves: string[] = []
    const detail = useG13Detail({
      allResponses: ref(new Map()),
      debouncedSave: () => { saves.push('ok') },
      isReadonly: ref(false),
    })
    const row = detail.ensureBelongRow('H3')
    expect(row.belongAccount).toBe('H3')
    expect(row.instrumentName).toContain('回写占位')
    expect(detail.rows.value).toHaveLength(1)
    expect(detail.ensureBelongRow('H3').rowId).toBe(row.rowId)
  })
})

describe('useG13Detail 对应科目FV勾稽（对齐致同核对列）', () => {
  it('成本+累计=公允价值 且 计入损益=审定 → allReconciled', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G13-detail-rows', {
        remark: JSON.stringify([{
          rowId: 'r1',
          seq: 1,
          instrumentName: '股票A',
          belongAccount: 'G1',
          openingFairValue: 100,
          closingFairValue: 130,
          currentUnadjusted: 30,
          adjustment: 0,
          cost: 100,
          periodFvChange: 30,
          cumulativeFvChange: 30,
          fairValue: 130,
          amountInPl: 30,
        }]),
      } as ChecklistResponse],
    ]))

    const detail = useG13Detail({
      allResponses,
      debouncedSave: () => {},
      isReadonly: ref(false),
    })

    const row = detail.rows.value[0]
    expect(row.fvChange).toBe(30)
    expect(row.fvReconciled).toBe(true)
    expect(row.bsReconciled).toBe(true)
    expect(row.plReconciled).toBe(true)
    expect(row.allReconciled).toBe(true)
    expect(detail.hasFvMismatch.value).toBe(false)
  })

  it('成本+累计≠公允价值 → bsReconciled false', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G13-detail-rows', {
        remark: JSON.stringify([{
          rowId: 'r1',
          seq: 1,
          instrumentName: '债券B',
          belongAccount: 'G1',
          currentUnadjusted: 10,
          adjustment: 0,
          openingFairValue: 0,
          closingFairValue: 10,
          cost: 100,
          cumulativeFvChange: 20,
          fairValue: 150, // 应为 120
          amountInPl: 10,
        }]),
      } as ChecklistResponse],
    ]))

    const detail = useG13Detail({
      allResponses,
      debouncedSave: () => {},
      isReadonly: ref(false),
    })

    expect(detail.rows.value[0].bsReconciled).toBe(false)
    expect(detail.rows.value[0].allReconciled).toBe(false)
    expect(detail.mismatchSummary.value).toContain('成本+累计')
  })

  it('旧数据仅有期初/期末时不因对应科目空而误红', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G13-detail-rows', {
        remark: JSON.stringify([{
          rowId: 'r1',
          seq: 1,
          instrumentName: '旧行',
          belongAccount: 'G1',
          openingFairValue: 100,
          closingFairValue: 130,
          currentUnadjusted: 30,
          adjustment: 0,
        }]),
      } as ChecklistResponse],
    ]))

    const detail = useG13Detail({
      allResponses,
      debouncedSave: () => {},
      isReadonly: ref(false),
    })

    const row = detail.rows.value[0]
    expect(row.fvReconciled).toBe(true)
    expect(row.bsReconciled).toBe(true) // 对应科目未填，跳过
    expect(row.fairValue).toBe(130) // 展示回退期末FV
  })

  it('改成本时若公允价值仍等于旧派生值则自动重算', () => {
    const saves: string[] = []
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G13-detail-rows', {
        remark: JSON.stringify([{
          rowId: 'r1',
          seq: 1,
          instrumentName: '基金C',
          belongAccount: 'G8',
          cost: 200,
          cumulativeFvChange: 50,
          fairValue: 250,
          currentUnadjusted: 0,
          adjustment: 0,
        }]),
      } as ChecklistResponse],
    ]))

    const detail = useG13Detail({
      allResponses,
      debouncedSave: (_id, data) => { if (data.remark) saves.push(data.remark) },
      isReadonly: ref(false),
    })

    detail.updateCell('r1', 'cost', 220)
    expect(detail.rows.value[0].fairValue).toBe(270)
    expect(detail.rows.value[0].bsReconciled).toBe(true)
  })
})

describe('G13 formula — 对应科目恒等式', () => {
  it('calcFairValueFromParts / isBsFvReconciled / isPlReconciled', () => {
    expect(calcFairValueFromParts(100, 30)).toBe(130)
    expect(isBsFvReconciled(100, 30, 130)).toBe(true)
    expect(isBsFvReconciled(100, 30, 140)).toBe(false)
    expect(isPlReconciled(30, 30)).toBe(true)
    expect(isPlReconciled(30, 25)).toBe(false)
  })
})
