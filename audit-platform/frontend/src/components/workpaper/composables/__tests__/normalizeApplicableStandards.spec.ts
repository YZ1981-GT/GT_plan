/**
 * `normalizeApplicableStandards` 守卫（applicable-standards-frontend-wiring R2）
 *
 * 背景：DB 权威源是 `projects.applicable_standard_v2 = {entity_type, scope, stage}`，
 * 而本函数此前只认字符串 / 数组 / `{type|code|value}` → 拿到 v2 对象返回 `[]`，
 * 披露 Tab 门控恒空：
 * - D3 两版对**所有**项目显示「当前项目不适用…」→ 用户不可达
 * - 其余循环门控恒开 → 可在国企项目编辑上市 Tab，而 `sync_from_workpaper` 不按
 *   `current_standard` 定位 → 数据写进错误章节
 *
 * 🔴 SHARED_SAMPLES 与后端 `backend/tests/test_applicable_standards_derive.py`
 * 的同名常量逐条对应（Property 3：前后端同口径）。
 */
import { describe, expect, it } from 'vitest'
import { normalizeApplicableStandards } from '../useF2FormData'

/** 与后端 `derive_applicable_standards` 的 SHARED_SAMPLES 一一对应 */
const SHARED_SAMPLES: Array<[Record<string, unknown>, string[]]> = [
  [
    { entity_type: 'soe', scope: 'standalone', stage: 'normal' },
    ['soe_standalone', 'soe', 'standalone'],
  ],
  [
    { entity_type: 'listed', scope: 'consolidated', stage: 'ipo' },
    ['listed_consolidated', 'listed', 'consolidated'],
  ],
  [
    { entity_type: 'private', scope: 'standalone', stage: 'normal' },
    ['private_standalone', 'private', 'standalone'],
  ],
]

describe('normalizeApplicableStandards — v2 结构化对象（Property 3：前后端同口径）', () => {
  it.each(SHARED_SAMPLES)('%o → %o', (input, expected) => {
    expect(normalizeApplicableStandards(input)).toEqual(expected)
  })

  it('JSON 字符串形式与对象形式结果一致', () => {
    for (const [obj, expected] of SHARED_SAMPLES) {
      expect(normalizeApplicableStandards(JSON.stringify(obj))).toEqual(expected)
    }
  })

  it('stage 不入列表（只影响 S 专项循环，不决定附注版本）', () => {
    const out = normalizeApplicableStandards({
      entity_type: 'listed', scope: 'standalone', stage: 'fraud_response',
    })
    expect(out).toEqual(['listed_standalone', 'listed', 'standalone'])
    expect(out.some((s) => s.includes('fraud'))).toBe(false)
  })

  it('只有 entity_type 时不拼组合值，仍给出维度值', () => {
    expect(normalizeApplicableStandards({ entity_type: 'listed' })).toEqual(['listed'])
  })

  it('只有 scope 时同理', () => {
    expect(normalizeApplicableStandards({ scope: 'consolidated' })).toEqual(['consolidated'])
  })

  it('大写输入归一为小写（历史向导可能写大写）', () => {
    expect(normalizeApplicableStandards({ entity_type: 'SOE', scope: 'Consolidated' }))
      .toEqual(['soe_consolidated', 'soe', 'consolidated'])
  })

  it('camelCase 键也认（前端某些路径转过驼峰）', () => {
    expect(normalizeApplicableStandards({ entityType: 'soe', scope: 'standalone' }))
      .toEqual(['soe_standalone', 'soe', 'standalone'])
  })

  it('元素去重（entity 与 scope 同名的极端输入不产生重复）', () => {
    const out = normalizeApplicableStandards({ entity_type: 'soe', scope: 'soe' })
    expect(out).toEqual(['soe_soe', 'soe'])
    expect(new Set(out).size).toBe(out.length)
  })
})

describe('normalizeApplicableStandards — 既有形态零回归（Property 4）', () => {
  it.each([
    [null, []],
    [undefined, []],
    ['', []],
    ['   ', []],
    ['listed_standalone', ['listed_standalone']],
    ['soe, listed', ['soe', 'listed']],
    ['soe；listed', ['soe', 'listed']],
    [['soe_standalone'], ['soe_standalone']],
    [['soe', '', null], ['soe']],
    [[{ type: 'listed' }], ['listed']],
    [[{ code: 'soe' }], ['soe']],
    [[{ value: 'listed_consolidated' }], ['listed_consolidated']],
    [{ type: 'listed' }, ['listed']],
    [{ code: 'soe' }, ['soe']],
    [{ standards: ['soe', 'listed'] }, ['soe', 'listed']],
    [{ list: ['listed_standalone'] }, ['listed_standalone']],
    ['["soe","listed"]', ['soe', 'listed']],
    [{}, []],
    [123, []],
  ] as Array<[unknown, string[]]>)('%o → %o', (input, expected) => {
    expect(normalizeApplicableStandards(input)).toEqual(expected)
  })
})
