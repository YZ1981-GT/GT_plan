/**
 * useG9Detail — 权威模板列模型判据（spec `g-cycle-single-region-detail-lanes` C-4）
 *
 * 六组：
 * ① 12 条模板公式
 * ② 未审线（P=C+M / Q=D+N，**不从审定数推**）
 * ③ O 列股息不进任何余额
 * ④ 迁移 + 丢弃计数
 * ⑤ 完整性校验四类
 * ⑥ 集成（composable 读写 store）
 *
 * 🔴 列模型的**双向**锁在后端判据 `test_g9_column_isomorphism.py`
 * （`FIELD_SPECS_G902` 的 json_key 集合与顺序 ≡ `G9DetailRow`）。本文件锁**行为**。
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  DROPPED_LEGACY_FIELDS,
  G9_SECTIONS,
  createG9MigrationStats,
  enrichG9DetailRow,
  isLegacyG9Row,
  migrateLegacyG9Row,
  parseG9DetailRows,
  scanG9DetailIntegrity,
  useG9Detail,
  type G9DetailRow,
} from '../useG9Detail'
import type { ChecklistResponse } from '../useF1FormData'

const G9_KEY = 'G9-detail-rows'

function row(patch: Partial<G9DetailRow> = {}): G9DetailRow {
  return enrichG9DetailRow({ rowId: 'r1', investTarget: '甲证券', ...patch }, 1)
}

// ════════════════════════════════════════════════════════════════════════════
// ① 12 条模板公式
// ════════════════════════════════════════════════════════════════════════════

describe('C-4 ① 12 条模板公式逐条', () => {
  const r = row({
    openingCost: 100,
    openingCumulativeFv: 20,
    openingAdjCost: 5,
    openingAdjFvChange: 3,
    openingReclass: -10,
    periodCost: 40,
    periodFvChange: 8,
    periodDividendIncome: 7,
    closingAdjCost: 2,
    closingAdjFvChange: 1,
    closingReclass: -15,
  })

  it('E = C+D（期初公允价值）', () => {
    expect(r.openingFairValue).toBe(120)
  })
  it('H = C+F（期初审定成本）', () => {
    expect(r.openingAuditedCost).toBe(105)
  })
  it('I = D+G（期初审定累计公允价值变动）', () => {
    expect(r.openingAuditedCumulativeFv).toBe(23)
  })
  it('J = H+I（期初审定公允价值 —— 三分量恒等式）', () => {
    expect(r.openingAuditedFairValue).toBe(128)
  })
  it('L = E+K（期初报表数）', () => {
    expect(r.openingReported).toBe(110)
  })
  it('P = C+M（期末成本）', () => {
    expect(r.closingCost).toBe(140)
  })
  it('Q = D+N（期末累计公允价值变动）', () => {
    expect(r.closingCumulativeFv).toBe(28)
  })
  it('R = P+Q（期末公允价值 —— 三分量恒等式）', () => {
    expect(r.closingFairValue).toBe(168)
  })
  it('U = P+S（期末审定成本）', () => {
    expect(r.closingAuditedCost).toBe(142)
  })
  it('V = Q+T（期末审定累计公允价值变动）', () => {
    expect(r.closingAuditedCumulativeFv).toBe(29)
  })
  it('W = U+V（期末审定公允价值 —— 三分量恒等式）', () => {
    expect(r.closingAuditedFairValue).toBe(171)
  })
  it('Y = R+X（期末报表数）', () => {
    expect(r.closingReported).toBe(153)
  })
})

// ════════════════════════════════════════════════════════════════════════════
// ② 未审线
// ════════════════════════════════════════════════════════════════════════════

describe('C-4 ② 未审线：P/Q 从期初**未审**推，不从审定数推', () => {
  it('期初有账项调整时，期末成本仍只用「期初未审成本 + 本期」', () => {
    const r = row({ openingCost: 100, openingAdjCost: 50, periodCost: 10 })
    // 若错走审定线会得到 100+50+10=160
    expect(r.openingAuditedCost).toBe(150)
    expect(r.closingCost).toBe(110)
  })

  it('期初有公允价值变动调整时，期末累计变动仍只用「期初未审 + 本期」', () => {
    const r = row({ openingCumulativeFv: 20, openingAdjFvChange: 30, periodFvChange: 5 })
    expect(r.openingAuditedCumulativeFv).toBe(50)
    expect(r.closingCumulativeFv).toBe(25)
  })

  it('审计调整只经 S/T 进入期末审定数，不污染期末未审数', () => {
    const r = row({ openingCost: 100, periodCost: 10, closingAdjCost: 7 })
    expect(r.closingCost).toBe(110)
    expect(r.closingAuditedCost).toBe(117)
  })
})

// ════════════════════════════════════════════════════════════════════════════
// ③ O 列股息
// ════════════════════════════════════════════════════════════════════════════

describe('C-4 ③ O 列「计入投资收益的股息」是损益项，不进任何余额', () => {
  it('股息不影响期末成本 / 累计变动 / 公允价值 / 报表数', () => {
    const base = row({ openingCost: 100, periodCost: 10, periodFvChange: 3 })
    const withDiv = row({ openingCost: 100, periodCost: 10, periodFvChange: 3, periodDividendIncome: 999 })
    for (const k of [
      'closingCost', 'closingCumulativeFv', 'closingFairValue',
      'closingAuditedFairValue', 'closingReported',
    ] as const) {
      expect(withDiv[k]).toBe(base[k])
    }
    expect(withDiv.periodDividendIncome).toBe(999)
  })
})

// ════════════════════════════════════════════════════════════════════════════
// ④ 迁移 + 丢弃计数
// ════════════════════════════════════════════════════════════════════════════

describe('C-4 ④ 存量载荷迁移与丢弃登记', () => {
  it('旧形态识别：出现旧独有键即判旧行', () => {
    expect(isLegacyG9Row({ assetName: '甲' })).toBe(true)
    expect(isLegacyG9Row({ classification: 'FVTPL' })).toBe(true)
    expect(isLegacyG9Row({ ociChange: 1 })).toBe(true)
    expect(isLegacyG9Row({ investTarget: '甲', openingCost: 1 })).toBe(false)
  })

  it('可映射项按 §3.2 落位：旧单值列落「成本」、增减轧成净额', () => {
    const p = migrateLegacyG9Row({
      assetName: '甲证券',
      classification: '债务工具投资',
      openingBalance: 100,
      openingAdjustment: 5,
      increaseAmount: 30,
      decreaseAmount: 8,
      fvChangeAmount: 4,
      closingAdjustment: 2,
      interestIncome: 6,
      confirmationStatus: '已函证已回函',
    })
    expect(p.investTarget).toBe('甲证券')
    expect(p.category).toBe('债务工具投资')
    expect(p.openingCost).toBe(100)   // 旧单值 → C（成本）
    expect(p.openingAdjCost).toBe(5)  // → F
    expect(p.periodCost).toBe(22)     // M = 增 − 减 = 30 − 8
    expect(p.periodFvChange).toBe(4)  // → N
    expect(p.closingAdjCost).toBe(2)  // → S
    expect(p.closingInterestReceivable).toBe(6) // → Z
    expect(p.confirmationStatus).toBe('已函证已回函')
  })

  it('公式列不从旧载荷带入（由 C..T 重算）', () => {
    const p = migrateLegacyG9Row({
      assetName: '甲', openingAdjusted: 999, closingBalance: 888, closingAdjusted: 777,
    })
    expect(p).not.toHaveProperty('openingAuditedFairValue')
    expect(p).not.toHaveProperty('closingFairValue')
    expect(p).not.toHaveProperty('closingAuditedFairValue')
  })

  it('丢弃项逐字段计数（只记真的有值的）', () => {
    const stats = createG9MigrationStats()
    migrateLegacyG9Row(
      { assetName: '甲', ociChange: 12, impairmentLoss: 3, fairValueLevel: 'Level3', maturityDate: '' },
      stats,
    )
    expect(stats.migratedRows).toBe(1)
    expect(stats.droppedByField.ociChange).toBe(1)
    expect(stats.droppedByField.impairmentLoss).toBe(1)
    expect(stats.droppedByField.fairValueLevel).toBe(1)
    // 空值不计（否则每行都报一堆假丢弃）
    expect(stats.droppedByField.maturityDate).toBeUndefined()
  })

  it('移除清单覆盖 FVOCI 与减值四列（会计错误）+ 层次估值方法两列（属 G9-4）', () => {
    const fields = DROPPED_LEGACY_FIELDS.map((d) => d.field)
    for (const f of ['ociChange', 'ociCumulative', 'impairmentLoss', 'impairmentProvision']) {
      expect(fields).toContain(f)
    }
    for (const f of ['fairValueLevel', 'valuationMethod']) {
      expect(fields).toContain(f)
    }
    expect(DROPPED_LEGACY_FIELDS.find((d) => d.field === 'ociChange')!.reason).toContain('当期损益')
    expect(DROPPED_LEGACY_FIELDS.find((d) => d.field === 'fairValueLevel')!.reason).toContain('G9-4')
  })

  it('parseG9DetailRows 同时产出 list 与 stats（不靠副作用）', () => {
    const { list, stats } = parseG9DetailRows(JSON.stringify([
      { rowId: 'a', assetName: '甲', openingBalance: 100, ociChange: 5 },
      { rowId: 'b', investTarget: '乙', openingCost: 50 },
    ]))
    expect(list).toHaveLength(2)
    expect(list[0].investTarget).toBe('甲')
    expect(list[0].openingCost).toBe(100)
    expect(stats.migratedRows).toBe(1)          // 只有第一行是旧形态
    expect(stats.droppedByField.ociChange).toBe(1)
  })

  it('载荷非数组 / 解析失败时返回空 list 而不抛', () => {
    expect(parseG9DetailRows('not json').list).toEqual([])
    expect(parseG9DetailRows('{"a":1}').list).toEqual([])
    expect(parseG9DetailRows(null).list).toEqual([])
  })
})

// ════════════════════════════════════════════════════════════════════════════
// ⑤ 完整性校验四类
// ════════════════════════════════════════════════════════════════════════════

describe('C-4 ⑤ 完整性校验四类', () => {
  it('有审定余额但投资项目为空', () => {
    const r = row({ investTarget: '', openingCost: 100 })
    expect(scanG9DetailIntegrity([r]).some((i) => i.field === 'investTarget')).toBe(true)
  })

  it('三分量恒等式被破坏时报出（人为篡改公式列）', () => {
    const r = { ...row({ openingCost: 100, openingCumulativeFv: 20 }), openingFairValue: 999 }
    const issues = scanG9DetailIntegrity([r])
    expect(issues.some((i) => i.field === 'openingFairValue')).toBe(true)
    expect(issues.find((i) => i.field === 'openingFairValue')!.message).toContain('E=C+D')
  })

  it('未审线被破坏时报出（期末成本被篡改）', () => {
    const r = { ...row({ openingCost: 100, periodCost: 10 }), closingCost: 500 }
    const issues = scanG9DetailIntegrity([r])
    expect(issues.some((i) => i.field === 'closingCost')).toBe(true)
    expect(issues.find((i) => i.field === 'closingCost')!.message).toContain('P=C+M')
  })

  it('有期末审定余额但未填发函情况', () => {
    const r = row({ openingCost: 100, confirmationStatus: '' })
    expect(scanG9DetailIntegrity([r]).some((i) => i.field === 'confirmationStatus')).toBe(true)
  })

  it('不再产出 FVOCI / 减值 / Level3 三类校验（列已移除）', () => {
    const issues = scanG9DetailIntegrity([row({ openingCost: 100, confirmationStatus: '不适用' })])
    for (const f of ['ociChange', 'impairmentLoss', 'valuationMethod', 'fairValueLevel']) {
      expect(issues.some((i) => i.field === f)).toBe(false)
    }
  })

  it('全部对齐时零问题', () => {
    const r = row({ openingCost: 100, periodCost: 10, confirmationStatus: '已函证已回函' })
    expect(scanG9DetailIntegrity([r])).toEqual([])
  })
})

// ════════════════════════════════════════════════════════════════════════════
// ⑥ 集成
// ════════════════════════════════════════════════════════════════════════════

function harness(payload?: unknown) {
  const map = new Map<string, ChecklistResponse>()
  if (payload !== undefined) {
    map.set(G9_KEY, { item_id: G9_KEY, remark: JSON.stringify(payload) } as ChecklistResponse)
  }
  const debouncedSave = vi.fn()
  const g9 = useG9Detail({
    allResponses: ref(map),
    debouncedSave,
    isReadonly: ref(false),
  })
  return { g9, debouncedSave, map }
}

describe('C-4 ⑥ composable 集成', () => {
  it('三个区的行按区分组，区小计 + 合计', () => {
    const { g9 } = harness([
      { rowId: 'a', section: 'main', investTarget: '甲', openingCost: 100 },
      { rowId: 'b', section: 'mandatory_fvtpl', investTarget: '乙', openingCost: 50 },
      { rowId: 'c', section: 'designated_fvtpl', investTarget: '丙', openingCost: 30 },
      { rowId: 'd', section: 'main', investTarget: '丁', openingCost: 20 },
    ])
    expect(g9.rowsBySection.value.main).toHaveLength(2)
    expect(g9.rowsBySection.value.mandatory_fvtpl).toHaveLength(1)
    expect(g9.rowsBySection.value.designated_fvtpl).toHaveLength(1)
    const sub = g9.sectionSubtotals.value
    expect(sub[G9_SECTIONS[0].title]).toBe(120)
    expect(sub[G9_SECTIONS[1].title]).toBe(50)
    expect(sub[G9_SECTIONS[2].title]).toBe(30)
    expect(sub['合计']).toBe(200)
  })

  it('缺 section 的行落默认区 main（存量载荷没有这个字段）', () => {
    const { g9 } = harness([{ rowId: 'a', investTarget: '甲', openingCost: 10 }])
    expect(g9.rows.value[0].section).toBe('main')
  })

  it('updateRow 写回并按模板公式重算', () => {
    const { g9, debouncedSave } = harness([
      { rowId: 'a', investTarget: '甲', openingCost: 100, openingCumulativeFv: 0 },
    ])
    g9.updateRow('a', { periodFvChange: 12 })
    const [itemId, payload] = debouncedSave.mock.calls.at(-1)!
    expect(itemId).toBe(G9_KEY)
    const written = JSON.parse((payload as { remark: string }).remark)
    expect(written[0].closingCumulativeFv).toBe(12)  // Q = D + N
    expect(written[0].closingFairValue).toBe(112)    // R = P + Q
  })

  it('旧载荷载入后 persistMigrationIfNeeded 回写一次新形态', () => {
    const { g9, debouncedSave } = harness([
      { rowId: 'a', assetName: '甲', openingBalance: 100, ociChange: 5 },
    ])
    expect(g9.hasLegacyPayload.value).toBe(true)
    expect(g9.persistMigrationIfNeeded()).toBe(1)
    const [, payload] = debouncedSave.mock.calls.at(-1)!
    const written = JSON.parse((payload as { remark: string }).remark)
    expect(written[0].investTarget).toBe('甲')
    expect(written[0].openingCost).toBe(100)
    expect(written[0]).not.toHaveProperty('ociChange')
    expect(written[0]).not.toHaveProperty('assetName')
  })

  it('新形态载荷不触发迁移回写', () => {
    const { g9, debouncedSave } = harness([
      { rowId: 'a', section: 'main', investTarget: '甲', openingCost: 100 },
    ])
    expect(g9.hasLegacyPayload.value).toBe(false)
    expect(g9.persistMigrationIfNeeded()).toBe(0)
    expect(debouncedSave).not.toHaveBeenCalled()
  })

  it('空 store 时零行且不抛', () => {
    const { g9 } = harness()
    expect(g9.rows.value).toEqual([])
    expect(g9.sectionSubtotals.value['合计']).toBe(0)
  })

  it('三个区的 key 与后端 row_section_value 逐字一致', () => {
    expect(G9_SECTIONS.map((s) => s.key)).toEqual(['main', 'mandatory_fvtpl', 'designated_fvtpl'])
    expect(G9_SECTIONS.map((s) => s.titleRow)).toEqual([11, 18, 25])
  })
})
