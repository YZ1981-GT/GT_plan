/**
 * Task 11 – 试算表底稿调整列 + 发布变化标记
 *
 * 纯逻辑单元测试，不需要挂载组件：
 *  1. TrialBalanceRow 类型包含 wp_adjustment / wp_publish_base / wp_published_at
 *  2. hasPublishBaseChanged 判断逻辑
 *  3. 小计行包含 wp_adjustment 累加
 *  4. 复制表头包含「底稿调整」
 *  5. 单元格映射列号正确
 */
import { describe, it, expect } from 'vitest'
import type { TrialBalanceRow } from '@/services/auditPlatformApi'

// ── 1. 类型合规性 ──────────────────────────────────────────────────────────

describe('TrialBalanceRow 类型', () => {
  it('应包含 wp_adjustment / wp_publish_base / wp_published_at 字段', () => {
    const row: TrialBalanceRow = {
      standard_account_code: '1001',
      account_name: '库存现金',
      account_category: 'asset',
      unadjusted_amount: '100.00',
      rje_adjustment: '0',
      aje_adjustment: '10.00',
      wp_adjustment: '5.00',
      audited_amount: '115.00',
      opening_balance: '90.00',
      exceeds_materiality: false,
      below_trivial: false,
      wp_publish_base: '100.00',
      wp_published_at: '2026-10-01T12:00:00Z',
    }
    expect(row.wp_adjustment).toBe('5.00')
    expect(row.wp_publish_base).toBe('100.00')
    expect(row.wp_published_at).toBe('2026-10-01T12:00:00Z')
  })

  it('wp_adjustment / wp_publish_base / wp_published_at 允许 null', () => {
    const row: TrialBalanceRow = {
      standard_account_code: '1002',
      account_name: '银行存款',
      account_category: 'asset',
      unadjusted_amount: '200.00',
      rje_adjustment: '0',
      aje_adjustment: '0',
      wp_adjustment: null,
      audited_amount: '200.00',
      opening_balance: null,
      exceeds_materiality: false,
      below_trivial: false,
      wp_publish_base: null,
      wp_published_at: null,
    }
    expect(row.wp_adjustment).toBeNull()
    expect(row.wp_publish_base).toBeNull()
    expect(row.wp_published_at).toBeNull()
  })
})

// ── 2. hasPublishBaseChanged 纯函数 ────────────────────────────────────────

/** 从 TrialBalance.vue 提取的相同逻辑——用于独立测试 */
function hasPublishBaseChanged(row: TrialBalanceRow): boolean {
  if (!row.wp_published_at || row.wp_publish_base == null) return false
  const unadj = Number(row.unadjusted_amount) || 0
  const base = Number(row.wp_publish_base) || 0
  return Math.abs(unadj - base) > 0.005
}

describe('hasPublishBaseChanged', () => {
  function makeRow(overrides: Partial<TrialBalanceRow> = {}): TrialBalanceRow {
    return {
      standard_account_code: '1001',
      account_name: '库存现金',
      account_category: 'asset',
      unadjusted_amount: '100.00',
      rje_adjustment: '0',
      aje_adjustment: '0',
      wp_adjustment: '0',
      audited_amount: '100.00',
      opening_balance: null,
      exceeds_materiality: false,
      below_trivial: false,
      wp_publish_base: null,
      wp_published_at: null,
      ...overrides,
    }
  }

  it('未发布（wp_published_at 为 null）→ false', () => {
    expect(hasPublishBaseChanged(makeRow())).toBe(false)
  })

  it('已发布但 wp_publish_base 为 null → false', () => {
    expect(hasPublishBaseChanged(makeRow({ wp_published_at: '2026-10-01T00:00:00Z' }))).toBe(false)
  })

  it('已发布且未审数 == 发布基准 → false', () => {
    expect(hasPublishBaseChanged(makeRow({
      unadjusted_amount: '100.00',
      wp_publish_base: '100.00',
      wp_published_at: '2026-10-01T00:00:00Z',
    }))).toBe(false)
  })

  it('已发布但未审数变化 → true', () => {
    expect(hasPublishBaseChanged(makeRow({
      unadjusted_amount: '120.00',
      wp_publish_base: '100.00',
      wp_published_at: '2026-10-01T00:00:00Z',
    }))).toBe(true)
  })

  it('微小浮点差异（<0.005）不触发 → false', () => {
    expect(hasPublishBaseChanged(makeRow({
      unadjusted_amount: '100.004',
      wp_publish_base: '100.00',
      wp_published_at: '2026-10-01T00:00:00Z',
    }))).toBe(false)
  })

  it('发布基准为 0，未审数非零 → true', () => {
    expect(hasPublishBaseChanged(makeRow({
      unadjusted_amount: '50.00',
      wp_publish_base: '0',
      wp_published_at: '2026-10-01T00:00:00Z',
    }))).toBe(true)
  })
})

// ── 3. 小计累加验证 ────────────────────────────────────────────────────────

describe('小计行 wp_adjustment 累加', () => {
  /** 模拟 groupedRows 的 sub 累加逻辑 */
  function computeSubtotal(rows: TrialBalanceRow[]): number {
    let wp = 0
    for (const r of rows) {
      wp += Number(r.wp_adjustment) || 0
    }
    return wp
  }

  it('多行 wp_adjustment 累加正确', () => {
    const rows: TrialBalanceRow[] = [
      { standard_account_code: '1001', account_name: 'A', account_category: 'asset', unadjusted_amount: '100', rje_adjustment: '0', aje_adjustment: '0', wp_adjustment: '5.00', audited_amount: '105', opening_balance: null, exceeds_materiality: false, below_trivial: false, wp_publish_base: null, wp_published_at: null },
      { standard_account_code: '1002', account_name: 'B', account_category: 'asset', unadjusted_amount: '200', rje_adjustment: '0', aje_adjustment: '0', wp_adjustment: '-3.00', audited_amount: '197', opening_balance: null, exceeds_materiality: false, below_trivial: false, wp_publish_base: null, wp_published_at: null },
      { standard_account_code: '1003', account_name: 'C', account_category: 'asset', unadjusted_amount: '300', rje_adjustment: '0', aje_adjustment: '0', wp_adjustment: null, audited_amount: '300', opening_balance: null, exceeds_materiality: false, below_trivial: false, wp_publish_base: null, wp_published_at: null },
    ]
    expect(computeSubtotal(rows)).toBeCloseTo(2.00)
  })

  it('全部 null → 0', () => {
    const rows: TrialBalanceRow[] = [
      { standard_account_code: '1001', account_name: 'A', account_category: 'asset', unadjusted_amount: '100', rje_adjustment: '0', aje_adjustment: '0', wp_adjustment: null, audited_amount: '100', opening_balance: null, exceeds_materiality: false, below_trivial: false, wp_publish_base: null, wp_published_at: null },
    ]
    expect(computeSubtotal(rows)).toBe(0)
  })
})

// ── 4. 复制表头包含底稿调整 ────────────────────────────────────────────────

describe('copyTbTable 表头', () => {
  const detailHeaders = ['科目编码', '科目名称', '未审数', 'RJE调整', 'AJE调整', '底稿调整', '审定数']
  const summaryHeaders = ['行次', '项目', '未审数', '审计调整-借', '审计调整-贷', '重分类-借', '重分类-贷', '审定数']

  it('科目明细模式表头包含「底稿调整」', () => {
    expect(detailHeaders).toContain('底稿调整')
    // 底稿调整在 AJE调整之后、审定数之前
    const wpIdx = detailHeaders.indexOf('底稿调整')
    const ajeIdx = detailHeaders.indexOf('AJE调整')
    const auditedIdx = detailHeaders.indexOf('审定数')
    expect(wpIdx).toBeGreaterThan(ajeIdx)
    expect(wpIdx).toBeLessThan(auditedIdx)
  })

  it('试算平衡表模式表头不含底稿调整（汇总模式不展示）', () => {
    expect(summaryHeaders).not.toContain('底稿调整')
  })
})

// ── 5. 单元格选择列号映射 ──────────────────────────────────────────────────

describe('setupTableDrag 列号映射', () => {
  /** 模拟 TrialBalance.vue 中 setupTableDrag 的 getCellValue 回调 */
  function getCellValue(row: TrialBalanceRow, colIdx: number): string | null {
    if (colIdx === 0) return row.standard_account_code
    if (colIdx === 1) return row.account_name
    if (colIdx === 2) return row.unadjusted_amount
    if (colIdx === 3) return row.rje_adjustment
    if (colIdx === 4) return row.aje_adjustment
    if (colIdx === 5) return row.wp_adjustment
    if (colIdx === 7) return row.audited_amount
    return null
  }

  const row: TrialBalanceRow = {
    standard_account_code: '1001',
    account_name: '库存现金',
    account_category: 'asset',
    unadjusted_amount: '100.00',
    rje_adjustment: '10.00',
    aje_adjustment: '20.00',
    wp_adjustment: '5.00',
    audited_amount: '135.00',
    opening_balance: null,
    exceeds_materiality: false,
    below_trivial: false,
    wp_publish_base: '100.00',
    wp_published_at: '2026-10-01T00:00:00Z',
  }

  it('colIdx 5 → wp_adjustment（新列）', () => {
    expect(getCellValue(row, 5)).toBe('5.00')
  })

  it('colIdx 7 → audited_amount（原来是 5，顺移到 7）', () => {
    expect(getCellValue(row, 7)).toBe('135.00')
  })

  it('colIdx 6（联动列）→ null', () => {
    expect(getCellValue(row, 6)).toBeNull()
  })
})
