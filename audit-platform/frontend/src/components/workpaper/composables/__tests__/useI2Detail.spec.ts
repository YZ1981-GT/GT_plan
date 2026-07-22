/**
 * useI2Detail — Excel 滚动勾稽 / I2-3 账项同步 单测
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  useI2Detail,
  normalizeI2DetailRow,
  rowAjeNet,
} from '../useI2Detail'

describe('recalcI2DetailRow — Excel 公式', () => {
  it('G=B+C-E-F；L=B+H；M=C+I；N=E+J；O=F+K；P=L+M-N-O；R=P-Q', () => {
    const row = normalizeI2DetailRow({
      projectName: '课题1',
      unadjOpening: 100,
      unadjIncrease: 50,
      unadjDecToIA: 20,
      unadjDecToPL: 10,
      openingAdj: 5,
      ajeIncrease: 8,
      ajeDecToIA: 3,
      ajeDecToPL: 2,
      relatedIAAuditedEnd: 120,
    })
    expect(row.unadjEnding).toBe(120) // 100+50-20-10
    expect(row.auditedOpening).toBe(105) // 100+5
    expect(row.auditedIncrease).toBe(58) // 50+8
    expect(row.auditedDecToIA).toBe(23) // 20+3
    expect(row.auditedDecToPL).toBe(12) // 10+2
    expect(row.auditedEnding).toBe(128) // 105+58-23-12
    expect(row.diffVsIA).toBe(8) // 128-120
    // 别名
    expect(row.capBeginAmount).toBe(100)
    expect(row.capIncrease).toBe(50)
    expect(row.transferToI1).toBe(23)
    expect(row.auditedEnd).toBe(128)
  })

  it('兼容旧 cap* 字段', () => {
    const row = normalizeI2DetailRow({
      projectName: '旧项目',
      capBeginAmount: 200,
      capIncrease: 80,
      transferToI1: 30,
      capDecrease: 50, // 30 转无形后剩余 20 转损益
    })
    expect(row.unadjOpening).toBe(200)
    expect(row.unadjIncrease).toBe(80)
    expect(row.unadjDecToIA).toBe(30)
    expect(row.unadjDecToPL).toBe(20)
    expect(row.unadjEnding).toBe(230)
  })
})

describe('useI2Detail syncAjeFromI23', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('按项目名匹配 I2-3 分录并写入账项列', () => {
    const allResponses = ref(new Map<string, any>([
      [
        'I2-2-rows',
        {
          remark: JSON.stringify([
            { projectName: '课题1', unadjOpening: 0 },
            { projectName: '课题2', unadjOpening: 0 },
          ]),
        },
      ],
      [
        'I2-3-rows',
        {
          remark: JSON.stringify([
            {
              description: '补记课题1资本化',
              category: '账项调整',
              accountCode: '1717',
              debitAmount: 1000,
              creditAmount: 0,
            },
            {
              description: '课题1转无形资产',
              category: '账项调整',
              accountCode: '1717',
              debitAmount: 0,
              creditAmount: 400,
            },
            {
              description: '课题2费用化转出',
              category: '账项调整',
              accountCode: '1717',
              debitAmount: 0,
              creditAmount: 200,
            },
            {
              description: '报表重分类课题1',
              category: '报表调整',
              accountCode: '1717',
              debitAmount: 50,
              creditAmount: 0,
            },
          ]),
        },
      ],
    ]))

    const api = useI2Detail({
      allResponses,
      saveResponses: vi.fn(async () => {}),
    })

    const res = api.syncAjeFromI23()
    expect(res.applied).toBeGreaterThan(0)

    const p1 = api.rows.value.find((r) => r.projectName === '课题1')!
    const p2 = api.rows.value.find((r) => r.projectName === '课题2')!
    expect(p1.ajeIncrease).toBe(1000)
    expect(p1.ajeDecToIA).toBe(400)
    expect(p2.ajeDecToPL).toBe(200)
    // 报表调整不计入
    expect(p1.ajeIncrease).not.toBe(1050)

    expect(api.ajeLinkage.value.detailAjeNet).toBe(rowAjeNet(p1) + rowAjeNet(p2))
  })

  it('合计行审定期末正确', () => {
    const allResponses = ref(new Map<string, any>([
      [
        'I2-2-rows',
        {
          remark: JSON.stringify([
            { projectName: 'A', unadjOpening: 10, unadjIncrease: 5 },
            { projectName: 'B', unadjOpening: 20, unadjIncrease: 8 },
          ]),
        },
      ],
    ]))
    const api = useI2Detail({
      allResponses,
      saveResponses: vi.fn(async () => {}),
    })
    expect(api.totalRow.value.unadjOpening).toBe(30)
    expect(api.totalRow.value.auditedEnding).toBe(43)
  })
})

describe('recalc after field update', () => {
  it('updateField 触发审定重算', () => {
    const allResponses = ref(new Map<string, any>([
      ['I2-2-rows', { remark: JSON.stringify([{ projectName: 'X', unadjOpening: 100 }]) }],
    ]))
    const api = useI2Detail({
      allResponses,
      saveResponses: vi.fn(async () => {}),
    })
    api.updateField(0, 'ajeIncrease', 25)
    expect(api.rows.value[0].auditedIncrease).toBe(25)
    expect(api.rows.value[0].auditedEnding).toBe(125)
  })
})
