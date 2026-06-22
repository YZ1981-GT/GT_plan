/**
 * useConfirmationStatus.spec.ts — 函证状态机单元测试
 *
 * 覆盖：
 * - 12 态合法转移
 * - 非法转移拒绝
 * - 可用事件查询
 * - distribution 统计
 * - 停滞预警
 * - 终态判定
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  CONFIRMATION_STATUSES,
  TRANSITION_TABLE,
  canTransition,
  transition,
  availableEvents,
  useConfirmationStatus,
  type ConfirmationStatus,
  type StatusEvent,
  type StatusRecord,
} from '../useConfirmationStatus'

describe('useConfirmationStatus — 状态机核心', () => {
  // ─── 基础转移逻辑 ──────────────────────────────────────────────────────────

  describe('transition()', () => {
    it('未核实 + VERIFY → 已核实', () => {
      expect(transition('未核实', 'VERIFY')).toBe('已核实')
    })

    it('已核实 + SEND → 已发函', () => {
      expect(transition('已核实', 'SEND')).toBe('已发函')
    })

    it('已发函 + REPLY_RECEIVED → 已回函', () => {
      expect(transition('已发函', 'REPLY_RECEIVED')).toBe('已回函')
    })

    it('已发函 + REPLY_TIMEOUT → 未回函', () => {
      expect(transition('已发函', 'REPLY_TIMEOUT')).toBe('未回函')
    })

    it('已发函 + FOLLOWUP → 跟函中', () => {
      expect(transition('已发函', 'FOLLOWUP')).toBe('跟函中')
    })

    it('跟函中 + REPLY_RECEIVED → 已回函', () => {
      expect(transition('跟函中', 'REPLY_RECEIVED')).toBe('已回函')
    })

    it('已回函 + MATCH → 相符', () => {
      expect(transition('已回函', 'MATCH')).toBe('相符')
    })

    it('已回函 + DIFF_FOUND → 有差异', () => {
      expect(transition('已回函', 'DIFF_FOUND')).toBe('有差异')
    })

    it('已回函 + VERIFY_REPLY → 待验证', () => {
      expect(transition('已回函', 'VERIFY_REPLY')).toBe('待验证')
    })

    it('待验证 + MATCH → 相符', () => {
      expect(transition('待验证', 'MATCH')).toBe('相符')
    })

    it('待验证 + DIFF_FOUND → 有差异', () => {
      expect(transition('待验证', 'DIFF_FOUND')).toBe('有差异')
    })

    it('未回函 + ALT_START → 替代中', () => {
      expect(transition('未回函', 'ALT_START')).toBe('替代中')
    })

    it('有差异 + ALT_START → 替代中', () => {
      expect(transition('有差异', 'ALT_START')).toBe('替代中')
    })

    it('相符 + COMPLETE → 完成', () => {
      expect(transition('相符', 'COMPLETE')).toBe('完成')
    })

    it('替代中 + COMPLETE → 完成', () => {
      expect(transition('替代中', 'COMPLETE')).toBe('完成')
    })

    it('已回函 + FRAUD_SIGNAL → 舞弊迹象', () => {
      expect(transition('已回函', 'FRAUD_SIGNAL')).toBe('舞弊迹象')
    })

    it('未回函 + FRAUD_SIGNAL → 舞弊迹象', () => {
      expect(transition('未回函', 'FRAUD_SIGNAL')).toBe('舞弊迹象')
    })
  })

  describe('非法转移拒绝', () => {
    it('未核实 + SEND → null（跳过核实不允许）', () => {
      expect(transition('未核实', 'SEND')).toBeNull()
    })

    it('完成 + VERIFY → null（终态不可转移）', () => {
      expect(transition('完成', 'VERIFY')).toBeNull()
    })

    it('未核实 + COMPLETE → null', () => {
      expect(transition('未核实', 'COMPLETE')).toBeNull()
    })

    it('相符 + DIFF_FOUND → null', () => {
      expect(transition('相符', 'DIFF_FOUND')).toBeNull()
    })
  })

  describe('canTransition()', () => {
    it('合法转移返回 true', () => {
      expect(canTransition('未核实', 'VERIFY')).toBe(true)
      expect(canTransition('已发函', 'REPLY_RECEIVED')).toBe(true)
    })

    it('非法转移返回 false', () => {
      expect(canTransition('完成', 'SEND')).toBe(false)
      expect(canTransition('未核实', 'MATCH')).toBe(false)
    })
  })

  describe('availableEvents()', () => {
    it('未核实只能 VERIFY', () => {
      expect(availableEvents('未核实')).toEqual(['VERIFY'])
    })

    it('已发函有 3 个可选事件', () => {
      const events = availableEvents('已发函')
      expect(events).toContain('FOLLOWUP')
      expect(events).toContain('REPLY_RECEIVED')
      expect(events).toContain('REPLY_TIMEOUT')
      expect(events).toHaveLength(3)
    })

    it('完成状态无可用事件', () => {
      expect(availableEvents('完成')).toHaveLength(0)
    })
  })

  // ─── Composable 级别测试 ───────────────────────────────────────────────────

  describe('useConfirmationStatus composable', () => {
    function createInstance(records: StatusRecord[] = []) {
      const recordsRef = ref<StatusRecord[]>(records)
      return useConfirmationStatus({ records: recordsRef, stalledDays: 7 })
    }

    it('statusOf 返回默认"未核实"', () => {
      const { statusOf } = createInstance()
      expect(statusOf('IDX-001')).toBe('未核实')
    })

    it('statusOf 返回已有记录状态', () => {
      const { statusOf } = createInstance([
        { confirm_index: 'IDX-001', status: '已发函' },
      ])
      expect(statusOf('IDX-001')).toBe('已发函')
    })

    it('tryTransition 成功转移', () => {
      const records = ref<StatusRecord[]>([
        { confirm_index: 'IDX-001', status: '未核实' },
      ])
      const { tryTransition, statusOf } = useConfirmationStatus({ records })

      const success = tryTransition('IDX-001', 'VERIFY')
      expect(success).toBe(true)
      expect(statusOf('IDX-001')).toBe('已核实')
    })

    it('tryTransition 非法转移返回 false', () => {
      const records = ref<StatusRecord[]>([
        { confirm_index: 'IDX-001', status: '未核实' },
      ])
      const { tryTransition, statusOf } = useConfirmationStatus({ records })

      const success = tryTransition('IDX-001', 'SEND')
      expect(success).toBe(false)
      expect(statusOf('IDX-001')).toBe('未核实')
    })

    it('tryTransition 新记录自动创建', () => {
      const records = ref<StatusRecord[]>([])
      const { tryTransition, statusOf } = useConfirmationStatus({ records })

      const success = tryTransition('IDX-NEW', 'VERIFY')
      expect(success).toBe(true)
      expect(statusOf('IDX-NEW')).toBe('已核实')
      expect(records.value).toHaveLength(1)
    })

    it('distribution 统计正确', () => {
      const records = ref<StatusRecord[]>([
        { confirm_index: 'A', status: '已发函' },
        { confirm_index: 'B', status: '已发函' },
        { confirm_index: 'C', status: '已回函' },
        { confirm_index: 'D', status: '完成' },
      ])
      const { distribution } = useConfirmationStatus({ records })

      const dist = distribution.value
      const sent = dist.find(d => d.status === '已发函')
      expect(sent?.count).toBe(2)
      expect(sent?.percentage).toBe(50)

      const replied = dist.find(d => d.status === '已回函')
      expect(replied?.count).toBe(1)
      expect(replied?.percentage).toBe(25)
    })

    it('stalledRecords 检测停滞（超 7 天）', () => {
      const oldDate = new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString()
      const recentDate = new Date().toISOString()

      const records = ref<StatusRecord[]>([
        { confirm_index: 'STALLED', status: '已发函', updated_at: oldDate },
        { confirm_index: 'RECENT', status: '已发函', updated_at: recentDate },
        { confirm_index: 'DONE', status: '完成', updated_at: oldDate },
      ])
      const { stalledRecords } = useConfirmationStatus({ records, stalledDays: 7 })

      // 只有 STALLED 预警（DONE 是终态不预警，RECENT 未超时）
      expect(stalledRecords.value).toHaveLength(1)
      expect(stalledRecords.value[0].confirm_index).toBe('STALLED')
    })

    it('isTerminal 判定终态', () => {
      const { isTerminal } = createInstance()
      expect(isTerminal('完成')).toBe(true)
      expect(isTerminal('舞弊迹象')).toBe(true)
      expect(isTerminal('已发函')).toBe(false)
      expect(isTerminal('未核实')).toBe(false)
    })
  })

  // ─── 完整性检查 ────────────────────────────────────────────────────────────

  describe('状态定义完整性', () => {
    it('共 12 个状态', () => {
      expect(CONFIRMATION_STATUSES).toHaveLength(12)
    })

    it('转移表中所有 from/to 都是有效状态', () => {
      for (const t of TRANSITION_TABLE) {
        expect(CONFIRMATION_STATUSES).toContain(t.from)
        expect(CONFIRMATION_STATUSES).toContain(t.to)
      }
    })

    it('每个非终态至少有一条出边', () => {
      const terminals: ConfirmationStatus[] = ['完成', '舞弊迹象']
      for (const status of CONFIRMATION_STATUSES) {
        if (terminals.includes(status)) continue
        const exits = TRANSITION_TABLE.filter(t => t.from === status)
        expect(exits.length).toBeGreaterThan(0)
      }
    })
  })
})
