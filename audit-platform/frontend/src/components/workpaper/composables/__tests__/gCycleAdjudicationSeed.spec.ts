/**
 * G 循环审定表「从四表库带入未审数」守卫。
 *
 * 四类锁死，每类对应一个已实测的缺陷形态：
 *
 * 1. **声明的 rowKey / field 必须真实存在且可编辑** —— 落点声明写错 rowKey 只会
 *    静默不填（`updateField` 里 `if (!def?.editable) return`），四层验证全查不出。
 *    本文件把声明与各循环的 `G*_ADJUDICATION_ITEMS` 逐一比对。
 * 2. **归类顺序 + 否决词** —— 「其他债权投资」包含「债权投资」，顺序错就串味。
 * 3. **未命中不兜底** —— 不得落进「其他」行（K2 实测把三行坏账准备全堆进「其他」）。
 * 4. **手工优先 / 幂等** —— 已录入的格进 conflicts、值相同的格不产生写入。
 *
 * spec: .kiro/specs/g-cycle-extraction-mapping-and-disclosure-alignment/
 *       Requirements 3.3, 3.4, 3.5 / Task 3.3
 */
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import fc from 'fast-check'

import {
  G11_FALLBACK_ROW,
  G11_SEED_SPEC,
  G2_SEED_SPEC,
  G6_FV_PLACEHOLDER_ROWS,
  G_SEED_SPECS,
  buildExplicitFallbackCells,
  buildG6FvSeedCells,
  buildGSeedCells,
  classifySeedLeaf,
  normalizeGAdjPrefill,
  normalizeSeedName,
  type GAdjPrefill,
  type GAdjPrefillLeaf,
} from '../gCycleAdjudicationSeed'
import {
  describeAdjPrefillPlan,
  planAdjudicationPrefill,
  planHasWork,
  resolveAdjPrefillWrites,
} from '../shared/adjudicationPrefillPlan'
import { G2_ADJUDICATION_ITEMS } from '../g2AdjudicationItems'
import { G6_ADJUDICATION_ITEMS } from '../g6AdjudicationItems'
import { G11_ADJUDICATION_ITEMS } from '../g11Constants'

// ─── 构造助手 ────────────────────────────────────────────────────────────────

function leaf(
  code: string,
  name: string,
  o: Partial<GAdjPrefillLeaf> = {},
): GAdjPrefillLeaf {
  return {
    code,
    name,
    slot: o.slot ?? 'gross',
    opening: o.opening ?? 0,
    closing: o.closing ?? 0,
    current: o.current ?? 0,
  }
}

function payload(
  leaves: GAdjPrefillLeaf[],
  period: 'balance' | 'current' = 'balance',
): GAdjPrefill {
  return {
    period,
    positive_side: period === 'current' ? 'credit' : '',
    slots: {
      gross: {
        label: '原值', found: true, is_provision: false, codes: ['1132'],
        opening: 0, closing: 0, current: 0,
      },
    },
    leaves,
    total: {
      opening: leaves.reduce((s, l) => s + l.opening, 0),
      closing: leaves.reduce((s, l) => s + l.closing, 0),
      current: leaves.reduce((s, l) => s + l.current, 0),
    },
    parent_check: null,
  }
}

// ─── Property 1：声明的 rowKey / field 必须真实存在且可编辑 ───────────────────

describe('Property 1：落点声明与审定表行定义交叉锁死', () => {
  const CASES: Array<{
    cycle: string
    rowKeys: string[]
    fields: string[]
    items: ReadonlyArray<{ rowKey: string; label: string; editable?: boolean }>
    /** 该循环的行定义是否有 `editable` 概念（无则只校验存在性） */
    hasEditable: boolean
  }> = [
    {
      cycle: 'G2',
      rowKeys: [
        ...G2_SEED_SPEC.rules.map((r) => r.rowKey),
        ...Object.values(G2_SEED_SPEC.defaults ?? {}),
      ],
      fields: [G2_SEED_SPEC.openingField!, G2_SEED_SPEC.closingField],
      items: G2_ADJUDICATION_ITEMS,
      hasEditable: true,
    },
    {
      cycle: 'G11',
      rowKeys: [
        ...G11_SEED_SPEC.rules.map((r) => r.rowKey),
        ...Object.values(G11_SEED_SPEC.defaults ?? {}),
      ],
      fields: [G11_SEED_SPEC.closingField],
      items: G11_ADJUDICATION_ITEMS,
      hasEditable: false,
    },
    {
      cycle: 'G6',
      rowKeys: [...G6_FV_PLACEHOLDER_ROWS],
      fields: ['openingUnadjusted', 'closingUnadjusted'],
      items: G6_ADJUDICATION_ITEMS,
      hasEditable: true,
    },
  ]

  it.each(CASES)('$cycle 声明的每个 rowKey 都存在于审定表行定义', ({ rowKeys, items }) => {
    expect(rowKeys.length).toBeGreaterThan(0)
    const known = new Set(items.map((d) => d.rowKey))
    for (const k of rowKeys) expect(known, `未知 rowKey: ${k}`).toContain(k)
  })

  it.each(CASES.filter((c) => c.hasEditable))(
    '$cycle 声明的每个 rowKey 都是**可编辑**行（不可编辑行写入会被静默丢弃）',
    ({ rowKeys, items }) => {
      for (const k of rowKeys) {
        const def = items.find((d) => d.rowKey === k)
        expect(def?.editable, `${k} 不是可编辑行`).toBe(true)
      }
    },
  )

  it('反向自检：不存在的 rowKey 一定会被上面的断言抓到', () => {
    const known = new Set(G2_ADJUDICATION_ITEMS.map((d) => d.rowKey))
    expect(known.has('gross-collective')).toBe(true)
    expect(known.has('bond-interest')).toBe(false) // 已废弃的旧利息来源行键
  })

  it('G2 的默认落点 = 平台既有的调整回写默认行（不是另造一个）', () => {
    const src = fs.readFileSync(
      path.resolve(__dirname, '../g2AdjudicationItems.ts'), 'utf-8',
    )
    const m = src.match(/G2_ADJ_WRITEBACK_ROW_KEY\s*=\s*'([^']+)'/)
    expect(m?.[1]).toBe(G2_SEED_SPEC.defaults?.gross)
  })

  it('G_SEED_SPECS 只登记走通用路径的循环（G6 走专用 buildG6FvSeedCells）', () => {
    expect(Object.keys(G_SEED_SPECS).sort()).toEqual(['G1', 'G10', 'G11', 'G2', 'G4'])
    expect(G_SEED_SPECS).not.toHaveProperty('G6')
  })
})

// ─── Property 2：归类顺序与否决词 ────────────────────────────────────────────

describe('Property 2：G11 按科目名归类的顺序与否决词', () => {
  const spec = G11_SEED_SPEC
  const CASES: Array<[string, string]> = [
    ['投资收益_其他债权投资持有期间的利息', 'oth_debt_hold_interest'],
    ['投资收益_其他债权投资处置收益', 'oth_debt_dispose'],
    ['投资收益_债权投资持有期间的利息收益', 'debt_hold_interest'],
    ['投资收益_债权投资处置收益', 'debt_dispose'],
    ['投资收益_交易性金融资产持有期间', 'trading_hold'],
    ['投资收益_处置交易性金融资产', 'trading_dispose'],
    ['投资收益_权益法核算收益', 'equity_method'],
    ['投资收益_处置长期股权投资', 'dispose_lt_equity'],
    ['投资收益_其他非流动金融资产持有', 'onfa_hold'],
    ['投资收益_处置其他非流动金融资产', 'onfa_dispose'],
    ['投资收益_其他权益工具股利', 'oei_dividend'],
    ['投资收益_衍生工具处置', 'derivative_dispose'],
    ['投资收益_现金流量套期无效部分', 'hedge_ineffective'],
    ['投资收益_债务重组', 'debt_restructuring'],
    ['投资收益_取得控制权重新计量利得', 'control_fv_gain'],
    ['投资收益_丧失控制权剩余股权重新计量', 'loss_control_fv_gain'],
  ]

  it.each(CASES)('「%s」→ %s', (name, expected) => {
    expect(classifySeedLeaf(leaf('6111.01', name), spec)).toBe(expected)
  })

  it('🔴 「其他债权投资」不得被「债权投资」规则吃掉（顺序即优先级）', () => {
    const idxOther = spec.rules.findIndex((r) => r.rowKey === 'oth_debt_hold_interest')
    const idxDebt = spec.rules.findIndex((r) => r.rowKey === 'debt_hold_interest')
    expect(idxOther).toBeGreaterThanOrEqual(0)
    expect(idxOther).toBeLessThan(idxDebt)
  })

  it('🔴 「处置」类必须先于「持有」类（否则处置收益被持有规则吃掉）', () => {
    const pairs: Array<[string, string]> = [
      ['trading_dispose', 'trading_hold'],
      ['debt_dispose', 'debt_hold_interest'],
      ['oth_debt_dispose', 'oth_debt_hold_interest'],
      ['onfa_dispose', 'onfa_hold'],
    ]
    for (const [dispose, hold] of pairs) {
      const a = spec.rules.findIndex((r) => r.rowKey === dispose)
      const b = spec.rules.findIndex((r) => r.rowKey === hold)
      expect(a, `${dispose} 应先于 ${hold}`).toBeLessThan(b)
    }
  })

  it('反向自检：把「债权投资」规则提到最前，其他债权投资就会串味', () => {
    const broken = {
      ...spec,
      rules: [
        { rowKey: 'debt_hold_interest', any: ['债权投资'] },
        ...spec.rules,
      ],
    }
    expect(classifySeedLeaf(leaf('6111.01', '投资收益_其他债权投资利息'), broken))
      .toBe('debt_hold_interest')
  })

  it('名称归一：全角括号 / 下划线 / 空白不影响命中', () => {
    expect(normalizeSeedName('投资收益（权益法）')).toBe('投资收益权益法')
    expect(classifySeedLeaf(leaf('6111.01', '投资收益（权益法 核算）'), spec))
      .toBe('equity_method')
  })
})

// ─── Property 3：未命中不兜底 ────────────────────────────────────────────────

describe('Property 3：未命中的叶子进待归类，绝不塞「其他」行', () => {
  it('G11 无默认落点声明', () => {
    expect(G11_SEED_SPEC.defaults).toBeUndefined()
  })

  it('客户叶子名不含任何关键字 → unclassified，且没有任何格写向 other', () => {
    const p = payload([
      leaf('6111.98', '投资收益_招商银行理财专户', { current: 123456.78 }),
      leaf('6111.99', '投资收益_待分配', { current: 1000 }),
    ], 'current')
    const out = buildGSeedCells(p, G11_SEED_SPEC)
    expect(out.cells).toHaveLength(0)
    expect(out.unclassified.map((u) => u.code)).toEqual(['6111.98', '6111.99'])
    expect(out.cells.some((c) => c.rowKey === 'other')).toBe(false)
  })

  it('「其他」行只在源模板真实关键字命中时才用 —— 本声明里没有任何规则指向它', () => {
    expect(G11_SEED_SPEC.rules.some((r) => r.rowKey === 'other')).toBe(false)
  })

  it('反向自检：给了 defaults 就会兜底（证明上面的断言不是空转）', () => {
    const withDefault = { ...G11_SEED_SPEC, defaults: { gross: 'other' } }
    const p = payload([leaf('6111.99', '投资收益_待分配', { current: 1000 })], 'current')
    const out = buildGSeedCells(p, withDefault)
    expect(out.unclassified).toHaveLength(0)
    expect(out.cells[0].rowKey).toBe('other')
    expect(out.usedDefaults.map((d) => d.rowKey)).toEqual(['other'])
  })
})

// ─── Property 3b：显式归入「其他」行 ≠ 自动兜底 ──────────────────────────────

describe('Property 3b：G11 待归类的显式一键归入（源模板 R24 就是「其他」行）', () => {
  it('兜底行键 / 标签与源模板一致，且确实存在于 18 行细目', () => {
    expect(G11_FALLBACK_ROW).toEqual({ rowKey: 'other', label: '其他' })
    const def = G11_ADJUDICATION_ITEMS.find((d) => d.rowKey === G11_FALLBACK_ROW.rowKey)
    expect(def?.label).toBe(G11_FALLBACK_ROW.label)
    // 源模板 R7:R24 共 18 行，「其他」是最后一行
    expect(G11_ADJUDICATION_ITEMS).toHaveLength(18)
    expect(G11_ADJUDICATION_ITEMS[17].rowKey).toBe('other')
  })

  it('🔴 源模板没有「成本法核算的长期股权投资收益」行（故成本法分红落「其他」）', () => {
    const labels = G11_ADJUDICATION_ITEMS.map((d) => d.label)
    expect(labels.some((l) => l.includes('成本法'))).toBe(false)
    expect(labels.some((l) => l.includes('权益法'))).toBe(true)
  })

  it('显式归入把多个待归类科目合并成一格，并带全部来源科目码', () => {
    const cells = buildExplicitFallbackCells(
      [
        { code: '6111.01', name: '投资收益_被投资单位分红', amount: 3_878_340, opening: 0 },
        { code: '6111.16', name: '投资收益_应收款项终止收益', amount: -1_200_267.76, opening: 0 },
      ],
      G11_FALLBACK_ROW,
      G11_SEED_SPEC,
      'current',
    )
    expect(cells).toHaveLength(1)
    expect(cells[0].rowKey).toBe('other')
    expect(cells[0].field).toBe('currentUnadjusted')
    expect(cells[0].amount).toBeCloseTo(2_678_072.24, 2)
    expect(cells[0].sourceCodes).toEqual(['6111.01', '6111.16'])
  })

  it('无待归类时返空（幂等，按钮不产生空写入）', () => {
    expect(buildExplicitFallbackCells([], G11_FALLBACK_ROW, G11_SEED_SPEC)).toEqual([])
  })

  it('🔴 自动路径**仍然**不兜底：显式归入是独立函数，不进 GSeedSpec.defaults', () => {
    expect(G11_SEED_SPEC.defaults).toBeUndefined()
    const p = payload([leaf('6111.01', '投资收益_被投资单位分红', { current: 100 })], 'current')
    expect(buildGSeedCells(p, G11_SEED_SPEC).cells).toHaveLength(0)
  })

  it('组件里「一键归入」必须是独立处理器且带确认框（不能挂在自动带入路径上）', () => {
    const src = fs.readFileSync(
      path.resolve(__dirname, '../../g11-investment-income/core/G11TabAdjudication.vue'),
      'utf-8',
    )
    expect(src).toContain('buildExplicitFallbackCells')
    // 🔴 只截**函数声明**之后的片段 —— `onFallbackToOther` 在模板里也出现（@click），
    //    从模板处起找会命中 `onPullFromFourTable` 里的写入调用，把断言变成假绿/假红。
    const declAt = src.indexOf('function onFallbackToOther')
    expect(declAt, '未找到 onFallbackToOther 函数声明').toBeGreaterThan(0)
    const body = src.slice(declAt)
    const iConfirm = body.indexOf('ElMessageBox.confirm')
    const iWrite = body.indexOf('resolveAdjPrefillWrites')
    expect(iConfirm, '归入前必须有确认框').toBeGreaterThan(0)
    expect(iWrite).toBeGreaterThan(0)
    expect(iConfirm).toBeLessThan(iWrite)
  })
})

// ─── Property 4：G2 默认落点 + 备抵段不 seed ─────────────────────────────────

describe('Property 4：G2 只落原值段，且默认「按组合计提」并明示', () => {
  const p = payload([
    leaf('1132.01', '应收利息_甲公司债券', { opening: 600, closing: 700 }),
    leaf('1132.02', '应收利息_定期存款', { opening: 400, closing: 500 }),
  ])

  it('两个叶子累加到同一默认行（一行对多子科目是常态）', () => {
    const out = buildGSeedCells(p, G2_SEED_SPEC)
    const closing = out.cells.find((c) => c.field === 'closingUnadjusted')!
    expect(closing.rowKey).toBe('gross-collective')
    expect(closing.amount).toBe(1200)
    const opening = out.cells.find((c) => c.field === 'openingUnadjusted')!
    expect(opening.amount).toBe(1000)
    expect(closing.sourceCodes).toEqual(['1132.01', '1132.02'])
  })

  it('用到默认落点时必须有告知文案（否则等于静默猜）', () => {
    const out = buildGSeedCells(p, G2_SEED_SPEC)
    expect(out.usedDefaults.map((d) => d.rowKey)).toEqual(['gross-collective'])
    expect(G2_SEED_SPEC.defaultNote).toBeTruthy()
    expect(G2_SEED_SPEC.defaultNote).toContain('按组合计提')
    expect(G2_SEED_SPEC.defaultNote).toContain('1231')
  })

  it('🔴 永不写向坏账准备段（应收利息坏账在 1231 族，由 D/K 循环管）', () => {
    const out = buildGSeedCells(p, G2_SEED_SPEC)
    expect(out.cells.every((c) => !c.rowKey.startsWith('provision-'))).toBe(true)
  })

  it('🔴 不使用任何「利息来源」旧桶键（那套 rowKey 已随 G2-1 重建废弃）', () => {
    const obsolete = ['bond-interest', 'other-bond-interest', 'deposit-interest']
    const declared = [
      ...G2_SEED_SPEC.rules.map((r) => r.rowKey),
      ...Object.values(G2_SEED_SPEC.defaults ?? {}),
    ]
    for (const k of obsolete) expect(declared).not.toContain(k)
  })
})

// ─── Property 5：G6 占位行数限制 ─────────────────────────────────────────────

describe('Property 5：G6 公允价值段按叶子顺序落 4 个占位行', () => {
  function g6Payload(n: number): GAdjPrefill {
    return payload(
      Array.from({ length: n }, (_, i) =>
        leaf(`1506.0${i + 1}`, `其他债权投资_债券${i + 1}`, { opening: 10 * (i + 1), closing: 20 * (i + 1) })),
    )
  }

  it('3 个叶子 → 落前 3 个占位行，无溢出', () => {
    const out = buildG6FvSeedCells(g6Payload(3))
    expect(out.cells.map((c) => c.rowKey)).toEqual([
      'fv-item-1', 'fv-item-1', 'fv-item-2', 'fv-item-2', 'fv-item-3', 'fv-item-3',
    ])
    expect(out.unclassified).toHaveLength(0)
    expect(out.mappings).toHaveLength(3)
  })

  it('🔴 超过 4 个叶子 → 第 5 个起进待归类（固定 4 行是源模板限制）', () => {
    const out = buildG6FvSeedCells(g6Payload(6))
    expect(out.mappings).toHaveLength(4)
    expect(out.unclassified.map((u) => u.code)).toEqual(['1506.05', '1506.06'])
  })

  it('mappings 给出「占位行 ← 来源子科目」（否则审计师看不出钱从哪来）', () => {
    const out = buildG6FvSeedCells(g6Payload(1))
    expect(out.mappings[0]).toEqual({
      rowKey: 'fv-item-1', code: '1506.01', name: '其他债权投资_债券1',
    })
  })

  it('只吃 gross 槽（备抵槽的钱不进公允价值段）', () => {
    const p = payload([
      leaf('1506.01', '其他债权投资_债券1', { closing: 100 }),
      leaf('1505', '债权投资减值准备', { slot: 'provision', closing: 50 }),
    ])
    const out = buildG6FvSeedCells(p)
    expect(out.mappings).toHaveLength(1)
    expect(out.cells.every((c) => c.sourceCodes?.[0] === '1506.01')).toBe(true)
  })
})

// ─── Property 6：载荷归一容错 ────────────────────────────────────────────────

describe('Property 6：normalizeGAdjPrefill 容错', () => {
  it.each([
    ['null', null],
    ['undefined', undefined],
    ['数组（旧形态）', [{ block: 'block1', name: 'x' }]],
    ['空 dict', {}],
    ['leaves 为空', { period: 'balance', leaves: [] }],
    ['leaves 元素无 code', { period: 'balance', leaves: [{ name: 'x' }] }],
  ])('%s → null', (_label, raw) => {
    expect(normalizeGAdjPrefill(raw)).toBeNull()
  })

  it('合法载荷 → 归一后字段齐备', () => {
    const out = normalizeGAdjPrefill({
      period: 'current',
      positive_side: 'credit',
      slots: { gross: { label: '投资收益', found: true, codes: ['6111'] } },
      leaves: [{ code: '6111.01', name: 'x', slot: 'gross', current: '5' }],
      total: { current: '5' },
      parent_check: { leaf_sum: 1, parent: 1, diff: 0 },
    })!
    expect(out.period).toBe('current')
    expect(out.positive_side).toBe('credit')
    expect(out.leaves[0].current).toBe(5)
    expect(out.slots.gross.found).toBe(true)
    expect(out.parent_check?.diff).toBe(0)
  })

  it('未命中的槽进 absentSlots（本项目无此科目 ≠ 该科目为 0）', () => {
    const p = normalizeGAdjPrefill({
      period: 'balance',
      slots: {
        gross: { label: '交易性金融资产', found: true, codes: ['1101'] },
        derivative: { label: '衍生金融资产', found: false, codes: [] },
      },
      leaves: [{ code: '1101.01', name: '交易性金融资产_股票', slot: 'gross', closing: 10 }],
    })
    const out = buildGSeedCells(p, { ...G2_SEED_SPEC, defaults: undefined })
    expect(out.absentSlots).toEqual([{ slotKey: 'derivative', label: '衍生金融资产' }])
  })
})

// ─── Property 7：手工优先 / 幂等 / 冲突 ──────────────────────────────────────

describe('Property 7：planAdjudicationPrefill 手工优先与幂等', () => {
  const cells = [
    { rowKey: 'r1', field: 'closingUnadjusted', amount: 100, label: '甲', periodLabel: '期末未审' },
    { rowKey: 'r2', field: 'closingUnadjusted', amount: 200, label: '乙', periodLabel: '期末未审' },
  ]

  it('空值 → writes；已有不同值 → conflicts；已相同 → identical', () => {
    const plan = planAdjudicationPrefill(cells, (c) => (c.rowKey === 'r1' ? null : 999))
    expect(plan.writes.map((w) => w.rowKey)).toEqual(['r1'])
    expect(plan.conflicts.map((w) => w.rowKey)).toEqual(['r2'])

    const plan2 = planAdjudicationPrefill(cells, (c) => (c.rowKey === 'r1' ? 100 : 200))
    expect(plan2.identical).toBe(2)
    expect(planHasWork(plan2)).toBe(false)
  })

  it('fill-blank 不含冲突项；overwrite 含全部', () => {
    const plan = planAdjudicationPrefill(cells, (c) => (c.rowKey === 'r1' ? null : 999))
    expect(resolveAdjPrefillWrites(plan).map((w) => w.rowKey)).toEqual(['r1'])
    expect(resolveAdjPrefillWrites(plan, 'overwrite').map((w) => w.rowKey).sort())
      .toEqual(['r1', 'r2'])
  })

  it('0 视为未填（审定表空格渲染为 0）', () => {
    const plan = planAdjudicationPrefill(cells, () => null)
    expect(plan.writes).toHaveLength(2)
  })

  it('非数值既有内容一律当已录入保护（进 conflicts 不静默覆盖）', () => {
    const plan = planAdjudicationPrefill(cells, () => '待确认')
    expect(plan.conflicts).toHaveLength(2)
    expect(plan.writes).toHaveLength(0)
  })

  it('摘要文案全中文且如实报待归类 / 无此科目', () => {
    const plan = planAdjudicationPrefill(cells, () => null, {
      unclassified: [{ code: '6111.99', name: 'x', amount: 1, opening: 0 }],
      absentSlots: [{ slotKey: 'derivative', label: '衍生金融资产' }],
    })
    const text = describeAdjPrefillPlan(plan)
    expect(text).toContain('补填 2 格')
    expect(text).toContain('1 个科目待归类')
    expect(text).toContain('衍生金融资产 本项目无此科目')
    expect(/[A-Za-z]{4,}/.test(text)).toBe(false)
  })
})

// ─── Property 8：三个 Tab 的按钮接线（源码级） ───────────────────────────────

describe('Property 8：审定表 Tab 按钮接线', () => {
  const TABS: Array<[string, string]> = [
    ['G2', '../../g2-interest-receivable/G2TabAdjudication.vue'],
    ['G6', '../../g6-other-bond-investment-main/core/G6TabAdjudication.vue'],
    ['G11', '../../g11-investment-income/core/G11TabAdjudication.vue'],
  ]

  function read(rel: string): string {
    return fs.readFileSync(path.resolve(__dirname, rel), 'utf-8')
  }

  /** 剥注释 —— 说明性注释里会写反例（如「原写死 '1505'」），不剥会误判 */
  function strip(src: string): string {
    return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|\s)\/\/[^\n]*/g, '$1')
  }

  it.each(TABS)('%s 有按钮 + loading + 只读禁用 + 读 adjudication_prefill', (_c, rel) => {
    const src = strip(read(rel))
    expect(src).toContain('从四表库带入未审数')
    expect(src).toContain('adjudication_prefill')
    expect(src).toContain('normalizeGAdjPrefill')
    expect(src).toMatch(/:loading="seeding"/)
    expect(src).toMatch(/:disabled="isReadonly \|\| !has/)
  })

  it.each(TABS)('%s 无数据时给中文提示（不静默空转）', (_c, rel) => {
    const src = strip(read(rel))
    expect(src).toContain('fourTableHint')
    expect(src).toMatch(/四表库暂无/)
  })

  it.each(TABS)('%s 走共享 plan 骨架（不各写一份手工优先判定）', (_c, rel) => {
    const src = strip(read(rel))
    expect(src).toContain('planAdjudicationPrefill')
    expect(src).toContain('resolveAdjPrefillWrites')
  })

  it('反向自检：strip 确实剥掉了注释里的反例字样', () => {
    const raw = read('../../g6-other-bond-investment-main/core/G6TabAdjudication.vue')
    expect(raw).toContain('1505')          // 纠错说明保留在注释里
    expect(strip(raw)).not.toContain('1505') // 代码里不得残留
  })

  it('🔴 G6 不再按行标签匹配（占位名 `投资项目N` 永不等于客户子科目名）', () => {
    const src = strip(read('../../g6-other-bond-investment-main/core/G6TabAdjudication.vue'))
    expect(src).not.toMatch(/r\.label === row\.name/)
    expect(src).toContain('buildG6FvSeedCells')
  })
})

// ─── PBT：合计守恒 ──────────────────────────────────────────────────────────

describe('PBT：归类不改变金额总量', () => {
  it('cells 合计 + unclassified 合计 == 载荷合计', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            name: fc.constantFrom(
              '投资收益_权益法核算', '投资收益_处置交易性金融资产',
              '投资收益_招行理财', '投资收益_待分配', '投资收益_其他债权投资利息',
            ),
            amount: fc.integer({ min: -1_000_000, max: 1_000_000 }),
          }),
          { minLength: 1, maxLength: 8 },
        ),
        (items) => {
          const p = payload(
            items.map((x, i) => leaf(`6111.${i + 1}`, x.name, { current: x.amount })),
            'current',
          )
          const out = buildGSeedCells(p, G11_SEED_SPEC)
          const seeded = out.cells.reduce((s, c) => s + c.amount, 0)
          const pending = out.unclassified.reduce((s, u) => s + u.amount, 0)
          const total = items.reduce((s, x) => s + x.amount, 0)
          expect(Math.abs(seeded + pending - total)).toBeLessThan(0.01)
        },
      ),
      { numRuns: 30 },
    )
  })
})
