/**
 * n2CrossSheetContract — N2 联动层与持久化契约一致性守卫
 *
 * 背景（真实缺陷，非假设）：
 * `useN2CrossSheet` 曾未随 N2 源模板对齐重构迁移，读旧模型键与旧字段：
 * - 明细侧读 `N2-2-rows` 的 beginning/accrual/payment（新版存 `N2-2-detail-rows`）
 * - 审定侧读 `N2-1-adjudication-rows` 的 endBalance/creditAmount（新模型无此列）
 * - 回退键读 `N2-1-end-balance-total`（全库无人写，写入方只写 `-end-audited-total`）
 * → 两侧恒 0 → diff=0 → 勾稽恒报「通过」的**假绿**，且已渲染进 N2TabIndex 联动状态列。
 *
 * 本守卫从两侧同时锁死：
 * P1 行为：喂真实形状的新模型数据，断言勾稽/联动算出非零正确值（假绿必红）
 * P2 源码：禁止 crossSheet 再出现旧键/旧字段字面量（防下次重构又漂移）
 * P3 契约：crossSheet 读的 item_id 必须等于持久化方 saveField 拼出的 item_id
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import fs from 'node:fs'
import path from 'node:path'

import { useN2CrossSheet, N2_CROSS_SHEET_ITEM_IDS } from '../useN2CrossSheet'
import type { ChecklistResponse } from '../useN2FormData'

// ─── Fixtures ────────────────────────────────────────────────────────────────

/** N2-1 审定表原始录入行（14 列模型 N2Adj14Row 落库形状：只存录入列，派生列不落库） */
function adjRow(taxType: string, endUnadj: number, endAje = 0, endRje = 0) {
  return {
    taxType,
    beginUnadj: 0,
    beginAje: 0,
    beginRje: 0,
    endUnadj,
    endAje,
    endRje,
    reason: '',
  }
}

/**
 * N2-2 明细表原始录入行（16 列模型 N2Detail16Row 落库形状）。
 * 审定期末 P = M+N−O = (unadjBegin+beginAdjust) + (unadj+aje+rje Payable) − (unadj+aje+rje Paid)
 */
function detailRow(
  taxType: string,
  opts: Partial<{
    unadjBegin: number; beginAdjust: number
    unadjPayable: number; ajePayable: number; rjePayable: number
    unadjPaid: number; ajePaid: number; rjePaid: number
  }> = {},
) {
  return {
    id: `row-${taxType}`,
    taxType,
    taxRate: 0,
    unadjBegin: 0, beginAdjust: 0,
    unadjPayable: 0, ajePayable: 0, rjePayable: 0,
    unadjPaid: 0, ajePaid: 0, rjePaid: 0,
    remark: '',
    ...opts,
  }
}

function mkResponses(entries: Record<string, unknown>): ReturnType<typeof ref<Map<string, ChecklistResponse>>> {
  const map = new Map<string, ChecklistResponse>()
  for (const [itemId, value] of Object.entries(entries)) {
    map.set(itemId, {
      item_id: itemId,
      conclusion: typeof value === 'string' ? value : JSON.stringify(value),
      remark: null,
    } as ChecklistResponse)
  }
  return ref(map) as any
}

const SRC = fs.readFileSync(
  path.resolve(__dirname, '../useN2CrossSheet.ts'),
  'utf-8',
)

/** 剥离注释后再做源码断言（否则本文件/被守卫文件的说明性反例会被数成真实调用） */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
}

const SRC_CODE = stripComments(SRC)

// ─── P1 行为：勾稽必须算出真值（假绿必红） ───────────────────────────────────

describe('P1 adjudicationVsDetail — 审定期末合计勾稽（源模板 N2-1!I22 ↔ N2-2!P25）', () => {
  it('两侧一致时 isMatch=true，且合计确实非零（防两侧恒 0 的假绿）', () => {
    // N2-1: 期末审定 = endUnadj+endAje+endRje = 100+20+5 = 125；800+0+0=800 → 合计 925
    // N2-2: P = (0+0) + (125) − (0) = 125；800 → 合计 925
    const allResponses = mkResponses({
      [N2_CROSS_SHEET_ITEM_IDS.adjudicationRows]: [
        adjRow('增值税', 100, 20, 5),
        adjRow('城建税', 800),
      ],
      [N2_CROSS_SHEET_ITEM_IDS.detailRows]: [
        detailRow('增值税', { unadjPayable: 100, ajePayable: 20, rjePayable: 5 }),
        detailRow('城建税', { unadjPayable: 800 }),
      ],
    })

    const { adjudicationVsDetail } = useN2CrossSheet(allResponses as any)

    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(adjudicationVsDetail.value.diff).toBe(0)

    // 🔴 反假绿：把明细侧清零后必须立刻失配且 diff = 审定侧合计 925（证明两侧都真取到了数）
    const onlyAdj = mkResponses({
      [N2_CROSS_SHEET_ITEM_IDS.adjudicationRows]: [
        adjRow('增值税', 100, 20, 5),
        adjRow('城建税', 800),
      ],
    })
    const r2 = useN2CrossSheet(onlyAdj as any)
    expect(r2.adjudicationVsDetail.value.diff).toBe(925)
    expect(r2.adjudicationVsDetail.value.isMatch).toBe(false)
  })

  it('明细侧按源模板 P=M+N−O 现算（已交冲减、期初调整计入）', () => {
    // M = 300+50 = 350 ; N = 100+10+5 = 115 ; O = 40+3+2 = 45 → P = 420
    const allResponses = mkResponses({
      [N2_CROSS_SHEET_ITEM_IDS.detailRows]: [
        detailRow('房产税', {
          unadjBegin: 300, beginAdjust: 50,
          unadjPayable: 100, ajePayable: 10, rjePayable: 5,
          unadjPaid: 40, ajePaid: 3, rjePaid: 2,
        }),
      ],
    })
    const { adjudicationVsDetail } = useN2CrossSheet(allResponses as any)
    // 审定侧无数据 → 0；diff = 0 − 420
    expect(adjudicationVsDetail.value.diff).toBe(-420)
  })

  it('无审定行数据时回退 N2-1-end-audited-total（而非全库无人写的 end-balance-total）', () => {
    const allResponses = mkResponses({
      [N2_CROSS_SHEET_ITEM_IDS.adjudicationEndAuditedTotal]: '660',
      [N2_CROSS_SHEET_ITEM_IDS.detailRows]: [
        detailRow('城建税', { unadjPayable: 660 }),
      ],
    })
    const { adjudicationVsDetail } = useN2CrossSheet(allResponses as any)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)

    // 写进旧回退键则不应被读到（证明键已切换）
    const legacy = mkResponses({
      'N2-1-end-balance-total': '660',
      [N2_CROSS_SHEET_ITEM_IDS.detailRows]: [detailRow('城建税', { unadjPayable: 660 })],
    })
    expect(useN2CrossSheet(legacy as any).adjudicationVsDetail.value.diff).toBe(-660)
  })
})

describe('P1 accrualToN4 — 本期应交取自 N2-2（源模板 N2-2!N = D+I+K）', () => {
  it('从明细表算出各税种本期应交，并排除不进 6403 的税种', () => {
    const allResponses = mkResponses({
      [N2_CROSS_SHEET_ITEM_IDS.detailRows]: [
        detailRow('城市维护建设税', { unadjPayable: 70, ajePayable: 20, rjePayable: 10 }),
        detailRow('房产税', { unadjPayable: 500 }),
        detailRow('增值税', { unadjPayable: 9999 }),        // 排除
        detailRow('企业所得税', { unadjPayable: 8888 }),    // 排除
      ],
    })
    const { accrualToN4 } = useN2CrossSheet(allResponses as any)
    const byTax = Object.fromEntries(accrualToN4.value.map(i => [i.tax, i.amount]))

    expect(byTax['城建税']).toBe(100)   // 归一化名 + D+I+K
    expect(byTax['房产税']).toBe(500)
    expect(byTax['增值税']).toBeUndefined()
    expect(byTax['企业所得税']).toBeUndefined()
  })

  it('不再从 N2-1 审定表取数（N2-1 是双期余额表，无本期发生额列）', () => {
    // 只喂 N2-1，且带旧字段 creditAmount → 必须取不到任何计提项
    const onlyAdj = mkResponses({
      [N2_CROSS_SHEET_ITEM_IDS.adjudicationRows]: [
        { ...adjRow('城建税', 0), creditAmount: 12345 },
      ],
    })
    expect(useN2CrossSheet(onlyAdj as any).accrualToN4.value).toEqual([])
  })
})

// ─── P2 源码：禁止旧键/旧字段复活 ────────────────────────────────────────────

describe('P2 源码级防漂移', () => {
  it('stripComments 自检（确保 P2 断言不是空转）', () => {
    expect(SRC).toContain('N2-2-rows')          // 注释中作为历史坑说明存在
    expect(SRC_CODE).not.toContain('N2-2-rows') // 代码中必须已无
  })

  it.each([
    ['N2-2-rows', '旧明细表 item_id'],
    ['N2-1-end-balance-total', '全库无人写的旧回退键'],
  ])('代码中不得出现旧 item_id 字面量 %s（%s）', (key) => {
    expect(SRC_CODE).not.toContain(key)
  })

  it.each([
    ['creditAmount', 'N2-1 旧模型本期贷方字段'],
    ['debitAmount', 'N2-1 旧模型本期借方字段'],
    ['endBalance', 'N2-1/N2-2 旧模型期末字段（新模型为 endAudited/audEnd 派生）'],
    ['accrual', 'N2-2 旧模型计提字段'],
    ['payment', 'N2-2 旧模型缴纳字段'],
  ])('代码中不得再读旧模型字段 %s（%s）', (field) => {
    // 只禁「属性读取 `.x`」与「对象/类型键 `x:` `x?:`」两种真实取值形态。
    // 刻意不匹配裸标识符：事件名 'tax-accrual:updated'、AccrualToN4Item 等命名含同词但与旧字段无关。
    expect(SRC_CODE).not.toMatch(new RegExp(`\\.${field}\\b`))
    expect(SRC_CODE).not.toMatch(new RegExp(`(^|[{,\\s])${field}\\s*\\??:`, 'm'))
  })

  it('审定/明细行键与回退键必须走 N2_CROSS_SHEET_ITEM_IDS，不散落字面量', () => {
    // per-tax 键 `N2-1-{税种}-audited` 曾有 6 条白名单豁免（adjudicationVsCalcTables 用），
    // 已随 adjudicationVsCalcTables 改按 taxType 现算而整体删除 → 白名单清空（无豁免）。
    const literals = SRC_CODE.match(/'N2-[12]-[a-z-]+'/g) ?? []

    expect([...new Set(literals)].sort()).toEqual([
      "'N2-1-adjudication-rows'",
      "'N2-1-end-audited-total'",
      "'N2-2-detail-rows'",
    ])
  })
})

// ─── P3 契约：与持久化方 saveField 拼键一致 ──────────────────────────────────

describe('P3 与持久化方的 item_id 契约', () => {
  const ADJ_SRC = fs.readFileSync(path.resolve(__dirname, '../useN2Adjudication.ts'), 'utf-8')
  const DETAIL_SRC = fs.readFileSync(path.resolve(__dirname, '../useN2Detail.ts'), 'utf-8')

  /** useN2FormData 的规则：saveField(sheet, field) → item_id = `N2-{sheet}-{field}` */
  function persistedIds(src: string): string[] {
    return [...src.matchAll(/saveField\(\s*'(\d+)'\s*,\s*'([a-z-]+)'/g)]
      .map(m => `N2-${m[1]}-${m[2]}`)
  }

  it('审定表读的行键与回退键都由 useN2Adjudication14 真实写入', () => {
    const ids = persistedIds(ADJ_SRC)
    expect(ids).toContain(N2_CROSS_SHEET_ITEM_IDS.adjudicationRows)
    expect(ids).toContain(N2_CROSS_SHEET_ITEM_IDS.adjudicationEndAuditedTotal)
  })

  it('明细表读的行键由 useN2Detail16 真实写入', () => {
    expect(persistedIds(DETAIL_SRC)).toContain(N2_CROSS_SHEET_ITEM_IDS.detailRows)
  })

  it('派生列不得出现在落库形状里（审定/明细两侧都只存录入列）', () => {
    // _currentRaw 物化的字段集合中不应含派生列
    for (const [src, derived] of [
      [ADJ_SRC, ['beginAudited', 'endAudited', 'unadjChange', 'auditedRate']],
      [DETAIL_SRC, ['audBegin', 'audPayable', 'audPaid', 'audEnd', 'unadjEnd']],
    ] as const) {
      const raw = src.match(/function _currentRaw\(\)[\s\S]*?\n  \}/)?.[0] ?? ''
      expect(raw.length).toBeGreaterThan(0)
      for (const f of derived) {
        expect(raw).not.toMatch(new RegExp(`^\\s*${f}:`, 'm'))
      }
    }
  })
})

// ─── P4 adjudicationVsCalcTables 反假绿（Task 5.3） ─────────────────────────

describe('P4 adjudicationVsCalcTables — 6 税种喂审定行后全部非 0（反假绿）', () => {
  /**
   * TAX_CALC_TABLE_MAP 的键（归一化后的税种名）：
   * 增值税 / 城建税 / 教育费附加 / 地方教育附加 / 房产税 / 土地增值税
   */
  const TAX_TYPES_IN_MAP = ['增值税', '城建税', '教育费附加', '地方教育附加', '房产税', '土地增值税']

  it('喂 6 税种审定行 → adjudicationVsCalcTables 6 项 diff 均非 0（测算侧为 0）', () => {
    // 构造审定行：6 税种各一行，endUnadj 各 100~600
    const adjRows = TAX_TYPES_IN_MAP.map((tax, i) => adjRow(tax, (i + 1) * 100))
    const allResponses = mkResponses({
      [N2_CROSS_SHEET_ITEM_IDS.adjudicationRows]: adjRows,
    })

    const { adjudicationVsCalcTables } = useN2CrossSheet(allResponses as any)
    const results = adjudicationVsCalcTables.value

    expect(results).toHaveLength(6)

    // 每项 diff 应等于审定侧值（因为测算侧键未设置 = 0）
    for (let i = 0; i < results.length; i++) {
      const expected = (i + 1) * 100 // endUnadj + endAje(0) + endRje(0)
      expect(results[i].tax).toBe(TAX_TYPES_IN_MAP[i])
      expect(results[i].diff).toBe(expected)
      expect(results[i].isMatch).toBe(false)
    }
  })

  it('diff === _adjRowEndAudited(row)（因测算侧键为 0）', () => {
    const adjRows = TAX_TYPES_IN_MAP.map((tax, i) => ({
      taxType: tax,
      beginUnadj: 0, beginAje: 0, beginRje: 0,
      endUnadj: (i + 1) * 100,
      endAje: (i + 1) * 10,
      endRje: (i + 1) * 5,
      reason: '',
    }))
    const allResponses = mkResponses({
      [N2_CROSS_SHEET_ITEM_IDS.adjudicationRows]: adjRows,
    })

    const { adjudicationVsCalcTables } = useN2CrossSheet(allResponses as any)
    const results = adjudicationVsCalcTables.value

    for (let i = 0; i < results.length; i++) {
      const expectedAudited = (i + 1) * 100 + (i + 1) * 10 + (i + 1) * 5
      expect(results[i].diff).toBe(expectedAudited)
    }
  })

  it('给测算侧也赋值 → diff=0 → isMatch=true（正向断言可恢复）', () => {
    const adjRows = TAX_TYPES_IN_MAP.map((tax, i) => adjRow(tax, (i + 1) * 100))
    // 构建测算侧匹配值
    const calcEntries: Record<string, unknown> = {
      [N2_CROSS_SHEET_ITEM_IDS.adjudicationRows]: adjRows,
      'N2-6-vat-payable': 100,             // 增值税
      'N2-8-surtax-urban': 200,            // 城建税
      'N2-8-surtax-education': 300,        // 教育费附加
      'N2-8-surtax-local-education': 400,  // 地方教育附加
      'N2-9-property-tax-total': 500,      // 房产税
      'N2-10-lvt-total': 600,              // 土地增值税
    }
    const allResponses = mkResponses(calcEntries)

    const { adjudicationVsCalcTables } = useN2CrossSheet(allResponses as any)
    const results = adjudicationVsCalcTables.value

    for (const r of results) {
      expect(r.diff).toBe(0)
      expect(r.isMatch).toBe(true)
    }
  })
})

// ─── P5 源码无 per-tax 字面量（Task 5.3） ────────────────────────────────────

describe('P5 源码无 N2-1-{tax}-audited per-tax 字面量', () => {
  it('反向自检：useN2CrossSheet.ts 源码非空且含 adjudicationVsCalcTables', () => {
    expect(SRC.length).toBeGreaterThan(100)
    expect(SRC_CODE).toContain('adjudicationVsCalcTables')
  })

  it('stripComments 后 0 命中 /N2-1-(?:vat|urban|education|local-education|property-tax|lvt)-audited/', () => {
    const re = /N2-1-(?:vat|urban|education|local-education|property-tax|lvt)-audited/g
    const matches = SRC_CODE.match(re) ?? []
    expect(matches).toHaveLength(0)
  })
})

// ─── P6 N2-6-vat-payable 口径断言（Task 5.3） ───────────────────────────────

describe('P6 N2-6-vat-payable 口径断言', () => {
  it('增值税审定行 5700 vs 测算侧 0 → diff=5700', () => {
    const adjRows = [
      { taxType: '增值税', beginUnadj: 0, beginAje: 0, beginRje: 0, endUnadj: 5000, endAje: 500, endRje: 200, reason: '' },
    ]
    const allResponses = mkResponses({
      [N2_CROSS_SHEET_ITEM_IDS.adjudicationRows]: adjRows,
    })

    const { adjudicationVsCalcTables } = useN2CrossSheet(allResponses as any)
    const vatItem = adjudicationVsCalcTables.value.find(r => r.tax === '增值税')!

    expect(vatItem.diff).toBe(5700) // 5000+500+200 - 0
    expect(vatItem.isMatch).toBe(false)
  })

  it('设 N2-6-vat-payable=5700 → diff=0 → isMatch=true', () => {
    const adjRows = [
      { taxType: '增值税', beginUnadj: 0, beginAje: 0, beginRje: 0, endUnadj: 5000, endAje: 500, endRje: 200, reason: '' },
    ]
    const allResponses = mkResponses({
      [N2_CROSS_SHEET_ITEM_IDS.adjudicationRows]: adjRows,
      'N2-6-vat-payable': 5700,
    })

    const { adjudicationVsCalcTables } = useN2CrossSheet(allResponses as any)
    const vatItem = adjudicationVsCalcTables.value.find(r => r.tax === '增值税')!

    expect(vatItem.diff).toBe(0)
    expect(vatItem.isMatch).toBe(true)
  })
})
