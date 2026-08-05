/**
 * useDiffSecuritiesData — 证券差异 additive 读回不丢 + 调账判断列迁移
 *   Property 1  diff-securities-v1 既有 payload 读→存→读逐字不变
 *   Property 2  need_adjust 点选枚举；旧 adjustment_note 非空映射「待定」+保留原文
 */
import { describe, it, expect } from 'vitest'
import { useDiffSecuritiesData, migrateAdjust } from '../useDiffSecuritiesData'
import type { SecuritiesDiffRow } from '../../diffSecuritiesTypes'

describe('Property 2 — migrateAdjust 调账判断列迁移', () => {
  it('非空 adjustment_note 且未设 need_adjust → 待定，保留原文', () => {
    const r = migrateAdjust({ adjustment_note: '待管理层确认' })
    expect(r.need_adjust).toBe('待定')
    expect(r.adjustment_note).toBe('待管理层确认')
  })

  it('已设 need_adjust 不被覆盖（幂等）', () => {
    const r = migrateAdjust({ need_adjust: '是', adjustment_note: '已确认调整' })
    expect(r.need_adjust).toBe('是')
    expect(r.adjustment_note).toBe('已确认调整')
    // 二次迁移不变
    expect(migrateAdjust(r).need_adjust).toBe('是')
  })

  it('adjustment_note 为空/空白 → 不设 need_adjust', () => {
    expect(migrateAdjust({}).need_adjust).toBeUndefined()
    expect(migrateAdjust({ adjustment_note: '   ' }).need_adjust).toBeUndefined()
  })
})

describe('Property 1 — additive 读回不丢', () => {
  const payload = {
    _format: 'diff-securities-v1' as const,
    rows: [
      {
        _row_id: 'r1', seq: 1,
        confirm_index: 'G0-3-001', security_name: '某股票',
        security_code: '600000', security_type: '股票',
        fund_account: 'ACC-1', account_holder: '本公司',
        booked_qty: 1000, booked_unit_fv: 10, booked_market_value: 10000,
        confirmed_qty: 1000, confirmed_unit_fv: 10.5, confirmed_market_value: 10500,
        diff_reason: '估值时点差异', support_evidence: '对账单',
        need_adjust: '是' as const, adjustment_note: '调增500',
        verify_conclusion: '已核实', remark: 'r',
      },
    ],
    conclusion: '结论', audit_note: '说明',
  }

  it('新增补列 + 源外字段读→存后逐字不变', () => {
    const data = useDiffSecuritiesData({ htmlData: () => payload, readonly: false })
    const out = data.buildPayload()
    const row = out.rows[0] as SecuritiesDiffRow
    // additive 补列
    expect(row.confirm_index).toBe('G0-3-001')
    expect(row.fund_account).toBe('ACC-1')
    expect(row.account_holder).toBe('本公司')
    expect(row.support_evidence).toBe('对账单')
    expect(row.need_adjust).toBe('是')
    // 源外增强保留
    expect(row.security_code).toBe('600000')
    expect(row.security_type).toBe('股票')
    expect(row.verify_conclusion).toBe('已核实')
    expect(row.adjustment_note).toBe('调增500')
    // 差异派生 —— 🔴 方向 = **账面 − 回函**（源模板表头 `差异③=①-②`）
    // 本 fixture：账面 10/10000 vs 回函 10.5/10500 → 账面低于回函 → 差异为**负**。
    // 原断言 `fv_diff=0.5` / `market_value_diff=500` 是旧方向（回函 − 账面）的镜像值，
    // 已随 Task 20（Requirement 10.2 / Property 27）纠正为负值。
    expect(row.qty_diff).toBe(0)
    expect(row.fv_diff).toBe(-0.5)
    expect(row.market_value_diff).toBe(-500)
  })

  it('差异方向为「账面 − 回函」：账面高于回函时三列为正（反向自检）', () => {
    const higherBook = {
      _format: 'diff-securities-v1' as const,
      rows: [
        {
          _row_id: 'r2',
          booked_qty: 1200,
          booked_unit_fv: 11,
          booked_market_value: 13200,
          confirmed_qty: 1000,
          confirmed_unit_fv: 10,
          confirmed_market_value: 10000,
        },
      ],
    }
    const data = useDiffSecuritiesData({ htmlData: () => higherBook, readonly: false })
    const row = data.rows.value[0]
    expect(row.qty_diff).toBe(200)
    expect(row.fv_diff).toBeCloseTo(1, 6)
    expect(row.market_value_diff).toBeCloseTo(3200, 6)
    // 有差异 → 仍被判定为差异行（下游全走 Math.abs，符号翻转不影响判定）
    expect(data.rowHasDiff(row)).toBe(true)
    expect(data.metrics.value.diff_count).toBe(1)
  })

  it('旧 payload（仅 adjustment_note 无 need_adjust）读入自动迁移待定', () => {
    const legacy = {
      _format: 'diff-securities-v1' as const,
      rows: [{ _row_id: 'r9', security_name: 'X', adjustment_note: '需复核' }],
    }
    const data = useDiffSecuritiesData({ htmlData: () => legacy, readonly: false })
    expect(data.rows.value[0].need_adjust).toBe('待定')
    expect(data.rows.value[0].adjustment_note).toBe('需复核')
  })
})
