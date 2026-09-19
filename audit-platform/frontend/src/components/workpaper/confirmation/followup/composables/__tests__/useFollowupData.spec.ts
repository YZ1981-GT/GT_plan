/**
 * useFollowupData.spec.ts — D0-3 跟函数据核心 composable 单元测试
 *
 * 覆盖：
 * 1. 初始化 confirmation-followup-v1 格式
 * 2. 非匹配格式 → 空
 * 3. addRow 自增序号
 * 4. deleteRows 按 ID 删除
 * 5. updateField 字段更新 + 控制结论自动派生
 * 6. importRows 批量导入
 * 7. progressMetrics: signed / control_pass / anomaly 统计
 * 8. deriveControlConclusion 逻辑
 * 9. buildPayload 结构正确性
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useFollowupData, deriveControlConclusion } from '../useFollowupData'
import type { FollowupRow, FollowupPayload } from '../../followupTypes'

// ─── 测试辅助 ────────────────────────────────────────────────────────────────

function createHtmlData(rows: Partial<FollowupRow>[] = []) {
  return {
    _format: 'confirmation-followup-v1' as const,
    rows,
  }
}

function makeRow(overrides: Partial<FollowupRow> = {}): FollowupRow {
  return {
    _row_id: `test-${Math.random().toString(36).slice(2, 8)}`,
    seq: 1,
    scenario: 'immediate',
    sign_status: 'unsigned',
    _source: 'manual',
    ...overrides,
  }
}

function setup(rows: Partial<FollowupRow>[] = []) {
  const data = ref(createHtmlData(rows))
  const composable = useFollowupData({
    htmlData: () => data.value,
    readonly: false,
  })
  return { composable, data }
}

// ─── 1. 初始化 ──────────────────────────────────────────────────────────────

describe('useFollowupData - initialization', () => {
  it('正确解析 confirmation-followup-v1 数据', () => {
    const rows = [
      makeRow({ seq: 1, entity_name: '公司A' }),
      makeRow({ seq: 2, entity_name: '公司B' }),
    ]
    const { composable } = setup(rows)

    expect(composable.rows.value).toHaveLength(2)
    expect(composable.rows.value[0].entity_name).toBe('公司A')
    expect(composable.isDirty.value).toBe(false)
  })

  it('缺少 _row_id 的行自动生成 ID', () => {
    const rows = [{ seq: 1, entity_name: '无ID公司' } as FollowupRow]
    const { composable } = setup(rows)
    expect(composable.rows.value[0]._row_id).toBeTruthy()
  })

  it('非 confirmation-followup-v1 格式初始化为空', () => {
    const data = ref({ _format: 'entity-verify-v1', rows: [{ seq: 1 }] })
    const composable = useFollowupData({
      htmlData: () => data.value,
      readonly: false,
    })
    expect(composable.rows.value).toHaveLength(0)
  })

  it('null htmlData 初始化为空', () => {
    const composable = useFollowupData({
      htmlData: () => null,
      readonly: false,
    })
    expect(composable.rows.value).toHaveLength(0)
    expect(composable.isDirty.value).toBe(false)
  })

  it('undefined htmlData 初始化为空', () => {
    const composable = useFollowupData({
      htmlData: () => undefined,
      readonly: false,
    })
    expect(composable.rows.value).toHaveLength(0)
  })
})

// ─── 3. addRow ──────────────────────────────────────────────────────────────

describe('useFollowupData - addRow', () => {
  it('addRow 追加新行，序号自增', () => {
    const { composable } = setup([makeRow({ seq: 3 })])

    const newRow = composable.addRow()

    expect(newRow.seq).toBe(4)
    expect(newRow._row_id).toBeTruthy()
    expect(newRow._source).toBe('manual')
    expect(newRow.scenario).toBe('immediate')
    expect(newRow.sign_status).toBe('unsigned')
    expect(composable.rows.value).toHaveLength(2)
    expect(composable.isDirty.value).toBe(true)
  })

  it('addRow 空行列表时从 1 开始', () => {
    const { composable } = setup([])
    const newRow = composable.addRow()
    expect(newRow.seq).toBe(1)
  })

  it('addRow 连续添加序号递增', () => {
    const { composable } = setup([])
    const row1 = composable.addRow()
    const row2 = composable.addRow()
    const row3 = composable.addRow()
    expect(row1.seq).toBe(1)
    expect(row2.seq).toBe(2)
    expect(row3.seq).toBe(3)
  })
})

// ─── 4. deleteRows ──────────────────────────────────────────────────────────

describe('useFollowupData - deleteRows', () => {
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
    expect(composable.isDirty.value).toBe(false)
  })

  it('deleteRows 不存在的 ID 不报错', () => {
    const { composable } = setup([makeRow({ _row_id: 'r1' })])
    composable.deleteRows(['nonexistent'])
    expect(composable.rows.value).toHaveLength(1)
  })
})

// ─── 5. updateField ─────────────────────────────────────────────────────────

describe('useFollowupData - updateField', () => {
  it('updateField 更新指定行字段', () => {
    const row = makeRow({ _row_id: 'r1', entity_name: '旧名称' })
    const { composable } = setup([row])

    composable.updateField('r1', 'entity_name', '新名称')

    expect(composable.rows.value[0].entity_name).toBe('新名称')
    expect(composable.isDirty.value).toBe(true)
  })

  it('updateField 不存在的 rowId 静默忽略', () => {
    const { composable } = setup([makeRow({ _row_id: 'r1', entity_name: '原始' })])
    composable.updateField('nonexistent', 'entity_name', '新值')
    expect(composable.rows.value[0].entity_name).toBe('原始')
  })

  it('updateField control 字段自动派生 control_conclusion', () => {
    const row = makeRow({ _row_id: 'r1', control_process: 'yes', control_identity: 'yes' })
    const { composable } = setup([row])

    composable.updateField('r1', 'control_normal_flow', 'yes')
    expect(composable.rows.value[0].control_conclusion).toBe('pass')

    composable.updateField('r1', 'control_identity', 'no')
    expect(composable.rows.value[0].control_conclusion).toBe('fail')
  })
})

// ─── 6. importRows ──────────────────────────────────────────────────────────

describe('useFollowupData - importRows', () => {
  it('importRows 批量添加行并自动递增序号', () => {
    const { composable } = setup([makeRow({ seq: 2 })])

    composable.importRows([
      { entity_name: '导入公司A' },
      { entity_name: '导入公司B' },
      { entity_name: '导入公司C' },
    ])

    expect(composable.rows.value).toHaveLength(4)
    expect(composable.rows.value[1].seq).toBe(3)
    expect(composable.rows.value[2].seq).toBe(4)
    expect(composable.rows.value[3].seq).toBe(5)
    expect(composable.isDirty.value).toBe(true)
  })

  it('importRows 默认 _source 为 import', () => {
    const { composable } = setup([])
    composable.importRows([{ entity_name: '导入公司' }])
    expect(composable.rows.value[0]._source).toBe('import')
  })

  it('importRows 保留原始 _source', () => {
    const { composable } = setup([])
    composable.importRows([{ entity_name: '公司', _source: 'd01_linkage' }])
    expect(composable.rows.value[0]._source).toBe('d01_linkage')
  })

  it('importRows 每行分配独立 _row_id', () => {
    const { composable } = setup([])
    composable.importRows([{ entity_name: 'A' }, { entity_name: 'B' }])
    const ids = composable.rows.value.map((r) => r._row_id)
    expect(ids[0]).toBeTruthy()
    expect(ids[1]).toBeTruthy()
    expect(ids[0]).not.toBe(ids[1])
  })

  it('importRows 自动派生 control_conclusion', () => {
    const { composable } = setup([])
    composable.importRows([
      { entity_name: 'A', control_process: 'yes', control_identity: 'yes', control_normal_flow: 'yes' },
      { entity_name: 'B', control_process: 'yes', control_identity: 'no', control_normal_flow: 'yes' },
    ])
    expect(composable.rows.value[0].control_conclusion).toBe('pass')
    expect(composable.rows.value[1].control_conclusion).toBe('fail')
  })
})

// ─── 7. progressMetrics ─────────────────────────────────────────────────────

describe('useFollowupData - progressMetrics', () => {
  it('统计 signed: sign_status === signed', () => {
    const rows = [
      makeRow({ _row_id: 's1', sign_status: 'signed' }),
      makeRow({ _row_id: 's2', sign_status: 'unsigned' }),
    ]
    const { composable } = setup(rows)
    const metrics = composable.progressMetrics.value
    expect(metrics.signed_count).toBe(1)
    expect(metrics.sign_rate).toBe(50)
  })

  it('统计 control_pass / control_fail', () => {
    const rows = [
      makeRow({ _row_id: 'p1', control_conclusion: 'pass' }),
      makeRow({ _row_id: 'f1', control_conclusion: 'fail' }),
      makeRow({ _row_id: 'i1', control_conclusion: 'incomplete' }),
    ]
    const { composable } = setup(rows)
    const metrics = composable.progressMetrics.value
    expect(metrics.control_pass_count).toBe(1)
    expect(metrics.control_fail_count).toBe(1)
    expect(metrics.control_pass_rate).toBeCloseTo(33.33, 1)
  })

  it('统计 anomaly: 任一 control = no', () => {
    const rows = [
      makeRow({ _row_id: 'a1', control_process: 'no' }),
      makeRow({ _row_id: 'a2', control_identity: 'no', control_normal_flow: 'no' }),
      makeRow({ _row_id: 'ok', control_process: 'yes', control_identity: 'yes', control_normal_flow: 'yes' }),
    ]
    const { composable } = setup(rows)
    expect(composable.progressMetrics.value.anomaly_count).toBe(2)
  })

  it('空行列表不除零，rates 为 0', () => {
    const { composable } = setup([])
    const metrics = composable.progressMetrics.value
    expect(metrics.total_count).toBe(0)
    expect(metrics.sign_rate).toBe(0)
    expect(metrics.control_pass_rate).toBe(0)
  })
})

// ─── 8. deriveControlConclusion ─────────────────────────────────────────────

describe('deriveControlConclusion', () => {
  it('全部 yes → pass', () => {
    const row = makeRow({ control_process: 'yes', control_identity: 'yes', control_normal_flow: 'yes' })
    expect(deriveControlConclusion(row)).toBe('pass')
  })

  it('任一 no → fail', () => {
    expect(deriveControlConclusion(makeRow({ control_process: 'no', control_identity: 'yes', control_normal_flow: 'yes' }))).toBe('fail')
    expect(deriveControlConclusion(makeRow({ control_process: 'yes', control_identity: 'no', control_normal_flow: 'yes' }))).toBe('fail')
    expect(deriveControlConclusion(makeRow({ control_process: 'yes', control_identity: 'yes', control_normal_flow: 'no' }))).toBe('fail')
  })

  it('含 na 或空 → incomplete', () => {
    expect(deriveControlConclusion(makeRow({ control_process: 'yes', control_identity: 'na', control_normal_flow: 'yes' }))).toBe('incomplete')
    expect(deriveControlConclusion(makeRow({ control_process: 'yes', control_identity: 'yes' }))).toBe('incomplete')
    expect(deriveControlConclusion(makeRow({}))).toBe('incomplete')
  })
})

// ─── 9. buildPayload ────────────────────────────────────────────────────────

describe('useFollowupData - buildPayload', () => {
  it('返回完整 FollowupPayload 结构', () => {
    const rows = [
      makeRow({ seq: 1, entity_name: '测试公司', sign_status: 'signed', control_conclusion: 'pass' }),
    ]
    const { composable } = setup(rows)
    const payload = composable.buildPayload()

    expect(payload._format).toBe('confirmation-followup-v1')
    expect(payload.rows).toHaveLength(1)
    expect(payload.rows[0].entity_name).toBe('测试公司')
    expect(payload.progress_summary).toBeDefined()
    expect(payload.progress_summary!.total_count).toBe(1)
    expect(payload.progress_summary!.signed_count).toBe(1)
    expect(payload.progress_summary!.sign_rate).toBe(100)
  })

  it('buildPayload 包含所有行数据', () => {
    const { composable } = setup([])
    composable.addRow()
    composable.addRow()
    composable.importRows([{ entity_name: '导入' }])
    const payload = composable.buildPayload()
    expect(payload.rows).toHaveLength(3)
  })

  it('buildPayload progress_summary 与 progressMetrics 一致', () => {
    const rows = [
      makeRow({ _row_id: 'r1', sign_status: 'signed', control_conclusion: 'pass' }),
      makeRow({ _row_id: 'r2', sign_status: 'unsigned', control_conclusion: 'fail', control_identity: 'no' }),
    ]
    const { composable } = setup(rows)
    const payload = composable.buildPayload()
    const metrics = composable.progressMetrics.value
    expect(payload.progress_summary).toEqual(metrics)
  })
})
