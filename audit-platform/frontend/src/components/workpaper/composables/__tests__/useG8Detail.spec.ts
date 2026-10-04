/**
 * useG8Detail — 权威模板列模型判据（spec `g-cycle-single-region-detail-lanes` C-8）
 *
 * 五组：
 * ① 8 条模板公式
 * ② FVOCI 口径（OCI 三列必须保留 / 本期 OCI 就是 J / 股利不进余额）
 * ③ 移除的 8 列（读取兼容但不回写、不进受管列）
 * ④ 完整性校验（分量恒等式 + 未审线 + OCI 滚动）
 * ⑤ 集成（composable 读写 store / 辅助核算种子 / 四段 tab）
 *
 * 🔴 列模型的**双向**锁在后端判据 `test_g8_column_isomorphism.py`
 * （`FIELD_SPECS_G802` 的 json_key 集合与顺序 ≡ `G8DetailRow`）。本文件锁**行为**。
 *
 * 🔴 **与 G9/G10 反向**：G8 是 FVOCI（受管表注释逐字「指定为以公允价值计量且其变动
 * 计入其他综合收益……该指定一经作出不得撤销」）⇒ OCI 三列是 CAS22 要求的，**不删**。
 * G9/G10 删 OCI 的依据是「那两张表全 FVTPL」。
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  DROPPED_LEGACY_G8_FIELDS,
  enrichG8DetailRow,
  scanG8DetailIntegrity,
  seedRowFromAux,
  useG8Detail,
  type G8DetailRow,
} from '../useG8Detail'
import type { ChecklistResponse } from '../useF1FormData'

const G8_KEY = 'G8-detail-rows'

function row(patch: Partial<G8DetailRow> = {}): G8DetailRow {
  return enrichG8DetailRow({ rowId: 'r1', investeeName: '甲公司', ...patch }, 1)
}

// ════════════════════════════════════════════════════════════════════════════
// ① 8 条模板公式
// ════════════════════════════════════════════════════════════════════════════

describe('C-8 ① 8 条模板公式逐条', () => {
  const r = row({
    openingCost: 100,
    openingFvAccum: 20,
    openingOciCumulative: 15,
    openingAdjustment: 5,
    movementCost: 40,
    movementFvChange: 8,
    disposalFvTransfer: -3,
    ociToRetainedEarnings: 2,
    dividendIncome: 999,
    closingAdjustment: 7,
  })

  it('E = SUM(C:D)（期初合计）', () => {
    expect(r.openingTotal).toBe(120)
  })
  it('H = E+G（期初审定数）', () => {
    expect(r.openingAdjusted).toBe(125)
  })
  it('M = I+J+K+L（本期变动合计，🔴 含 OCI 转留存 L）', () => {
    expect(r.movementTotal).toBe(47)
  })
  it('O = C+I（期末成本，未审线）', () => {
    expect(r.closingCost).toBe(140)
  })
  it('P = D+J+K（期末累计公允价值变动，🔴 含处置结转 K）', () => {
    expect(r.closingFvAccum).toBe(25)
  })
  it('Q = O+P（期末合计）', () => {
    expect(r.closingTotal).toBe(165)
  })
  it('R = F+J+L（期末 OCI 累计）', () => {
    expect(r.closingOciCumulative).toBe(25)
  })
  it('T = Q+S（期末审定数）', () => {
    expect(r.closingAdjusted).toBe(172)
  })
})

// ════════════════════════════════════════════════════════════════════════════
// ② FVOCI 口径
// ════════════════════════════════════════════════════════════════════════════

describe('C-8 ② FVOCI 口径（与 G9/G10 反向）', () => {
  it('🔴 OCI 三列必须在受管行模型里（F 期初累计 / L 本期转留存 / R 期末累计）', () => {
    const keys = Object.keys(row())
    expect(keys).toContain('openingOciCumulative')
    expect(keys).toContain('ociToRetainedEarnings')
    expect(keys).toContain('closingOciCumulative')
  })

  it('🔴 本期 OCI 就是模板 J 列 —— 不存在独立的 ociCurrentChange 字段', () => {
    const keys = Object.keys(row())
    expect(keys).toContain('movementFvChange')
    expect(keys).not.toContain('ociCurrentChange')
    // J 同时推高期末累计公允价值变动 P 与期末 OCI 累计 R
    const withJ = row({ openingFvAccum: 20, openingOciCumulative: 15, movementFvChange: 8 })
    const without = row({ openingFvAccum: 20, openingOciCumulative: 15 })
    expect(withJ.closingFvAccum - without.closingFvAccum).toBe(8)
    expect(withJ.closingOciCumulative - without.closingOciCumulative).toBe(8)
  })

  it('🔴 处置结转 K 进 P 但**不**进 R（OCI 累计的减少走 L 转留存）', () => {
    const withK = row({ openingFvAccum: 20, openingOciCumulative: 15, disposalFvTransfer: -5 })
    const without = row({ openingFvAccum: 20, openingOciCumulative: 15 })
    expect(withK.closingFvAccum - without.closingFvAccum).toBe(-5)
    expect(withK.closingOciCumulative).toBe(without.closingOciCumulative)
  })

  it('🔴 OCI 转留存 L 进 M 与 R，但**不**进 P（那是公允价值分量）', () => {
    const withL = row({ openingFvAccum: 20, openingOciCumulative: 15, ociToRetainedEarnings: -6 })
    const without = row({ openingFvAccum: 20, openingOciCumulative: 15 })
    expect(withL.movementTotal - without.movementTotal).toBe(-6)
    expect(withL.closingOciCumulative - without.closingOciCumulative).toBe(-6)
    expect(withL.closingFvAccum).toBe(without.closingFvAccum)
  })

  it('🔴 股利收入 N 是损益项，不进任何余额', () => {
    const base = row({ openingCost: 100, movementCost: 10, movementFvChange: 3 })
    const withDiv = row({ openingCost: 100, movementCost: 10, movementFvChange: 3, dividendIncome: 999 })
    for (const k of [
      'openingTotal', 'openingAdjusted', 'movementTotal',
      'closingCost', 'closingFvAccum', 'closingTotal', 'closingOciCumulative', 'closingAdjusted',
    ] as const) {
      expect(withDiv[k]).toBe(base[k])
    }
  })

  it('🔴 本期成本是净额列 —— 无 decreaseAmount，负值直接表达减少', () => {
    const r = row({ openingCost: 100, movementCost: -30 })
    expect(Object.keys(r)).not.toContain('decreaseAmount')
    expect(r.closingCost).toBe(70)
  })
})

// ════════════════════════════════════════════════════════════════════════════
// ③ 移除的 8 列
// ════════════════════════════════════════════════════════════════════════════

describe('C-8 ③ 移除 8 列：读取兼容但不回写、不进受管列', () => {
  it('移除清单 8 条，每条给出归属', () => {
    expect(DROPPED_LEGACY_G8_FIELDS).toHaveLength(8)
    for (const d of DROPPED_LEGACY_G8_FIELDS) {
      expect(d.reason.trim().length).toBeGreaterThan(0)
    }
  })

  it('五列公允价值测试族的归属逐字指名 G8-4', () => {
    const byField = new Map(DROPPED_LEGACY_G8_FIELDS.map((d) => [d.field, d.reason]))
    for (const f of ['fairValueLevel', 'valuationMethod', 'shareCount', 'pricePerShare', 'fairValueTotal']) {
      expect(byField.get(f)).toMatch(/G8-4/)
    }
  })

  it('🔴 decreaseAmount / ociCurrentChange 的移除理由要点明「双源」', () => {
    const byField = new Map(DROPPED_LEGACY_G8_FIELDS.map((d) => [d.field, d.reason]))
    expect(byField.get('decreaseAmount')).toMatch(/净额|双源/)
    expect(byField.get('ociCurrentChange')).toMatch(/双源/)
  })

  it('全部 8 个字段都不出现在受管行模型里', () => {
    const managed = new Set(Object.keys(row()))
    for (const d of DROPPED_LEGACY_G8_FIELDS) {
      expect(managed.has(d.field)).toBe(false)
    }
  })

  it('legacy 单值期初 openingBalance 反推 C/D 两分量', () => {
    const r = enrichG8DetailRow(
      { rowId: 'x', investeeName: '乙', openingCost: 100, openingBalance: 130 },
      1,
    )
    expect(r.openingCost).toBe(100)
    expect(r.openingFvAccum).toBe(30)
    expect(r.openingTotal).toBe(130)
    expect(Object.keys(r)).not.toContain('openingBalance')
  })

  it('legacy increaseAmount − decreaseAmount 合并成 I 净额', () => {
    const r = enrichG8DetailRow(
      { rowId: 'x', increaseAmount: 50, decreaseAmount: 20 },
      1,
    )
    expect(r.movementCost).toBe(30)
    expect(Object.keys(r)).not.toContain('increaseAmount')
  })

  it('legacy fvChangeAmount 落 J；ociCurrentChange 不采用（与 J 双源）', () => {
    const r = enrichG8DetailRow({ rowId: 'x', fvChangeAmount: 8, ociCurrentChange: 999 }, 1)
    expect(r.movementFvChange).toBe(8)
  })

  it('legacy ociOpeningCumulative 落 F', () => {
    const r = enrichG8DetailRow({ rowId: 'x', ociOpeningCumulative: 15 }, 1)
    expect(r.openingOciCumulative).toBe(15)
  })

  it('legacy 只有 ociCumulativeChange（期末累计）时反推 F 保住 R', () => {
    const r = enrichG8DetailRow({ rowId: 'x', ociCumulativeChange: 200 }, 1)
    expect(r.openingOciCumulative).toBe(200)
    expect(r.closingOciCumulative).toBe(200)
  })

  it('公式列不从旧载荷带入（由 C/D/F/G/I/J/K/L/S 重算）', () => {
    const r = enrichG8DetailRow(
      {
        rowId: 'x',
        openingCost: 100,
        openingFvAccum: 20,
        openingTotal: 999,
        openingAdjusted: 888,
        movementTotal: 777,
        closingCost: 666,
        closingTotal: 555,
        closingAdjusted: 444,
      },
      1,
    )
    expect(r.openingTotal).toBe(120)
    expect(r.openingAdjusted).toBe(120)
    expect(r.movementTotal).toBe(0)
    expect(r.closingCost).toBe(100)
    expect(r.closingTotal).toBe(120)
    expect(r.closingAdjusted).toBe(120)
  })
})

// ════════════════════════════════════════════════════════════════════════════
// ④ 完整性校验
// ════════════════════════════════════════════════════════════════════════════

describe('C-8 ④ 完整性校验', () => {
  it('有审定余额但未填指定 OCI 原因', () => {
    const r = row({ openingCost: 100 })
    expect(scanG8DetailIntegrity([r]).some((i) => i.field === 'designationReason')).toBe(true)
  })

  it('OCI 转留存已填金额但未说明原因', () => {
    const r = row({ openingCost: 100, designationReason: '战略持有', ociToRetainedEarnings: -5 })
    expect(scanG8DetailIntegrity([r]).some((i) => i.field === 'transferReason')).toBe(true)
  })

  it('有审定余额但被投资单位名称为空', () => {
    const r = row({ investeeName: '', openingCost: 100 })
    expect(scanG8DetailIntegrity([r]).some((i) => i.field === 'investeeName')).toBe(true)
  })

  it('期初分量恒等式 E=C+D 被破坏时报出', () => {
    const r = { ...row({ openingCost: 100, openingFvAccum: 20 }), openingTotal: 999 }
    expect(scanG8DetailIntegrity([r]).some((i) => i.field === 'openingTotal')).toBe(true)
  })

  it('期末成本未审线 O=C+I 被破坏时报出', () => {
    const r = { ...row({ openingCost: 100, movementCost: 10 }), closingCost: 500 }
    expect(scanG8DetailIntegrity([r]).some((i) => i.field === 'closingCost')).toBe(true)
  })

  it('🔴 P=D+J+K 被破坏时报出，且提示点名「处置时结转」', () => {
    const r = { ...row({ openingFvAccum: 20, disposalFvTransfer: -3 }), closingFvAccum: 99 }
    const hit = scanG8DetailIntegrity([r]).find((i) => i.field === 'closingFvAccum')
    expect(hit).toBeTruthy()
    expect(hit!.message).toContain('处置')
  })

  it('🔴 R=F+J+L 被破坏时报出（OCI 滚动）', () => {
    const r = { ...row({ openingOciCumulative: 15, movementFvChange: 8 }), closingOciCumulative: 99 }
    expect(scanG8DetailIntegrity([r]).some((i) => i.field === 'closingOciCumulative')).toBe(true)
  })

  it('🔴 M=I+J+K+L 被破坏时报出，且提示点名「OCI 转入留存收益」', () => {
    const r = { ...row({ movementCost: 10, ociToRetainedEarnings: -6 }), movementTotal: 99 }
    const hit = scanG8DetailIntegrity([r]).find((i) => i.field === 'movementTotal')
    expect(hit).toBeTruthy()
    expect(hit!.message).toContain('OCI')
  })

  it('不再产出「Level3 缺估值方法」/「公允合计 ≠ 数量×单价」/「本期OCI≠FV变动」三类', () => {
    const issues = scanG8DetailIntegrity([
      row({ openingCost: 100, designationReason: '战略持有' }),
    ])
    for (const f of ['valuationMethod', 'fairValueTotal', 'ociCurrentChange', 'fairValueLevel']) {
      expect(issues.some((i) => i.field === f)).toBe(false)
    }
  })

  it('全部对齐时零问题', () => {
    const r = row({ openingCost: 100, movementCost: 10, designationReason: '非交易性战略持有' })
    expect(scanG8DetailIntegrity([r])).toEqual([])
  })
})

// ════════════════════════════════════════════════════════════════════════════
// ⑤ 集成
// ════════════════════════════════════════════════════════════════════════════

describe('C-8 ⑤ seedRowFromAux 与 composable 集成', () => {
  it('🔴 辅助核算种子：期初全额落成本分量 C，轧差落 J 本期公允价值变动', () => {
    const r = seedRowFromAux(
      { investeeName: '甲公司', openingBalance: 800, closingBalance: 900, auxType: '项目' } as never,
      1,
    )
    expect(r.openingCost).toBe(800)
    expect(r.openingFvAccum).toBe(0)
    expect(r.openingTotal).toBe(800)
    expect(r.movementFvChange).toBe(100)
    expect(r.closingTotal).toBe(900)
  })

  it('已有行被人工拆过分量时，轧差不再覆盖', () => {
    const existing = row({ movementCost: 60, movementFvChange: 40 })
    const r = seedRowFromAux(
      { investeeName: '甲公司', openingBalance: 800, closingBalance: 900, auxType: '项目' } as never,
      1,
      existing,
    )
    expect(r.movementFvChange).toBe(40)
    expect(r.movementCost).toBe(60)
  })

  it('种子不再往已删除的 remark 列写提示', () => {
    const r = seedRowFromAux(
      { investeeName: '甲公司', openingBalance: 100, closingBalance: 100, auxType: '项目' } as never,
      1,
    )
    expect(Object.keys(r)).not.toContain('remark')
  })

  it('载荷落 remark 且按模板公式重算', () => {
    const { g8 } = harness([
      { rowId: 'a', investeeName: '甲公司', openingCost: 100, openingFvAccum: 20 },
    ])
    expect(g8.rows.value).toHaveLength(1)
    expect(g8.rows.value[0].openingTotal).toBe(120)
  })

  it('updateRow 写回并按模板公式重算', () => {
    const { g8, debouncedSave } = harness([
      { rowId: 'a', investeeName: '甲公司', openingCost: 100, openingFvAccum: 0 },
    ])
    g8.updateRow('a', { openingFvAccum: 25 })
    expect(debouncedSave).toHaveBeenCalledWith(G8_KEY, expect.objectContaining({ remark: expect.any(String) }))
    const saved = JSON.parse(String(debouncedSave.mock.calls[0][1].remark))
    expect(saved[0].openingTotal).toBe(125)
  })

  it('只读时 updateRow 不改不存', () => {
    const map = new Map<string, ChecklistResponse>([
      [G8_KEY, {
        item_id: G8_KEY,
        remark: JSON.stringify([{ rowId: 'a', investeeName: '甲', openingCost: 100 }]),
      } as ChecklistResponse],
    ])
    const debouncedSave = vi.fn()
    const g8 = useG8Detail({ allResponses: ref(map), debouncedSave, isReadonly: ref(true) })
    g8.updateRow('a', { openingCost: 999 })
    expect(g8.rows.value[0].openingCost).toBe(100)
    expect(debouncedSave).not.toHaveBeenCalled()
  })

  it('totals 按模板列聚合（含处置结转 / OCI 转留存 / 股利）', () => {
    const { g8 } = harness([
      { rowId: 'a', investeeName: '甲', openingCost: 100, disposalFvTransfer: -3, ociToRetainedEarnings: -2, dividendIncome: 7 },
      { rowId: 'b', investeeName: '乙', openingCost: 50, disposalFvTransfer: -1, ociToRetainedEarnings: -1, dividendIncome: 3 },
    ])
    expect(g8.totals.value.disposalFvTransfer).toBe(-4)
    expect(g8.totals.value.ociToRetainedEarnings).toBe(-3)
    expect(g8.totals.value.dividendIncome).toBe(10)
    expect(g8.totals.value.closingTotal).toBe(146)
  })

  it('🔴 activeTab 四段（对齐模板四个一级分组）', () => {
    const { g8 } = harness()
    expect(g8.activeTab.value).toBe('basic')
    for (const tab of ['opening', 'movement', 'closing'] as const) {
      g8.activeTab.value = tab
      expect(g8.activeTab.value).toBe(tab)
    }
  })

  it('🔴 回写 G8-1 的期末未审取模板 Q 列合计（不是已删除的 closingBalance）', () => {
    const { g8, debouncedSave } = harness([
      { rowId: 'a', investeeName: '甲', openingCost: 100, movementCost: 20, movementFvChange: 5 },
    ])
    expect(g8.pushTotalsToAdjudication()).toBe(true)
    const adjCall = debouncedSave.mock.calls.find((c) => String(c[0]).startsWith('G8-adj'))
    expect(adjCall).toBeTruthy()
    expect(JSON.stringify(adjCall![1])).toContain('125')
  })

  it('空 store 时零行且不抛', () => {
    const { g8 } = harness()
    expect(g8.rows.value).toEqual([])
    expect(g8.integrityIssues.value).toEqual([])
  })

  it('载荷非数组 / 解析失败时零行而不抛', () => {
    for (const bad of ['not json', '{"a":1}']) {
      const map = new Map<string, ChecklistResponse>([
        [G8_KEY, { item_id: G8_KEY, remark: bad } as ChecklistResponse],
      ])
      const g8 = useG8Detail({ allResponses: ref(map), debouncedSave: vi.fn(), isReadonly: ref(false) })
      expect(g8.rows.value).toEqual([])
    }
  })

  it('缺 rowId 的旧行按 id 回落、都没有则现铸（不丢行）', () => {
    const { g8 } = harness([{ id: 'legacy-1', investeeName: '甲' }, { investeeName: '乙' }])
    expect(g8.rows.value).toHaveLength(2)
    expect(g8.rows.value[0].rowId).toBe('legacy-1')
    expect(g8.rows.value[1].rowId).toMatch(/^g8d-/)
  })
})

function harness(payload?: unknown) {
  const map = new Map<string, ChecklistResponse>()
  if (payload !== undefined) {
    map.set(G8_KEY, { item_id: G8_KEY, remark: JSON.stringify(payload) } as ChecklistResponse)
  }
  const debouncedSave = vi.fn()
  const g8 = useG8Detail({
    allResponses: ref(map),
    debouncedSave,
    isReadonly: ref(false),
  })
  return { g8, debouncedSave, map }
}
