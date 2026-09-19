/**
 * useReliabilityData.spec.ts — D0-7 回函可靠性验证数据 composable 单测
 *
 * 覆盖：CRUD + 条件列联动 + metrics + D0-1 去重 + buildPayload
 */
import { describe, it, expect } from 'vitest'
import { useReliabilityData } from '../useReliabilityData'
import type { ReliabilityRow, ReliabilityPayload } from '../../reliabilityTypes'

function createComposable(rows: ReliabilityRow[] = [], extra?: any) {
  const htmlData = {
    _format: 'reliability-v1',
    rows,
    ...extra,
  }
  return useReliabilityData({
    htmlData: () => htmlData,
    readonly: false,
  })
}

describe('useReliabilityData', () => {
  // ── CRUD ──────────────────────────────────────────────────────────────────

  describe('CRUD', () => {
    it('addRow 应新增一行并设置默认值', () => {
      const data = createComposable()
      const row = data.addRow()
      expect(row._row_id).toBeTruthy()
      expect(row.seq).toBe(1)
      expect(row.original_returned).toBe('否')
      expect(row._source).toBe('manual')
      expect(data.rows.value).toHaveLength(1)
      expect(data.isDirty.value).toBe(true)
    })

    it('deleteRows 应按 ID 删除', () => {
      const data = createComposable()
      const row1 = data.addRow()
      const row2 = data.addRow()
      data.deleteRows([row1._row_id!])
      expect(data.rows.value).toHaveLength(1)
      expect(data.rows.value[0]._row_id).toBe(row2._row_id)
    })

    it('updateField 应更新指定字段', () => {
      const data = createComposable()
      const row = data.addRow()
      data.updateField(row._row_id!, 'entity_name', '测试公司')
      expect(data.rows.value[0].entity_name).toBe('测试公司')
    })

    it('addRow 序号应递增', () => {
      const data = createComposable([
        { _row_id: 'r1', seq: 3, confirm_index: 'C001' },
      ])
      const newRow = data.addRow()
      expect(newRow.seq).toBe(4)
    })
  })

  // ── 条件列联动 ────────────────────────────────────────────────────────────

  describe('条件列联动', () => {
    it('isVerificationDisabled 寄回原件=是返回 true', () => {
      const data = createComposable()
      const row: ReliabilityRow = { original_returned: '是' }
      expect(data.isVerificationDisabled(row)).toBe(true)
    })

    it('isVerificationDisabled 寄回原件=否返回 false', () => {
      const data = createComposable()
      const row: ReliabilityRow = { original_returned: '否' }
      expect(data.isVerificationDisabled(row)).toBe(false)
    })

    it('updateField original_returned 切到"是"应清空验证字段', () => {
      const data = createComposable([{
        _row_id: 'r1',
        seq: 1,
        original_returned: '否',
        identity_verified: true,
        identity_method: '电话确认',
        email_verified: true,
        email_domain: '@test.com',
        phone_called: true,
        phone_source: '工商',
        reliability_note: '已确认',
      }])
      data.updateField('r1', 'original_returned', '是')
      const row = data.rows.value[0]
      expect(row.identity_verified).toBeUndefined()
      expect(row.identity_method).toBeUndefined()
      expect(row.email_verified).toBeUndefined()
      expect(row.email_domain).toBeUndefined()
      expect(row.phone_called).toBeUndefined()
      expect(row.phone_source).toBeUndefined()
      expect(row.reliability_note).toBeUndefined()
    })
  })

  // ── D0-1 去重导入 ─────────────────────────────────────────────────────────

  describe('importRows（D0-1 带入去重）', () => {
    it('按 confirm_index 去重，已有的不重复导入', () => {
      const data = createComposable([
        { _row_id: 'r1', seq: 1, confirm_index: 'C001' },
      ])
      data.importRows([
        { confirm_index: 'C001', entity_name: '重复公司', reply_method: '传真' },
        { confirm_index: 'C002', entity_name: '新公司', reply_method: '电子邮件' },
      ])
      expect(data.rows.value).toHaveLength(2)
      expect(data.rows.value[1].confirm_index).toBe('C002')
      expect(data.rows.value[1].entity_name).toBe('新公司')
      expect(data.rows.value[1]._source).toBe('auto')
      expect(data.rows.value[1].original_returned).toBe('否')
    })

    it('导入行序号续接现有最大值', () => {
      const data = createComposable([
        { _row_id: 'r1', seq: 5, confirm_index: 'C001' },
      ])
      data.importRows([
        { confirm_index: 'C010', entity_name: 'A' },
        { confirm_index: 'C011', entity_name: 'B' },
      ])
      expect(data.rows.value[1].seq).toBe(6)
      expect(data.rows.value[2].seq).toBe(7)
    })
  })

  // ── metrics ───────────────────────────────────────────────────────────────

  describe('metrics 看板指标', () => {
    it('正确计算已验证率/不可靠/寄回原件', () => {
      const data = createComposable([
        { _row_id: 'r1', seq: 1, conclusion_status: '可靠', original_returned: '否' },
        { _row_id: 'r2', seq: 2, conclusion_status: '不可靠', original_returned: '否' },
        { _row_id: 'r3', seq: 3, original_returned: '是' },
        { _row_id: 'r4', seq: 4, original_returned: '否' }, // 未验证
      ])
      const m = data.metrics.value
      expect(m.total_count).toBe(4)
      expect(m.verified_count).toBe(2) // r1 + r2 有 conclusion_status
      expect(m.verified_rate).toBe(50)
      expect(m.reliable_count).toBe(1)
      expect(m.unreliable_count).toBe(1)
      expect(m.original_returned_count).toBe(1)
    })
  })

  // ── 质量红线 ──────────────────────────────────────────────────────────────

  describe('getRowQualityStatus', () => {
    it('寄回原件=是 → ok', () => {
      const data = createComposable()
      expect(data.getRowQualityStatus({ original_returned: '是' })).toBe('ok')
    })

    it('结论=不可靠 → danger', () => {
      const data = createComposable()
      expect(data.getRowQualityStatus({ original_returned: '否', conclusion_status: '不可靠' })).toBe('danger')
    })

    it('结论空 → warning', () => {
      const data = createComposable()
      expect(data.getRowQualityStatus({ original_returned: '否' })).toBe('warning')
    })

    it('结论=可靠 → ok', () => {
      const data = createComposable()
      expect(data.getRowQualityStatus({ original_returned: '否', conclusion_status: '可靠' })).toBe('ok')
    })
  })

  // ── buildPayload ──────────────────────────────────────────────────────────

  describe('buildPayload', () => {
    it('格式标识应为 reliability-v1', () => {
      const data = createComposable()
      data.addRow()
      const payload = data.buildPayload()
      expect(payload._format).toBe('reliability-v1')
      expect(payload.rows).toHaveLength(1)
    })

    it('寄回原件=是的行不持久化验证字段', () => {
      const data = createComposable([{
        _row_id: 'r1',
        seq: 1,
        original_returned: '是',
        identity_verified: true,
        email_verified: true,
      }])
      const payload = data.buildPayload()
      const row = payload.rows[0]
      expect(row.identity_verified).toBeUndefined()
      expect(row.email_verified).toBeUndefined()
    })

    it('寄回原件=否的行保留验证字段', () => {
      const data = createComposable([{
        _row_id: 'r1',
        seq: 1,
        original_returned: '否',
        identity_verified: true,
        email_domain: '@test.com',
      }])
      const payload = data.buildPayload()
      const row = payload.rows[0]
      expect(row.identity_verified).toBe(true)
      expect(row.email_domain).toBe('@test.com')
    })

    it('包含审计说明和结论', () => {
      const data = createComposable([], {
        audit_note: { note_general: '测试说明' },
        conclusion: { conclusion_type: '可靠', conclusion_text: '全部可靠' },
      })
      const payload = data.buildPayload()
      expect(payload.audit_note?.note_general).toBe('测试说明')
      expect(payload.conclusion?.conclusion_type).toBe('可靠')
    })
  })

  // ── 初始化 ────────────────────────────────────────────────────────────────

  describe('初始化', () => {
    it('非 reliability-v1 格式返回空数组', () => {
      const data = useReliabilityData({
        htmlData: () => ({ _format: 'old-format', rows: [{ seq: 1 }] }),
        readonly: false,
      })
      expect(data.rows.value).toHaveLength(0)
    })

    it('null htmlData 返回空数组', () => {
      const data = useReliabilityData({
        htmlData: () => null,
        readonly: false,
      })
      expect(data.rows.value).toHaveLength(0)
    })

    it('正确初始化 reliability-v1 数据', () => {
      const data = createComposable([
        { seq: 1, confirm_index: 'C001', entity_name: '测试' },
        { seq: 2, confirm_index: 'C002', entity_name: '公司' },
      ])
      expect(data.rows.value).toHaveLength(2)
      expect(data.rows.value[0]._row_id).toBeTruthy()
      expect(data.isDirty.value).toBe(false)
    })
  })
})
