/**
 * K9 管理费用 — 集成测试（composable联动逻辑）
 *
 * Spec: .kiro/specs/k9-admin-expenses/ Task 7.2
 * Requirements: 2.5, 4.4, 5.4, 7.1
 *
 * 测试：
 * - useK9Adjudication: 行创建/单元格更新/computedRows公式重算/合计行/TB回写
 * - useK9Detail: 添加行 + 月度数据 → subtotal联动
 * - useK9Analysis: 设置行数据 → isAbnormal自动标记
 * - useK9Cutoff: 添加样本 + 跨期日期 → isCross自动计算
 * - useK9CrossSheet: adjudicationVsDetail交叉验证
 * - useK9FormData: setTbValues更新state
 *
 * Mock: http调用（无后端依赖），eventBus验证
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'

// ─── Mock http / eventBus / ElMessage before imports ─────────────────────────

vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { data: [] } }),
    put: vi.fn().mockResolvedValue({ data: { code: 0 } }),
    post: vi.fn().mockResolvedValue({ data: { code: 0 } }),
  },
}))

vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
  ElMessageBox: { prompt: vi.fn().mockResolvedValue({ value: 'test' }) },
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: { data: [] } }),
    put: vi.fn().mockResolvedValue({ data: { code: 0 } }),
    post: vi.fn().mockResolvedValue({ data: { code: 0 } }),
  },
}))

import { useK9Adjudication } from '../composables/useK9Adjudication'
import { useK9Detail } from '../composables/useK9Detail'
import { useK9Analysis } from '../composables/useK9Analysis'
import { useK9Cutoff } from '../composables/useK9Cutoff'
import { useK9CrossSheet } from '../composables/useK9CrossSheet'

// ═══════════════════════════════════════════════════════════════════════════════
// useK9Adjudication — 行CRUD + 公式重算
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK9Adjudication — 集成', () => {
  let allResponses: ReturnType<typeof ref<Map<string, any>>>
  let saveSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    allResponses = ref(new Map())
    saveSpy = vi.fn()
  })

  it('初始化后默认行存在', () => {
    const adj = useK9Adjudication({
      allResponses,
      projectId: ref('p1'),
      wpId: ref('wp1'),
      onSave: saveSpy,
    })
    expect(adj.rows.value.length).toBeGreaterThan(0)
    // 默认行包含"职工薪酬"等
    const names = adj.rows.value.map(r => r.projectName)
    expect(names).toContain('职工薪酬')
    expect(names).toContain('办公费')
  })

  it('updateCell → computedRows重算审定数', async () => {
    const adj = useK9Adjudication({
      allResponses,
      projectId: ref('p1'),
      wpId: ref('wp1'),
      onSave: saveSpy,
    })
    const firstRow = adj.rows.value[0]
    // 设置借方=1000, 贷方=200 → 未审=800, AJE=100, RJE=50 → 审定=950
    adj.updateCell(firstRow.rowKey, 'unadjustedDebit', 1000)
    adj.updateCell(firstRow.rowKey, 'unadjustedCredit', 200)
    adj.updateCell(firstRow.rowKey, 'aje', 100)
    adj.updateCell(firstRow.rowKey, 'rje', 50)
    await nextTick()

    const updated = adj.rows.value.find(r => r.rowKey === firstRow.rowKey)!
    // 未审 = 1000 - 200 = 800
    expect(updated.unadjusted).toBe(800)
    // 审定 = 800 + 100 + 50 = 950
    expect(updated.audited).toBe(950)
  })

  it('addRow → 行数增加', () => {
    const adj = useK9Adjudication({
      allResponses,
      projectId: ref('p1'),
      wpId: ref('wp1'),
      onSave: saveSpy,
    })
    const before = adj.rows.value.length
    adj.addRow('新增费用项')
    expect(adj.rows.value.length).toBe(before + 1)
    const last = adj.rows.value[adj.rows.value.length - 1]
    expect(last.projectName).toBe('新增费用项')
    expect(last.audited).toBe(0)
  })

  it('totalRow合计正确', async () => {
    const adj = useK9Adjudication({
      allResponses,
      projectId: ref('p1'),
      wpId: ref('wp1'),
      onSave: saveSpy,
    })
    const row1 = adj.rows.value[0]
    const row2 = adj.rows.value[1]
    adj.updateCell(row1.rowKey, 'unadjustedDebit', 500)
    adj.updateCell(row2.rowKey, 'unadjustedDebit', 300)
    await nextTick()

    // totalRow.unadjustedDebit = 500 + 300 + 其他行0 = 800
    expect(adj.totalRow.value.unadjustedDebit).toBe(800)
  })

  it('removeRow → 行数减少', () => {
    const adj = useK9Adjudication({
      allResponses,
      projectId: ref('p1'),
      wpId: ref('wp1'),
      onSave: saveSpy,
    })
    const before = adj.rows.value.length
    const firstKey = adj.rows.value[0].rowKey
    adj.removeRow(firstKey)
    expect(adj.rows.value.length).toBe(before - 1)
  })

  it('isReadonly=true时updateCell无效', () => {
    const adj = useK9Adjudication({
      allResponses,
      projectId: ref('p1'),
      wpId: ref('wp1'),
      isReadonly: ref(true),
      onSave: saveSpy,
    })
    const row = adj.rows.value[0]
    adj.updateCell(row.rowKey, 'unadjustedDebit', 9999)
    // 只读模式下不应修改
    expect(adj.rows.value[0].unadjustedDebit).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useK9Detail — 月度数据 + subtotal
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK9Detail — 集成', () => {
  let allResponses: ReturnType<typeof ref<Map<string, any>>>
  let saveSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    allResponses = ref(new Map())
    saveSpy = vi.fn()
  })

  it('addRow后行数增加', () => {
    const detail = useK9Detail({
      allResponses,
      projectId: ref('p1'),
      wpId: ref('wp1'),
      onSave: saveSpy,
    })
    detail.addRow('差旅费', '660201')
    expect(detail.rows.value.length).toBe(1)
    expect(detail.rows.value[0].accountName).toBe('差旅费')
  })

  it('月度数据更新 → subtotal联动', async () => {
    const detail = useK9Detail({
      allResponses,
      projectId: ref('p1'),
      wpId: ref('wp1'),
      onSave: saveSpy,
    })
    detail.addRow('办公费', '660202')
    const rowKey = detail.rows.value[0].rowKey

    // 1月=1000, 2月=2000, 3月=500
    detail.updateCell(rowKey, 'month-0', 1000)
    detail.updateCell(rowKey, 'month-1', 2000)
    detail.updateCell(rowKey, 'month-2', 500)
    await nextTick()

    const updated = detail.rows.value[0]
    // unadjTotal = SUM(months) = 3500
    expect(updated.unadjTotal).toBe(3500)
    // audited = unadjTotal + aje + rje = 3500 + 0 + 0 = 3500
    expect(updated.audited).toBe(3500)
    // subtotal也应为3500
    expect(detail.subtotal.value.unadjTotal).toBe(3500)
    expect(detail.subtotal.value.audited).toBe(3500)
  })

  it('多行subtotal合计', async () => {
    const detail = useK9Detail({
      allResponses,
      projectId: ref('p1'),
      wpId: ref('wp1'),
      onSave: saveSpy,
    })
    detail.addRow('办公费', '660202')
    detail.addRow('差旅费', '660203')
    const key1 = detail.rows.value[0].rowKey
    const key2 = detail.rows.value[1].rowKey

    detail.updateCell(key1, 'month-0', 1000)
    detail.updateCell(key2, 'month-0', 500)
    await nextTick()

    expect(detail.subtotal.value.unadjTotal).toBe(1500)
    expect(detail.subtotal.value.months[0]).toBe(1500)
  })

  it('AJE/RJE影响审定数', async () => {
    const detail = useK9Detail({
      allResponses,
      projectId: ref('p1'),
      wpId: ref('wp1'),
      onSave: saveSpy,
    })
    detail.addRow('中介费', '660204')
    const rowKey = detail.rows.value[0].rowKey

    detail.updateCell(rowKey, 'month-0', 2000)
    detail.updateCell(rowKey, 'aje', 300)
    detail.updateCell(rowKey, 'rje', -100)
    await nextTick()

    const row = detail.rows.value[0]
    expect(row.unadjTotal).toBe(2000)
    // audited = 2000 + 300 + (-100) = 2200
    expect(row.audited).toBe(2200)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useK9Analysis — isAbnormal标记
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK9Analysis — 集成', () => {
  let allResponses: ReturnType<typeof ref<Map<string, any>>>
  let saveSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    allResponses = ref(new Map())
    saveSpy = vi.fn()
  })

  it('populateFromDetail后行自动计算', async () => {
    const analysis = useK9Analysis({
      allResponses,
      projectId: ref('p1'),
      wpId: ref('wp1'),
      revenue: ref(100000),
      onSave: saveSpy,
    })
    analysis.populateFromDetail([
      { projectName: '办公费', audited: 5000, priorAmount: 3000 },
      { projectName: '差旅费', audited: 2000, priorAmount: 10000 },
    ])
    await nextTick()

    const rows = analysis.rows.value
    expect(rows.length).toBe(2)

    // 办公费: (5000-3000)/|3000| = 0.667 > 0.3 → abnormal
    expect(rows[0].changeRate).toBeCloseTo(0.667, 2)
    expect(rows[0].isAbnormal).toBe(true)

    // 差旅费: (2000-10000)/|10000| = -0.8 → |−0.8|>0.3 → abnormal
    expect(rows[1].changeRate).toBeCloseTo(-0.8)
    expect(rows[1].isAbnormal).toBe(true)
  })

  it('正常项目不标记abnormal', async () => {
    const analysis = useK9Analysis({
      allResponses,
      projectId: ref('p1'),
      wpId: ref('wp1'),
      revenue: ref(100000),
      onSave: saveSpy,
    })
    analysis.populateFromDetail([
      // (1100-1000)/|1000| = 0.1 < 0.3 → normal
      { projectName: '水电费', audited: 1100, priorAmount: 1000 },
    ])
    await nextTick()

    expect(analysis.rows.value[0].isAbnormal).toBe(false)
    expect(analysis.rows.value[0].changeRate).toBeCloseTo(0.1)
  })

  it('summary正确统计异常项目数', async () => {
    const analysis = useK9Analysis({
      allResponses,
      projectId: ref('p1'),
      wpId: ref('wp1'),
      revenue: ref(100000),
      onSave: saveSpy,
    })
    analysis.populateFromDetail([
      { projectName: '办公费', audited: 5000, priorAmount: 3000 }, // abnormal
      { projectName: '水电费', audited: 1100, priorAmount: 1000 }, // normal
      { projectName: '差旅费', audited: 200, priorAmount: 10000 }, // abnormal
    ])
    await nextTick()

    expect(analysis.summary.value.totalItems).toBe(3)
    expect(analysis.summary.value.abnormalCount).toBe(2)
    expect(analysis.summary.value.normalCount).toBe(1)
    expect(analysis.summary.value.abnormalProjects).toContain('办公费')
    expect(analysis.summary.value.abnormalProjects).toContain('差旅费')
  })

  it('占收入比正确计算', async () => {
    const analysis = useK9Analysis({
      allResponses,
      projectId: ref('p1'),
      wpId: ref('wp1'),
      revenue: ref(50000),
      onSave: saveSpy,
    })
    analysis.populateFromDetail([
      { projectName: '办公费', audited: 5000, priorAmount: 3000 },
    ])
    await nextTick()

    // 5000/50000 = 0.1
    expect(analysis.rows.value[0].ratioToRevenue).toBeCloseTo(0.1)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useK9Cutoff — 跨期日期计算
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK9Cutoff — 集成', () => {
  let allResponses: ReturnType<typeof ref<Map<string, any>>>
  let saveSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    allResponses = ref(new Map())
    saveSpy = vi.fn()
  })

  it('addSample → 样本数增加', () => {
    const cutoff = useK9Cutoff({
      direction: 'V2S',
      allResponses,
      projectId: ref('p1'),
      wpId: ref('wp1'),
      periodEnd: ref('2025-12-31'),
      onSave: saveSpy,
    })
    cutoff.addSample({
      voucherNo: 'V001',
      bookDate: '2025-12-30',
      sourceDate: '2025-12-28',
      amount: 5000,
    })
    expect(cutoff.samples.value.length).toBe(1)
  })

  it('同期日期 → isCross=false', async () => {
    const cutoff = useK9Cutoff({
      direction: 'V2S',
      allResponses,
      projectId: ref('p1'),
      wpId: ref('wp1'),
      periodEnd: ref('2025-12-31'),
      onSave: saveSpy,
    })
    cutoff.addSample({
      voucherNo: 'V001',
      bookDate: '2025-12-30',
      sourceDate: '2025-12-28',
    })
    await nextTick()

    expect(cutoff.samples.value[0].isCross).toBe(false)
  })

  it('跨期日期 → isCross=true', async () => {
    const cutoff = useK9Cutoff({
      direction: 'V2S',
      allResponses,
      projectId: ref('p1'),
      wpId: ref('wp1'),
      periodEnd: ref('2025-12-31'),
      onSave: saveSpy,
    })
    cutoff.addSample({
      voucherNo: 'V002',
      bookDate: '2026-01-03', // 1月记账
      sourceDate: '2025-12-29', // 12月原始凭证
    })
    await nextTick()

    expect(cutoff.samples.value[0].isCross).toBe(true)
  })

  it('updateCell修改日期后 → isCross自动重算', async () => {
    const cutoff = useK9Cutoff({
      direction: 'V2S',
      allResponses,
      projectId: ref('p1'),
      wpId: ref('wp1'),
      periodEnd: ref('2025-12-31'),
      onSave: saveSpy,
    })
    cutoff.addSample({
      voucherNo: 'V003',
      bookDate: '2025-12-30',
      sourceDate: '2025-12-28',
    })
    await nextTick()
    expect(cutoff.samples.value[0].isCross).toBe(false)

    // 把bookDate改到次月
    const rowKey = cutoff.samples.value[0].rowKey
    cutoff.updateCell(rowKey, 'bookDate', '2026-01-05')
    await nextTick()
    expect(cutoff.samples.value[0].isCross).toBe(true)
  })

  it('summary统计跨期项目数', async () => {
    const cutoff = useK9Cutoff({
      direction: 'S2V',
      allResponses,
      projectId: ref('p1'),
      wpId: ref('wp1'),
      periodEnd: ref('2025-12-31'),
      onSave: saveSpy,
    })
    cutoff.addSample({ voucherNo: 'V1', bookDate: '2025-12-30', sourceDate: '2025-12-28' })
    cutoff.addSample({ voucherNo: 'V2', bookDate: '2026-01-02', sourceDate: '2025-12-29' })
    cutoff.addSample({ voucherNo: 'V3', bookDate: '2026-01-05', sourceDate: '2025-12-31' })
    await nextTick()

    // V1同期，V2跨期，V3跨期
    expect(cutoff.summary.value.totalSamples).toBe(3)
    expect(cutoff.summary.value.crossPeriodCount).toBe(2)
    expect(cutoff.summary.value.normalCount).toBe(1)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useK9CrossSheet — adjudicationVsDetail 交叉验证
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK9CrossSheet — 集成', () => {
  it('两端一致 → isMatch=true', async () => {
    const allResponses = ref(new Map<string, any>([
      ['K9-1-audited-total', { remark: '15000' }],
      ['K9-2-total-audited', { remark: '15000' }],
    ]))
    const cross = useK9CrossSheet(allResponses)
    await nextTick()

    expect(cross.adjudicationVsDetail.value.isMatch).toBe(true)
    expect(cross.adjudicationVsDetail.value.diff).toBeCloseTo(0)
  })

  it('两端不一致 → isMatch=false, diff有值', async () => {
    const allResponses = ref(new Map<string, any>([
      ['K9-1-audited-total', { remark: '15000' }],
      ['K9-2-total-audited', { remark: '14500' }],
    ]))
    const cross = useK9CrossSheet(allResponses)
    await nextTick()

    expect(cross.adjudicationVsDetail.value.isMatch).toBe(false)
    expect(cross.adjudicationVsDetail.value.diff).toBeCloseTo(500)
  })

  it('allResponses为空 → diff=0, isMatch=true', async () => {
    const allResponses = ref(new Map<string, any>())
    const cross = useK9CrossSheet(allResponses)
    await nextTick()

    expect(cross.adjudicationVsDetail.value.diff).toBe(0)
    expect(cross.adjudicationVsDetail.value.isMatch).toBe(true)
  })

  it('analysisVsDetail 验证', async () => {
    const allResponses = ref(new Map<string, any>([
      ['K9-4-analysis-total', { remark: '10000' }],
      ['K9-2-total-audited', { remark: '10000' }],
    ]))
    const cross = useK9CrossSheet(allResponses)
    await nextTick()

    expect(cross.analysisVsDetail.value.isMatch).toBe(true)
  })

  it('analysisVsDetail 不匹配', async () => {
    const allResponses = ref(new Map<string, any>([
      ['K9-4-analysis-total', { remark: '10000' }],
      ['K9-2-total-audited', { remark: '9500' }],
    ]))
    const cross = useK9CrossSheet(allResponses)
    await nextTick()

    expect(cross.analysisVsDetail.value.isMatch).toBe(false)
  })
})
