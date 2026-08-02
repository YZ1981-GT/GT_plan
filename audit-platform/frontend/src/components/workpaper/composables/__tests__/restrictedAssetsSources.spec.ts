/**
 * 受限资产**数据来源声明表**契约（`restrictedAssetsSources.ts`）。
 *
 * **Validates: restricted-assets-note-row-scope-rollout Requirements 3.1, 3.2, 3.3
 * / Properties 8, 9, 10**
 *
 * 🔴 本文件锁死的核心判断（用户 2026-08-02 明确）：
 * 各循环的受限金额是**底稿事实**（存在 `checklist_responses` 里，与 listed/soe 变体无关），
 * **「只有期末数」不是不接的理由** —— 只有期末就只推期末，
 * listed 侧不推「（续：上年年末）」续表（推 0 会覆盖审计师手填的上年年末值）。
 *
 * 字段名与真实底稿逐字对齐（改一侧漏一侧就红）：
 * - `D2-pledge-rows` → `PledgeRow.{pledgeAmount, pledgee, pledgePurpose}`（`useD2PledgeCheck`）
 * - `H1-listed-mortgage-rows` / `H1-soe-restricted-rows`
 *   → `DisclosureRestrictedRow.{name, amount, description}`（`useH1TitleCheck`）
 * - `H2-listed-mortgage-rows` → `ListedMortgageRow.{name, amount, description}`
 * - `I1-8-rows` → `I1TitleRow.{mortgageRestricted, mortgageValue, mortgageNature}`
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  buildRestrictedAssetsPayloads,
  isRestrictedAssetsOwnerApplicable,
  RESTRICTED_ASSETS_OWNERS,
  RESTRICTED_ASSETS_TABLE,
  summarizeRestrictedRows,
  type RestrictedAssetsOwner,
} from '../restrictedAssetsNoteSectionMap'
import {
  condenseReasons,
  findRestrictedAssetsSource,
  readRestrictedRows,
  REASON_CAP,
  REASON_ELLIPSIS,
  RESTRICTED_ASSETS_SOURCES,
  RESTRICTED_ASSETS_UNSOURCED,
  type ResponseMap,
} from '../restrictedAssetsSources'

const SHEETS = { listed: '附注披露信息(上市公司)', soe: '附注披露信息(国企)' }

function responses(map: Record<string, unknown>): ResponseMap {
  const out = new Map<string, { remark?: string | null }>()
  for (const [k, v] of Object.entries(map)) {
    out.set(k, { remark: typeof v === 'string' ? v : JSON.stringify(v) })
  }
  return out
}

describe('声明表完备性', () => {
  it('声明表 ∪ 未接入表 ∪ {E1, D1 直接接线} == 全部 8 个 owner', () => {
    const declared = new Set(RESTRICTED_ASSETS_SOURCES.map((s) => s.owner))
    const unsourced = new Set(Object.keys(RESTRICTED_ASSETS_UNSOURCED))
    const direct = new Set<RestrictedAssetsOwner>(['BS-002', 'BS-005'])
    expect([...declared].filter((o) => unsourced.has(o)), '同一 owner 不能既有源又登记无源')
      .toEqual([])
    expect([...declared].filter((o) => direct.has(o)), 'E1/D1 走内存行模型，不该进声明表')
      .toEqual([])
    expect(new Set([...declared, ...unsourced, ...direct])).toEqual(
      new Set(Object.keys(RESTRICTED_ASSETS_OWNERS)),
    )
  })

  it('每条声明都有 owner / wpCode / 非空 itemIds / 说明', () => {
    for (const s of RESTRICTED_ASSETS_SOURCES) {
      expect(RESTRICTED_ASSETS_OWNERS[s.owner], `${s.owner} 不是合法段 code`).toBeTruthy()
      expect(s.wpCode).toMatch(/^[A-Z]\d+$/)
      expect(s.itemIds.length, `${s.owner} 无数据源键`).toBeGreaterThan(0)
      expect(s.note.length, `${s.owner} 说明太短`).toBeGreaterThan(10)
      // 空响应 → 空明细（fail safe，绝不造数据）
      expect(s.collect(new Map())).toEqual([])
    }
  })

  it('owner 没有声明源时 findRestrictedAssetsSource 返 undefined（不静默造数据）', () => {
    expect(findRestrictedAssetsSource('BS-010')).toBeUndefined()
    expect(findRestrictedAssetsSource('BS-007')).toBeUndefined()
    expect(findRestrictedAssetsSource('BS-006')).toBeTruthy()
  })

  it('未接入理由每条 ≥20 字，且只剩「真的没有数据」两条', () => {
    expect(Object.keys(RESTRICTED_ASSETS_UNSOURCED).sort()).toEqual(['BS-007', 'BS-010'])
    for (const [k, v] of Object.entries(RESTRICTED_ASSETS_UNSOURCED)) {
      expect(v.length, `${k} 理由太短`).toBeGreaterThan(20)
    }
  })
})

describe('readRestrictedRows —— legacy 键回退', () => {
  it('按优先级取第一个非空数组', () => {
    const r = responses({ a: [], b: [{ x: 1 }], c: [{ x: 2 }] })
    expect(readRestrictedRows(r, ['a', 'b', 'c'])).toEqual([{ x: 1 }])
  })

  it('非 JSON / 非数组 / 空数组一律跳过', () => {
    const r = responses({ a: '这是一段自由文本', b: { not: 'array' }, c: [], d: [{ ok: true }] })
    expect(readRestrictedRows(r, ['a', 'b', 'c', 'd'])).toEqual([{ ok: true }])
  })

  it('全都取不到 → []', () => {
    expect(readRestrictedRows(responses({}), ['a', 'b'])).toEqual([])
    expect(readRestrictedRows(new Map(), ['a'])).toEqual([])
  })
})

describe('condenseReasons —— 原因收敛（金额不动）', () => {
  it(`去重后最多 ${REASON_CAP} 条，其余写「${REASON_ELLIPSIS}」`, () => {
    const out = condenseReasons([
      { endAmount: 1, reason: 'A' },
      { endAmount: 2, reason: 'B' },
      { endAmount: 3, reason: 'A' },
      { endAmount: 4, reason: 'C' },
      { endAmount: 5, reason: 'D' },
      { endAmount: 6, reason: 'E' },
    ])
    expect(out.map((d) => d.reason)).toEqual(['A', 'B', 'A', 'C', REASON_ELLIPSIS, REASON_ELLIPSIS])
    // 金额一条不少（受限金额必须完整求和）
    expect(out.map((d) => d.endAmount)).toEqual([1, 2, 3, 4, 5, 6])
    const [row] = summarizeRestrictedRows('固定资产', out)
    expect(row.endAmount).toBe(21)
    expect(row.reason).toBe(`A；B；C；${REASON_ELLIPSIS}`)
  })

  it('空原因保持空串，不产生「等」', () => {
    const out = condenseReasons([{ endAmount: 1 }, { endAmount: 2, reason: '  ' }])
    expect(out.map((d) => d.reason)).toEqual(['', ''])
  })
})

describe('D2（BS-006 应收账款）—— D2-pledge-rows', () => {
  const src = findRestrictedAssetsSource('BS-006')!

  it('取 pledgeAmount，原因带质权人 + 质押目的', () => {
    const details = src.collect(
      responses({
        'D2-pledge-rows': [
          {
            debtorName: '甲公司',
            pledgeAmount: 1200000,
            pledgee: '工商银行',
            pledgePurpose: '短期借款质押',
            status: '有效',
          },
          { debtorName: '乙公司', pledgeAmount: '300000.5', pledgee: '工商银行', pledgePurpose: '短期借款质押' },
        ],
      }),
    )
    expect(details.map((d) => d.endAmount)).toEqual([1200000, 300000.5])
    // 两行同质权人同目的 → summarize 去重成一条
    const [row] = summarizeRestrictedRows(RESTRICTED_ASSETS_OWNERS['BS-006'], details)
    expect(row.label).toBe('应收账款')
    expect(row.endAmount).toBe(1500000.5)
    expect(row.reason).toBe('已质押（工商银行，短期借款质押）')
    expect('priorAmount' in row, 'D2 质押表只有期末口径 → 不得凭空补期初').toBe(false)
  })

  it('无质权人/目的 → 只写动作词', () => {
    const details = src.collect(responses({ 'D2-pledge-rows': [{ pledgeAmount: 100 }] }))
    expect(details[0].reason).toBe('已质押')
  })

  it('listed 只推主表（无期初）；soe 推单表含受限原因', () => {
    const details = src.collect(
      responses({ 'D2-pledge-rows': [{ pledgeAmount: 100, pledgee: '工行' }] }),
    )
    const rows = summarizeRestrictedRows(RESTRICTED_ASSETS_OWNERS['BS-006'], details)
    const listed = buildRestrictedAssetsPayloads(
      'listed',
      'wp-d2',
      ['listed_standalone'],
      { ownerRowCode: 'BS-006', rows },
      SHEETS,
    )
    expect(listed.length, 'listed 应只有主表一个 payload').toBe(1)
    expect((listed[0].sub_table_data as any)[RESTRICTED_ASSETS_TABLE.listedMain]).toEqual([
      { label: '应收账款', end_amount: 100 },
    ])
    const soe = buildRestrictedAssetsPayloads(
      'soe',
      'wp-d2',
      ['soe_standalone'],
      { ownerRowCode: 'BS-006', rows },
      SHEETS,
    )
    expect((soe[0].sub_table_data as any)[RESTRICTED_ASSETS_TABLE.soe]).toEqual([
      { label: '应收账款', end_carrying: 100, reason: '已质押（工行）' },
    ])
  })
})

describe('H1（BS-028 固定资产）—— H1-16/H1-17 抵押行', () => {
  const src = findRestrictedAssetsSource('BS-028')!

  it('两个变体键内容相同 → 任一有数据即用（底稿事实与变体无关）', () => {
    const rows = [{ name: '厂房A', amount: 5000000, description: '权利限制:抵押；性质:借款抵押' }]
    for (const key of ['H1-listed-mortgage-rows', 'H1-soe-restricted-rows']) {
      const details = src.collect(responses({ [key]: rows }))
      expect(details, `${key} 未被读取`).toHaveLength(1)
      expect(details[0].endAmount).toBe(5000000)
    }
  })

  it('legacy 上市旧键仍可回退读取', () => {
    const details = src.collect(
      responses({ 'H1-disc-listed-restricted-rows': [{ name: '厂房B', amount: 1 }] }),
    )
    expect(details).toHaveLength(1)
  })

  it('🔴 不把底稿拼接出来的长串 description 塞进受限原因', () => {
    const details = src.collect(
      responses({
        'H1-listed-mortgage-rows': [
          {
            name: 'FA-001 厂房 某市某路1号',
            amount: 100,
            description: '权利限制:抵押；性质:银行借款抵押；抵押权人:工商银行某分行；抵押面积:1200㎡；权证:粤(2020)某字第123号；抵押/账面金额:1,000,000',
          },
        ],
      }),
    )
    expect(details[0].reason).toBe('抵押/担保')
    expect(details[0].reason).not.toContain('权证')
  })

  it('无 amount 时回退账面净值 / 账面价值', () => {
    expect(
      src.collect(responses({ 'H1-listed-mortgage-rows': [{ netValue: 777 }] }))[0].endAmount,
    ).toBe(777)
    expect(
      src.collect(responses({ 'H1-listed-mortgage-rows': [{ bookValue: 888 }] }))[0].endAmount,
    ).toBe(888)
  })

  it('两个变体都有落点', () => {
    expect(isRestrictedAssetsOwnerApplicable('listed', 'BS-028')).toBe(true)
    expect(isRestrictedAssetsOwnerApplicable('soe', 'BS-028')).toBe(true)
  })
})

describe('H2（BS-029 在建工程，仅 soe）—— H2-2 抵押行', () => {
  const src = findRestrictedAssetsSource('BS-029')!

  it('取 amount（审定净值口径），原因固定「抵押/担保」', () => {
    const details = src.collect(
      responses({
        'H2-listed-mortgage-rows': [
          { name: '一期工程', amount: 2000000, description: '编号CIP-1；在建工程抵押/担保' },
        ],
      }),
    )
    expect(details).toEqual([{ endAmount: 2000000, reason: '抵押/担保' }])
  })

  it('🔴 段只在 soe：listed 侧构造载荷恒为 []（跨变体不可凑）', () => {
    const rows = summarizeRestrictedRows(RESTRICTED_ASSETS_OWNERS['BS-029'], [
      { endAmount: 100, reason: '抵押/担保' },
    ])
    expect(
      buildRestrictedAssetsPayloads('listed', 'wp-h2', [], { ownerRowCode: 'BS-029', rows }, SHEETS),
    ).toEqual([])
    expect(
      buildRestrictedAssetsPayloads('soe', 'wp-h2', [], { ownerRowCode: 'BS-029', rows }, SHEETS)
        .length,
    ).toBe(1)
  })
})

describe('I1（BS-032 无形资产）—— I1-8 权属检查', () => {
  const src = findRestrictedAssetsSource('BS-032')!

  const I18 = [
    { name: '土地使用权A', mortgageRestricted: 'Y', mortgageValue: 3000000, mortgageNature: '银行借款抵押' },
    { name: '土地使用权B', mortgageRestricted: 'N', mortgageValue: 999999, mortgageNature: '' },
    { name: '软件C', mortgageRestricted: '', mortgageValue: 123 },
    { name: '土地使用权D', mortgageRestricted: 'y', mortgageValue: 500000, mortgageNature: '银行借款抵押' },
  ]

  it('只取 mortgageRestricted=Y（大小写不敏感），金额取抵押价值', () => {
    const details = src.collect(responses({ 'I1-8-rows': I18 }))
    expect(details.map((d) => d.endAmount)).toEqual([3000000, 500000])
    const [row] = summarizeRestrictedRows(RESTRICTED_ASSETS_OWNERS['BS-032'], details)
    expect(row.endAmount).toBe(3500000)
    expect(row.reason).toBe('抵押/受限（银行借款抵押）')
  })

  it('🔴 未办妥权属证书的行不进受限资产（两种不同披露）', () => {
    // I1-8 里权属证书未办妥体现在 certNo 空，与 mortgageRestricted 无关
    const details = src.collect(
      responses({ 'I1-8-rows': [{ name: '未办证土地', certNo: '', mortgageRestricted: 'N', mortgageValue: 100 }] }),
    )
    expect(details).toEqual([])
  })

  it('无抵押行 → [] → 不推空段（否则段被恢复成模板骨架）', () => {
    const details = src.collect(responses({ 'I1-8-rows': [I18[1]] }))
    const rows = summarizeRestrictedRows(RESTRICTED_ASSETS_OWNERS['BS-032'], details)
    for (const variant of ['listed', 'soe'] as const) {
      expect(
        buildRestrictedAssetsPayloads(variant, 'wp-i1', [], { ownerRowCode: 'BS-032', rows }, SHEETS),
      ).toEqual([])
    }
  })
})

describe('🔴 反向自检 + 源码级锁死', () => {
  const SRC = readFileSync(resolve(__dirname, '../restrictedAssetsSources.ts'), 'utf-8')
  const CLEAN = SRC.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/[^\n]*/g, '$1')

  it('stripComments 生效（防守卫空转）', () => {
    expect(SRC).toContain('底稿事实')
    expect(CLEAN).not.toContain('底稿事实')
  })

  it('声明表里的每个 item_id 都在实现里被真的读取（不是只写在注释里）', () => {
    for (const s of RESTRICTED_ASSETS_SOURCES) {
      for (const id of s.itemIds) {
        expect(CLEAN, `${id} 只出现在注释里`).toContain(`'${id}'`)
      }
    }
  })

  it('🔴 没有任何来源声明 priorAmount（这四个来源都只有期末口径）', () => {
    for (const s of RESTRICTED_ASSETS_SOURCES) {
      const details = s.collect(
        responses(Object.fromEntries(s.itemIds.map((id) => [id, [{ amount: 1, pledgeAmount: 1, mortgageValue: 1, mortgageRestricted: 'Y' }]]))),
      )
      for (const d of details) {
        expect('priorAmount' in d, `${s.owner} 不该声明 priorAmount`).toBe(false)
      }
    }
  })

  it('反向自检：把 mortgageRestricted 过滤去掉会多算 N 行（证明过滤不空转）', () => {
    const rows = [
      { mortgageRestricted: 'Y', mortgageValue: 10 },
      { mortgageRestricted: 'N', mortgageValue: 90 },
    ]
    const filtered = findRestrictedAssetsSource('BS-032')!.collect(responses({ 'I1-8-rows': rows }))
    expect(filtered.reduce((s, d) => s + (d.endAmount || 0), 0)).toBe(10)
    // 不过滤的口径（旧错误行为）会是 100
    expect(rows.reduce((s, r) => s + r.mortgageValue, 0)).toBe(100)
  })
})
