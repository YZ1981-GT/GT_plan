/**
 * useConfirmationData.spec.ts — 函证汇总表数据核心 composable 单元测试
 *
 * 覆盖 Tasks 2.1 ~ 2.8:
 * - CRUD: addRow / deleteRows / updateField
 * - dashboardMetrics 响应式重算
 * - buildPayload 结构正确性
 * - computeConfirmedAmount 4 种业务规则
 * - coverageMetrics warn_level 阈值
 * - _overridden 标志保持用户值
 */
import { describe, it, expect, vi } from 'vitest'
import { ref, nextTick } from 'vue'
import { useConfirmationData } from '../useConfirmationData'
import type { ConfirmationRow, ConfirmationPayload } from '../../confirmationTypes'

// ─── 测试辅助 ────────────────────────────────────────────────────────────────

function createHtmlData(rows: ConfirmationRow[] = [], extra: Record<string, any> = {}) {
  return {
    _format: 'confirmation-v1' as const,
    rows,
    sampling: extra.sampling ?? {},
    notes: extra.notes ?? {},
    conclusion: extra.conclusion ?? {},
    ...extra,
  }
}

function makeRow(overrides: Partial<ConfirmationRow> = {}): ConfirmationRow {
  return {
    _row_id: `test-${Math.random().toString(36).slice(2, 8)}`,
    seq: 1,
    account_type: '应收账款',
    amount: 10000,
    ...overrides,
  }
}

function setup(rows: ConfirmationRow[] = [], extra: Record<string, any> = {}) {
  const data = ref(createHtmlData(rows, extra))
  const composable = useConfirmationData({
    htmlData: () => data.value,
    readonly: false,
  })
  return { composable, data }
}

// ─── CRUD 测试（Task 2.2） ───────────────────────────────────────────────────

describe('useConfirmationData - CRUD', () => {
  it('addRow 追加新行，序号自增', () => {
    const { composable } = setup([makeRow({ seq: 3 })])

    const newRow = composable.addRow()

    expect(newRow.seq).toBe(4)
    expect(newRow._row_id).toBeTruthy()
    expect(newRow._source).toBe('manual')
    expect(composable.rows.value).toHaveLength(2)
    expect(composable.isDirty.value).toBe(true)
  })

  it('addRow 空行列表时从 1 开始', () => {
    const { composable } = setup([])
    const newRow = composable.addRow()
    expect(newRow.seq).toBe(1)
  })

  it('deleteRows 按 _row_id 删除指定行', () => {
    const row1 = makeRow({ _row_id: 'r1', seq: 1 })
    const row2 = makeRow({ _row_id: 'r2', seq: 2 })
    const row3 = makeRow({ _row_id: 'r3', seq: 3 })
    const { composable } = setup([row1, row2, row3])

    composable.deleteRows(['r1', 'r3'])

    expect(composable.rows.value).toHaveLength(1)
    expect(composable.rows.value[0]._row_id).toBe('r2')
    expect(composable.isDirty.value).toBe(true)
  })

  it('deleteRows 空数组不影响数据', () => {
    const { composable } = setup([makeRow()])
    composable.deleteRows([])
    expect(composable.rows.value).toHaveLength(1)
  })

  it('updateField 更新指定行字段', () => {
    const row = makeRow({ _row_id: 'r1', entity_name: '旧名称' })
    const { composable } = setup([row])

    composable.updateField('r1', 'entity_name', '新名称')

    expect(composable.rows.value[0].entity_name).toBe('新名称')
    expect(composable.isDirty.value).toBe(true)
  })

  it('updateField 不存在的 rowId 静默忽略', () => {
    const { composable } = setup([makeRow({ _row_id: 'r1' })])
    composable.updateField('nonexistent', 'entity_name', '值')
    expect(composable.rows.value[0].entity_name).toBeUndefined()
  })
})

// ─── dashboardMetrics 响应式重算（Task 2.4） ──────────────────────────────────

describe('useConfirmationData - dashboardMetrics', () => {
  it('按 account_type 聚合指标', () => {
    const rows = [
      makeRow({ account_type: '应收账款', amount: 5000, is_replied: true, match_status: '相符' }),
      makeRow({ account_type: '应收账款', amount: 3000, is_replied: true, match_status: '不符', reply_amount: 2500 }),
      makeRow({ account_type: '合同负债', amount: 8000, is_replied: false, match_status: '未回函', confirmation_method: '消极式' }),
    ]
    const { composable } = setup(rows)

    const metrics = composable.dashboardMetrics.value
    expect(metrics).toHaveLength(2)

    const ar = metrics.find((m) => m.account_type === '应收账款')!
    expect(ar.total_count).toBe(2)
    expect(ar.replied_count).toBe(2)
    expect(ar.matched_count).toBe(1)
    expect(ar.total_amount).toBe(8000)
    // 相符=5000, 不符=reply_amount=2500
    expect(ar.confirmed_amount).toBe(7500)

    const cl = metrics.find((m) => m.account_type === '合同负债')!
    expect(cl.total_count).toBe(1)
    expect(cl.replied_count).toBe(0)
    // 消极式未回函→amount=8000
    expect(cl.confirmed_amount).toBe(8000)
  })

  it('添加行后 dashboardMetrics 响应式更新', () => {
    const { composable } = setup([
      makeRow({ account_type: '应收账款', amount: 1000, match_status: '相符' }),
    ])

    expect(composable.dashboardMetrics.value[0].total_count).toBe(1)

    // 添加一行
    const newRow = composable.addRow()
    composable.updateField(newRow._row_id!, 'account_type', '应收账款')
    composable.updateField(newRow._row_id!, 'amount', 2000)
    composable.updateField(newRow._row_id!, 'match_status', '相符')

    const updated = composable.dashboardMetrics.value.find((m) => m.account_type === '应收账款')!
    expect(updated.total_count).toBe(2)
    expect(updated.total_amount).toBe(3000)
  })
})

// ─── buildPayload 结构测试（Task 2.6） ────────────────────────────────────────

describe('useConfirmationData - buildPayload', () => {
  it('返回完整 ConfirmationPayload 结构', () => {
    const rows = [makeRow({ match_status: '相符', amount: 1000 })]
    const { composable } = setup(rows, {
      sampling: { sampling_method: '统计抽样' },
      notes: { note_general: '正常' },
      conclusion: { conclusion_type: 'A', conclusion_text: '无保留' },
    })

    const payload = composable.buildPayload()

    expect(payload._format).toBe('confirmation-v1')
    expect(payload.rows).toHaveLength(1)
    expect(payload.rows[0].confirmed_amount).toBe(1000)
    expect(payload.rows[0].difference).toBe(0) // 相符 → 0
    expect(payload.summary_config?.account_types).toContain('应收账款')
    expect(payload.sampling.sampling_method).toBe('统计抽样')
    expect(payload.notes.note_general).toBe('正常')
    expect(payload.conclusion.conclusion_type).toBe('A')
  })

  it('buildPayload 中 confirmed_amount 实时重算', () => {
    const row = makeRow({
      match_status: '不符',
      amount: 5000,
      reply_amount: 4000,
    })
    const { composable } = setup([row])
    const payload = composable.buildPayload()

    // 不符→reply_amount
    expect(payload.rows[0].confirmed_amount).toBe(4000)
    // difference = amount - reply_amount
    expect(payload.rows[0].difference).toBe(1000)
  })
})

// ─── computeConfirmedAmount 4 种业务规则（Task 2.5） ──────────────────────────

describe('useConfirmationData - computeConfirmedAmount', () => {
  it('相符 → amount', () => {
    const { composable } = setup([])
    const row = makeRow({ match_status: '相符', amount: 10000, reply_amount: 10000 })
    expect(composable.computeConfirmedAmount(row)).toBe(10000)
  })

  it('不符 → reply_amount', () => {
    const { composable } = setup([])
    const row = makeRow({ match_status: '不符', amount: 10000, reply_amount: 8000 })
    expect(composable.computeConfirmedAmount(row)).toBe(8000)
  })

  it('未回函 + 消极式 → amount（视同确认）', () => {
    const { composable } = setup([])
    const row = makeRow({
      match_status: '未回函',
      confirmation_method: '消极式',
      amount: 6000,
    })
    expect(composable.computeConfirmedAmount(row)).toBe(6000)
  })

  it('未回函 + 积极式 → alt_confirmed ?? 0', () => {
    const { composable } = setup([])

    // 有 alt_confirmed
    const row1 = makeRow({
      match_status: '未回函',
      confirmation_method: '积极式',
      amount: 6000,
      alt_confirmed: 5500,
    })
    expect(composable.computeConfirmedAmount(row1)).toBe(5500)

    // 无 alt_confirmed
    const row2 = makeRow({
      match_status: '未回函',
      confirmation_method: '积极式',
      amount: 6000,
    })
    expect(composable.computeConfirmedAmount(row2)).toBe(0)
  })

  it('_overridden=true 保持用户值', () => {
    const { composable } = setup([])
    const row = makeRow({
      match_status: '相符',
      amount: 10000,
      confirmed_amount: 7777,
      _overridden: true,
    })
    // 即使规则计算应该是 10000，但用户覆盖优先
    expect(composable.computeConfirmedAmount(row)).toBe(7777)
  })

  it('无 match_status 默认返回 0', () => {
    const { composable } = setup([])
    const row = makeRow({ amount: 5000 })
    expect(composable.computeConfirmedAmount(row)).toBe(0)
  })
})

// ─── coverageMetrics & warn_level（Task 2.8） ─────────────────────────────────

describe('useConfirmationData - coverageMetrics', () => {
  it('回函率 < 80% → danger', () => {
    // 10 行中只有 7 行回函 = 70% < 80%
    const rows = Array.from({ length: 10 }, (_, i) =>
      makeRow({
        _row_id: `r${i}`,
        seq: i + 1,
        amount: 1000,
        is_replied: i < 7,
        match_status: i < 7 ? '相符' : '未回函',
        confirmation_method: '积极式',
      })
    )
    const { composable } = setup(rows)
    const metrics = composable.coverageMetrics.value

    expect(metrics.reply_coverage).toBe(70)
    expect(metrics.warn_level).toBe('danger')
  })

  it('回函率 >= 80% 且覆盖率 < 50% → warn', () => {
    // 10 行全回函（reply=100%），但 confirmed 只有少量
    const rows = Array.from({ length: 10 }, (_, i) =>
      makeRow({
        _row_id: `r${i}`,
        seq: i + 1,
        amount: 10000,
        is_replied: true,
        match_status: '不符',
        // reply_amount 很小，使确认金额 < 50% 总额
        reply_amount: i < 4 ? 10000 : 0,
      })
    )
    const { composable } = setup(rows)
    const metrics = composable.coverageMetrics.value

    expect(metrics.reply_coverage).toBe(100)
    // confirmed = 4*10000 = 40000, total = 100000, coverage = 40%
    expect(metrics.confirmation_coverage).toBe(40)
    expect(metrics.warn_level).toBe('warn')
  })

  it('回函率 >= 80% 且覆盖率 >= 50% → ok', () => {
    const rows = Array.from({ length: 10 }, (_, i) =>
      makeRow({
        _row_id: `r${i}`,
        seq: i + 1,
        amount: 1000,
        is_replied: true,
        match_status: '相符',
      })
    )
    const { composable } = setup(rows)
    const metrics = composable.coverageMetrics.value

    expect(metrics.reply_coverage).toBe(100)
    expect(metrics.confirmation_coverage).toBe(100)
    expect(metrics.warn_level).toBe('ok')
  })

  it('空行列表不除零', () => {
    const { composable } = setup([])
    const metrics = composable.coverageMetrics.value
    expect(metrics.confirmation_coverage).toBe(0)
    expect(metrics.reply_coverage).toBe(0)
    expect(metrics.warn_level).toBe('danger') // 0% < 80% → danger
  })
})

// ─── _overridden 标志在 updateField 中的行为 ──────────────────────────────────

describe('useConfirmationData - _overridden flag', () => {
  it('updateField 更新非 confirmed_amount 字段时自动重算', () => {
    const row = makeRow({
      _row_id: 'r1',
      match_status: '相符',
      amount: 5000,
    })
    const { composable } = setup([row])

    // 修改 amount → confirmed_amount 应该跟着变
    composable.updateField('r1', 'amount', 8000)
    expect(composable.rows.value[0].confirmed_amount).toBe(8000)
  })

  it('_overridden=true 时 updateField 其他字段不覆盖 confirmed_amount', () => {
    const row = makeRow({
      _row_id: 'r1',
      match_status: '相符',
      amount: 5000,
      confirmed_amount: 9999,
      _overridden: true,
    })
    const { composable } = setup([row])

    // 修改 amount，但因为 _overridden=true，confirmed_amount 不变
    composable.updateField('r1', 'amount', 8000)
    expect(composable.rows.value[0].confirmed_amount).toBe(9999)
  })
})

// ─── Account Tabs（Task 2.3） ────────────────────────────────────────────────

describe('useConfirmationData - accountTabs', () => {
  it('去重排序科目大类', () => {
    const rows = [
      makeRow({ account_type: '合同负债' }),
      makeRow({ account_type: '应收账款' }),
      makeRow({ account_type: '合同负债' }),
      makeRow({ account_type: '银行存款' }),
    ]
    const { composable } = setup(rows)
    expect(composable.accountTabs.value).toEqual(['合同负债', '应收账款', '银行存款'])
  })

  it('activeTab 空字符串 = 全部', () => {
    const rows = [
      makeRow({ _row_id: 'r1', account_type: '应收账款' }),
      makeRow({ _row_id: 'r2', account_type: '合同负债' }),
    ]
    const { composable } = setup(rows)

    expect(composable.activeTab.value).toBe('')
    expect(composable.filteredRows.value).toHaveLength(2)
  })

  it('设置 activeTab 过滤行', () => {
    const rows = [
      makeRow({ _row_id: 'r1', account_type: '应收账款' }),
      makeRow({ _row_id: 'r2', account_type: '合同负债' }),
      makeRow({ _row_id: 'r3', account_type: '应收账款' }),
    ]
    const { composable } = setup(rows)

    composable.activeTab.value = '应收账款'
    expect(composable.filteredRows.value).toHaveLength(2)
    expect(composable.filteredRows.value.every((r) => r.account_type === '应收账款')).toBe(true)
  })
})

// ─── 初始化（Task 2.1） ──────────────────────────────────────────────────────

describe('useConfirmationData - initialization', () => {
  it('非 confirmation-v1 格式初始化为空', () => {
    const data = ref({ _format: 'other', rows: [{ amount: 100 }] })
    const composable = useConfirmationData({
      htmlData: () => data.value,
      readonly: false,
    })
    expect(composable.rows.value).toHaveLength(0)
  })

  it('null htmlData 初始化为空', () => {
    const composable = useConfirmationData({
      htmlData: () => null,
      readonly: false,
    })
    expect(composable.rows.value).toHaveLength(0)
    expect(composable.isDirty.value).toBe(false)
  })

  it('正确解析 confirmation-v1 数据', () => {
    const rows = [makeRow({ amount: 5000 }), makeRow({ amount: 3000 })]
    const { composable } = setup(rows, {
      sampling: { sampling_method: '全部发函' },
    })

    expect(composable.rows.value).toHaveLength(2)
    expect(composable.sampling.value.sampling_method).toBe('全部发函')
    expect(composable.isDirty.value).toBe(false)
  })

  it('缺少 _row_id 的行自动生成 ID', () => {
    const rows = [{ seq: 1, amount: 1000 } as ConfirmationRow]
    const { composable } = setup(rows)
    expect(composable.rows.value[0]._row_id).toBeTruthy()
  })
})
