import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import {
  defaultQaItems,
  emptyInterviewDetailEntity,
  enrichInterviewDetailEntity,
  migrateInterviewDetailEntities,
  pruneInterviewDetailEntities,
} from '../useF2InterviewDetailFormulas'
import { useF2InterviewDetail } from '../useF2InterviewDetail'
import type { ChecklistResponse } from '../useF2SpecialFormData'

describe('F2-72 访谈记录公式', () => {
  it('默认十一项提纲', () => {
    expect(defaultQaItems()).toHaveLength(11)
    expect(defaultQaItems()[0].key).toBe('q1')
    expect(defaultQaItems()[9].key).toBe('q10')
  })

  it('多余空份裁剪为一份', () => {
    expect(pruneInterviewDetailEntities([
      emptyInterviewDetailEntity(),
      emptyInterviewDetailEntity(2),
    ])).toHaveLength(1)
  })

  it('按回答题数计算完整度，核心题未填则待完善', () => {
    const entity = emptyInterviewDetailEntity()
    entity.supplierName = '供应商A'
    entity.interviewee = '张三'
    entity.interviewDate = '2025-06-01'
    entity.qaItems[0].answer = '自我介绍'
    entity.qaItems[1].answer = '公司概况'
    const enriched = enrichInterviewDetailEntity(entity)
    expect(enriched.answeredCount).toBe(2)
    expect(enriched.completionPct).toBeCloseTo(2 / 11)
    expect(enriched.isIncomplete).toBe(true)
  })

  it('外协、其他资金往来、关联关系及未确认声明触发风险', () => {
    const entity = emptyInterviewDetailEntity()
    entity.supplierName = 'A'
    entity.qaItems.find((item) => item.key === 'q7')!.answer = '部分外协，外协厂家为B公司'
    entity.qaItems.find((item) => item.key === 'q8')!.answer = '存在资金拆借'
    entity.qaItems.find((item) => item.key === 'q9')!.answer = '股东存在亲属关系'
    entity.declarationAck = false
    const enriched = enrichInterviewDetailEntity(entity)
    expect(enriched.riskFlags).toEqual([
      '存在外协生产',
      '存在其他资金往来',
      '可能存在关联关系',
      '真实性声明未确认',
    ])
  })

  it('迁移旧自由问答模型到十一项提纲', () => {
    const migrated = migrateInterviewDetailEntities([
      {
        id: 'old',
        supplierName: '供应商A',
        interviewDate: '2025-03-01',
        interviewee: '李四（总经理）',
        topic: '产能核实',
        auditFocus: '关注外协',
        conclusion: '未见重大异常',
        qaPairs: [
          { id: '1', question: '请介绍一下您', answer: '我是李四' },
          { id: '2', question: '公司情况', answer: '注册资本500万' },
        ],
      },
      { id: 'blank', supplierName: '' },
    ])
    expect(migrated).toHaveLength(1)
    expect(migrated[0].supplierName).toBe('供应商A')
    expect(migrated[0].qaItems).toHaveLength(11)
    expect(migrated[0].qaItems[0].answer).toBe('我是李四')
    expect(migrated[0].qaItems[1].answer).toBe('注册资本500万')
    expect(migrated[0].conclusion).toBe('未见重大异常')
    expect(migrated[0].remark).toBe('产能核实')
  })
})

describe('F2-72 composable', () => {
  function setup(initial?: unknown, extra?: Record<string, unknown>) {
    const map = new Map<string, ChecklistResponse>()
    if (initial !== undefined) {
      map.set('F2-72-entities', {
        item_id: 'F2-72-entities',
        conclusion: null,
        remark: JSON.stringify(initial),
      })
    }
    for (const [key, value] of Object.entries(extra ?? {})) {
      map.set(key, { item_id: key, conclusion: null, remark: JSON.stringify(value) })
    }
    const allResponses = ref(map)
    const iv = useF2InterviewDetail({ allResponses, isReadonly: ref(false) })
    return { allResponses, iv }
  }

  it('旧数据迁移后立即回写新问卷模型', () => {
    const { allResponses, iv } = setup([
      {
        id: '1',
        supplierName: 'A',
        interviewee: '王五',
        qaPairs: [{ id: 'x', question: 'Q1', answer: 'A1' }],
        conclusion: '无异常',
      },
    ])
    expect(iv.entities.value[0].qaItems[0].answer).toBe('A1')
    const saved = JSON.parse(allResponses.value.get('F2-72-entities')!.remark!)
    expect(saved[0].qaItems).toHaveLength(11)
  })

  it('新增空份不被自身回显裁剪', () => {
    const { iv } = setup()
    iv.addEntity()
    expect(iv.entities.value).toHaveLength(2)
    expect(iv.entities.value[1].attSlot).toBe(2)
  })

  it('联动 F2-71/70/68 回填访谈信息与题干草稿', () => {
    const { iv } = setup(undefined, {
      'F2-71-rows': [{
        id: '1',
        supplierName: '供应商A',
        interviewDate: '2025-06-10',
        interviewee: '赵六（采购）',
        reason: '第一大供应商',
        method: '实地走访',
      }],
      'F2-70-entities': [{
        id: '2',
        supplierName: '供应商A',
        legalRepresentative: '钱七',
        registeredCapital: '1000万',
        registeredAddress: '合肥市',
        businessScope: '化工原料',
        staffScale: '80人',
      }],
      'F2-68-rows': {
        currentRows: [{ id: '3', supplierName: '供应商A', purchaseAmount: 1250000 }],
        priorRows: [],
      },
    })
    expect(iv.linkage.value.knownSuppliers).toContain('供应商A')
    const id = iv.entities.value[0].id
    iv.updateEntity(id, { supplierName: '供应商A' })
    iv.applyLinkage(id)
    expect(iv.entities.value[0].interviewee).toBe('赵六（采购）')
    expect(iv.entities.value[0].interviewDate).toBe('2025-06-10')
    expect(iv.entities.value[0].qaItems.find((item) => item.key === 'q2')!.answer).toContain('F2-70')
    expect(iv.entities.value[0].qaItems.find((item) => item.key === 'q5')!.answer).toContain('1,250,000')
  })
})
