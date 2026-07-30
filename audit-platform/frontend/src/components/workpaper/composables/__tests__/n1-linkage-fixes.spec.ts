/**
 * N1 联动修复回归守卫
 *
 * 覆盖本轮修复的确定性缺陷，防止回归：
 * 1. hydration — composable 在 allResponses 异步填充后重新装载（原刷新即丢数据）
 * 2. 明细期末口径 — 手工 endDiff 生效（原为死列）+ roll-forward 自校验
 * 3. 披露取数真源键 — N1-2-detail-rows / N1-5-loss-rows（原读 N1-2-rows / N1-5-loss-expiry-rows 死链）
 * 4. 披露派生金额 — 用同一 engine 重算（原读不落库的 computed 字段恒 0）
 * 5. 审定表 ↔ N1-3 调整分录勾稽（原 N1-1-aje-net 写了没人读）
 * 6. 审定表 TB 核对 + 从 N1-2 带入未审数
 */
import { describe, it, expect, vi } from 'vitest'
import { effectScope, ref, nextTick } from 'vue'
import { useN1Detail } from '../useN1Detail'
import { useN1LossCheck } from '../useN1LossCheck'
import { useN1Adjudication } from '../useN1Adjudication'
import { useN1CrossSheet } from '../useN1CrossSheet'
import {
  deriveDisclosureDetailRows,
  deriveDisclosureLossRows,
  deriveUnrecognizedFromLoss,
  resolveDeductibleDiff,
  N1_DETAIL_ROWS_KEY,
  N1_LOSS_ROWS_KEY,
  N1_LOSS_ROWS_KEY_V2,
} from '../useN1DisclosureSource'

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * `useN1FormData` 的测试桩。
 *
 * 🔴 `getField` / `setField` 必须与真实实现同 item_id 约定（`N1-{sheet}-{field}`）：
 * 桩此前缺这两个方法，`useN1Adjudication._readNote` 调 `formData.getField('1', ...)`
 * 时抛 `is not a function`，导致本文件 5 条用例整体失败（与披露改造无关的既有缺口）。
 */
function makeFormDataStub(allResponses: any) {
  const itemIdOf = (sheet: string, field: string) => `N1-${sheet}-${field}`
  return {
    allResponses,
    tbSeed: ref({ beginBalance: 0, debitAmount: 0, creditAmount: 0, endBalance: 0 }),
    getField: (sheet: string, field: string) =>
      allResponses.value.get(itemIdOf(sheet, field))?.conclusion ?? null,
    setField: vi.fn((sheet: string, field: string, value: any) => {
      const itemId = itemIdOf(sheet, field)
      allResponses.value.set(itemId, {
        item_id: itemId,
        conclusion: typeof value === 'string' ? value : JSON.stringify(value),
        remark: null,
      })
      return Promise.resolve()
    }),
    setTbValues: vi.fn(),
    loadData: vi.fn(() => Promise.resolve()),
    debouncedSave: vi.fn(),
    saveField: vi.fn(),
    saveBatch: vi.fn(() => Promise.resolve()),
    writebackTB: vi.fn(),
  } as any
}

function detailRow(over: Record<string, any> = {}) {
  return {
    id: 'row-1',
    itemName: '存货（跌价准备）',
    category: '资产减值准备',
    bookValue: 1_000_000,
    taxBase: 1_500_000,
    beginDiff: 400_000,
    beginTaxRate: 0.25,
    beginAje: 0,
    beginRje: 0,
    endDiff: 0,
    endTaxRate: 0.25,
    endAje: 0,
    endRje: 0,
    recognized: 0,
    reversed: 0,
    remark: '',
    ...over,
  }
}

// ─── 1. hydration ────────────────────────────────────────────────────────────

describe('N1 hydration — allResponses 异步填充后重新装载', () => {
  it('明细表：setup 时为空，loadData 完成后 hydrate 出行数据', async () => {
    const allResponses = ref(new Map<string, any>())
    const scope = effectScope()
    let detail: any
    scope.run(() => {
      detail = useN1Detail({
        wpId: ref('wp-1'),
        projectId: ref('p-1'),
        allResponses,
        formData: makeFormDataStub(allResponses),
      })
    })
    // setup 阶段（loadData 未完成）→ 无行
    expect(detail.rows.value).toHaveLength(0)

    // 模拟 loadResponses 整体替换 Map
    allResponses.value = new Map([
      [N1_DETAIL_ROWS_KEY, { conclusion: JSON.stringify([detailRow()]) }],
    ])
    await nextTick()

    expect(detail.rows.value).toHaveLength(1)
    expect(detail.rows.value[0].itemName).toBe('存货（跌价准备）')
    scope.stop()
  })

  it('亏损表：hydrate 后行数据可用', async () => {
    const allResponses = ref(new Map<string, any>())
    const scope = effectScope()
    let loss: any
    scope.run(() => {
      loss = useN1LossCheck({
        wpId: ref('wp-1'),
        projectId: ref('p-1'),
        allResponses,
        formData: makeFormDataStub(allResponses),
        // 🔴 入参名是 `auditYear`（Req 2.1 禁用 new Date()）；桩此前写 `currentYear`
        // → composable 内 `auditYear.value` 抛 undefined，本用例长期红
        auditYear: ref(2025),
      })
    })
    expect(loss.rows.value).toHaveLength(0)

    // 🔴 hydrate 读的是 N1-5 **新模型**键 `N1_LOSS_ROWS_KEY_V2`（'N1-5-rows'）与
    // 新行字段（expiryYear / bookAmount / auditAdjustment / recognizedAmount / …）。
    // 本用例原先写 legacy 键 `N1-5-loss-rows` + legacy 行形状（lossAmount/maxYears/…）
    // → hydrate 恒不命中、rows 恒空，自 spec `n1-loss-check-source-alignment`
    // 重建 N1-5 后长期红。fixture 已按新模型重写。
    allResponses.value = new Map([
      [
        N1_LOSS_ROWS_KEY_V2,
        {
          conclusion: JSON.stringify([
            {
              id: 'loss-1',
              expiryYear: 2027,
              lossYear: 2022,
              priorUnrecognized: 0,
              bookAmount: 5_000_000,
              auditAdjustment: -1_000_000,
              recognizedAmount: 0,
              taxRate: 0.25,
              basis: '预计未来应纳税所得额不足',
              sufficient: 'no',
              sourceOperating: false,
              sourceTemporaryDiff: false,
              sourceOther: false,
              indexRef: '',
            },
          ]),
        },
      ],
    ])
    await nextTick()

    expect(loss.rows.value).toHaveLength(1)
    // 审定金额 = 账面 + 审计调整；未确认额 = 审定 − 有效确认额（未届满行确认额为 0）
    expect(loss.rows.value[0].auditedAmount).toBe(4_000_000)
    expect(loss.rows.value[0].unrecognizedAmount).toBe(4_000_000)
    expect(loss.rows.value[0].isExpired).toBe(false)
    scope.stop()
  })

  it('明细表：存储已有行时 seedDefaultRows 被拒绝（防覆盖已录数据）', () => {
    const allResponses = ref(
      new Map<string, any>([
        [N1_DETAIL_ROWS_KEY, { conclusion: JSON.stringify([detailRow()]) }],
      ]),
    )
    const scope = effectScope()
    let detail: any
    scope.run(() => {
      detail = useN1Detail({
        wpId: ref('wp-1'),
        projectId: ref('p-1'),
        allResponses,
        formData: makeFormDataStub(allResponses),
      })
    })
    const before = detail.rows.value.length
    detail.seedDefaultRows()
    expect(detail.rows.value.length).toBe(before)
    scope.stop()
  })
})

// ─── 2. 明细期末口径 + roll-forward ──────────────────────────────────────────

describe('N1-2 期末可抵扣差异口径', () => {
  it('手工 endDiff 优先生效（原为死列）', () => {
    expect(resolveDeductibleDiff({ endDiff: 300_000, taxBase: 1_500_000, bookValue: 1_000_000 })).toBe(300_000)
  })

  it('未录 endDiff 时回退「计税基础−账面价值」，负值取 0', () => {
    expect(resolveDeductibleDiff({ endDiff: 0, taxBase: 1_500_000, bookValue: 1_000_000 })).toBe(500_000)
    expect(resolveDeductibleDiff({ endDiff: 0, taxBase: 800_000, bookValue: 1_000_000 })).toBe(0)
  })

  it('roll-forward 自校验：期末审定 ≠ 期初+确认−转回 时标记差异', () => {
    const allResponses = ref(
      new Map<string, any>([
        [
          N1_DETAIL_ROWS_KEY,
          {
            conclusion: JSON.stringify([
              detailRow({ endDiff: 400_000, recognized: 100_000, reversed: 0 }),
            ]),
          },
        ],
      ]),
    )
    const scope = effectScope()
    let detail: any
    scope.run(() => {
      detail = useN1Detail({
        wpId: ref('wp-1'),
        projectId: ref('p-1'),
        allResponses,
        formData: makeFormDataStub(allResponses),
      })
    })
    const row = detail.rows.value[0]
    // 期初递延税 = 400000×25% = 100000；期末 = 400000×25% = 100000
    // roll-forward 推导 = 100000 + 100000 − 0 = 200000 → 差异 −100000
    expect(row.beginAudited).toBe(100_000)
    expect(row.endAudited).toBe(100_000)
    expect(row.rollForwardEnd).toBe(200_000)
    expect(row.hasRollForwardDiff).toBe(true)
    scope.stop()
  })
})

// ─── 3/4. 披露取数真源键 + 派生金额重算 ──────────────────────────────────────

describe('披露表取数（真源键 + engine 重算）', () => {
  it('从 N1-2-detail-rows 派生金额（原读 N1-2-rows 恒空）', () => {
    const map = new Map<string, any>([
      [
        N1_DETAIL_ROWS_KEY,
        {
          conclusion: JSON.stringify([
            detailRow({ beginDiff: 400_000, endDiff: 600_000, endAje: 10_000 }),
          ]),
        },
      ],
    ])
    const rows = deriveDisclosureDetailRows(map)
    expect(rows).toHaveLength(1)
    expect(rows[0].item).toBe('存货（跌价准备）')
    expect(rows[0].beginDeferredTax).toBe(100_000) // 400000×25%
    expect(rows[0].endDeferredTax).toBe(150_000) // 600000×25%
    expect(rows[0].endBalance).toBe(160_000) // +AJE 10000
    expect(rows[0].deductibleDiff).toBe(600_000)
  })

  it('旧键 N1-2-rows 不再被误当真源（返回空）', () => {
    const map = new Map<string, any>([
      ['N1-2-rows', { conclusion: JSON.stringify([detailRow()]) }],
    ])
    expect(deriveDisclosureDetailRows(map)).toHaveLength(0)
  })

  it('从 N1-5-loss-rows 派生到期/未弥补/可确认额', () => {
    const map = new Map<string, any>([
      [
        N1_LOSS_ROWS_KEY,
        {
          conclusion: JSON.stringify([
            {
              lossYear: 2022,
              lossAmount: 5_000_000,
              maxYears: 5,
              recoveredBegin: 1_000_000,
              currentRecovery: 0,
              futureTaxableIncome: 3_000_000,
              taxRate: 0.25,
            },
            {
              lossYear: 2018,
              lossAmount: 2_000_000,
              maxYears: 5,
              recoveredBegin: 0,
              currentRecovery: 0,
              futureTaxableIncome: 5_000_000,
              taxRate: 0.25,
            },
          ]),
        },
      ],
    ])
    const rows = deriveDisclosureLossRows(map, 2025)
    expect(rows).toHaveLength(2)
    // 2022 年亏损：未弥补 400 万，未来所得 300 万 → min×25% = 75 万，且不足标记
    expect(rows[0].unrecovered).toBe(4_000_000)
    expect(rows[0].expiryYear).toBe('2027')
    expect(rows[0].isExpired).toBe(false)
    expect(rows[0].recognizableAsset).toBe(750_000)
    expect(rows[0].isInsufficient).toBe(true)
    // 2018 年亏损：2025−2018=7 > 5 → 届满，不可确认
    expect(rows[1].isExpired).toBe(true)
    expect(rows[1].recognizableAsset).toBe(0)
  })

  it('审计年度影响届满判断（不能用当前年）', () => {
    const map = new Map<string, any>([
      [
        N1_LOSS_ROWS_KEY,
        {
          conclusion: JSON.stringify([
            { lossYear: 2020, lossAmount: 1_000_000, maxYears: 5, futureTaxableIncome: 5_000_000, taxRate: 0.25 },
          ]),
        },
      ],
    ])
    expect(deriveDisclosureLossRows(map, 2025)[0].isExpired).toBe(false) // 2025−2020=5 ≤ 5
    expect(deriveDisclosureLossRows(map, 2026)[0].isExpired).toBe(true) // 6 > 5
  })

  it('未确认递延税资产从亏损行派生（超出未来所得额部分）', () => {
    const rows = deriveDisclosureLossRows(
      new Map<string, any>([
        [
          N1_LOSS_ROWS_KEY,
          {
            conclusion: JSON.stringify([
              { lossYear: 2023, lossAmount: 10_000_000, maxYears: 5, futureTaxableIncome: 4_000_000, taxRate: 0.25 },
            ]),
          },
        ],
      ]),
      2025,
    )
    const { unrecognizedLossAmount, unrecognizedLossAsset } = deriveUnrecognizedFromLoss(rows)
    expect(unrecognizedLossAmount).toBe(6_000_000) // 1000万 − 400万
    expect(unrecognizedLossAsset).toBe(1_500_000) // ×25%
  })
})

// ─── 5. 审定表 ↔ N1-3 调整分录勾稽 ───────────────────────────────────────────

describe('N1-1 ↔ N1-3 调整分录勾稽', () => {
  it('N1-3 净影响与审定表 AJE/RJE 合计一致 → isMatch', () => {
    const allResponses = ref(
      new Map<string, any>([
        ['N1-1-aje-net', { conclusion: '50000' }],
        ['N1-1-rje-net', { conclusion: '-20000' }],
      ]),
    )
    const scope = effectScope()
    scope.run(() => {
      const cs = useN1CrossSheet(allResponses, () => ({ endAje: 50_000, endRje: -20_000 }))
      expect(cs.adjustmentReconcile.value.hasAdjustment).toBe(true)
      expect(cs.adjustmentReconcile.value.isMatch).toBe(true)
    })
    scope.stop()
  })

  it('N1-3 已录但审定表未反映 → 产生差异告警', () => {
    const allResponses = ref(new Map<string, any>([['N1-1-aje-net', { conclusion: '50000' }]]))
    const scope = effectScope()
    scope.run(() => {
      const cs = useN1CrossSheet(allResponses, () => ({ endAje: 0, endRje: 0 }))
      expect(cs.adjustmentReconcile.value.isMatch).toBe(false)
      expect(cs.adjustmentReconcile.value.ajeDiff).toBe(-50_000)
    })
    scope.stop()
  })

  it('N1-3 未录调整时不产生告警（hasAdjustment=false）', () => {
    const allResponses = ref(new Map<string, any>())
    const scope = effectScope()
    scope.run(() => {
      const cs = useN1CrossSheet(allResponses, () => ({ endAje: 0, endRje: 0 }))
      expect(cs.adjustmentReconcile.value.hasAdjustment).toBe(false)
    })
    scope.stop()
  })
})

// ─── 6. 审定表 TB 核对 + 从 N1-2 带入 ────────────────────────────────────────

describe('N1-1 审定表 TB 核对与带入', () => {
  it('TB 未取到数时不产生误导性告警（hasTb=false）', () => {
    const allResponses = ref(new Map<string, any>())
    const scope = effectScope()
    scope.run(() => {
      const formData = makeFormDataStub(allResponses)
      const adj = useN1Adjudication({
        wpId: ref('wp-1'),
        projectId: ref('p-1'),
        allResponses,
        formData,
      })
      expect(adj.tbReconcile.value.hasTb).toBe(false)
    })
    scope.stop()
  })

  it('TB 有值时算出差异数', () => {
    const allResponses = ref(new Map<string, any>())
    const scope = effectScope()
    scope.run(() => {
      const formData = makeFormDataStub(allResponses)
      formData.tbSeed = ref({ beginBalance: 0, debitAmount: 0, creditAmount: 0, endBalance: 900_000 })
      const adj = useN1Adjudication({
        wpId: ref('wp-1'),
        projectId: ref('p-1'),
        allResponses,
        formData,
      })
      adj.updateRow(0, 'endUnadjusted', 1_000_000)
      expect(adj.tbReconcile.value.hasTb).toBe(true)
      expect(adj.tbReconcile.value.diff).toBe(100_000)
      expect(adj.tbReconcile.value.isMatch).toBe(false)
    })
    scope.stop()
  })

  it('从 N1-2 带入未审数：按分类聚合、保留 AJE/RJE', () => {
    const allResponses = ref(
      new Map<string, any>([
        [
          N1_DETAIL_ROWS_KEY,
          {
            conclusion: JSON.stringify([
              detailRow({ category: '资产减值准备', beginDiff: 400_000, endDiff: 600_000 }),
              detailRow({ id: 'row-2', category: '资产减值准备', beginDiff: 0, endDiff: 200_000 }),
              // 非 7 类 → 归入「其他」
              detailRow({ id: 'row-3', category: '预提费用', beginDiff: 0, endDiff: 100_000 }),
            ]),
          },
        ],
      ]),
    )
    const scope = effectScope()
    scope.run(() => {
      const adj = useN1Adjudication({
        wpId: ref('wp-1'),
        projectId: ref('p-1'),
        allResponses,
        formData: makeFormDataStub(allResponses),
      })
      // 手工 AJE 先录入
      adj.updateRow(0, 'endAje', 12_345)

      const count = adj.pullFromDetail()
      expect(count).toBe(3)

      const impair = adj.rows.value.find((r: any) => r.category === '资产减值准备')!
      expect(impair.beginUnadjusted).toBe(100_000) // 400000×25%
      expect(impair.endUnadjusted).toBe(200_000) // (600000+200000)×25%
      expect(impair.endAje).toBe(12_345) // AJE 保留

      const other = adj.rows.value.find((r: any) => r.category === '其他')!
      expect(other.endUnadjusted).toBe(25_000) // 100000×25%
    })
    scope.stop()
  })

  it('N1-2 无数据时带入返回 0（不清空审定表）', () => {
    const allResponses = ref(new Map<string, any>())
    const scope = effectScope()
    scope.run(() => {
      const adj = useN1Adjudication({
        wpId: ref('wp-1'),
        projectId: ref('p-1'),
        allResponses,
        formData: makeFormDataStub(allResponses),
      })
      adj.updateRow(0, 'endUnadjusted', 888)
      expect(adj.pullFromDetail()).toBe(0)
      expect(adj.rows.value[0].endUnadjusted).toBe(888)
    })
    scope.stop()
  })
})
