/**
 * N1 披露表四表直通预填 / 骨架 / 行镜像 / 二选一分支守卫。
 *
 * spec: `.kiro/specs/n1-four-table-extraction-and-disclosure-alignment/`
 * Properties: 4（手工优先且不写 0）/ 5（预填优先级单调）/ 6（亏损到期 6 行）
 *             7（行镜像幂等保值）/ 8（分支推送与清理互补）
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import fc from 'fast-check'

import {
  N1_ASSET_ITEMS,
  N1_LIABILITY_ITEMS,
  N1_LIABILITY_SLOTS,
  N1_LIABILITY_SLOT_DEFS,
  N1_LIABILITY_SLOT_LABEL,
  defaultLossExpiryRows,
  mirrorNetOffsetRows,
  n1LiabilitySlotOf,
  useN1DisclosureTables,
  type N1PrefillMap,
  type NetOffsetRowModel,
  type UnoffsetRowModel,
} from '../useN1DisclosureTables'
import {
  N1_SUB_TABLE_KEYS,
  buildN1SyncPayload,
  n1BranchTableKeys,
  resolveN1BranchTables,
  type N1DisclosureSnapshot,
  type N1DisclosureVariant,
} from '../n1NoteSectionMap'

// ─── helpers ─────────────────────────────────────────────────────────────────

type Resp = { conclusion?: string | null; remark?: string | null }

function setup(opts: {
  variant?: N1DisclosureVariant
  responses?: Array<[string, Resp]>
  assetPrefill?: N1PrefillMap
  liabilityPrefill?: N1PrefillMap
  auditYear?: number
} = {}) {
  const variant = opts.variant ?? 'listed'
  const allResponses = ref(new Map<string, Resp>(opts.responses ?? []))
  const tables = useN1DisclosureTables({
    variant,
    allResponses,
    auditYear: ref(opts.auditYear ?? 2025),
    adjudicationPrefill: ref(opts.assetPrefill ?? {}),
    liabilityPrefill: ref(opts.liabilityPrefill ?? {}),
  })
  tables.restore()
  return { tables, allResponses, variant }
}

const ASSET_PREFILL: N1PrefillMap = {
  资产减值准备: { opening: 3983376.55, closing: 4100000 },
  可抵扣亏损: { opening: 1172298.25, closing: 1200000 },
}

const LIAB_PREFILL: N1PrefillMap = {
  lease: { opening: 528013.88, closing: 233512.19 },
  depreciation: { opening: 0, closing: 90000 },
}

// ─── 语义槽单一真源 ──────────────────────────────────────────────────────────

describe('负债段语义槽（单一真源）', () => {
  it('槽序 = 源模板 R23:R27 行序，与后端 _N1_LIABILITY_SLOTS 一致', () => {
    expect([...N1_LIABILITY_SLOTS]).toEqual([
      'depreciation',
      'afs_fv',
      'investment_property_fv',
      'lease',
      'other',
    ])
  })

  it('行骨架由槽定义派生（无行名双真源）', () => {
    expect(N1_LIABILITY_ITEMS.listed).toEqual(N1_LIABILITY_SLOT_DEFS.map((d) => d.listed))
    expect(N1_LIABILITY_ITEMS.soe).toEqual(N1_LIABILITY_SLOT_DEFS.map((d) => d.soe))
  })

  it('第 4 项两版用语必须不同（上市使用权资产 / 国企租赁形成）', () => {
    expect(N1_LIABILITY_SLOT_LABEL.lease.listed).toBe('使用权资产')
    expect(N1_LIABILITY_SLOT_LABEL.lease.soe).toBe('租赁形成')
    expect(N1_LIABILITY_ITEMS.listed[3]).not.toBe(N1_LIABILITY_ITEMS.soe[3])
  })

  it('反查按变体生效，未命中返回 undefined（不猜）', () => {
    expect(n1LiabilitySlotOf('listed', '使用权资产')).toBe('lease')
    expect(n1LiabilitySlotOf('soe', '租赁形成')).toBe('lease')
    // 交叉用语不得互认，否则两版行名会串味
    expect(n1LiabilitySlotOf('soe', '使用权资产')).toBeUndefined()
    expect(n1LiabilitySlotOf('listed', '租赁形成')).toBeUndefined()
    expect(n1LiabilitySlotOf('listed', '不存在的行')).toBeUndefined()
  })

  it('资产段 7 项逐字等于源模板 R13:R19（与后端 7 类同构）', () => {
    expect([...N1_ASSET_ITEMS]).toEqual([
      '资产减值准备',
      '可抵扣亏损',
      '内部交易未实现利润',
      '公允价值变动',
      '租赁负债',
      '购入摊销年限小于税法规定的资产',
      '其他',
    ])
  })
})

// ─── Property 4 / 5: 预填 ────────────────────────────────────────────────────

describe('Property 4/5 — 四表直通预填', () => {
  it('资产段按行名从 adjudication_prefill 带出期初/期末递延所得税资产', () => {
    const { tables } = setup({ assetPrefill: ASSET_PREFILL })
    const row = tables.assetRows.value.find((r) => r.item === '资产减值准备')!
    expect(row.endTax).toBe(4100000)
    expect(row.priorTax).toBe(3983376.55)
  })

  it('暂时性差异列保持 null（四表推不出税率 → 宁缺勿造）', () => {
    const { tables } = setup({ assetPrefill: ASSET_PREFILL })
    const row = tables.assetRows.value.find((r) => r.item === '资产减值准备')!
    expect(row.endDiff).toBeNull()
    expect(row.priorDiff).toBeNull()
  })

  it('预填值为 0 时写 null 不写 0（0 会被误读为「已核实为零」）', () => {
    const { tables } = setup({ liabilityPrefill: LIAB_PREFILL })
    const row = tables.liabilityRows.value.find((r) => r.item === '购入摊销年限大于税法规定的资产')!
    expect(row.priorTax).toBeNull() // opening = 0
    expect(row.endTax).toBe(90000)
  })

  it('负债段按语义槽映射到本变体行名', () => {
    const listed = setup({ variant: 'listed', liabilityPrefill: LIAB_PREFILL })
    expect(listed.tables.liabilityRows.value.find((r) => r.item === '使用权资产')!.endTax).toBe(
      233512.19,
    )
    const soe = setup({ variant: 'soe', liabilityPrefill: LIAB_PREFILL })
    expect(soe.tables.liabilityRows.value.find((r) => r.item === '租赁形成')!.endTax).toBe(
      233512.19,
    )
  })

  it('已持久化（手工录入）时不被四表覆盖', () => {
    const saved = JSON.stringify({
      asset: [{ item: '资产减值准备', endDiff: 1, endTax: 2, priorDiff: 3, priorTax: 4 }],
      liability: [{ item: '使用权资产', endDiff: 5, endTax: 6, priorDiff: 7, priorTax: 8 }],
    })
    const { tables } = setup({
      responses: [['N1-disclosure-listed-unoffset', { conclusion: saved }]],
      assetPrefill: ASSET_PREFILL,
      liabilityPrefill: LIAB_PREFILL,
    })
    expect(tables.assetRows.value[0].endTax).toBe(2)
    expect(tables.liabilityRows.value[0].endTax).toBe(6)
  })

  it('N1-2 明细优先于四表（明细含暂时性差异，信息更全）', () => {
    const detail = JSON.stringify([
      {
        itemName: '坏账准备',
        category: '资产减值准备',
        endDiff: 8000000,
        endTaxRate: 0.25,
        beginDiff: 4000000,
        beginTaxRate: 0.25,
      },
    ])
    const { tables } = setup({
      responses: [['N1-2-detail-rows', { conclusion: detail }]],
      assetPrefill: ASSET_PREFILL,
    })
    const row = tables.assetRows.value.find((r) => r.item === '资产减值准备')!
    // N1-2 派生 = 8,000,000 × 25% = 2,000,000（不是四表的 4,100,000）
    expect(row.endTax).toBe(2000000)
    expect(row.endDiff).toBe(8000000)
  })

  it('无预填时全空骨架（不写 0）', () => {
    const { tables } = setup()
    for (const r of [...tables.assetRows.value, ...tables.liabilityRows.value]) {
      expect([r.endDiff, r.endTax, r.priorDiff, r.priorTax]).toEqual([null, null, null, null])
    }
  })

  it('Property 4（PBT）：任意预填下，已有值的行恒不被改写', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (existing, incoming) => {
          const saved = JSON.stringify({
            asset: [
              { item: '资产减值准备', endDiff: null, endTax: existing, priorDiff: null, priorTax: null },
            ],
          })
          const { tables } = setup({
            responses: [['N1-disclosure-listed-unoffset', { conclusion: saved }]],
            assetPrefill: { 资产减值准备: { opening: incoming, closing: incoming } },
          })
          expect(tables.assetRows.value[0].endTax).toBe(existing)
        },
      ),
      { numRuns: 25 },
    )
  })
})

// ─── Property 6: 亏损到期骨架 ────────────────────────────────────────────────

describe('Property 6 — 亏损到期骨架 6 行', () => {
  it('auditYear .. auditYear+5（源模板 R46:R51 的 6 行设计）', () => {
    expect(defaultLossExpiryRows(2025).map((r) => r.item)).toEqual([
      '2025年',
      '2026年',
      '2027年',
      '2028年',
      '2029年',
      '2030年',
    ])
  })

  it('PBT：任意年度恒 6 行且连续、金额全空', () => {
    fc.assert(
      fc.property(fc.integer({ min: 1990, max: 2200 }), (y) => {
        const rows = defaultLossExpiryRows(y)
        expect(rows).toHaveLength(6)
        expect(rows.map((r) => r.item)).toEqual(
          Array.from({ length: 6 }, (_, i) => `${y + i}年`),
        )
        expect(rows.every((r) => r.end === null && r.prior === null)).toBe(true)
      }),
      { numRuns: 30 },
    )
  })

  it('composable 初始化即产出 6 行', () => {
    const { tables } = setup({ auditYear: 2025 })
    expect(tables.lossExpiryRows.value.filter((r) => /^\d{4}年$/.test(r.item))).toHaveLength(6)
  })
})

// ─── Property 7: 行镜像 ─────────────────────────────────────────────────────

describe('Property 7 — 国企表(2)A 行标签镜像表(1)', () => {
  const mk = (item: string): UnoffsetRowModel => ({
    item,
    endDiff: null,
    endTax: null,
    priorDiff: null,
    priorTax: null,
  })
  const mkNet = (item: string, netEnd: number | null): NetOffsetRowModel => ({
    item,
    netEnd,
    diffEnd: null,
    netPrior: null,
    diffPrior: null,
  })

  it('输出标签恒等于 src', () => {
    const out = mirrorNetOffsetRows([mk('A'), mk('B')], [mkNet('X', 1)])
    expect(out.map((r) => r.item)).toEqual(['A', 'B'])
  })

  it('同标签行金额被保留（行增删时不丢已录数据）', () => {
    const out = mirrorNetOffsetRows(
      [mk('A'), mk('新增'), mk('B')],
      [mkNet('A', 100), mkNet('B', 200)],
    )
    expect(out.map((r) => r.netEnd)).toEqual([100, null, 200])
  })

  it('幂等：重复调用结果不变', () => {
    const src = [mk('A'), mk('B')]
    const once = mirrorNetOffsetRows(src, [mkNet('A', 5)])
    const twice = mirrorNetOffsetRows(src, once)
    expect(twice).toEqual(once)
  })

  it('PBT：行数恒等于 src、标签恒等于 src', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 6 }), { maxLength: 8 }),
        fc.array(fc.string({ minLength: 1, maxLength: 6 }), { maxLength: 8 }),
        (a, b) => {
          const out = mirrorNetOffsetRows(a.map(mk), b.map((x) => mkNet(x, 1)))
          expect(out).toHaveLength(a.length)
          expect(out.map((r) => r.item)).toEqual(a)
        },
      ),
      { numRuns: 30 },
    )
  })

  it('国企 composable 初始化时表(2)A 行集镜像表(1)', () => {
    const { tables } = setup({ variant: 'soe' })
    expect(tables.netOffsetAssetRows.value.map((r) => r.item)).toEqual([...N1_ASSET_ITEMS])
    expect(tables.netOffsetLiabilityRows.value.map((r) => r.item)).toEqual([
      ...N1_LIABILITY_ITEMS.soe,
    ])
  })
})

// ─── Property 8: 分支推送与清理互补 ─────────────────────────────────────────

describe('Property 8 — 披露分支推送与 _removed_table_keys 互补', () => {
  const CTX = { wpId: 'wp-1', year: 2025 }

  function snap(over: Partial<N1DisclosureSnapshot> = {}): N1DisclosureSnapshot {
    return {
      assetRows: [],
      liabilityRows: [],
      unrecognizedRows: [],
      lossExpiryRows: [],
      netOffsetAssetRows: [],
      netOffsetLiabilityRows: [],
      offsetDetailRows: [],
      ...over,
    }
  }

  it('pushed 与 removed 恒无交集，并集覆盖全部分支表', () => {
    const cases: Array<[N1DisclosureVariant, Partial<N1DisclosureSnapshot>]> = [
      ['listed', {}],
      ['listed', { netOffsetApplicable: true }],
      ['listed', { netOffsetApplicable: false }],
      ['soe', {}],
      ['soe', { offsetMode: 'undecided' }],
      ['soe', { offsetMode: 'gross' }],
      ['soe', { offsetMode: 'net' }],
    ]
    for (const [variant, over] of cases) {
      const { pushed, removed } = resolveN1BranchTables(variant, over)
      expect(pushed.filter((k) => removed.includes(k))).toEqual([])
      expect(new Set([...pushed, ...removed])).toEqual(new Set(n1BranchTableKeys(variant)))
    }
  })

  it('未判断（缺省）时全推、不删任何表 —— 零回归', () => {
    const p = buildN1SyncPayload('soe', snap(), CTX)
    const K = N1_SUB_TABLE_KEYS.soe
    expect(p.sub_table_data).toHaveProperty(K.unoffset)
    expect(p.sub_table_data).toHaveProperty(K.netOffset)
    expect(p.sub_table_data).toHaveProperty(K.offsetDetail)
    expect(p.sub_table_data._removed_table_keys).toBeUndefined()

    const l = buildN1SyncPayload('listed', snap(), CTX)
    expect(l.sub_table_data).toHaveProperty(N1_SUB_TABLE_KEYS.listed.netOffset)
    expect(l.sub_table_data._removed_table_keys).toBeUndefined()
  })

  it('国企 gross：只推（1），（2）A/（2）B 跳过', () => {
    const p = buildN1SyncPayload('soe', snap({ offsetMode: 'gross' }), CTX)
    const K = N1_SUB_TABLE_KEYS.soe
    expect(p.sub_table_data).toHaveProperty(K.unoffset)
    expect(p.sub_table_data).not.toHaveProperty(K.netOffset)
    expect(p.sub_table_data).not.toHaveProperty(K.offsetDetail)
  })

  it('国企 net：只推（2）A/（2）B，（1）跳过（源模板 R7）', () => {
    const p = buildN1SyncPayload('soe', snap({ offsetMode: 'net' }), CTX)
    const K = N1_SUB_TABLE_KEYS.soe
    expect(p.sub_table_data).not.toHaveProperty(K.unoffset)
    expect(p.sub_table_data).toHaveProperty(K.netOffset)
    expect(p.sub_table_data).toHaveProperty(K.offsetDetail)
  })

  it('只删「上次由本底稿推过」的表（从未推过不越权删）', () => {
    const K = N1_SUB_TABLE_KEYS.soe
    // 上次推过（2）A/（2）B → 切 gross 后应删
    const withHistory = buildN1SyncPayload(
      'soe',
      snap({ offsetMode: 'gross', previouslySyncedTables: [K.netOffset, K.offsetDetail] }),
      CTX,
    )
    expect(withHistory.sub_table_data._removed_table_keys).toEqual([K.netOffset, K.offsetDetail])
    // 从未推过 → 不出现 removed 键
    const noHistory = buildN1SyncPayload('soe', snap({ offsetMode: 'gross' }), CTX)
    expect(noHistory.sub_table_data._removed_table_keys).toBeUndefined()
  })

  it('上市明确「不适用」且曾推过 → 表(2)进 _removed_table_keys', () => {
    const key = N1_SUB_TABLE_KEYS.listed.netOffset
    const p = buildN1SyncPayload(
      'listed',
      snap({ netOffsetApplicable: false, previouslySyncedTables: [key] }),
      CTX,
    )
    expect(p.sub_table_data).not.toHaveProperty(key)
    expect(p.sub_table_data._removed_table_keys).toEqual([key])
  })

  it('columns 键集恒与 sub_table_data 数据键集一致（投影器按键名匹配列头）', () => {
    const cases: Array<[N1DisclosureVariant, Partial<N1DisclosureSnapshot>]> = [
      ['listed', {}],
      ['listed', { netOffsetApplicable: false }],
      ['soe', { offsetMode: 'gross' }],
      ['soe', { offsetMode: 'net' }],
      ['soe', {}],
    ]
    for (const [variant, over] of cases) {
      const p = buildN1SyncPayload(variant, snap(over), CTX)
      const dataKeys = Object.keys(p.sub_table_data).filter((k) => !k.startsWith('_'))
      expect(Object.keys(p.columns).sort()).toEqual(dataKeys.sort())
    }
  })
})
