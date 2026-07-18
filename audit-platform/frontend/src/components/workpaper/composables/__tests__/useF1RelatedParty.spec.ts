/**
 * useF1RelatedParty 纯函数单测 — F1-6 13 列逻辑
 */
import { describe, it, expect } from 'vitest'
import {
  recalcRelatedPartyRow,
  normalizeRelatedPartyRow,
  mergeRelatedPartyFromImport,
  createEmptyRelatedPartyRow,
  F1_RELATED_PARTY_RELATIONSHIP_OPTIONS,
} from '../useF1RelatedParty'

describe('useF1RelatedParty helpers', () => {
  it('recalcRelatedPartyRow: end = prior + debit - credit; book = end - badDebt', () => {
    const row = recalcRelatedPartyRow({
      ...createEmptyRelatedPartyRow(),
      priorBalance: 100,
      debit: 50,
      credit: 20,
      badDebt: 10,
    })
    expect(row.endBalance).toBe(130)
    expect(row.bookValue).toBe(120)
  })

  it('normalizeRelatedPartyRow migrates legacy field aliases', () => {
    const row = normalizeRelatedPartyRow({
      customerName: '甲关联方',
      priorBalance: 200,
      debit: 30,
      credit: 10,
      badDebtProvision: 5,
      nature: '预付货款',
      postPeriodSettlement: 40,
    })
    expect(row.partyName).toBe('甲关联方')
    expect(row.endBalance).toBe(220)
    expect(row.badDebt).toBe(5)
    expect(row.bookValue).toBe(215)
    expect(row.natureDescription).toBe('预付货款')
    expect(row.postPeriodDelivery).toBe(40)
  })

  it('F1_RELATED_PARTY_RELATIONSHIP_OPTIONS includes Excel enums', () => {
    expect(F1_RELATED_PARTY_RELATIONSHIP_OPTIONS).toContain('实际控制人')
    expect(F1_RELATED_PARTY_RELATIONSHIP_OPTIONS).toContain('合营企业')
    expect(F1_RELATED_PARTY_RELATIONSHIP_OPTIONS).toContain('其他关联方')
  })

  it('mergeRelatedPartyFromImport updates same party and keeps remarks', () => {
    const existing = [
      recalcRelatedPartyRow({
        ...createEmptyRelatedPartyRow(),
        partyName: '甲',
        relationship: '子公司',
        priorBalance: 100,
        debit: 0,
        credit: 0,
        natureDescription: '已填性质',
        agingDescription: '旧账龄',
        remark: '保留备注',
      }),
    ]
    const merged = mergeRelatedPartyFromImport(existing, [
      {
        customerName: '甲',
        relationType: '母公司',
        priorAudited: 150,
        endAudited: 200,
        debit: 80,
        credit: 30,
        nature: '预付工程款',
        agingDescription: '1-2年:150',
        postPeriodSettlement: 25,
      },
      {
        customerName: '乙',
        relationType: '联营企业',
        priorAudited: 50,
        endAudited: 50,
        debit: 0,
        credit: 0,
        nature: '预付货款',
      },
    ])
    expect(merged).toHaveLength(2)
    const a = merged.find(r => r.partyName === '甲')!
    expect(a.priorBalance).toBe(150)
    expect(a.debit).toBe(80)
    expect(a.credit).toBe(30)
    expect(a.endBalance).toBe(200)
    expect(a.relationship).toBe('母公司')
    expect(a.natureDescription).toBe('预付工程款')
    expect(a.agingDescription).toBe('1-2年:150')
    expect(a.postPeriodDelivery).toBe(25)
    expect(a.remark).toBe('保留备注')
    const b = merged.find(r => r.partyName === '乙')!
    expect(b.relationship).toBe('联营企业')
    expect(b.endBalance).toBe(50)
  })
})
