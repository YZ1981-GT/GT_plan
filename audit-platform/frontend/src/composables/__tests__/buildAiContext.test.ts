/**
 * buildAiContext 单元测试
 *
 * Feature: platform-global-hardening
 * Requirements: 9.1, 9.2
 */
import { describe, it, expect } from 'vitest'
import { buildAiContext, enrichAiContext, type AiContext } from '../buildAiContext'

describe('buildAiContext', () => {
  it('返回非空 context 对象', () => {
    const ctx = buildAiContext('D2')
    expect(ctx).not.toBeNull()
    expect(ctx).not.toBeUndefined()
    expect(ctx.wpCode).toBe('D2')
  })

  it('wpCode 正确设置', () => {
    const ctx = buildAiContext('F3A')
    expect(ctx.wpCode).toBe('F3A')
  })

  it('sheet 参数正确传递', () => {
    const ctx = buildAiContext('D2-5', '账龄分析')
    expect(ctx.sheet).toBe('账龄分析')
  })

  it('未传 sheet 时默认为空字符串', () => {
    const ctx = buildAiContext('K10')
    expect(ctx.sheet).toBe('')
  })

  it('methodology 包含循环特定方法论', () => {
    const ctxD = buildAiContext('D2')
    expect(ctxD.methodology).toContain('D2')
    expect(ctxD.methodology).toContain('应收')

    const ctxF = buildAiContext('F3')
    expect(ctxF.methodology).toContain('存货')

    const ctxK = buildAiContext('K10')
    expect(ctxK.methodology).toContain('负债')
  })

  it('methodology 含 CAS 准则引用', () => {
    const ctx = buildAiContext('D2-1')
    expect(ctx.methodology).toContain('CAS')
  })

  it('sheet 参数出现在 methodology 中', () => {
    const ctx = buildAiContext('D2', '坏账计提')
    expect(ctx.methodology).toContain('坏账计提')
  })

  it('linkedData 包含科目族信息', () => {
    const ctx = buildAiContext('G4')
    expect(ctx.linkedData.subject).toContain('投资')
    expect(ctx.linkedData.cyclePrefix).toBe('G')
    expect(ctx.linkedData.wpCode).toBe('G4')
  })

  it('对所有循环前缀都返回非空 context', () => {
    const prefixes = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'S']
    for (const p of prefixes) {
      const ctx = buildAiContext(`${p}1`)
      expect(ctx).not.toBeNull()
      expect(ctx.wpCode).toBe(`${p}1`)
      expect(ctx.methodology.length).toBeGreaterThan(0)
    }
  })

  it('返回所有约定键集', () => {
    const ctx = buildAiContext('D2', 'sheet1')
    const keys = Object.keys(ctx)
    expect(keys).toContain('wpCode')
    expect(keys).toContain('sheet')
    expect(keys).toContain('linkedData')
    expect(keys).toContain('auditedAmounts')
    expect(keys).toContain('agingData')
    expect(keys).toContain('anomalies')
    expect(keys).toContain('methodology')
    expect(keys).toContain('extra')
  })

  it('空 wpCode 也不返回 null/undefined', () => {
    const ctx = buildAiContext('')
    expect(ctx).not.toBeNull()
    expect(ctx).not.toBeUndefined()
    expect(ctx.wpCode).toBe('')
    expect(ctx.methodology.length).toBeGreaterThan(0)
  })
})

describe('enrichAiContext', () => {
  it('合并 auditedAmounts', () => {
    const base = buildAiContext('D2')
    const enriched = enrichAiContext(base, {
      auditedAmounts: { '1122': 500000, '1231': 100000 },
    })
    expect(enriched.auditedAmounts['1122']).toBe(500000)
    expect(enriched.auditedAmounts['1231']).toBe(100000)
  })

  it('合并 agingData', () => {
    const base = buildAiContext('D2')
    const enriched = enrichAiContext(base, {
      agingData: [{ band: '1年以内', amount: 300000 }],
    })
    expect(enriched.agingData).toHaveLength(1)
    expect(enriched.agingData[0]).toHaveProperty('band', '1年以内')
  })

  it('合并 anomalies', () => {
    const base = buildAiContext('D2')
    const enriched = enrichAiContext(base, {
      anomalies: ['客户A长期挂账超12月', '客户B金额异常波动'],
    })
    expect(enriched.anomalies).toHaveLength(2)
    expect(enriched.anomalies[0]).toContain('客户A')
  })

  it('不修改原始 base 对象', () => {
    const base = buildAiContext('D2')
    const originalAnomalies = [...base.anomalies]
    enrichAiContext(base, { anomalies: ['test'] })
    expect(base.anomalies).toEqual(originalAnomalies)
  })

  it('合并 extra 字段', () => {
    const base = buildAiContext('D2')
    const enriched = enrichAiContext(base, {
      extra: { customField: 'value' },
    })
    expect(enriched.extra.customField).toBe('value')
  })

  it('合并 linkedData', () => {
    const base = buildAiContext('D2')
    const enriched = enrichAiContext(base, {
      linkedData: { tbAmount: 1000000 },
    })
    expect(enriched.linkedData.tbAmount).toBe(1000000)
    // 原有字段保留
    expect(enriched.linkedData.wpCode).toBe('D2')
  })
})
