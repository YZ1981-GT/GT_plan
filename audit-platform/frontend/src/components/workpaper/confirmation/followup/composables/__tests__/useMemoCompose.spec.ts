/**
 * useMemoCompose.spec.ts — D0-3 备忘录自动拼装 composable 单元测试
 *
 * 覆盖：
 * 1. immediate 场景模板拼装
 * 2. later_follow 场景模板拼装
 * 3. 缺失字段检测
 * 4. override 守卫（手动覆盖时不重新生成）
 * 5. regenerate 强制重新生成
 * 6. later_received 补记追加
 * 7. applyToRow
 */
import { describe, it, expect } from 'vitest'
import { useMemoCompose } from '../useMemoCompose'
import type { FollowupRow } from '../../followupTypes'

function makeRow(overrides: Partial<FollowupRow> = {}): FollowupRow {
  return {
    _row_id: 'test-row',
    seq: 1,
    scenario: 'immediate',
    ...overrides,
  }
}

describe('useMemoCompose', () => {
  const { compose, applyToRow, regenerate } = useMemoCompose()

  // ─── 1. immediate 场景 ─────────────────────────────────────────────────────

  describe('immediate scenario', () => {
    it('完整字段生成备忘录无缺失', () => {
      const row = makeRow({
        scenario: 'immediate',
        followup_date: '2026-06-20',
        entity_name: '中远海运集团',
        entity_address: '上海市浦东新区100号',
        confirm_contact: '张财务',
        confirm_identity_verified: '是',
        confirm_location: '财务部办公室',
        // ── 源模板 X0-3 A10/A13 要求的要素（h0 spec R9.1/R9.2 补入模板后必填） ──
        followup_staff: '王审计',
        escort_desc: '在无被审计单位人员陪同下独立',
        confirm_staff_no: 'FIN-0088',
        received_confirm_index: 'D0-1-001',
      })

      const { text, missingFields } = compose(row)

      expect(missingFields).toHaveLength(0)
      expect(text).toContain('2026-06-20')
      expect(text).toContain('中远海运集团')
      expect(text).toContain('上海市浦东新区100号')
      expect(text).toContain('张财务')
      expect(text).toContain('财务部办公室')
      expect(text).toContain('正常业务流程')
      // 陪同情况与工号是串通舞弊防范的关键证据，必须出现在备忘录里
      expect(text).toContain('无被审计单位人员陪同')
      expect(text).toContain('FIN-0088')
    })

    it('缺失字段保留占位符并报告', () => {
      const row = makeRow({
        scenario: 'immediate',
        followup_date: '2026-06-20',
        entity_name: '测试公司',
        // entity_address, confirm_contact, confirm_identity_verified, confirm_location 缺失
      })

      const { text, missingFields } = compose(row)

      // missingFields 与占位符均为中文标签（供 FollowupMemoPreview 直接展示给审计师）
      expect(missingFields).toContain('单位地址')
      expect(missingFields).toContain('确认联系人')
      expect(missingFields).toContain('身份确认情况')
      expect(missingFields).toContain('确认地点')
      expect(text).toContain('〔单位地址〕')
      expect(text).toContain('〔确认联系人〕')
    })
  })

  // ─── 2. later_follow 场景 ──────────────────────────────────────────────────

  describe('later_follow scenario', () => {
    it('完整字段生成备忘录无缺失', () => {
      const row = makeRow({
        scenario: 'later_follow',
        leave_date: '2026-06-18',
        entity_name: '中海地产',
        entity_address: '深圳市南山区50号',
        leave_contact: '李经理',
        follow_call_date: '2026-06-20',
        follow_call_phone: '0755-12345678',
        follow_call_result: '对方确认余额无误',
        followup_staff: '王审计',
        escort_desc: '与被审计单位财务部张主管一同',
        leave_staff_no: 'FIN-0102',
        received_office: '审计二部',
      })

      const { text, missingFields } = compose(row)

      expect(missingFields).toHaveLength(0)
      expect(text).toContain('FIN-0102')
      expect(text).toContain('2026-06-18')
      expect(text).toContain('中海地产')
      expect(text).toContain('李经理')
      expect(text).toContain('0755-12345678')
      expect(text).toContain('独立公开来源')
      expect(text).toContain('对方确认余额无误')
    })

    it('缺失字段保留占位符', () => {
      const row = makeRow({ scenario: 'later_follow', entity_name: '测试' })
      const { text, missingFields } = compose(row)

      expect(missingFields).toContain('留函日期')
      expect(missingFields).toContain('留函联系人')
      expect(missingFields).toContain('跟踪致电日期')
      expect(missingFields).toContain('跟踪电话')
      expect(missingFields).toContain('跟踪结果')
      expect(text).toContain('〔留函日期〕')
    })
  })

  // ─── 3. later_received 补记 ────────────────────────────────────────────────

  describe('later_received supplement', () => {
    it('later_received=true 追加补记段落', () => {
      const row = makeRow({
        scenario: 'immediate',
        followup_date: '2026-06-20',
        entity_name: '公司',
        entity_address: '地址',
        confirm_contact: '联系人',
        confirm_identity_verified: '是',
        confirm_location: '办公室',
        followup_staff: '王审计',
        escort_desc: '独立',
        confirm_staff_no: 'X-1',
        later_received: true,
        received_date: '2026-06-25',
        received_office: '审计二部',
        received_confirm_index: 'D0-1-001',
      })

      const { text, missingFields } = compose(row)

      expect(missingFields).toHaveLength(0)
      expect(text).toContain('【补记】')
      expect(text).toContain('2026-06-25')
      expect(text).toContain('审计二部')
      expect(text).toContain('D0-1-001')
    })

    it('later_received=false 不追加补记', () => {
      const row = makeRow({
        scenario: 'immediate',
        followup_date: '2026-06-20',
        entity_name: '公司',
        entity_address: '地址',
        confirm_contact: '联系人',
        confirm_identity_verified: '是',
        confirm_location: '办公室',
        later_received: false,
      })

      const { text } = compose(row)
      expect(text).not.toContain('【补记】')
    })
  })

  // ─── 4. override 守卫 ──────────────────────────────────────────────────────

  describe('override guard', () => {
    it('memo_overridden=true 时返回手动文本', () => {
      const row = makeRow({
        memo_overridden: true,
        memo_text: '手动编写的备忘录内容',
        entity_name: '不应出现',
      })

      const { text, missingFields } = compose(row)

      expect(text).toBe('手动编写的备忘录内容')
      expect(missingFields).toHaveLength(0)
    })

    it('applyToRow 不覆盖已手动的行', () => {
      const row = makeRow({
        memo_overridden: true,
        memo_text: '手动内容',
      })

      const result = applyToRow(row)
      expect(result.memo_text).toBe('手动内容')
    })
  })

  // ─── 5. regenerate ─────────────────────────────────────────────────────────

  describe('regenerate', () => {
    it('强制重新生成，忽略 override 标志', () => {
      const row = makeRow({
        scenario: 'immediate',
        memo_overridden: true,
        memo_text: '旧手动文本',
        followup_date: '2026-06-20',
        entity_name: '公司X',
        entity_address: '地址X',
        confirm_contact: '张三',
        confirm_identity_verified: '是',
        confirm_location: '会议室',
      })

      const result = regenerate(row)

      expect(result.memo_overridden).toBe(false)
      expect(result.memo_text).toContain('公司X')
      expect(result.memo_text).toContain('2026-06-20')
      expect(result.memo_text).not.toBe('旧手动文本')
    })
  })

  // ─── 6. applyToRow ─────────────────────────────────────────────────────────

  describe('applyToRow', () => {
    it('自动拼装并写入 memo_text', () => {
      const row = makeRow({
        scenario: 'immediate',
        followup_date: '2026-06-20',
        entity_name: '公司Y',
        entity_address: '地址Y',
        confirm_contact: '李四',
        confirm_identity_verified: '否',
        confirm_location: '前台',
      })

      const result = applyToRow(row)

      expect(result.memo_text).toContain('公司Y')
      expect(result.memo_text).toContain('李四')
    })
  })
})
