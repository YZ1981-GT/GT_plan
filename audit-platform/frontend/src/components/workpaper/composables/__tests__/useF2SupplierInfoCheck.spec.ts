import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import {
  emptySupplierInfoEntity,
  enrichSupplierInfoEntity,
  isBlankSupplierInfoEntity,
  migrateSupplierInfoEntities,
  pruneSupplierInfoEntities,
  supplierInfoSummary,
} from '../useF2SupplierInfoCheckFormulas'
import { useF2SupplierInfoCheck } from '../useF2SupplierInfoCheck'
import type { ChecklistResponse } from '../useF2SpecialFormData'

describe('F2-70 供应商信息核查公式', () => {
  it('多余空列裁剪为一列', () => {
    expect(pruneSupplierInfoEntities([
      emptySupplierInfoEntity(),
      emptySupplierInfoEntity(),
    ])).toHaveLength(1)
    const filled = emptySupplierInfoEntity()
    filled.supplierName = '供应商A'
    expect(isBlankSupplierInfoEntity(filled)).toBe(false)
  })

  it('按核查项目计算信息完整度', () => {
    const entity = emptySupplierInfoEntity()
    entity.supplierName = '供应商A'
    entity.creditCode = '91110000MA00'
    entity.registeredAddress = '北京市朝阳区'
    entity.establishDate = '2015-06-01'
    entity.registeredCapital = '1000万'
    entity.legalRepresentative = '张三'
    const enriched = enrichSupplierInfoEntity(entity)
    expect(enriched.completedCount).toBe(5)
    expect(enriched.completionPct).toBeCloseTo(0.5)
  })

  it('关联方、同为客户、失信及经营状态异常触发风险提示', () => {
    const entity = emptySupplierInfoEntity()
    entity.supplierName = '供应商A'
    entity.isRelatedParty = '是'
    entity.isAlsoCustomer = '是'
    entity.isDishonest = '是'
    entity.businessStatus = '已注销'
    const enriched = enrichSupplierInfoEntity(entity)
    expect(enriched.riskFlags).toEqual(['关联方', '同为客户', '失信名单', '经营状态异常'])
    expect(enriched.isRisk).toBe(true)
    entity.isRelatedParty = '否'
    entity.isAlsoCustomer = '否'
    entity.isDishonest = '否'
    entity.businessStatus = '存续'
    expect(enrichSupplierInfoEntity(entity).isRisk).toBe(false)
  })

  it('汇总建档、信息不全与风险供应商数量', () => {
    const risky = emptySupplierInfoEntity()
    risky.supplierName = 'A'
    risky.isRelatedParty = '是'
    const blank = emptySupplierInfoEntity()
    const summary = supplierInfoSummary([risky, blank])
    expect(summary).toMatchObject({ supplierCount: 1, riskCount: 1, incompleteCount: 1 })
  })

  it('迁移旧主从档案模型字段', () => {
    const migrated = migrateSupplierInfoEntities([
      {
        id: 'old',
        supplierName: '供应商A',
        creditCode: '9111',
        legalRepresentative: '张三',
        registeredCapital: '500万',
        establishDate: '2018-01-01',
        businessScope: '钢材销售',
        operatingAddress: '上海市浦东新区',
        employeeCount: 35,
        financialStatus: '存续',
        checkMethod: '企查查',
        checkConclusion: '未见异常',
      },
      { id: 'blank', supplierName: '' },
    ])
    expect(migrated).toHaveLength(1)
    expect(migrated[0]).toMatchObject({
      supplierName: '供应商A',
      registeredAddress: '上海市浦东新区',
      staffScale: '35',
      businessStatus: '存续',
      infoSource: '企查查',
      remark: '未见异常',
    })
  })
})

describe('F2-70 composable', () => {
  function setup(initial?: unknown) {
    const map = new Map<string, ChecklistResponse>()
    if (initial !== undefined) {
      map.set('F2-70-entities', {
        item_id: 'F2-70-entities',
        conclusion: null,
        remark: JSON.stringify(initial),
      })
    }
    const allResponses = ref(map)
    const ic = useF2SupplierInfoCheck({ allResponses, isReadonly: ref(false) })
    return { allResponses, ic }
  }

  it('旧数据迁移后立即回写新模型', () => {
    const { allResponses, ic } = setup([
      { id: '1', supplierName: 'A', operatingAddress: '北京', checkMethod: '公示系统' },
    ])
    expect(ic.entities.value[0].registeredAddress).toBe('北京')
    const saved = JSON.parse(allResponses.value.get('F2-70-entities')!.remark!)
    expect(saved[0].infoSource).toBe('公示系统')
  })

  it('新增空列不被自身回显裁剪', () => {
    const { ic } = setup()
    ic.addEntity()
    expect(ic.entities.value).toHaveLength(2)
  })

  it('弹窗录入草稿一次性建档并立即持久化', () => {
    const { allResponses, ic } = setup()
    const id = ic.addEntityFrom({
      supplierName: '弹窗供应商',
      creditCode: '9134',
      isRelatedParty: '是',
    })
    expect(ic.entities.value.some((entity) => entity.id === id)).toBe(true)
    const saved = JSON.parse(allResponses.value.get('F2-70-entities')!.remark!)
    expect(saved.some((row: { supplierName: string }) => row.supplierName === '弹窗供应商')).toBe(true)
    expect(ic.summary.value.riskCount).toBe(1)
  })

  it('更新穿透核查字段后统计实时联动', () => {
    const { ic } = setup()
    const id = ic.entities.value[0].id
    ic.updateEntity(id, { supplierName: 'A', isDishonest: '是' })
    expect(ic.summary.value.riskCount).toBe(1)
    expect(ic.enrichedEntities.value[0].riskFlags).toContain('失信名单')
  })
})
