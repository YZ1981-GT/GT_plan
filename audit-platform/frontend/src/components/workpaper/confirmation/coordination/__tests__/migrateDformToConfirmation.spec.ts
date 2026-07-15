import { describe, expect, it } from 'vitest'
import {
  isLegacyDformPayload,
  mapDformRowToConfirmation,
  migrateDformToConfirmationV1,
} from '../migrateDformToConfirmation'

describe('migrateDformToConfirmation', () => {
  it('detects legacy d-form payload', () => {
    expect(isLegacyDformPayload({ rows: [{ 被函证单位: '甲' }] })).toBe(true)
    expect(isLegacyDformPayload({ _format: 'confirmation-v1', rows: [] })).toBe(false)
    expect(isLegacyDformPayload({ _format: 'entity-verify-v1', rows: [] })).toBe(false)
  })

  it('maps common chinese column labels', () => {
    const r = mapDformRowToConfirmation(
      {
        函证索引号: 'E0-001',
        被函证单位: 'XX银行',
        函证金额: 1000,
        回函金额: 1000,
        相符情况: '相符',
        科目: '银行存款',
      },
      1,
    )
    expect(r.confirm_index).toBe('E0-001')
    expect(r.entity_name).toBe('XX银行')
    expect(r.amount).toBe(1000)
    expect(r.reply_amount).toBe(1000)
    expect(r.match_status).toBe('相符')
    expect(r.account_type).toBe('银行存款')
    expect(r._source).toBe('migrated')
  })

  it('builds confirmation-v1 with legacy snapshot', () => {
    const legacy = { rows: [{ 被询证单位: '甲公司', 账面金额: 50 }], context: { x: 1 } }
    const payload = migrateDformToConfirmationV1(legacy)
    expect(payload._format).toBe('confirmation-v1')
    expect(payload.rows.length).toBe(1)
    expect(payload.rows[0].entity_name).toBe('甲公司')
    expect((payload as any)._legacy_dform).toBe(legacy)
  })
})
