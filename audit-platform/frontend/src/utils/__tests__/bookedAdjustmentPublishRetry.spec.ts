import { describe, expect, it } from 'vitest'
import {
  addBookedAdjustmentAck, bookedAdjustmentConfirmText, parseBookedAdjustmentAckError,
} from '../bookedAdjustmentPublishRetry'

describe('客户已入账调整发布确认重试', () => {
  const groups = [
    { entry_group_id: 'g1', adjustment_no: 'AJE-001', account_codes: ['1122'] },
    { entry_group_id: 'g2', adjustment_no: 'AJE-002', account_codes: ['6702'] },
  ]

  it('识别 FastAPI detail 与平台信封两种形状', () => {
    expect(parseBookedAdjustmentAckError({ detail: { error_code: 'BOOKED_ADJUSTMENTS_UNACKED', groups } })).toEqual(groups)
    expect(parseBookedAdjustmentAckError({ message: { error_code: 'BOOKED_ADJUSTMENTS_UNACKED', groups } })).toEqual(groups)
    expect(parseBookedAdjustmentAckError({ detail: { error_code: 'OTHER', groups } })).toBeNull()
  })

  it('重发保留原发布 token 和行，只增加去重后的确认组', () => {
    const config: any = {
      method: 'post', url: '/api/workpapers/w1/audit-determination/publish-to-tb',
      data: JSON.stringify({ sheet_name: '审定表D2-1', publish_token: 'token-1', writeback_rows: [{ account_code: '1122', audited_amount: 1 }] }),
      headers: {},
    }
    const retry = addBookedAdjustmentAck(config, [...groups, groups[0]])
    expect(retry.data).toEqual({
      sheet_name: '审定表D2-1', publish_token: 'token-1',
      writeback_rows: [{ account_code: '1122', audited_amount: 1 }],
      booked_adjustments_ack: ['g1', 'g2'],
    })
  })

  it('确认文案点名调整编号，不伪称系统已自动移除', () => {
    const text = bookedAdjustmentConfirmText(groups)
    expect(text).toContain('AJE-001、AJE-002')
    expect(text).toContain('请确认')
    expect(text).not.toContain('已自动移除')
  })
})
