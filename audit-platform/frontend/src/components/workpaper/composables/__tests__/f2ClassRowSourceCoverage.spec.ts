/**
 * F2 分类表取数覆盖守卫（Sprint 8 / R23~R26）
 *
 * 核心不变式：披露分类行的 `sourceKeys` 并集必须覆盖 F2-1 审定表的**全部非跌价
 * rowKey**，否则该科目的审定数在披露表没有落点 —— 分类表合计 ≠ F2-1 审定合计，
 * 附注也永远拿不到。上市侧曾漏 `dev-costs`(1409) / `dev-products`(1408) /
 * `price-difference`(1412)，房企与商业零售企业的存货审定数直接丢失。
 *
 * 无科目来源的行（数据资源 / 其他 / 土地储备）不参与该覆盖检查，
 * 但必须有替代的取值路径（联动或手工录入），本文件一并锁死。
 */
import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import { F2_ROW_KEY_ACCOUNT, F2_IMPAIRMENT_ACCOUNT } from '../f2AccountModel'
import {
  F2_LISTED_DISCLOSURE_CATEGORIES,
  useF2DisclosureListed,
} from '../useF2DisclosureListed'
import {
  F2_SOE_DISCLOSURE_CATEGORIES,
  F2_SOE_MANUAL_CLASS_ROW_KEYS,
  useF2DisclosureSoe,
} from '../useF2DisclosureSoe'
import { deriveDataResourceClassRow } from '../f2DataResourceInventory'
import type { ChecklistResponse } from '../useF2FormData'

/** 审定表全部非跌价 rowKey（跌价准备 1471 走 impairment 区块，不在分类取数里） */
const AUDIT_ROW_KEYS = Object.entries(F2_ROW_KEY_ACCOUNT)
  .filter(([, account]) => account !== F2_IMPAIRMENT_ACCOUNT)
  .map(([rowKey]) => rowKey)

/**
 * 完全无科目来源的行（`sourceKeys` 必须为空，靠联动或手工录入取值）。
 *
 * 国企「其他」不在此列：它保留 1412 商品进销差价的跨表取数，
 * 手工录入是**叠加**在取数值之上（源模板国企版有「其他」行，上市版没有 →
 * 上市把 1412 并入库存商品）。
 */
const SOURCELESS_ROW_KEYS = new Set(['data-resources', 'land-reserve'])

function unionSourceKeys(
  cats: ReadonlyArray<{ sourceKeys: readonly string[] }>,
): Set<string> {
  const out = new Set<string>()
  for (const c of cats) for (const k of c.sourceKeys) out.add(k)
  return out
}

describe('R23 分类表 sourceKeys 覆盖审定表全部科目', () => {
  it.each([
    ['listed', F2_LISTED_DISCLOSURE_CATEGORIES],
    ['soe', F2_SOE_DISCLOSURE_CATEGORIES],
  ] as const)('%s 无漏取科目', (_variant, cats) => {
    const used = unionSourceKeys(cats)
    const missing = AUDIT_ROW_KEYS.filter((k) => !used.has(k))
    expect(
      missing,
      `以下审定表科目在披露分类表没有落点 → 该科目审定数丢失、合计与 F2-1 不等：${missing.join(', ')}`,
    ).toEqual([])
  })

  it.each([
    ['listed', F2_LISTED_DISCLOSURE_CATEGORIES],
    ['soe', F2_SOE_DISCLOSURE_CATEGORIES],
  ] as const)('%s 无死键（sourceKeys 必须都是审定表真实 rowKey）', (_variant, cats) => {
    const stray = [...unionSourceKeys(cats)].filter((k) => !AUDIT_ROW_KEYS.includes(k))
    expect(stray, `死键取不到任何数，纯空转：${stray.join(', ')}`).toEqual([])
  })

  it.each([
    ['listed', F2_LISTED_DISCLOSURE_CATEGORIES],
    ['soe', F2_SOE_DISCLOSURE_CATEGORIES],
  ] as const)('%s 无科目来源的行必须显式声明空 sourceKeys', (_variant, cats) => {
    for (const c of cats as ReadonlyArray<{ rowKey: string; sourceKeys: readonly string[] }>) {
      if (SOURCELESS_ROW_KEYS.has(c.rowKey)) {
        expect(c.sourceKeys.length, `${c.rowKey} 应为空（靠联动/手工录入）`).toBe(0)
      }
    }
  })

  it('上市补齐「开发成本」「开发产品」两个种类行（源模板注要求）', () => {
    const labels = F2_LISTED_DISCLOSURE_CATEGORIES.map((c) => c.label)
    expect(labels).toEqual([
      '原材料', '在产品', '开发成本', '委托加工物资', '库存商品', '开发产品',
      '发出商品', '周转材料', '合同履约成本', '消耗性生物资产', '数据资源',
    ])
  })

  it('1412 商品进销差价并入上市「库存商品」（1406 的备抵科目）', () => {
    const fg = F2_LISTED_DISCLOSURE_CATEGORIES.find((c) => c.rowKey === 'finished-goods')
    expect(fg?.sourceKeys).toContain('price-difference')
  })
})

// ─── R25 数据资源联动 ────────────────────────────────────────────────
describe('R25 数据资源行联动', () => {
  const drValues = {
    'gross-open': { purchased: 100, selfProcessed: 200, other: 0 },
    'gross-inc': { purchased: 50, selfProcessed: 0, other: 0 },
    'gross-dec': { purchased: 20, selfProcessed: 0, other: 0 },
    'imp-open': { purchased: 10, selfProcessed: 0, other: 0 },
    'imp-inc': { purchased: 5, selfProcessed: 0, other: 0 },
    'imp-dec': { purchased: 1, selfProcessed: 0, other: 0 },
  }

  it('纯函数：期末 = 期初 + 增加 − 减少，期初取 1.期初余额', () => {
    expect(deriveDataResourceClassRow(drValues)).toEqual({
      priorGross: 300,
      endGross: 330,
      priorImpairment: 10,
      endImpairment: 14,
    })
  })

  it('表未填时返回全 0（不凭空造数）', () => {
    expect(deriveDataResourceClassRow({})).toEqual({
      endGross: 0, endImpairment: 0, priorGross: 0, priorImpairment: 0,
    })
    expect(deriveDataResourceClassRow(null)).toEqual({
      endGross: 0, endImpairment: 0, priorGross: 0, priorImpairment: 0,
    })
  })

  it.each([
    ['listed', 'F2-note-listed-s8-data-resource'],
    ['soe', 'F2-note-soe-s5-data-resource'],
  ] as const)('%s 分类表「数据资源」行随表联动，且勾稽不再假告警', (variant, itemId) => {
    const map = new Map<string, ChecklistResponse>([
      [itemId, { item_id: itemId, conclusion: null, remark: JSON.stringify(drValues) }],
    ])
    const opts = {
      allResponses: ref(map),
      isReadonly: ref(false),
      applicableStandards: ref([variant === 'listed' ? 'listed_standalone' : 'soe_standalone']),
    }
    const api = variant === 'listed' ? useF2DisclosureListed(opts) : useF2DisclosureSoe(opts)
    const row = api.section1Rows.value.find((r) => r.rowKey === 'data-resources')
    expect(row).toBeDefined()
    expect(row!.endGross).toBe(330)
    expect(row!.endImpairment).toBe(14)
    expect(row!.endNet).toBe(316)
    expect(row!.priorGross).toBe(300)
    // 联动后与数据资源表恒一致 → 勾稽差异不再常亮
    expect(api.drTieFailures.value).toEqual([])
  })
})

// ─── R26 国企手工录入 ────────────────────────────────────────────────
describe('R26 国企「其他」「土地储备」手工录入', () => {
  function soeApi(map = new Map<string, ChecklistResponse>()) {
    return useF2DisclosureSoe({
      allResponses: ref(map),
      isReadonly: ref(false),
      applicableStandards: ref(['soe_standalone']),
    })
  }

  it('白名单只含无科目来源的两行', () => {
    expect([...F2_SOE_MANUAL_CLASS_ROW_KEYS]).toEqual(['other', 'land-reserve'])
  })

  it('可录入并派生账面价值（叠加在 1412 跨表取数之上）', () => {
    const api = soeApi()
    api.updateS1Field('other', 'endGross', 5000)
    api.updateS1Field('other', 'endImpairment', 200)
    const row = api.section1Rows.value.find((r) => r.rowKey === 'other')
    expect(row!.endGross).toBe(5000)
    expect(row!.endImpairment).toBe(200)
    expect(row!.endNet).toBe(4800)
  })

  it('土地储备行 sourceKeys 为空 → 手工值即最终值', () => {
    const api = soeApi()
    api.updateS1Field('land-reserve', 'priorGross', 777)
    const row = api.section1Rows.value.find((r) => r.rowKey === 'land-reserve')
    expect(row!.priorGross).toBe(777)
    expect(row!.priorNet).toBe(777)
  })

  it('白名单外的行拒绝手工覆盖（保住 F2-1 审定表的唯一权威）', () => {
    const api = soeApi()
    api.updateS1Field('raw-combined', 'endGross', 9999)
    expect(api.section1Rows.value.find((r) => r.rowKey === 'raw-combined')!.endGross).toBe(0)
  })

  it('「其中：土地储备」录入后仍不计入合计（防双计）', () => {
    const api = soeApi()
    api.updateS1Field('other', 'endGross', 1000)
    api.updateS1Field('land-reserve', 'endGross', 400)
    // 合计只累加 kind==='normal' 行 → 400 的「其中」行不重复计入
    expect(api.section1Total.value.endGross).toBe(1000)
  })
})
