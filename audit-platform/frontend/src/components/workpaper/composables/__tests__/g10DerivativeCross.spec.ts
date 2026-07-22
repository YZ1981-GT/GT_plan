import { describe, expect, it } from 'vitest'
import {
  buildG10DerivativeContractNoteFromDetails,
  collectG10DerivativeNonCompliantIssues,
  filterG10DerivativeDetailRows,
  isFromG108,
  isG10DerivativeDetailRow,
  pushG10DerivativeCheckToDetail,
  pushG10DerivativeIssuesToAdjustment,
} from '../g10DerivativeCross'
import { enrichG10DetailRow } from '../useG10Detail'

describe('g10DerivativeCross', () => {
  it('isG10DerivativeDetailRow 识别衍生行', () => {
    expect(isG10DerivativeDetailRow({ isDerivative: true, liabilityType: '', liabilityName: '债券' })).toBe(true)
    expect(isG10DerivativeDetailRow({ isDerivative: false, liabilityType: '衍生金融负债', liabilityName: 'A' })).toBe(true)
    expect(isG10DerivativeDetailRow({ isDerivative: false, liabilityType: '债券', liabilityName: '利率互换' })).toBe(true)
    expect(isG10DerivativeDetailRow({ isDerivative: false, liabilityType: '债券', liabilityName: '短融' })).toBe(false)
  })

  it('buildG10DerivativeContractNoteFromDetails 汇总主合同', () => {
    const row = enrichG10DetailRow({
      rowId: 'd1',
      liabilityName: '利率互换',
      hostContractDesc: '贷款合同',
      closingAdjusted: 100,
    }, 1)
    const note = buildG10DerivativeContractNoteFromDetails([row])
    expect(note).toContain('利率互换')
    expect(note).toContain('贷款合同')
  })

  it('pushG10DerivativeCheckToDetail 回写嵌入衍生判断', () => {
    const responses = new Map<string, { remark?: string }>()
    responses.set('G10-detail-rows', {
      remark: JSON.stringify([{
        rowId: 'd1',
        liabilityName: '利率互换',
        isDerivative: true,
        liabilityType: '衍生金融负债',
      }]),
    })
    const saves: string[] = []
    const n = pushG10DerivativeCheckToDetail(
      responses as any,
      (id, data) => {
        saves.push(id)
        responses.set(id, data as any)
      },
      {
        links: [{ detailRowId: 'd1', liabilityName: '利率互换' }],
        wizardConclusion: '应整体 FVTPL',
        overallConclusion: '未见异常',
      },
    )
    expect(n).toBe(1)
    const rows = JSON.parse(String(responses.get('G10-detail-rows')?.remark))
    expect(rows[0].embeddedDerivativeJudgment).toContain('G10-8')
    expect(rows[0].embeddedDerivativeJudgment).toContain('FVTPL')
  })

  it('filterG10DerivativeDetailRows 过滤', () => {
    const rows = [
      enrichG10DetailRow({ rowId: 'a', liabilityName: '债券' }, 1),
      enrichG10DetailRow({ rowId: 'b', liabilityName: '期权', isDerivative: true }, 2),
    ]
    expect(filterG10DerivativeDetailRows(rows)).toHaveLength(1)
  })

  it('pushG10DerivativeIssuesToAdjustment 不合规备忘写入 G10-3', () => {
    const saves: Array<{ id: string; data: any }> = []
    const responses = new Map<string, { remark?: string }>()
    const { pushed } = pushG10DerivativeIssuesToAdjustment(
      responses as any,
      (id, data) => {
        saves.push({ id, data })
        responses.set(id, data as any)
      },
      [{
        rowId: 'q1',
        sectionNo: '2',
        sectionTitle: '嵌入衍生',
        checkItem: '拆分判断',
        riskLevel: 'high',
        auditConclusion: '应拆分',
      }],
    )
    expect(pushed).toBe(1)
    const rows = JSON.parse(String(saves.find((s) => s.id === 'G10-aje-rows')?.data.remark))
    expect(rows).toHaveLength(2)
    expect(rows[0].summary).toContain('G10-8 衍生不合规')
    expect(isFromG108(rows[0])).toBe(true)
  })
})
