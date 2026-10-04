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
  // 🔴 C-7（spec g-cycle-single-region-detail-lanes）：`明细表G10-2` 按权威模板重构为
  //    19 列 A..S，`isDerivative` / `liabilityType` / `hostContractDesc` /
  //    `embeddedDerivativeJudgment` 四列的权威源是 `衍生金融工具核查表G10-8`，已从明细行移除。
  //    ⇒ 候选判定只按 B 列项目名称；已核查的确认关系走 G10-8 的链接清单。
  it('isG10DerivativeDetailRow 只按项目名称判定（权威属性在 G10-8）', () => {
    expect(isG10DerivativeDetailRow({ liabilityName: '利率互换' })).toBe(true)
    expect(isG10DerivativeDetailRow({ liabilityName: '外汇远期' })).toBe(true)
    expect(isG10DerivativeDetailRow({ liabilityName: '衍生金融负债' })).toBe(true)
    expect(isG10DerivativeDetailRow({ liabilityName: '短融' })).toBe(false)
    expect(isG10DerivativeDetailRow({ liabilityName: '债券' })).toBe(false)
  })

  it('buildG10DerivativeContractNoteFromDetails 只用 G10-2 的受管列', () => {
    const row = enrichG10DetailRow({
      rowId: 'd1',
      liabilityName: '利率互换',
      maturityDate: '2026-12-31',
      closingAdjustment: 100,
    }, 1)
    const note = buildG10DerivativeContractNoteFromDetails([row])
    expect(note).toContain('利率互换')
    expect(note).toContain('2026-12-31')
    // 主合同描述属 G10-8，不再从明细行取
    expect(note).not.toContain('贷款合同')
  })

  it('pushG10DerivativeCheckToDetail 已停用：恒 0 且不写 store（方向错）', () => {
    const responses = new Map<string, { remark?: string }>()
    const before = JSON.stringify([{ rowId: 'd1', liabilityName: '利率互换' }])
    responses.set('G10-detail-rows', { remark: before })
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
    expect(n).toBe(0)
    expect(saves).toEqual([])
    expect(responses.get('G10-detail-rows')?.remark).toBe(before)
  })

  it('filterG10DerivativeDetailRows 过滤', () => {
    const rows = [
      enrichG10DetailRow({ rowId: 'a', liabilityName: '债券' }, 1),
      enrichG10DetailRow({ rowId: 'b', liabilityName: '期权' }, 2),
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
