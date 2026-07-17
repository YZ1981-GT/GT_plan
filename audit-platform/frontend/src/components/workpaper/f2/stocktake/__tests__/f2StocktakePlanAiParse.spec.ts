import { describe, it, expect } from 'vitest'
import { parseF2PlanAiContent } from '../f2StocktakePlanAiParse'

describe('parseF2PlanAiContent', () => {
  it('parses json fence into fields + conclusion', () => {
    const raw =
      '```json\n' +
      JSON.stringify({
        entityName: 'A公司',
        purpose: '存在性',
        scope: '本部存货',
        planConclusion: '结论适当',
      }) +
      '\n```'
    const r = parseF2PlanAiContent(raw)
    expect(r.fields.entityName).toBe('A公司')
    expect(r.fields.purpose).toBe('存在性')
    expect(r.fields.scope).toBe('本部存货')
    expect(r.conclusion).toBe('结论适当')
  })

  it('parses markdown meta lines', () => {
    const md =
      '**被审计单位**：重药控股安徽有限公司\n' +
      '**审计年度**：2025\n\n' +
      '### 一、监盘范围与目标\n' +
      '**物理地点**：主仓库、区域仓\n' +
      '**审计目标**：核实账面存货是否存在\n\n' +
      '### 八、监盘要求\n' +
      '抽盘数量不少于50%'
    const r = parseF2PlanAiContent(md)
    expect(r.fields.entityName).toContain('重药')
    expect(r.fields.auditYear).toBe('2025')
    expect(Object.keys(r.fields).length).toBeGreaterThan(2)
  })
})
