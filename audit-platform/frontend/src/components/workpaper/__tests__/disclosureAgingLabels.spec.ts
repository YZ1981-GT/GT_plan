/**
 * 账龄标签「配置口径 → 披露口径」映射契约。
 *
 * spec: disclosure-columns-coverage-rollout R6
 * - Property 7：映射全域性与保守性
 * - Property 8：底稿显示口径不受影响（在 d2NoteSectionMap.spec.ts 侧断言）
 */
import { describe, expect, it } from 'vitest'
import {
  buildDisclosureAgingLabelMap,
  DISCLOSURE_AGING_LABELS,
  DISCLOSURE_AGING_LABEL_VALUES,
  DISCLOSURE_AGING_WITHIN1_SOE,
  DISCLOSURE_STRUCT_ROW_LABELS,
  lookupDisclosureAgingLabel,
  SOE_AGING_OVERRIDES,
  toDisclosureAgingLabel,
} from '../composables/disclosureAgingLabels'
import { D2_AGING_LABEL_OVERRIDES } from '../composables/d2NoteSectionMap'
import { F4_NOTE_AGING_LABEL } from '../composables/f4NoteSectionMap'
import { K1_NOTE_AGING_LABEL } from '../composables/k1DisclosureModel'
import { PRESET_SEGMENTS } from '@/composables/useAgingConfig'

describe('disclosureAgingLabels', () => {
  it('映射表 key 覆盖全部预设账龄段（3年段 + 5年段）', () => {
    const presetKeys = new Set(
      Object.values(PRESET_SEGMENTS).flat().map((s) => s.key),
    )
    for (const key of presetKeys) {
      expect(DISCLOSURE_AGING_LABELS[key], `预设段 ${key} 缺披露口径映射`).toBeTruthy()
    }
  })

  it('披露口径值域用「至」不用连字符（附注模板字面）', () => {
    for (const v of DISCLOSURE_AGING_LABEL_VALUES) {
      expect(v, `${v} 含连字符，仍是配置口径`).not.toMatch(/-/)
    }
    expect(DISCLOSURE_AGING_LABELS.y1to2).toBe('1至2年')
    expect(DISCLOSURE_AGING_LABELS.y2to3).toBe('2至3年')
    expect(DISCLOSURE_AGING_LABELS.y3to4).toBe('3至4年')
    expect(DISCLOSURE_AGING_LABELS.y4to5).toBe('4至5年')
    expect(DISCLOSURE_AGING_LABELS.over3).toBe('3年以上')
    expect(DISCLOSURE_AGING_LABELS.over5).toBe('5年以上')
  })

  it('Property 7 预设段按 key 映射，配置 label 被忽略', () => {
    // 5 年段预设的 label 是 `1-2年`，映射后必须是 `1至2年`
    const seg = PRESET_SEGMENTS.FIVE_YEAR.find((s) => s.key === 'y1to2')!
    expect(seg.label).toBe('1-2年')
    expect(toDisclosureAgingLabel(seg)).toBe('1至2年')
  })

  it('Property 7 overrides 优先于共享表，且只影响声明过的 key', () => {
    const overrides = { within1: '1年以内（含1年）' }
    expect(toDisclosureAgingLabel({ key: 'within1', label: '1年以内' }, overrides)).toBe('1年以内（含1年）')
    // 未声明的 key 仍取共享表
    expect(toDisclosureAgingLabel({ key: 'y2to3', label: '2-3年' }, overrides)).toBe('2至3年')
  })

  it('Property 7 自定义段原样透传（禁止杜撰）', () => {
    expect(toDisclosureAgingLabel({ key: 'm0to6', label: '6个月以内' })).toBe('6个月以内')
    expect(toDisclosureAgingLabel({ key: 'custom_x', label: '自定义分段A' })).toBe('自定义分段A')
    // 无 key 且非结构行 → 原样
    expect(toDisclosureAgingLabel({ label: '未命名' })).toBe('未命名')
  })

  it('结构行按 label 映射为附注模板字面（全角空格）', () => {
    expect(DISCLOSURE_STRUCT_ROW_LABELS['小计']).toBe('小 计')
    expect(DISCLOSURE_STRUCT_ROW_LABELS['合计']).toBe('合 计')
    expect(toDisclosureAgingLabel({ key: '__subtotal', label: '小计' })).toBe('小 计')
    expect(toDisclosureAgingLabel({ key: '__total', label: '合计' })).toBe('合 计')
    expect(toDisclosureAgingLabel({ key: '__within1_subtotal', label: '1年以内小计' })).toBe('1年以内小计：')
    // 「减：坏账准备」模板字面与底稿一致 → 原样
    expect(toDisclosureAgingLabel({ key: '__badDebt', label: '减：坏账准备' })).toBe('减：坏账准备')
  })

  it('映射表为不可变对象（防运行时被改写）', () => {
    expect(Object.isFrozen(DISCLOSURE_AGING_LABELS)).toBe(true)
    expect(Object.isFrozen(DISCLOSURE_STRUCT_ROW_LABELS)).toBe(true)
    expect(Object.isFrozen(SOE_AGING_OVERRIDES)).toBe(true)
  })

  it('「1年以内 / 1年以上」两桶口径进共享表（D3 八、38 实测行名）', () => {
    expect(DISCLOSURE_AGING_LABELS.over1).toBe('1年以上')
    expect(lookupDisclosureAgingLabel('over1')).toBe('1年以上')
    // 两桶首档在国企走 override
    expect(lookupDisclosureAgingLabel('within1', SOE_AGING_OVERRIDES)).toBe('1年以内（含1年）')
  })
})

describe('SOE_AGING_OVERRIDES 单一真源（R6.3 收敛）', () => {
  it('国企首档字面只在共享模块维护一份', () => {
    expect(DISCLOSURE_AGING_WITHIN1_SOE).toBe('1年以内（含1年）')
    expect(SOE_AGING_OVERRIDES).toEqual({ within1: DISCLOSURE_AGING_WITHIN1_SOE })
  })

  it('D2 / F4 / K1 均引用共享常量，不再各写一遍字面量', () => {
    // D2：上市无覆盖，国企引用共享常量（同一对象引用 → 不可能漂移）
    expect(D2_AGING_LABEL_OVERRIDES.listed).toEqual({})
    expect(D2_AGING_LABEL_OVERRIDES.soe).toBe(SOE_AGING_OVERRIDES)
    // F4：按账龄表仅国企（八、37）→ 首档为国企口径，其余取共享表
    expect(F4_NOTE_AGING_LABEL.within1).toBe(DISCLOSURE_AGING_WITHIN1_SOE)
    expect(F4_NOTE_AGING_LABEL.y1to2).toBe('1至2年')
    expect(F4_NOTE_AGING_LABEL.over3).toBe('3年以上')
    // K1：首档用通用口径 → 不传 overrides
    expect(K1_NOTE_AGING_LABEL.within1).toBe('1年以内')
    expect(K1_NOTE_AGING_LABEL).toEqual(buildDisclosureAgingLabelMap())
  })

  it('buildDisclosureAgingLabelMap 产出新对象（不污染共享表）', () => {
    const map = buildDisclosureAgingLabelMap(SOE_AGING_OVERRIDES)
    expect(map).not.toBe(DISCLOSURE_AGING_LABELS)
    expect(map.within1).toBe(DISCLOSURE_AGING_WITHIN1_SOE)
    expect(DISCLOSURE_AGING_LABELS.within1).toBe('1年以内')
  })
})
