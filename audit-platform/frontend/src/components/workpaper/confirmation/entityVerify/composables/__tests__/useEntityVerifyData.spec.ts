/**
 * useEntityVerifyData.spec.ts — D0-2 核实数据核心 composable 单元测试
 *
 * 覆盖 Tasks 2.1 ~ 2.5:
 * 1. 初始化 entity-verify-v1 格式
 * 2. 非匹配格式 → 空
 * 3. addRow 自增序号
 * 4. deleteRows 按 ID 删除
 * 5. updateField 字段更新
 * 6. importRows 批量导入
 * 7. progressMetrics: verified/pending/returned 统计 + rates
 * 8. buildPayload 结构正确性
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useEntityVerifyData } from '../useEntityVerifyData'
import type { EntityVerifyRow, EntityVerifyPayload } from '../../entityVerifyTypes'

// ─── 测试辅助 ────────────────────────────────────────────────────────────────

function createHtmlData(rows: Partial<EntityVerifyRow>[] = []) {
  return {
    _format: 'entity-verify-v1' as const,
    rows,
  }
}

function makeRow(overrides: Partial<EntityVerifyRow> = {}): EntityVerifyRow {
  return {
    _row_id: `test-${Math.random().toString(36).slice(2, 8)}`,
    seq: 1,
    _source: 'manual',
    row_status: 'ok',
    ...overrides,
  }
}

function setup(rows: Partial<EntityVerifyRow>[] = []) {
  const data = ref(createHtmlData(rows))
  const composable = useEntityVerifyData({
    htmlData: () => data.value,
    readonly: false,
  })
  return { composable, data }
}

// ─── 1. 初始化 entity-verify-v1 格式 ─────────────────────────────────────────

describe('useEntityVerifyData - initialization', () => {
  it('正确解析 entity-verify-v1 数据', () => {
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
    const rows = [{ seq: 1, entity_name: '无ID公司' } as EntityVerifyRow]
    const { composable } = setup(rows)
    expect(composable.rows.value[0]._row_id).toBeTruthy()
  })

  // ─── 2. 非匹配格式 → 空 ────────────────────────────────────────────────────

  it('非 entity-verify-v1 格式初始化为空', () => {
    const data = ref({ _format: 'confirmation-v1', rows: [{ amount: 100 }] })
    const composable = useEntityVerifyData({
      htmlData: () => data.value,
      readonly: false,
    })
    expect(composable.rows.value).toHaveLength(0)
  })

  it('null htmlData 初始化为空', () => {
    const composable = useEntityVerifyData({
      htmlData: () => null,
      readonly: false,
    })
    expect(composable.rows.value).toHaveLength(0)
    expect(composable.isDirty.value).toBe(false)
  })

  it('undefined htmlData 初始化为空', () => {
    const composable = useEntityVerifyData({
      htmlData: () => undefined,
      readonly: false,
    })
    expect(composable.rows.value).toHaveLength(0)
  })
})

// ─── 3. addRow 自增序号 ──────────────────────────────────────────────────────

describe('useEntityVerifyData - addRow', () => {
  it('addRow 追加新行，序号自增', () => {
    const { composable } = setup([makeRow({ seq: 3 })])

    const newRow = composable.addRow()

    expect(newRow.seq).toBe(4)
    expect(newRow._row_id).toBeTruthy()
    expect(newRow._source).toBe('manual')
    expect(newRow.row_status).toBe('ok')
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

// ─── 4. deleteRows 按 ID 删除 ────────────────────────────────────────────────

describe('useEntityVerifyData - deleteRows', () => {
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

// ─── 5. updateField 字段更新 ─────────────────────────────────────────────────

describe('useEntityVerifyData - updateField', () => {
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

  it('updateField 更新 match 字段', () => {
    const row = makeRow({ _row_id: 'r1', name_match: 'pending' })
    const { composable } = setup([row])

    composable.updateField('r1', 'name_match', 'consistent')
    expect(composable.rows.value[0].name_match).toBe('consistent')
  })
})

// ─── 6. importRows 批量导入 ──────────────────────────────────────────────────

describe('useEntityVerifyData - importRows', () => {
  it('importRows 批量添加行并自动递增序号', () => {
    const { composable } = setup([makeRow({ seq: 2 })])

    composable.importRows([
      { entity_name: '导入公司A' },
      { entity_name: '导入公司B' },
      { entity_name: '导入公司C' },
    ])

    expect(composable.rows.value).toHaveLength(4) // 1 existing + 3 imported
    expect(composable.rows.value[1].seq).toBe(3)
    expect(composable.rows.value[2].seq).toBe(4)
    expect(composable.rows.value[3].seq).toBe(5)
    expect(composable.isDirty.value).toBe(true)
  })

  it('importRows 默认 _source 为 import', () => {
    const { composable } = setup([])

    composable.importRows([{ entity_name: '导入公司' }])

    expect(composable.rows.value[0]._source).toBe('import')
    expect(composable.rows.value[0].row_status).toBe('ok')
  })

  it('importRows 保留原始 _source', () => {
    const { composable } = setup([])

    composable.importRows([{ entity_name: '公司', _source: 'qcc_api' }])

    expect(composable.rows.value[0]._source).toBe('qcc_api')
  })

  it('importRows 每行分配独立 _row_id', () => {
    const { composable } = setup([])

    composable.importRows([{ entity_name: 'A' }, { entity_name: 'B' }])

    const ids = composable.rows.value.map((r) => r._row_id)
    expect(ids[0]).toBeTruthy()
    expect(ids[1]).toBeTruthy()
    expect(ids[0]).not.toBe(ids[1])
  })
})

// ─── 7. progressMetrics 进度指标 ─────────────────────────────────────────────

describe('useEntityVerifyData - progressMetrics', () => {
  it('统计 verified: 4个 match 全部 consistent', () => {
    const verifiedRow = makeRow({
      _row_id: 'v1',
      name_match: 'consistent',
      address_match: 'consistent',
      contact_match: 'consistent',
      phone_match: 'consistent',
    })
    const partialRow = makeRow({
      _row_id: 'p1',
      name_match: 'consistent',
      address_match: 'inconsistent',
      contact_match: 'consistent',
      phone_match: 'consistent',
    })
    const { composable } = setup([verifiedRow, partialRow])

    const metrics = composable.progressMetrics.value
    expect(metrics.total_count).toBe(2)
    expect(metrics.verified_count).toBe(1)
    expect(metrics.verify_rate).toBe(50)
  })

  it('统计 pending: name_match 为空或 pending', () => {
    const pendingRow1 = makeRow({ _row_id: 'p1' }) // name_match undefined
    const pendingRow2 = makeRow({ _row_id: 'p2', name_match: 'pending' })
    const activeRow = makeRow({ _row_id: 'a1', name_match: 'consistent' })
    const { composable } = setup([pendingRow1, pendingRow2, activeRow])

    expect(composable.progressMetrics.value.pending_count).toBe(2)
  })

  it('统计 returned: first_result === 退回', () => {
    const returnedRow = makeRow({ _row_id: 'ret1', first_result: '退回' })
    const deliveredRow = makeRow({ _row_id: 'del1', first_result: '送抵' })
    const { composable } = setup([returnedRow, deliveredRow])

    const metrics = composable.progressMetrics.value
    expect(metrics.returned_count).toBe(1)
    expect(metrics.return_rate).toBe(50)
  })

  it('统计 fraud_flag: row_status === fraud_flag', () => {
    const flaggedRow = makeRow({ _row_id: 'f1', row_status: 'fraud_flag' })
    const okRow = makeRow({ _row_id: 'ok1', row_status: 'ok' })
    const { composable } = setup([flaggedRow, okRow])

    expect(composable.progressMetrics.value.fraud_flag_count).toBe(1)
  })

  it('空行列表不除零，rates 为 0', () => {
    const { composable } = setup([])
    const metrics = composable.progressMetrics.value

    expect(metrics.total_count).toBe(0)
    expect(metrics.verified_count).toBe(0)
    expect(metrics.verify_rate).toBe(0)
    expect(metrics.return_rate).toBe(0)
  })

  it('CRUD 操作后 progressMetrics 响应式更新', () => {
    const { composable } = setup([])

    // 添加一行
    const row = composable.addRow()
    expect(composable.progressMetrics.value.total_count).toBe(1)
    expect(composable.progressMetrics.value.pending_count).toBe(1)

    // 更新为全部 consistent
    composable.updateField(row._row_id!, 'name_match', 'consistent')
    composable.updateField(row._row_id!, 'address_match', 'consistent')
    composable.updateField(row._row_id!, 'contact_match', 'consistent')
    composable.updateField(row._row_id!, 'phone_match', 'consistent')

    expect(composable.progressMetrics.value.verified_count).toBe(1)
    expect(composable.progressMetrics.value.verify_rate).toBe(100)
  })
})

// ─── 8. buildPayload 结构正确性 ──────────────────────────────────────────────

describe('useEntityVerifyData - buildPayload', () => {
  it('返回完整 EntityVerifyPayload 结构', () => {
    const rows = [
      makeRow({
        seq: 1,
        entity_name: '测试公司',
        name_match: 'consistent',
        address_match: 'consistent',
        contact_match: 'consistent',
        phone_match: 'consistent',
      }),
    ]
    const { composable } = setup(rows)

    const payload = composable.buildPayload()

    expect(payload._format).toBe('entity-verify-v1')
    expect(payload.rows).toHaveLength(1)
    expect(payload.rows[0].entity_name).toBe('测试公司')
    expect(payload.progress_summary).toBeDefined()
    expect(payload.progress_summary!.total_count).toBe(1)
    expect(payload.progress_summary!.verified_count).toBe(1)
    expect(payload.progress_summary!.verify_rate).toBe(100)
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
      makeRow({ _row_id: 'r1', first_result: '退回', row_status: 'fraud_flag' }),
      makeRow({
        _row_id: 'r2',
        name_match: 'consistent',
        address_match: 'consistent',
        contact_match: 'consistent',
        phone_match: 'consistent',
      }),
    ]
    const { composable } = setup(rows)

    const payload = composable.buildPayload()
    const metrics = composable.progressMetrics.value

    expect(payload.progress_summary).toEqual(metrics)
  })
})
