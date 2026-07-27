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

function setup(
  rows: ConfirmationRow[] = [],
  extra: Record<string, any> = {},
  population: number | null = null,
) {
  const data = ref(createHtmlData(rows, extra))
  const composable = useConfirmationData({
    htmlData: () => data.value,
    readonly: false,
    population: () => population,
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
  // P5: 回函覆盖率 = 已回函笔数 / 已发函笔数（笔数口径）
  it('回函覆盖率 < 80% → danger（笔数口径 repliedCount/sentCount）', () => {
    // 10 行全已发函（带 confirmation_method），仅 7 行回函 = 70% < 80%
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
    const { composable } = setup(rows, {}, 10000)
    const metrics = composable.coverageMetrics.value

    expect(metrics.reply_coverage).toBe(70) // 7/10（sentCount=10 全在途）
    expect(metrics.warn_level).toBe('danger')
  })

  // P6: 已发函笔数用在途语义，非 rows.length（未发函行不计入分母）
  it('未发函行不计入已发函笔数（sentCount 用在途语义）', () => {
    const rows = [
      // 已发函且回函
      makeRow({ _row_id: 'a', amount: 1000, is_replied: true, match_status: '相符' }),
      makeRow({ _row_id: 'b', amount: 1000, is_replied: true, match_status: '相符' }),
      // 未发函（无任何在途信号）→ 不计入 sentCount 分母
      makeRow({ _row_id: 'c', amount: 1000 }),
    ]
    const { composable } = setup(rows, {}, 100000)
    const metrics = composable.coverageMetrics.value
    // sentCount=2, replied=2 → 100%（而非 2/3=66.7 的总笔数口径）
    expect(metrics.reply_coverage).toBe(100)
  })

  // P1/P3/P9: population 可用时函证/确认覆盖率以 population 为分母
  it('回函达标但函证覆盖率 < 50% → warn（population 分母）', () => {
    // 10 行全回函，发函总额=100000；population=250000 → 函证覆盖率=40% < 50%
    const rows = Array.from({ length: 10 }, (_, i) =>
      makeRow({
        _row_id: `r${i}`,
        seq: i + 1,
        amount: 10000,
        is_replied: true,
        match_status: '不符',
        reply_amount: i < 4 ? 10000 : 0,
      })
    )
    const { composable } = setup(rows, {}, 250000)
    const metrics = composable.coverageMetrics.value

    expect(metrics.reply_coverage).toBe(100)
    expect(metrics.confirmation_coverage).toBe(40) // 100000/250000
    expect(metrics.confirmed_coverage).toBe(16)    // 40000/250000
    expect(metrics.population_available).toBe(true)
    expect(metrics.warn_level).toBe('warn')
  })

  it('回函达标且函证覆盖率 >= 50% → ok', () => {
    const rows = Array.from({ length: 10 }, (_, i) =>
      makeRow({
        _row_id: `r${i}`,
        seq: i + 1,
        amount: 1000,
        is_replied: true,
        match_status: '相符',
      })
    )
    // 发函总额=10000；population=10000 → 函证覆盖率=100%
    const { composable } = setup(rows, {}, 10000)
    const metrics = composable.coverageMetrics.value

    expect(metrics.reply_coverage).toBe(100)
    expect(metrics.confirmation_coverage).toBe(100)
    expect(metrics.warn_level).toBe('ok')
  })

  // P2: population 缺失 → 覆盖率 null 且不误导，warn_level 仅由回函率决定
  it('population 缺失 → 函证/确认覆盖率为 null，population_available=false', () => {
    const rows = Array.from({ length: 5 }, (_, i) =>
      makeRow({ _row_id: `r${i}`, amount: 1000, is_replied: true, match_status: '相符' })
    )
    const { composable } = setup(rows, {}, null) // 无 population
    const metrics = composable.coverageMetrics.value

    expect(metrics.confirmation_coverage).toBeNull()
    expect(metrics.confirmed_coverage).toBeNull()
    expect(metrics.population_available).toBe(false)
    expect(metrics.reply_coverage).toBe(100) // 回函率仍算
    expect(metrics.warn_level).toBe('ok')    // 仅由回函率决定（100≥80）
  })

  it('population 缺失 + 回函率不足 → 仍 danger（仅由回函率决定）', () => {
    const rows = Array.from({ length: 10 }, (_, i) =>
      makeRow({
        _row_id: `r${i}`,
        amount: 1000,
        is_replied: i < 5,
        match_status: i < 5 ? '相符' : '未回函',
        confirmation_method: '积极式',
      })
    )
    const { composable } = setup(rows, {}, null)
    const metrics = composable.coverageMetrics.value
    expect(metrics.confirmation_coverage).toBeNull()
    expect(metrics.reply_coverage).toBe(50)
    expect(metrics.warn_level).toBe('danger')
  })

  it('population <= 0 视为不可用', () => {
    const rows = [makeRow({ amount: 1000, is_replied: true, match_status: '相符' })]
    const { composable } = setup(rows, {}, 0)
    const metrics = composable.coverageMetrics.value
    expect(metrics.confirmation_coverage).toBeNull()
    expect(metrics.population_available).toBe(false)
  })

  // P5 除零 + P2 空态
  it('空行列表不除零', () => {
    const { composable } = setup([], {}, 10000)
    const metrics = composable.coverageMetrics.value
    expect(metrics.confirmation_coverage).toBe(0) // 发函总额 0 / population = 0
    expect(metrics.reply_coverage).toBe(0)         // sentCount=0 → 0
    expect(metrics.warn_level).toBe('danger')      // 回函率 0 < 80
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

// ─── E0 重建：Summary_Sheet 承载五类账户（Task 3.2 / Property 13） ──────────

describe('E0 accountTabs 动态派生（五类账户）', () => {
  it('E0-1 五类账户 account_type 各派生一个页签（无需硬编码）', () => {
    const rows = [
      makeRow({ account_type: '银行存款', amount: 100 }),
      makeRow({ account_type: '其他货币资金', amount: 200 }),
      makeRow({ account_type: '短期借款', amount: 300 }),
      makeRow({ account_type: '应付票据', amount: 400 }),
      makeRow({ account_type: '理财产品', amount: 500 }),
    ]
    const { composable } = setup(rows)
    const tabs = composable.accountTabs.value
    expect(tabs).toHaveLength(5)
    expect(tabs).toEqual(expect.arrayContaining([
      '银行存款', '其他货币资金', '短期借款', '应付票据', '理财产品',
    ]))
  })

  it('同类账户去重，只派生唯一页签', () => {
    const rows = [
      makeRow({ account_type: '银行存款', amount: 100 }),
      makeRow({ account_type: '银行存款', amount: 200 }),
    ]
    const { composable } = setup(rows)
    expect(composable.accountTabs.value).toEqual(['银行存款'])
  })
})
