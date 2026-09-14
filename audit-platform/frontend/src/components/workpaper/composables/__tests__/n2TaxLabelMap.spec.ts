/**
 * n2TaxLabelMap.spec.ts — N2 税种归一映射表守卫
 *
 * 测试内写死 13 条字面量，不引用被测模块常量，人工锁定源模板原文。
 * spec: .kiro/specs/n2-disclosure-and-extraction-alignment/ Task 4.1
 */
import { describe, it, expect } from 'vitest'
import {
  N2_FIXED_TAX_LABELS,
  normalizeTaxLabel,
  DISCLOSURE_LABEL_BY_CLASSIFY_KEY,
  N2_TAX_LABEL_MAP,
} from '../n2TaxLabelMap'

describe('N2_FIXED_TAX_LABELS 逐字比对源模板', () => {
  // 人工写死的 13 条源模板 R8~R20 逐字 label（排序同源模板行序）
  const EXPECTED_13_LABELS = [
    '企业所得税',
    '增值税',
    '消费税',
    '资源税',
    '土地增值税',
    '城市维护建设税',
    '车船牌照税',
    '房产税',
    '土地使用税',
    '教育费附加',
    '矿产资源补偿费',
    '代扣代缴外国企业所得税',
    '代扣代缴个人所得税',
  ]

  it('应恰好有 13 行', () => {
    expect(N2_FIXED_TAX_LABELS).toHaveLength(13)
  })

  it('逐字逐行相等', () => {
    expect([...N2_FIXED_TAX_LABELS]).toEqual(EXPECTED_13_LABELS)
  })
})

describe('normalizeTaxLabel 变体名→规范名', () => {
  const cases: [string, string][] = [
    // 增值税族
    ['未交增值税', '增值税'],
    ['简易计税', '增值税'],
    ['转让金融商品应交增值税', '增值税'],
    ['代扣代缴增值税', '增值税'],
    ['应交税费-未交增值税', '增值税'],
    // 城建税
    ['城建税', '城市维护建设税'],
    ['城市维护建设', '城市维护建设税'],
    ['应交税费-城市维护建设税', '城市维护建设税'],
    // 车船税
    ['车船税', '车船牌照税'],
    ['车船使用税', '车船牌照税'],
    // 土地使用税
    ['城镇土地使用税', '土地使用税'],
    // 个人所得税 → 代扣代缴行
    ['个人所得税', '代扣代缴个人所得税'],
    // 地方教育附加 → 教育费附加
    ['地方教育附加', '教育费附加'],
    ['地方教育费附加', '教育费附加'],
    // 精确命中
    ['矿产资源补偿费', '矿产资源补偿费'],
    ['土地增值税', '土地增值税'],
    ['企业所得税', '企业所得税'],
    ['资源税', '资源税'],
    ['消费税', '消费税'],
    ['房产税', '房产税'],
    // 印花税不归一到固定行，保留原名
    ['印花税', '印花税'],
    // 空串 → 空串
    ['', ''],
    // null/undefined 类
    [' ', ''],
  ]

  it.each(cases)('"%s" → "%s"', (input, expected) => {
    expect(normalizeTaxLabel(input)).toBe(expected)
  })

  it('增值税精确命中直接返回规范名', () => {
    expect(normalizeTaxLabel('增值税')).toBe('增值税')
  })

  it('土地增值税不被增值税匹配抢走', () => {
    expect(normalizeTaxLabel('土地增值税')).toBe('土地增值税')
  })

  it('代扣代缴外国企业所得税优先于企业所得税', () => {
    expect(normalizeTaxLabel('代扣代缴外国企业所得税')).toBe('代扣代缴外国企业所得税')
  })
})

describe('DISCLOSURE_LABEL_BY_CLASSIFY_KEY 覆盖 13 个 classifyKey', () => {
  const EXPECTED_CLASSIFY_KEYS = new Set([
    'cit',
    'vat',
    'consumption',
    'resource',
    'lvt',
    'urban',
    'vehicle',
    'property',
    'land-use',
    'education',
    'mineral',
    'wh-foreign-cit',
    'wh-iit',
  ])

  it('应恰好有 13 个键', () => {
    expect(Object.keys(DISCLOSURE_LABEL_BY_CLASSIFY_KEY)).toHaveLength(13)
  })

  it('键集合与期望完全相等', () => {
    const actual = new Set(Object.keys(DISCLOSURE_LABEL_BY_CLASSIFY_KEY))
    expect(actual).toEqual(EXPECTED_CLASSIFY_KEYS)
  })

  it('每个 classifyKey 对应的 label 在 N2_FIXED_TAX_LABELS 中', () => {
    for (const label of Object.values(DISCLOSURE_LABEL_BY_CLASSIFY_KEY)) {
      expect(N2_FIXED_TAX_LABELS).toContain(label)
    }
  })

  it('N2_TAX_LABEL_MAP 所有 classifyKey 都能反查到对应 label', () => {
    for (const entry of Object.values(N2_TAX_LABEL_MAP)) {
      expect(DISCLOSURE_LABEL_BY_CLASSIFY_KEY[entry.classifyKey]).toBe(entry.disclosureLabel)
    }
  })
})
