import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import {
  emptyInterviewSummaryEntity,
  enrichInterviewSummaryEntity,
  isBlankInterviewSummaryEntity,
  migrateInterviewSummaryEntities,
  nextAttSlot,
  pruneInterviewSummaryEntities,
  interviewSummarySummary,
} from '../useF2InterviewSummaryFormulas'
import { useF2InterviewSummary } from '../useF2InterviewSummary'
import type { ChecklistResponse } from '../useF2SpecialFormData'

describe('F2-71 访谈汇总公式', () => {
  it('多余空列裁剪为一列，附件槽位不参与空判断', () => {
    const blank = emptyInterviewSummaryEntity(5)
    expect(isBlankInterviewSummaryEntity(blank)).toBe(true)
    expect(pruneInterviewSummaryEntities([blank, emptyInterviewSummaryEntity(6)])).toHaveLength(1)
  })

  it('附件槽位取现有最大值加一', () => {
    const a = emptyInterviewSummaryEntity(1)
    const b = emptyInterviewSummaryEntity(4)
    expect(nextAttSlot([a, b])).toBe(5)
  })

  it('按访谈必填项计算完整度', () => {
    const entity = emptyInterviewSummaryEntity()
    entity.supplierName = 'A'
    entity.interviewDate = '2025-06-01'
    entity.reason = '第一大供应商'
    entity.method = '实地走访'
    entity.interviewee = '张三（总经理）'
    const enriched = enrichInterviewSummaryEntity(entity)
    expect(enriched.completedCount).toBe(4)
    expect(enriched.completionPct).toBeCloseTo(0.5)
  })

  it('地址不一致、金额不符、未现场函证及结论存疑触发风险', () => {
    const entity = emptyInterviewSummaryEntity()
    entity.supplierName = 'A'
    entity.registeredAddress = '北京市朝阳区XX路1号'
    entity.visitAddress = '上海市浦东新区YY路2号'
    entity.transactionAmountMatch = '否'
    entity.balanceMatch = '否'
    entity.onSiteConfirmation = '否'
    entity.conclusion = '发现异常情况'
    const enriched = enrichInterviewSummaryEntity(entity)
    expect(enriched.isAddressMismatch).toBe(true)
    expect(enriched.riskFlags).toEqual([
      '走访与注册地址不一致', '交易金额不符', '往来金额不符', '未现场函证', '结论存疑',
    ])
  })

  it('地址仅标点空格差异不视为不一致', () => {
    const entity = emptyInterviewSummaryEntity()
    entity.registeredAddress = '北京市 朝阳区XX路1号'
    entity.visitAddress = '北京市朝阳区XX路1号'
    expect(enrichInterviewSummaryEntity(entity).isAddressMismatch).toBe(false)
  })

  it('汇总访谈、待完善及风险供应商数量', () => {
    const done = emptyInterviewSummaryEntity()
    done.supplierName = 'A'
    done.interviewDate = '2025-06-01'
    done.reason = '重大'
    done.method = '实地走访'
    done.interviewee = '张三'
    done.auditors = '李四'
    done.focusPoints = '产能'
    done.conclusion = '未见异常'
    done.recordIndex = 'F2-72-1'
    const risky = emptyInterviewSummaryEntity()
    risky.supplierName = 'B'
    risky.transactionAmountMatch = '否'
    const summary = interviewSummarySummary([done, risky])
    expect(summary).toMatchObject({ supplierCount: 2, riskCount: 1, incompleteCount: 1 })
  })

  it('迁移旧9列平铺模型（受访人职务合并、摘要并入关注要点）', () => {
    const migrated = migrateInterviewSummaryEntities([
      {
        id: 'old', supplierName: '供应商A', interviewDate: '2025-01-05',
        method: '现场访谈', interviewee: '王五', intervieweeTitle: '采购总监',
        summary: '核实产能与交易', concerns: '价格偏高', conclusion: '存在疑点',
      },
      { id: 'blank', supplierName: '' },
    ])
    expect(migrated).toHaveLength(1)
    expect(migrated[0]).toMatchObject({
      supplierName: '供应商A',
      method: '实地走访',
      interviewee: '王五（采购总监）',
      focusPoints: '核实产能与交易；关注：价格偏高',
      conclusion: '存在疑点',
      attSlot: 1,
    })
  })
})

describe('F2-71 composable', () => {
  function setup(initial?: unknown, extra?: Record<string, unknown>) {
    const map = new Map<string, ChecklistResponse>()
    if (initial !== undefined) {
      map.set('F2-71-rows', {
        item_id: 'F2-71-rows',
        conclusion: null,
        remark: JSON.stringify(initial),
      })
    }
    for (const [key, value] of Object.entries(extra ?? {})) {
      map.set(key, { item_id: key, conclusion: null, remark: JSON.stringify(value) })
    }
    const allResponses = ref(map)
    const iv = useF2InterviewSummary({ allResponses, isReadonly: ref(false) })
    return { allResponses, iv }
  }

  it('旧数据迁移后立即回写新模型', () => {
    const { allResponses, iv } = setup([
      { id: '1', supplierName: 'A', summary: '产能核实', conclusion: '无异常' },
    ])
    expect(iv.entities.value[0].focusPoints).toBe('产能核实')
    const saved = JSON.parse(allResponses.value.get('F2-71-rows')!.remark!)
    expect(saved[0].attSlot).toBe(1)
  })

  it('新增空列不被自身回显裁剪且附件槽位递增', () => {
    const { iv } = setup()
    iv.addEntity()
    expect(iv.entities.value).toHaveLength(2)
    expect(iv.entities.value[1].attSlot).toBe(2)
  })

  it('联动 F2-70 注册地址与 F2-68 采购额', () => {
    const { iv } = setup(undefined, {
      'F2-70-entities': [{ id: 'x', supplierName: '供应商A', registeredAddress: '北京市海淀区' }],
      'F2-68-rows': { currentRows: [{ id: 'y', supplierName: '供应商A', purchaseAmount: 8800 }], priorRows: [] },
      'F2-72-entities': [{ id: 'z', supplierName: '供应商A' }],
    })
    expect(iv.linkage.value.registeredAddressOf('供应商A')).toBe('北京市海淀区')
    expect(iv.linkage.value.purchaseAmountOf('供应商A')).toBe(8800)
    expect(iv.linkage.value.knownSuppliers).toContain('供应商A')
    expect(iv.linkage.value.interviewDetailSuppliers).toContain('供应商A')

    const id = iv.entities.value[0].id
    iv.updateEntity(id, { supplierName: '供应商A' })
    iv.fillRegisteredAddress(id)
    expect(iv.entities.value[0].registeredAddress).toBe('北京市海淀区')
  })

  it('弹窗录入草稿自动补注册地址并持久化', () => {
    const { allResponses, iv } = setup(undefined, {
      'F2-70-entities': [{ id: 'x', supplierName: '供应商B', registeredAddress: '上海市青浦区' }],
    })
    const id = iv.addEntityFrom({ supplierName: '供应商B', method: '实地走访' })
    const created = iv.entities.value.find((entity) => entity.id === id)!
    expect(created.registeredAddress).toBe('上海市青浦区')
    const saved = JSON.parse(allResponses.value.get('F2-71-rows')!.remark!)
    expect(saved.some((row: { supplierName: string }) => row.supplierName === '供应商B')).toBe(true)
  })
})
