import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import {
  calcUndisclosedMatchTotal,
  emptyUndisclosedPartyRow,
  enrichUndisclosedPartyRow,
  migrateUndisclosedPartyRows,
  pruneBlankUndisclosedPartyRows,
} from '../useF2UndisclosedPartyFormulas'
import { useF2UndisclosedParty } from '../useF2UndisclosedParty'
import type { ChecklistResponse } from '../useF2SpecialFormData'

describe('F2-67 人员身份交叉核对公式', () => {
  it('默认仅保留一行', () => {
    expect(pruneBlankUndisclosedPartyRows([
      emptyUndisclosedPartyRow(),
      emptyUndisclosedPartyRow(),
    ])).toHaveLength(1)
  })

  it('汇总全部身份及部门匹配次数', () => {
    const row = emptyUndisclosedPartyRow()
    row.personalSupplier = 1
    row.contractSignee = 2
    row.financeDept = 1
    row.productionDept = 3
    expect(calcUndisclosedMatchTotal(row)).toBe(7)
  })

  it('有匹配建议Y，无匹配的已填姓名建议N', () => {
    const matched = emptyUndisclosedPartyRow()
    matched.name = '张三'
    matched.supplierLegalPerson = 1
    expect(enrichUndisclosedPartyRow(matched)).toMatchObject({
      total: 1,
      suggestedRelated: 'Y',
      isAbnormal: true,
    })

    const clear = emptyUndisclosedPartyRow()
    clear.name = '李四'
    expect(enrichUndisclosedPartyRow(clear)).toMatchObject({
      total: 0,
      suggestedRelated: 'N',
      isAbnormal: false,
    })
  })

  it('人工Y/N判断优先于系统建议', () => {
    const row = emptyUndisclosedPartyRow()
    row.name = '同名但已排除'
    row.supplierLegalPerson = 1
    row.isRelated = 'N'
    const enriched = enrichUndisclosedPartyRow(row)
    expect(enriched.suggestedRelated).toBe('Y')
    expect(enriched.isAbnormal).toBe(false)
  })

  it('迁移旧工商核查数据并裁剪空行', () => {
    const migrated = migrateUndisclosedPartyRows([
      {
        id: 'old-1',
        supplierName: '供应商甲',
        relationType: '控股股东',
        relationToClient: '实际控制人亲属',
        isDisclosed: '否',
        checkConclusion: '需进一步核查',
        indexNo: 'F2-67-1',
      },
      { id: 'blank', supplierName: '' },
    ])
    expect(migrated).toHaveLength(1)
    expect(migrated[0]).toMatchObject({
      name: '供应商甲',
      isRelated: 'Y',
      identity: '控股股东 / 实际控制人亲属',
      note: '需进一步核查',
      indexRef: 'F2-67-1',
    })
  })
})

describe('F2-67 composable', () => {
  function setup(initial?: unknown) {
    const map = new Map<string, ChecklistResponse>()
    if (initial !== undefined) {
      map.set('F2-67-rows', {
        item_id: 'F2-67-rows',
        conclusion: null,
        remark: JSON.stringify(initial),
      })
    }
    const allResponses = ref(map)
    const up = useF2UndisclosedParty({ allResponses, isReadonly: ref(false) })
    return { allResponses, up }
  }

  it('旧数据迁移后回写并只保留有效行', () => {
    const { allResponses, up } = setup([
      { id: '1', supplierName: 'A供应商', relationType: '近亲属', isDisclosed: '否' },
      { id: '2', supplierName: '' },
    ])
    expect(up.rows.value).toHaveLength(1)
    expect(up.filteredRows.value[0].isAbnormal).toBe(true)
    const saved = JSON.parse(allResponses.value.get('F2-67-rows')!.remark!)
    expect(saved[0].name).toBe('A供应商')
  })

  it('新增空行不被自身回显立即裁剪', () => {
    const { up } = setup()
    up.addRow()
    expect(up.rows.value).toHaveLength(2)
  })

  it('更新匹配列后合计和统计实时联动', () => {
    const { up } = setup()
    const id = up.rows.value[0].id
    up.updateRow(id, {
      name: '王五',
      personalSupplier: 1,
      managementDept: 1,
      annualPurchaseAmount: 942.91,
    })
    expect(up.filteredRows.value[0].total).toBe(2)
    expect(up.riskSummary.value.matched).toBe(1)
    expect(up.riskSummary.value.totalPurchaseAmount).toBe(942.91)
  })
})
