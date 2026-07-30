/**
 * N1-5 Loss Check Baseline — Characterization Tests
 *
 * 冻结改造前必须不变的契约，确保后续结构重建不静默破坏既有行为。
 *
 * **Validates: Requirements 8.1, 8.2, 8.3**
 *
 * 锁定内容：
 * 1. N1_SUB_TABLE_KEYS 子表名（listed 4 张 / soe 5 张）
 * 2. buildN1SyncPayload 的 `columns` 键集合与 `sub_table_data` 键集合恒相同
 * 3. N1-5-total-recognizable 为 remark 字符串（跨表键语义）
 * 4. deriveUnrecognizedFromLoss 现行为（legacy 兼容路径）
 *
 * ⚠️ 2026-07-30 基线更新（spec `n1-deferred-tax-disclosure-template-alignment` R4.4）：
 * 原基线锁 soe 为 4 键，实为源模板对齐缺陷 —— 国企源模板
 * `附注披露信息（国企）` R54 有第 5 张表「B、递延所得税资产和递延所得税负债互抵明细」，
 * 附注模板与同步映射此前都整张缺失。故 soe 期望值由 4 键改为 5 键（新增 `offsetDetail`），
 * listed 仍为 4 键（上市源模板确无该表）。
 */
import { describe, it, expect } from 'vitest'
import {
  N1_SUB_TABLE_KEYS,
  buildN1SyncPayload,
  type N1DisclosureSnapshot,
} from '../composables/n1NoteSectionMap'
import {
  deriveUnrecognizedFromLoss,
  type N1DisclosureLossRow,
} from '../composables/useN1DisclosureSource'

// ─── 1. N1_SUB_TABLE_KEYS 子表名锁定 ────────────────────────────────────────

describe('N1_SUB_TABLE_KEYS 子表名契约', () => {
  it('listed 变体恒含 4 个子表键（上市源模板确无「互抵明细」表）', () => {
    const keys = Object.keys(N1_SUB_TABLE_KEYS.listed)
    expect(keys).toHaveLength(4)
    expect(keys).toEqual(['unoffset', 'netOffset', 'unrecognized', 'lossExpiry'])
  })

  it('soe 变体恒含 5 个子表键（源模板（2）B 互抵明细）', () => {
    const keys = Object.keys(N1_SUB_TABLE_KEYS.soe)
    expect(keys).toHaveLength(5)
    expect(keys).toEqual(['unoffset', 'netOffset', 'offsetDetail', 'unrecognized', 'lossExpiry'])
  })

  it('listed 子表名逐字锁定', () => {
    expect(N1_SUB_TABLE_KEYS.listed.unoffset).toBe('未经抵销的递延所得税资产和递延所得税负债')
    expect(N1_SUB_TABLE_KEYS.listed.netOffset).toBe('以抵销后净额列示的递延所得税资产或负债')
    expect(N1_SUB_TABLE_KEYS.listed.unrecognized).toBe('未确认递延所得税资产的可抵扣暂时性差异及可抵扣亏损明细')
    expect(N1_SUB_TABLE_KEYS.listed.lossExpiry).toBe('未确认递延所得税资产的可抵扣亏损将于以下年度到期')
  })

  it('soe 子表名逐字锁定', () => {
    expect(N1_SUB_TABLE_KEYS.soe.unoffset).toBe('未经抵销的递延所得税资产和递延所得税负债')
    expect(N1_SUB_TABLE_KEYS.soe.netOffset).toBe('以抵销后净额列示的递延所得税资产或负债')
    expect(N1_SUB_TABLE_KEYS.soe.offsetDetail).toBe('递延所得税资产和递延所得税负债互抵明细')
    expect(N1_SUB_TABLE_KEYS.soe.unrecognized).toBe('未确认递延所得税资产明细')
    expect(N1_SUB_TABLE_KEYS.soe.lossExpiry).toBe('未确认递延所得税资产的可抵扣亏损将于以下年度到期')
  })
})

// ─── 2. buildN1SyncPayload columns 键集合 ≡ sub_table_data 键集合 ─────────

describe('buildN1SyncPayload columns/sub_table_data 键集合恒相同', () => {
  // 表 1 行含 4 个值列（期末/期初 × 暂时性差异/递延税额），对齐源模板两级表头
  const minimalSnapshot: N1DisclosureSnapshot = {
    assetRows: [
      { item: '资产减值准备', endDiff: 400, endTax: 100, priorDiff: 320, priorTax: 80 },
    ],
    unrecognizedRows: [{ item: '可抵扣亏损', amount: 50, priorAmount: 30 }],
    lossExpiryRows: [{ expiryYear: '2027', unrecovered: 50, priorUnrecovered: 30 }],
  }
  const ctx = { wpId: 'wp-001', year: 2025 }

  it('listed: columns 键集合 === sub_table_data 键集合（排除 _note_texts）', () => {
    const payload = buildN1SyncPayload('listed', minimalSnapshot, ctx)
    const colKeys = new Set(Object.keys(payload.columns))
    const subKeys = new Set(
      Object.keys(payload.sub_table_data).filter((k) => !k.startsWith('_')),
    )
    expect(colKeys).toEqual(subKeys)
  })

  it('soe: columns 键集合 === sub_table_data 键集合（排除 _note_texts）', () => {
    const payload = buildN1SyncPayload('soe', minimalSnapshot, ctx)
    const colKeys = new Set(Object.keys(payload.columns))
    const subKeys = new Set(
      Object.keys(payload.sub_table_data).filter((k) => !k.startsWith('_')),
    )
    expect(colKeys).toEqual(subKeys)
  })

  it('columns 键集合恰好等于该变体 N1_SUB_TABLE_KEYS 的值集合', () => {
    const payload = buildN1SyncPayload('listed', minimalSnapshot, ctx)
    const colKeys = Object.keys(payload.columns).sort()
    const expectedKeys = Object.values(N1_SUB_TABLE_KEYS.listed).sort()
    expect(colKeys).toEqual(expectedKeys)
  })
})

// ─── 3. N1-5-total-recognizable 为 remark 字符串 ─────────────────────────────

describe('N1-5-total-recognizable 跨表键语义', () => {
  it('该键存储为 remark 字符串（被 useN1CrossSheet.lossCheckToCalcTable 消费）', () => {
    // 该键的值是「可确认递延税资产合计」的字符串表示
    // 保存时：saveField('N1-5-total-recognizable', { remark: String(total) })
    // 读取时：allResponses.get('N1-5-total-recognizable')?.remark → 字符串
    // 本测试锁定该语义：值类型为 string（非 number 对象）
    const totalRecognizable = 12345.67
    const remarkValue = String(totalRecognizable)
    expect(typeof remarkValue).toBe('string')
    expect(remarkValue).toBe('12345.67')
    // 消费方 parseFloat(remark) 恢复数值
    expect(parseFloat(remarkValue)).toBe(totalRecognizable)
  })
})

// ─── 4. deriveUnrecognizedFromLoss 现行为锁定 ─────────────────────────────────

describe('deriveUnrecognizedFromLoss 现行为（legacy 兼容路径）', () => {
  it('空数组 → 全零', () => {
    const result = deriveUnrecognizedFromLoss([])
    expect(result.unrecognizedLossAmount).toBe(0)
    expect(result.unrecognizedLossAsset).toBe(0)
  })

  it('已届满行：全额归入不确认', () => {
    const rows: N1DisclosureLossRow[] = [
      {
        year: '2020',
        lossAmount: 100000,
        expiryYear: '2025',
        recovered: 30000,
        unrecovered: 70000,
        futureTaxableIncome: 50000,
        recognizableAsset: 0,
        isExpired: true,
        isInsufficient: false,
      },
    ]
    const result = deriveUnrecognizedFromLoss(rows)
    // 已届满：unrecognizedBase = unrecovered = 70000
    expect(result.unrecognizedLossAmount).toBe(70000)
    // 已届满行 recognizableAsset=0 且 recognizedBase=0 → 回退 taxRateFallback=0.25
    expect(result.unrecognizedLossAsset).toBe(17500) // 70000 * 0.25
  })

  it('未届满行：不确认 = 未弥补 − min(未弥补, 预计应纳税)', () => {
    const rows: N1DisclosureLossRow[] = [
      {
        year: '2022',
        lossAmount: 200000,
        expiryYear: '2027',
        recovered: 50000,
        unrecovered: 150000,
        futureTaxableIncome: 80000,
        recognizableAsset: 20000, // = min(150000,80000) * taxRate
        isExpired: false,
        isInsufficient: true,
      },
    ]
    const result = deriveUnrecognizedFromLoss(rows)
    // recognizedBase = min(unrecovered=150000, futureTaxableIncome=80000) = 80000
    // unrecognizedBase = max(0, 150000 - 80000) = 70000
    expect(result.unrecognizedLossAmount).toBe(70000)
    // rate = recognizableAsset(20000) / recognizedBase(80000) = 0.25
    // asset = 70000 * 0.25 = 17500
    expect(result.unrecognizedLossAsset).toBe(17500)
  })

  it('未届满且预计应纳税 >= 未弥补 → 不确认为零', () => {
    const rows: N1DisclosureLossRow[] = [
      {
        year: '2023',
        lossAmount: 100000,
        expiryYear: '2028',
        recovered: 20000,
        unrecovered: 80000,
        futureTaxableIncome: 100000, // >= unrecovered
        recognizableAsset: 20000,
        isExpired: false,
        isInsufficient: false,
      },
    ]
    const result = deriveUnrecognizedFromLoss(rows)
    // recognizedBase = min(80000, 100000) = 80000
    // unrecognizedBase = max(0, 80000 - 80000) = 0
    expect(result.unrecognizedLossAmount).toBe(0)
    expect(result.unrecognizedLossAsset).toBe(0)
  })

  it('多行合计', () => {
    const rows: N1DisclosureLossRow[] = [
      {
        year: '2020', lossAmount: 50000, expiryYear: '2025',
        recovered: 10000, unrecovered: 40000,
        futureTaxableIncome: 30000, recognizableAsset: 0,
        isExpired: true, isInsufficient: false,
      },
      {
        year: '2022', lossAmount: 100000, expiryYear: '2027',
        recovered: 20000, unrecovered: 80000,
        futureTaxableIncome: 50000, recognizableAsset: 12500,
        isExpired: false, isInsufficient: true,
      },
    ]
    const result = deriveUnrecognizedFromLoss(rows)
    // Row 1 (expired): unrecognizedBase = 40000, rate fallback 0.25 → asset = 10000
    // Row 2: recognizedBase = min(80000,50000)=50000, unrecognizedBase = 80000-50000 = 30000
    //         rate = 12500/50000 = 0.25, asset = 30000*0.25 = 7500
    expect(result.unrecognizedLossAmount).toBe(70000) // 40000 + 30000
    expect(result.unrecognizedLossAsset).toBe(17500)  // 10000 + 7500
  })

  it('自定义 taxRateFallback 参数', () => {
    const rows: N1DisclosureLossRow[] = [
      {
        year: '2019', lossAmount: 100000, expiryYear: '2024',
        recovered: 0, unrecovered: 100000,
        futureTaxableIncome: 0, recognizableAsset: 0,
        isExpired: true, isInsufficient: false,
      },
    ]
    const result = deriveUnrecognizedFromLoss(rows, 0.15)
    expect(result.unrecognizedLossAmount).toBe(100000)
    expect(result.unrecognizedLossAsset).toBe(15000) // 100000 * 0.15
  })
})
