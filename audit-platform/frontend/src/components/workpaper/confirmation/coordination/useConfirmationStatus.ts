/**
 * useConfirmationStatus.ts — 函证状态机 composable
 *
 * 12 态状态机：
 * 未核实 → 已核实 → 已发函 → 跟函中 → 已回函/未回函 → 待验证 → 相符/有差异 → 替代中/完成 → 舞弊迹象
 *
 * 事件驱动转移 + 验证 + 分布统计 + 停滞预警
 *
 * Sprint 2 Tasks 2.2, 2.5
 */
import { computed, type Ref } from 'vue'

// ─── 状态定义（12 态） ───────────────────────────────────────────────────────

export const CONFIRMATION_STATUSES = [
  '未核实',
  '已核实',
  '已发函',
  '跟函中',
  '已回函',
  '未回函',
  '待验证',
  '相符',
  '有差异',
  '替代中',
  '完成',
  '舞弊迹象',
] as const

export type ConfirmationStatus = typeof CONFIRMATION_STATUSES[number]

// ─── 状态转移事件 ────────────────────────────────────────────────────────────

export type StatusEvent =
  | 'VERIFY'           // D0-2 核实通过 → 已核实
  | 'SEND'             // D0-1 发函 → 已发函
  | 'FOLLOWUP'         // D0-3 跟函 → 跟函中
  | 'REPLY_RECEIVED'   // D0-1 收到回函 → 已回函
  | 'REPLY_TIMEOUT'    // 超期未回 → 未回函
  | 'VERIFY_REPLY'     // D0-7 验证回函 → 待验证
  | 'MATCH'            // 验证相符 → 相符
  | 'DIFF_FOUND'       // D0-4 发现差异 → 有差异
  | 'ALT_START'        // D0-5/D0-6 启动替代 → 替代中
  | 'COMPLETE'         // 最终完成 → 完成
  | 'FRAUD_SIGNAL'     // D0-8 舞弊迹象 → 舞弊迹象

// ─── 合法转移表（from → event → to） ────────────────────────────────────────

export interface Transition {
  from: ConfirmationStatus
  event: StatusEvent
  to: ConfirmationStatus
}

export const TRANSITION_TABLE: Transition[] = [
  { from: '未核实', event: 'VERIFY', to: '已核实' },
  { from: '已核实', event: 'SEND', to: '已发函' },
  { from: '已发函', event: 'FOLLOWUP', to: '跟函中' },
  { from: '已发函', event: 'REPLY_RECEIVED', to: '已回函' },
  { from: '已发函', event: 'REPLY_TIMEOUT', to: '未回函' },
  { from: '跟函中', event: 'REPLY_RECEIVED', to: '已回函' },
  { from: '跟函中', event: 'REPLY_TIMEOUT', to: '未回函' },
  { from: '已回函', event: 'VERIFY_REPLY', to: '待验证' },
  { from: '已回函', event: 'MATCH', to: '相符' },
  { from: '已回函', event: 'DIFF_FOUND', to: '有差异' },
  { from: '待验证', event: 'MATCH', to: '相符' },
  { from: '待验证', event: 'DIFF_FOUND', to: '有差异' },
  { from: '未回函', event: 'ALT_START', to: '替代中' },
  { from: '有差异', event: 'ALT_START', to: '替代中' },
  { from: '相符', event: 'COMPLETE', to: '完成' },
  { from: '替代中', event: 'COMPLETE', to: '完成' },
  { from: '有差异', event: 'COMPLETE', to: '完成' },
  // 舞弊迹象可从多个状态触发（任何已回函后的状态）
  { from: '已回函', event: 'FRAUD_SIGNAL', to: '舞弊迹象' },
  { from: '待验证', event: 'FRAUD_SIGNAL', to: '舞弊迹象' },
  { from: '有差异', event: 'FRAUD_SIGNAL', to: '舞弊迹象' },
  { from: '替代中', event: 'FRAUD_SIGNAL', to: '舞弊迹象' },
  { from: '未回函', event: 'FRAUD_SIGNAL', to: '舞弊迹象' },
]

// ─── 状态机核心逻辑 ──────────────────────────────────────────────────────────

export interface StatusRecord {
  confirm_index: string
  status: ConfirmationStatus
  updated_at?: string
}

/**
 * 校验状态转移是否合法
 */
export function canTransition(current: ConfirmationStatus, event: StatusEvent): boolean {
  return TRANSITION_TABLE.some(t => t.from === current && t.event === event)
}

/**
 * 执行状态转移，返回新状态；非法转移返回 null
 */
export function transition(current: ConfirmationStatus, event: StatusEvent): ConfirmationStatus | null {
  const match = TRANSITION_TABLE.find(t => t.from === current && t.event === event)
  return match?.to ?? null
}

/**
 * 获取当前状态可用的所有事件
 */
export function availableEvents(current: ConfirmationStatus): StatusEvent[] {
  return TRANSITION_TABLE
    .filter(t => t.from === current)
    .map(t => t.event)
}

// ─── Composable 主体 ─────────────────────────────────────────────────────────

export interface UseConfirmationStatusOptions {
  /** 全部函证状态记录（响应式） */
  records: Ref<StatusRecord[]>
  /** 停滞天数阈值（默认 7 天） */
  stalledDays?: number
}

export interface StatusDistribution {
  status: ConfirmationStatus
  count: number
  percentage: number
}

export function useConfirmationStatus(options: UseConfirmationStatusOptions) {
  const { records, stalledDays = 7 } = options

  /**
   * 获取指定函证的当前状态
   */
  function statusOf(confirmIndex: string): ConfirmationStatus {
    const record = records.value.find(r => r.confirm_index === confirmIndex)
    return record?.status ?? '未核实'
  }

  /**
   * 尝试转移状态，返回是否成功
   */
  function tryTransition(confirmIndex: string, event: StatusEvent): boolean {
    const record = records.value.find(r => r.confirm_index === confirmIndex)
    if (!record) {
      // 新记录，从"未核实"开始
      const newStatus = transition('未核实', event)
      if (!newStatus) return false
      records.value.push({
        confirm_index: confirmIndex,
        status: newStatus,
        updated_at: new Date().toISOString(),
      })
      return true
    }

    const newStatus = transition(record.status, event)
    if (!newStatus) return false

    record.status = newStatus
    record.updated_at = new Date().toISOString()
    return true
  }

  /**
   * 状态分布统计（看板用）
   */
  const distribution = computed<StatusDistribution[]>(() => {
    const total = records.value.length
    if (total === 0) return []

    const countMap = new Map<ConfirmationStatus, number>()
    for (const status of CONFIRMATION_STATUSES) {
      countMap.set(status, 0)
    }
    for (const record of records.value) {
      const current = countMap.get(record.status) ?? 0
      countMap.set(record.status, current + 1)
    }

    return CONFIRMATION_STATUSES.map(status => ({
      status,
      count: countMap.get(status) ?? 0,
      percentage: total > 0 ? ((countMap.get(status) ?? 0) / total) * 100 : 0,
    }))
  })

  /**
   * 停滞预警：超过阈值天数未变化的函证
   */
  const stalledRecords = computed<StatusRecord[]>(() => {
    const now = Date.now()
    const threshold = stalledDays * 24 * 60 * 60 * 1000

    return records.value.filter(record => {
      // 终态不预警
      if (record.status === '完成' || record.status === '舞弊迹象') return false
      if (!record.updated_at) return true // 无时间戳视为停滞
      const elapsed = now - new Date(record.updated_at).getTime()
      return elapsed > threshold
    })
  })

  /**
   * 是否处于终态
   */
  function isTerminal(status: ConfirmationStatus): boolean {
    return status === '完成' || status === '舞弊迹象'
  }

  return {
    statusOf,
    tryTransition,
    canTransition,
    availableEvents,
    distribution,
    stalledRecords,
    isTerminal,
  }
}
