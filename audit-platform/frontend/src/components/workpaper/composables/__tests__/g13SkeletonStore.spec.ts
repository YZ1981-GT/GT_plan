import { describe, it, expect } from 'vitest'
import {
  G13_SKELETON_ROW_KEYS,
  TEMPLATE_BELONG_LABELS_G13,
  TEMPLATE_ROW_LABELS_G13,
  buildSkeletonPersistPayload,
  clearSkeletonOverride,
  countSkeletonOverrides,
  mergeSkeletonOverrides,
  parseStoredSkeleton,
  setSkeletonOverride,
  templateBelongLabelOf,
  type G13SkeletonStoredRow,
} from '../g13SkeletonStore'
import { buildG13CategorySkeleton } from '../g13CategorySkeleton'
import { G13_ADJUDICATION_ITEMS } from '../g13Constants'

/** 三条工具明细：G1 普通 / G1 指定 / G9 衍生 */
const DETAIL_ROWS = [
  {
    rowId: 'r1',
    belongAccount: 'G1',
    instrumentType: '股票',
    currentUnadjusted: 100,
    adjustment: 10,
    currentAudited: 110,
    cost: 900,
    periodFvChange: 110,
    cumulativeFvChange: 100,
    fairValue: 1000,
    amountInPl: 110,
  },
  {
    rowId: 'r2',
    belongAccount: 'G1',
    instrumentType: '指定FVTPL',
    currentUnadjusted: 40,
    adjustment: 0,
    currentAudited: 40,
    cost: 360,
    periodFvChange: 40,
    cumulativeFvChange: 40,
    fairValue: 400,
    amountInPl: 40,
  },
  {
    rowId: 'r3',
    belongAccount: 'G9',
    instrumentType: '衍生工具',
    currentUnadjusted: 20,
    adjustment: 0,
    currentAudited: 20,
    cost: 0,
    periodFvChange: 20,
    cumulativeFvChange: 20,
    fairValue: 20,
    amountInPl: 20,
  },
]

describe('G13 骨架行序与模板逐行对应', () => {
  it('10 行固定行集，行序取自 G13_ADJUDICATION_ITEMS', () => {
    expect(G13_SKELETON_ROW_KEYS.length).toBe(10)
    expect(G13_SKELETON_ROW_KEYS).toEqual(G13_ADJUDICATION_ITEMS.map((d) => d.rowKey))
    expect(TEMPLATE_ROW_LABELS_G13.length).toBe(10)
    expect(TEMPLATE_BELONG_LABELS_G13.length).toBe(10)
  })

  it('模板 A 列行名 = 前端 label 加缩进前缀（不是逐字相等）', () => {
    G13_ADJUDICATION_ITEMS.forEach((def, i) => {
      const tpl = TEMPLATE_ROW_LABELS_G13[i]
      expect(tpl.trim()).toBe(def.label)
      // indent=1 的子行在模板里带前导空格；indent=0 的顶层行不带
      if (def.indent === 0) expect(tpl).toBe(def.label)
    })
  })

  it('模板 E20 为空 ⇒ 最后一行的对应科目是空串', () => {
    expect(templateBelongLabelOf('other')).toBe('')
    expect(templateBelongLabelOf('trading_assets')).toBe('交易性金融资产')
    // 🔴 分隔符是 `/` 不是 `-`（模板逐格实测）
    expect(templateBelongLabelOf('derivative_assets')).toBe('交易性金融资产/衍生金融资产')
    expect(templateBelongLabelOf('不存在的key')).toBe('')
  })
})

describe('parseStoredSkeleton 容错', () => {
  it('空/坏 JSON/非数组一律读作空 Map，不抛', () => {
    expect(parseStoredSkeleton(null).size).toBe(0)
    expect(parseStoredSkeleton('').size).toBe(0)
    expect(parseStoredSkeleton('{不是 json').size).toBe(0)
    expect(parseStoredSkeleton('{"rowKey":"x"}').size).toBe(0)
  })

  it('过滤掉不在固定行集里的 rowKey', () => {
    const json = JSON.stringify([
      { rowKey: 'trading_assets', cost: 1, manualOverride: true },
      { rowKey: '野生行', cost: 2, manualOverride: true },
      { rowKey: '', cost: 3 },
    ])
    const m = parseStoredSkeleton(json)
    expect([...m.keys()]).toEqual(['trading_assets'])
  })
})

describe('mergeSkeletonOverrides 手工覆盖优先', () => {
  const agg = buildG13CategorySkeleton(DETAIL_ROWS)

  it('无覆盖时逐行等于汇总值，并补上模板 E 列科目名', () => {
    const merged = mergeSkeletonOverrides(agg, new Map())
    expect(merged.length).toBe(10)
    expect(merged.every((r) => r.manualOverride === false)).toBe(true)
    const trading = merged.find((r) => r.rowKey === 'trading_assets')!
    // 主行含全部 G1 工具（普通 100+10 + 指定 40）
    expect(trading.currentUnadjusted).toBe(140)
    expect(trading.belongLabel).toBe('交易性金融资产')
    const other = merged.find((r) => r.rowKey === 'other')!
    expect(other.belongLabel).toBe('')
  })

  it('🔴 有 manualOverride 的行用存库值，不被汇总冲掉', () => {
    const stored = new Map<string, G13SkeletonStoredRow>([
      ['trading_assets', { rowKey: 'trading_assets', currentUnadjusted: 777, manualOverride: true }],
    ])
    const merged = mergeSkeletonOverrides(agg, stored)
    const trading = merged.find((r) => r.rowKey === 'trading_assets')!
    expect(trading.currentUnadjusted).toBe(777)
    expect(trading.manualOverride).toBe(true)
    // 其余行不受影响
    const deriv = merged.find((r) => r.rowKey === 'derivative_assets')!
    expect(deriv.currentUnadjusted).toBe(20)
    expect(deriv.manualOverride).toBe(false)
  })

  it('🔴 覆盖后公式列按模板口径重算（D=B+C · I=F+H · J=G）', () => {
    const stored = new Map<string, G13SkeletonStoredRow>([
      [
        'trading_assets',
        {
          rowKey: 'trading_assets',
          currentUnadjusted: 500,
          adjustment: 30,
          cost: 800,
          cumulativeFvChange: 200,
          periodFvChange: 530,
          manualOverride: true,
        },
      ],
    ])
    const r = mergeSkeletonOverrides(agg, stored).find((x) => x.rowKey === 'trading_assets')!
    expect(r.currentAudited).toBe(530) // D = B + C
    expect(r.fairValue).toBe(1000) // I = F + H
    expect(r.amountInPl).toBe(530) // J = G
    expect(r.plReconciled).toBe(true) // K = (J == D)
  })

  it('覆盖行只填部分字段时，未填字段回落汇总值', () => {
    const stored = new Map<string, G13SkeletonStoredRow>([
      ['trading_assets', { rowKey: 'trading_assets', cost: 1234, manualOverride: true }],
    ])
    const r = mergeSkeletonOverrides(agg, stored).find((x) => x.rowKey === 'trading_assets')!
    expect(r.cost).toBe(1234)
    expect(r.currentUnadjusted).toBe(140) // 回落汇总
  })

  it('manualOverride=false 的存库行只供 E 列科目名，不覆盖金额', () => {
    const stored = new Map<string, G13SkeletonStoredRow>([
      [
        'trading_assets',
        { rowKey: 'trading_assets', currentUnadjusted: 999, belongLabel: '改过的科目名', manualOverride: false },
      ],
    ])
    const r = mergeSkeletonOverrides(agg, stored).find((x) => x.rowKey === 'trading_assets')!
    expect(r.currentUnadjusted).toBe(140)
    expect(r.belongLabel).toBe('改过的科目名')
  })
})

describe('落库 payload 与覆盖增删', () => {
  const agg = buildG13CategorySkeleton(DETAIL_ROWS)

  it('🔴 恒写 10 行且行序等于模板行序（缺行会让行表引擎错位）', () => {
    const payload = buildSkeletonPersistPayload(mergeSkeletonOverrides(agg, new Map()))
    expect(payload.length).toBe(10)
    expect(payload.map((r) => r.rowKey)).toEqual([...G13_SKELETON_ROW_KEYS])
    expect(payload.every((r) => r.manualOverride === false)).toBe(true)
  })

  it('setSkeletonOverride 自动置标记且不改入参', () => {
    const before = new Map<string, G13SkeletonStoredRow>()
    const after = setSkeletonOverride(before, 'trading_assets', 'cost', '88')
    expect(before.size).toBe(0)
    expect(after.get('trading_assets')).toMatchObject({ cost: 88, manualOverride: true })
    expect(countSkeletonOverrides(after)).toBe(1)
  })

  it('setSkeletonOverride 对未知 rowKey 原样返回', () => {
    const before = new Map<string, G13SkeletonStoredRow>()
    expect(setSkeletonOverride(before, '野生行', 'cost', 1)).toBe(before)
  })

  it('文本列按字符串存、数值列按数值存', () => {
    let m = new Map<string, G13SkeletonStoredRow>()
    m = setSkeletonOverride(m, 'other', 'sourceIndex', 'wp:G13-3')
    m = setSkeletonOverride(m, 'other', 'adjustment', '不是数字')
    expect(m.get('other')!.sourceIndex).toBe('wp:G13-3')
    expect(m.get('other')!.adjustment).toBe(0)
  })

  it('clearSkeletonOverride 退回汇总口径', () => {
    let m = setSkeletonOverride(new Map(), 'trading_assets', 'currentUnadjusted', 777)
    m = clearSkeletonOverride(m, 'trading_assets')
    expect(countSkeletonOverrides(m)).toBe(0)
    const r = mergeSkeletonOverrides(agg, m).find((x) => x.rowKey === 'trading_assets')!
    expect(r.currentUnadjusted).toBe(140)
    expect(r.manualOverride).toBe(false)
  })
})
