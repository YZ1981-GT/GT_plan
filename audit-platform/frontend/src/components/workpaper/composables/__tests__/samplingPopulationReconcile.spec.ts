/**
 * 总体完整性核对 — 纯函数测试
 *
 * spec: voucher-sampling-reconcile-balance-source
 * Task 8
 *
 * 覆盖：
 * - parseReconcileInfo：新后端 / 旧后端 / null
 * - resolvePopulationReconcile：手工优先 / 逐方向 / 旧响应回落 / 未执行
 * - describeReconcileIssue：未执行 / 不符 / 一致
 * - reconcilePresetsFor：未执行给预置 / 不符不给 / 一致不给
 * - reconcileBasisLabel
 * - formatMovementPair
 */

import { describe, it, expect } from 'vitest'
import {
  parseReconcileInfo,
  resolvePopulationReconcile,
  describeReconcileIssue,
  reconcilePresetsFor,
  reconcileBasisLabel,
  formatMovementPair,
  parseAmountInput,
  type PopulationReconcileInfo,
  type PopulationReconcileResult,
} from '../samplingPopulationReconcile'

// ─── parseReconcileInfo ──────────────────────────────────────────────────────

describe('parseReconcileInfo', () => {
  it('null stats → null', () => {
    expect(parseReconcileInfo(null)).toBeNull()
  })

  it('新后端（含逐方向字段）', () => {
    const info = parseReconcileInfo({
      reconcile_available: true,
      book_amount: '1900',
      reconcile_basis: 'tb_balance_movement',
      reconcile_ledger_debit: '1000',
      reconcile_ledger_credit: '900',
      reconcile_book_debit: '1000',
      reconcile_book_credit: '900',
      reconcile_unavailable_reason: null,
    })
    expect(info).not.toBeNull()
    expect(info!.available).toBe(true)
    expect(info!.ledgerDebit).toBe('1000')
    expect(info!.bookCredit).toBe('900')
    expect(info!.unavailableReason).toBeNull()
  })

  it('旧后端（无逐方向字段）→ 逐方向为 null', () => {
    const info = parseReconcileInfo({
      reconcile_available: true,
      book_amount: '500',
      reconcile_basis: 'trial_balance_audited_occurrence',
    })
    expect(info!.available).toBe(true)
    expect(info!.bookAmount).toBe('500')
    expect(info!.ledgerDebit).toBeNull()
    expect(info!.bookDebit).toBeNull()
  })

  it('不可用', () => {
    const info = parseReconcileInfo({
      reconcile_available: false,
      book_amount: null,
      reconcile_unavailable_reason: '余额表无行',
    })
    expect(info!.available).toBe(false)
    expect(info!.unavailableReason).toBe('余额表无行')
  })
})

// ─── resolvePopulationReconcile ──────────────────────────────────────────────

function mkInfo(overrides: Partial<PopulationReconcileInfo> = {}): PopulationReconcileInfo {
  return {
    available: true,
    bookAmount: '1900',
    basis: 'tb_balance_movement',
    unavailableReason: null,
    ledgerDebit: '1000',
    ledgerCredit: '900',
    bookDebit: '1000',
    bookCredit: '900',
    ...overrides,
  }
}

describe('resolvePopulationReconcile', () => {
  it('手工录入优先', () => {
    const r = resolvePopulationReconcile({
      info: mkInfo(),
      manualBook: '2000',
      populationAmount: '1800',
      thresholdPct: 0.05,
    })
    expect(r).not.toBeNull()
    expect(r!.mode).toBe('manual')
    expect(r!.directions).toHaveLength(1)
  })

  it('自动逐方向（新后端）', () => {
    const r = resolvePopulationReconcile({
      info: mkInfo(),
      manualBook: null,
      populationAmount: '1800',
      thresholdPct: 0.05,
    })
    expect(r).not.toBeNull()
    expect(r!.mode).toBe('directional')
    expect(r!.directions).toHaveLength(2)
    expect(r!.withinThreshold).toBe(true) // 1000==1000, 900==900
  })

  it('逐方向不符', () => {
    const r = resolvePopulationReconcile({
      info: mkInfo({ ledgerDebit: '1200' }), // 1200 vs 1000, diff=200 > 1000*0.05=50
      manualBook: null,
      populationAmount: '2100',
      thresholdPct: 0.05,
    })
    expect(r!.withinThreshold).toBe(false)
    expect(r!.directions[0].withinThreshold).toBe(false) // 借方不符
    expect(r!.directions[1].withinThreshold).toBe(true)  // 贷方一致
  })

  it('旧后端回落单值', () => {
    const r = resolvePopulationReconcile({
      info: mkInfo({ ledgerDebit: null, ledgerCredit: null, bookDebit: null, bookCredit: null }),
      manualBook: null,
      populationAmount: '1900',
      thresholdPct: 0.05,
    })
    expect(r).not.toBeNull()
    expect(r!.mode).toBe('single')
    expect(r!.directions).toHaveLength(1)
  })

  it('未执行核对 → null', () => {
    const r = resolvePopulationReconcile({
      info: mkInfo({ available: false, bookAmount: null, ledgerDebit: null, bookDebit: null }),
      manualBook: null,
      populationAmount: '1900',
      thresholdPct: 0.05,
    })
    expect(r).toBeNull()
  })

  it('info 为 null 且无手工输入 → null', () => {
    const r = resolvePopulationReconcile({
      info: null,
      manualBook: null,
      populationAmount: '1900',
      thresholdPct: 0.05,
    })
    expect(r).toBeNull()
  })

  it('负数账面不误判', () => {
    // 余额表 credit 为负数（红字冲销）
    const r = resolvePopulationReconcile({
      info: mkInfo({ ledgerCredit: '-100', bookCredit: '-100' }),
      manualBook: null,
      populationAmount: '900',
      thresholdPct: 0.05,
    })
    expect(r!.directions[1].withinThreshold).toBe(true)
  })

  it('手工录入带千分位逗号与「元」：按数值参与比对（不被当成 0）', () => {
    const r = resolvePopulationReconcile({
      info: mkInfo(), // 序时账 借1000 + 贷900 = 1900
      manualBook: ' 1,900.00元',
      populationAmount: '1800',
      thresholdPct: 0.05,
    })
    expect(r!.mode).toBe('manual')
    expect(r!.directions[0].book).toBe('1900.00')
    expect(r!.withinThreshold).toBe(true)
  })

  it('手工录入无法识别 → 不参与比对，回落自动核对', () => {
    const r = resolvePopulationReconcile({
      info: mkInfo(),
      manualBook: '约一千九百',
      populationAmount: '1800',
      thresholdPct: 0.05,
    })
    expect(r!.mode).toBe('directional')
  })

  it('手工输入空白字符串 → 不视为手工录入', () => {
    const r = resolvePopulationReconcile({
      info: mkInfo(),
      manualBook: '   ',
      populationAmount: '1800',
      thresholdPct: 0.05,
    })
    expect(r!.mode).toBe('directional') // 回落自动
  })
})

// ─── describeReconcileIssue ──────────────────────────────────────────────────

describe('describeReconcileIssue', () => {
  it('未执行核对 → 含不可用原因', () => {
    const info = mkInfo({ available: false, unavailableReason: '余额表无行' })
    const msg = describeReconcileIssue(null, info, 0.05)
    expect(msg).not.toBeNull()
    expect(msg).toContain('余额表无行')
    expect(msg).toContain('未执行')
  })

  it('不符 → 含差异数字', () => {
    const result: PopulationReconcileResult = {
      withinThreshold: false,
      directions: [
        { label: '借方发生额', ledger: '1200.00', book: '1000.00', diff: '200.00', withinThreshold: false },
        { label: '贷方发生额', ledger: '900.00', book: '900.00', diff: '0.00', withinThreshold: true },
      ],
      mode: 'directional',
    }
    const msg = describeReconcileIssue(result, mkInfo(), 0.05)
    expect(msg).not.toBeNull()
    expect(msg).toContain('不符')
    expect(msg).toContain('借方发生额')
    expect(msg).not.toContain('贷方发生额') // 贷方一致不列出
  })

  it('一致 → null', () => {
    const result: PopulationReconcileResult = {
      withinThreshold: true,
      directions: [
        { label: '借方', ledger: '1000.00', book: '1000.00', diff: '0.00', withinThreshold: true },
        { label: '贷方', ledger: '900.00', book: '900.00', diff: '0.00', withinThreshold: true },
      ],
      mode: 'directional',
    }
    expect(describeReconcileIssue(result, mkInfo(), 0.05)).toBeNull()
  })
})

// ─── reconcilePresetsFor ─────────────────────────────────────────────────────

describe('reconcilePresetsFor', () => {
  it('未执行核对 → 预置理由与改造前引擎内的三条逐字一致（顺序不变）', () => {
    expect(reconcilePresetsFor(null)).toEqual([
      '该科目无独立明细表，已与总账另行核对一致，确认抽样总体完整',
      '已与科目余额表核对一致，序时账总体金额与账面无差异',
      '本科目审定表已独立编制，抽样总体取自同一数据源，不再重复核对',
    ])
  })

  it('返回副本：调用方改动不影响下一次结果', () => {
    reconcilePresetsFor(null).pop()
    expect(reconcilePresetsFor(null)).toHaveLength(3)
  })

  it('不符 → 空（不给一致类预置理由）', () => {
    const result: PopulationReconcileResult = {
      withinThreshold: false,
      directions: [],
      mode: 'directional',
    }
    expect(reconcilePresetsFor(result)).toEqual([])
  })

  it('一致 → 空（无需放行）', () => {
    const result: PopulationReconcileResult = {
      withinThreshold: true,
      directions: [],
      mode: 'directional',
    }
    expect(reconcilePresetsFor(result)).toEqual([])
  })
})

// ─── reconcileBasisLabel ─────────────────────────────────────────────────────

describe('reconcileBasisLabel', () => {
  it('tb_balance_movement → 科目余额表发生额', () => {
    expect(reconcileBasisLabel('tb_balance_movement')).toBe('科目余额表发生额')
  })

  it('trial_balance_audited_occurrence → 试算表审定发生额', () => {
    expect(reconcileBasisLabel('trial_balance_audited_occurrence')).toBe('试算表审定发生额')
  })

  it('null → 独立来源', () => {
    expect(reconcileBasisLabel(null)).toBe('独立来源')
  })
})

// ─── parseAmountInput ────────────────────────────────────────────────────────

describe('parseAmountInput', () => {
  it.each([
    ['1912193756.05', '1912193756.05'],
    ['1,912,193,756.05', '1912193756.05'],
    ['1，912，193，756.05', '1912193756.05'],
    [' 1 912 193 756.05 ', '1912193756.05'],
    ['1912193756.05元', '1912193756.05'],
    ['-738600.67', '-738600.67'],
  ])('%s → %s', (raw, expected) => {
    expect(parseAmountInput(raw)).toBe(expected)
  })

  it.each(['', '   ', 'abc', '1.2.3', '1e5', null, undefined])('%s → null（无法识别）', raw => {
    expect(parseAmountInput(raw as any)).toBeNull()
  })
})

// ─── formatMovementPair ──────────────────────────────────────────────────────

describe('formatMovementPair', () => {
  it('正常值', () => {
    const s = formatMovementPair('1000.50', '900.30')
    expect(s).toContain('1,000.50')
    expect(s).toContain('900.30')
    expect(s).toContain('借')
    expect(s).toContain('贷')
  })

  it('null → 横杠', () => {
    const s = formatMovementPair(null, null)
    expect(s).toContain('-')
  })
})
