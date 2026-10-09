/**
 * useG10Detail — 权威模板列模型判据（spec `g-cycle-single-region-detail-lanes` C-7）
 *
 * 五组：
 * ① 6 条模板公式
 * ② 负债侧三条口径（L 含利息 J / K 走未审线 / 调整审定单列）
 * ③ 移除的 16 列（读取兼容但不回写、不进受管列）
 * ④ 完整性校验（含新增的未审线两条）
 * ⑤ 集成（composable 读写 store / 单区无 section）
 *
 * 🔴 列模型的**双向**锁在后端判据 `test_g10_column_isomorphism.py`
 * （`FIELD_SPECS_G1002` 的 json_key 集合与顺序 ≡ `G10DetailRow`）。本文件锁**行为**。
 *
 * 🔴 与 G9 的 C-4 判据（`useG9Detail.spec.ts`）刻意**不对称**的地方：
 * G9 真库有 605 B 真载荷 ⇒ 它有整套迁移函数（`migrateLegacyG9Row` / `isLegacyG9Row` /
 * `createG9MigrationStats` / `parseG9DetailRows` 返 `{list,stats}`）与迁移回写。
 * G10 真库是 **2 B 空数组**（无真实行数据）⇒ 只做 `enrichG10DetailRow` 内的**读取
 * 兼容**，不造迁移统计与回写。照 G9 补一套迁移判据在 G10 上是给不存在的数据写代码。
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  DROPPED_LEGACY_G10_FIELDS,
  enrichG10DetailRow,
  scanG10DetailIntegrity,
  useG10Detail,
  type G10DetailRow,
} from '../useG10Detail'
import type { ChecklistResponse } from '../useF1FormData'

const G10_KEY = 'G10-detail-rows'

function row(patch: Partial<G10DetailRow> = {}): G10DetailRow {
  return enrichG10DetailRow({ rowId: 'r1', liabilityName: '甲债券', ...patch }, 1)
}

// ════════════════════════════════════════════════════════════════════════════
// ① 6 条模板公式
// ════════════════════════════════════════════════════════════════════════════

describe('C-7 ① 6 条模板公式逐条', () => {
  const r = row({
    openingInitialAmount: 100,
    openingFvAccum: 20,
    openingAdjustment: 5,
    movementInitialAmount: 40,
    movementFvChange: 8,
    interestExpense: 3,
    closingAdjustment: 7,
  })

  it('E = C+D（期初公允价值）', () => {
    expect(r.openingFairValue).toBe(120)
  })
  it('G = E+F（期初审定数，单列调整）', () => {
    expect(r.openingAdjusted).toBe(125)
  })
  it('K = C+H（期末初始确认金额）', () => {
    expect(r.closingInitialAmount).toBe(140)
  })
  it('L = D+I+J（期末累计公允价值变动，含利息）', () => {
    expect(r.closingFvAccum).toBe(31)
  })
  it('M = K+L（期末公允价值）', () => {
    expect(r.closingFairValue).toBe(171)
  })
  it('O = M+N（期末审定数，单列调整）', () => {
    expect(r.closingAdjusted).toBe(178)
  })
})

// ════════════════════════════════════════════════════════════════════════════
// ② 负债侧三条口径
// ════════════════════════════════════════════════════════════════════════════

describe('C-7 ② 负债侧三条口径', () => {
  it('🔴 L 含利息 J —— 漏 J 会让期末累计变动与审定数系统性偏小', () => {
    const withInterest = row({ openingFvAccum: 20, movementFvChange: 8, interestExpense: 3 })
    const without = row({ openingFvAccum: 20, movementFvChange: 8 })
    expect(withInterest.closingFvAccum - without.closingFvAccum).toBe(3)
    // 利息同时推高期末公允价值与审定数（负债账面价值随之增加）
    expect(withInterest.closingFairValue - without.closingFairValue).toBe(3)
    expect(withInterest.closingAdjusted - without.closingAdjusted).toBe(3)
  })

  it('🔴 K 走未审线：期初有调整数时，期末初始确认金额不受其影响', () => {
    const r = row({ openingInitialAmount: 100, openingAdjustment: 50, movementInitialAmount: 10 })
    // 若错走审定线（从 G 推）会得到 100+50+10=160
    expect(r.closingInitialAmount).toBe(110)
    expect(r.openingAdjusted).toBe(150)
  })

  it('🔴 期末调整只经 N 进入审定数 O，不污染期末未审数 M', () => {
    const r = row({ openingInitialAmount: 100, movementInitialAmount: 10, closingAdjustment: 7 })
    expect(r.closingInitialAmount).toBe(110)
    expect(r.closingFairValue).toBe(110)
    expect(r.closingAdjusted).toBe(117)
  })

  it('🔴 调整与审定都是单列 —— 行模型里各自只有一个字段（不像 G9 拆两分量）', () => {
    const keys = Object.keys(row())
    // 调整数各一个（F / N），审定数各一个（G / O）
    expect(keys.filter((k) => /Adjustment$/.test(k))).toEqual([
      'openingAdjustment',
      'closingAdjustment',
    ])
    expect(keys.filter((k) => /Adjusted$/.test(k))).toEqual([
      'openingAdjusted',
      'closingAdjusted',
    ])
    // G9 形态的两分量字段一个都不应存在
    for (const g9Only of ['openingAdjCost', 'openingAdjFvChange', 'closingAdjCost', 'closingAdjFvChange']) {
      expect(keys).not.toContain(g9Only)
    }
  })

  it('🔴 本期变动是净额列 —— 无 currentDecrease，负值直接表达减少', () => {
    const r = row({ openingInitialAmount: 100, movementInitialAmount: -30 })
    expect(Object.keys(r)).not.toContain('currentDecrease')
    expect(r.closingInitialAmount).toBe(70)
  })
})

// ════════════════════════════════════════════════════════════════════════════
// ③ 移除的 16 列
// ════════════════════════════════════════════════════════════════════════════

describe('C-7 ③ 移除 16 列：读取兼容但不回写、不进受管列', () => {
  it('移除清单 16 条，每条给出归属', () => {
    expect(DROPPED_LEGACY_G10_FIELDS).toHaveLength(16)
    for (const d of DROPPED_LEGACY_G10_FIELDS) {
      expect(d.reason.trim().length).toBeGreaterThan(0)
    }
  })

  it('层次/估值/衍生三族的归属逐字指名 G10-5 / G10-6 / G10-8', () => {
    const byField = new Map(DROPPED_LEGACY_G10_FIELDS.map((d) => [d.field, d.reason]))
    expect(byField.get('fairValueLevel')).toMatch(/G10-5|G10-6/)
    expect(byField.get('valuationMethod')).toMatch(/G10-5/)
    expect(byField.get('isDerivative')).toMatch(/G10-8/)
    expect(byField.get('hostContractDesc')).toMatch(/G10-8/)
    expect(byField.get('embeddedDerivativeJudgment')).toMatch(/G10-8/)
  })

  it('🔴 G10 是负债不对外发函 —— confirmationStatus 的移除理由要说清这点', () => {
    const byField = new Map(DROPPED_LEGACY_G10_FIELDS.map((d) => [d.field, d.reason]))
    expect(byField.get('confirmationStatus')).toMatch(/负债|函证/)
  })

  it('全部 16 个字段都不出现在受管行模型里', () => {
    const managed = new Set(Object.keys(row()))
    for (const d of DROPPED_LEGACY_G10_FIELDS) {
      expect(managed.has(d.field)).toBe(false)
    }
  })

  it('四个 legacy 单值键只作读取兼容落位，不回写原名', () => {
    const r = enrichG10DetailRow(
      {
        rowId: 'x',
        liabilityName: '乙债券',
        initialAmount: 100,
        openingBalance: 130,
        currentIncrease: 20,
        profitLossAmount: 6,
      },
      1,
    )
    // initialAmount → C；openingBalance 反推 D = 130-100；currentIncrease → H；profitLossAmount → I
    expect(r.openingInitialAmount).toBe(100)
    expect(r.openingFvAccum).toBe(30)
    expect(r.openingFairValue).toBe(130)
    expect(r.movementInitialAmount).toBe(20)
    expect(r.movementFvChange).toBe(6)
    // 原名不回写
    expect(Object.keys(r)).not.toContain('initialAmount')
    expect(Object.keys(r)).not.toContain('openingBalance')
    expect(Object.keys(r)).not.toContain('currentIncrease')
    expect(Object.keys(r)).not.toContain('profitLossAmount')
  })

  it('显式提供新列时 legacy 键不再参与（新列优先）', () => {
    const r = enrichG10DetailRow(
      { rowId: 'x', openingInitialAmount: 200, initialAmount: 999, openingFvAccum: 5, openingBalance: 888 },
      1,
    )
    expect(r.openingInitialAmount).toBe(200)
    expect(r.openingFvAccum).toBe(5)
  })

  it('公式列不从旧载荷带入（由 C/D/F/H/I/J/N 重算）', () => {
    const r = enrichG10DetailRow(
      {
        rowId: 'x',
        openingInitialAmount: 100,
        openingFvAccum: 20,
        openingFairValue: 999,
        openingAdjusted: 888,
        closingFairValue: 777,
        closingAdjusted: 666,
      },
      1,
    )
    expect(r.openingFairValue).toBe(120)
    expect(r.openingAdjusted).toBe(120)
    expect(r.closingFairValue).toBe(120)
    expect(r.closingAdjusted).toBe(120)
  })
})

// ════════════════════════════════════════════════════════════════════════════
// ④ 完整性校验
// ════════════════════════════════════════════════════════════════════════════

describe('C-7 ④ 完整性校验', () => {
  it('有审定余额但项目名称为空', () => {
    const r = row({ liabilityName: '', openingInitialAmount: 100 })
    expect(scanG10DetailIntegrity([r]).some((i) => i.field === 'liabilityName')).toBe(true)
  })

  it('期初分量恒等式被破坏时报出', () => {
    const r = { ...row({ openingInitialAmount: 100, openingFvAccum: 20 }), openingFairValue: 999 }
    expect(scanG10DetailIntegrity([r]).some((i) => i.field === 'openingFairValue')).toBe(true)
  })

  it('期末分量恒等式被破坏时报出', () => {
    const r = { ...row({ openingInitialAmount: 100 }), closingFairValue: 999 }
    expect(scanG10DetailIntegrity([r]).some((i) => i.field === 'closingFairValue')).toBe(true)
  })

  it('🔴 未审线 K=C+H 被破坏时报出（改造前校验的是走审定线的 legacy closingBalance）', () => {
    const r = { ...row({ openingInitialAmount: 100, movementInitialAmount: 10 }), closingInitialAmount: 500 }
    const issues = scanG10DetailIntegrity([r])
    expect(issues.some((i) => i.field === 'closingInitialAmount')).toBe(true)
  })

  it('🔴 L=D+I+J 被破坏时报出，且提示里点名「计入财务费用的利息」', () => {
    const r = { ...row({ openingFvAccum: 20, movementFvChange: 8, interestExpense: 3 }), closingFvAccum: 99 }
    const issues = scanG10DetailIntegrity([r])
    const hit = issues.find((i) => i.field === 'closingFvAccum')
    expect(hit).toBeTruthy()
    expect(hit!.message).toContain('利息')
  })

  it('不再产出 Level3 缺估值方法 / OCI / 减值三类校验（列已移除）', () => {
    const issues = scanG10DetailIntegrity([row({ openingInitialAmount: 100 })])
    for (const f of ['fairValueLevel', 'valuationMethod', 'ociChange', 'impairmentLoss']) {
      expect(issues.some((i) => i.field === f)).toBe(false)
    }
  })

  it('全部对齐时零问题', () => {
    expect(scanG10DetailIntegrity([row({ openingInitialAmount: 100, movementInitialAmount: 10 })])).toEqual([])
  })
})

// ════════════════════════════════════════════════════════════════════════════
// ⑤ 集成
// ════════════════════════════════════════════════════════════════════════════

function harness(payload?: unknown) {
  const map = new Map<string, ChecklistResponse>()
  if (payload !== undefined) {
    map.set(G10_KEY, { item_id: G10_KEY, remark: JSON.stringify(payload) } as ChecklistResponse)
  }
  const debouncedSave = vi.fn()
  const g10 = useG10Detail({
    allResponses: ref(map),
    debouncedSave,
    isReadonly: ref(false),
  })
  return { g10, debouncedSave, map }
}

describe('C-7 ⑤ composable 集成', () => {
  it('载荷落 remark 且按模板公式重算', () => {
    const { g10 } = harness([
      { rowId: 'a', liabilityName: '甲债券', openingInitialAmount: 100, openingFvAccum: 20 },
    ])
    expect(g10.rows.value).toHaveLength(1)
    expect(g10.rows.value[0].openingFairValue).toBe(120)
  })

  it('🔴 单区：行模型不带 section（那是 G9 三区的形态）', () => {
    const { g10 } = harness([{ rowId: 'a', liabilityName: '甲债券', section: 'main' }])
    expect(Object.keys(g10.rows.value[0])).not.toContain('section')
  })

  it('updateRow 写回并按模板公式重算', () => {
    const { g10, debouncedSave } = harness([
      { rowId: 'a', liabilityName: '甲债券', openingInitialAmount: 100, openingFvAccum: 0 },
    ])
    g10.updateRow('a', { openingFvAccum: 25 })
    expect(g10.rows.value[0].openingFairValue).toBe(125)
    expect(debouncedSave).toHaveBeenCalledWith(G10_KEY, expect.objectContaining({ remark: expect.any(String) }))
  })

  it('只读时 updateRow 不改不存', () => {
    const map = new Map<string, ChecklistResponse>([
      [G10_KEY, { item_id: G10_KEY, remark: JSON.stringify([{ rowId: 'a', liabilityName: '甲', openingInitialAmount: 100 }]) } as ChecklistResponse],
    ])
    const debouncedSave = vi.fn()
    const g10 = useG10Detail({ allResponses: ref(map), debouncedSave, isReadonly: ref(true) })
    g10.updateRow('a', { openingInitialAmount: 999 })
    expect(g10.rows.value[0].openingInitialAmount).toBe(100)
    expect(debouncedSave).not.toHaveBeenCalled()
  })

  it('totals 按模板列聚合（含利息合计）', () => {
    const { g10 } = harness([
      { rowId: 'a', liabilityName: '甲', openingInitialAmount: 100, interestExpense: 3 },
      { rowId: 'b', liabilityName: '乙', openingInitialAmount: 50, interestExpense: 2 },
    ])
    expect(g10.totals.value.interestExpense).toBe(5)
    expect(g10.totals.value.closingFairValue).toBe(155)
  })

  it('🔴 categorySubtotals 按 A 列「类别」分组（不是已删除的 liabilityType）', () => {
    const { g10 } = harness([
      { rowId: 'a', liabilityName: '甲', liabilityCategory: '指定类', openingInitialAmount: 100 },
      { rowId: 'b', liabilityName: '乙', liabilityCategory: '交易类', openingInitialAmount: 50 },
    ])
    expect(g10.categorySubtotals.value['指定类']).toBe(100)
    expect(g10.categorySubtotals.value['交易类']).toBe(50)
    expect(g10.categorySubtotals.value['总计']).toBe(150)
  })

  it('🔴 level3MissingMethodCount 恒 0（校验已迁 G10-5/G10-6）', () => {
    const { g10 } = harness([{ rowId: 'a', liabilityName: '甲', openingInitialAmount: 100 }])
    expect(g10.level3MissingMethodCount.value).toBe(0)
  })

  it('activeTab 四段（模板四个一级分组）', () => {
    const { g10 } = harness()
    expect(g10.activeTab.value).toBe('basic')
    for (const tab of ['opening', 'movement', 'closing'] as const) {
      g10.activeTab.value = tab
      expect(g10.activeTab.value).toBe(tab)
    }
  })

  it('空 store 时零行且不抛', () => {
    const { g10 } = harness()
    expect(g10.rows.value).toEqual([])
    expect(g10.integrityIssues.value).toEqual([])
  })

  it('载荷非数组 / 解析失败时零行而不抛', () => {
    for (const bad of ['not json', '{"a":1}']) {
      const map = new Map<string, ChecklistResponse>([
        [G10_KEY, { item_id: G10_KEY, remark: bad } as ChecklistResponse],
      ])
      const g10 = useG10Detail({ allResponses: ref(map), debouncedSave: vi.fn(), isReadonly: ref(false) })
      expect(g10.rows.value).toEqual([])
    }
  })

  it('缺 rowId 的旧行按 id 回落、都没有则现铸（不丢行）', () => {
    const { g10 } = harness([
      { id: 'legacy-1', liabilityName: '甲' },
      { liabilityName: '乙' },
    ])
    expect(g10.rows.value).toHaveLength(2)
    expect(g10.rows.value[0].rowId).toBe('legacy-1')
    expect(g10.rows.value[1].rowId).toMatch(/^g10d-/)
  })
})
