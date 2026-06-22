/**
 * useFraudSignalCollector.ts — 上游舞弊迹象自动汇集 D0-8
 *
 * 从 D0-2 / D0-7 / D0-3 / D0-1 自动收集舞弊信号，
 * 映射到 D0-8 预设检查条目（19 条）的对应位置。
 *
 * Sprint 2/4 — 跨表联动核心
 */
import { computed, type Ref } from 'vue'

// ─── 舞弊信号来源定义 ────────────────────────────────────────────────────────

export type FraudSignalSource = 'D0-2' | 'D0-7' | 'D0-3' | 'D0-1'

export interface FraudSignal {
  /** 信号来源底稿 */
  source: FraudSignalSource
  /** 关联函证索引号 */
  confirm_index: string
  /** 信号类型标识 */
  signalType: FraudSignalType
  /** 信号描述（人可读） */
  description: string
  /** 映射到 D0-8 第几条检查项（1-based） */
  targetItemNo: number
  /** 信号发现时间 */
  detected_at: string
  /** 严重程度 */
  severity: 'low' | 'medium' | 'high'
}

export type FraudSignalType =
  | 'RED_FLAG_ADDRESS_CLUSTER'    // D0-2: 地址聚类（多家公司同地址）
  | 'RED_FLAG_PHONE_ADJACENT'    // D0-2: 号段相邻
  | 'RED_FLAG_EMPLOYEE_MATCH'    // D0-2: 撞员工名单
  | 'RED_FLAG_SAME_SENDER'       // D0-2: 同寄件人
  | 'RELIABILITY_UNRELIABLE'     // D0-7: 回函不可靠
  | 'CONTROL_FAILURE'            // D0-3: 控制检查否（串通迹象）
  | 'LOW_REPLY_RATE'             // D0-1: 回函率异常低
  | 'UNUSUAL_PATTERN'            // 通用异常模式

// ─── 信号→D0-8 检查项映射表 ─────────────────────────────────────────────────

/**
 * D0-8 预置 19 条舞弊风险迹象中，上游可自动映射的条目：
 * - 第 7 条：回函可靠性存疑（D0-7 不可靠）
 * - 第 10 条：被函证单位异常特征（D0-2 红旗）
 * - 第 14 条：回函率异常低（D0-1 统计）
 * - 第 15 条：控制环节串通迹象（D0-3 控制否）
 */
const SIGNAL_TO_ITEM_MAP: Record<FraudSignalType, number> = {
  RED_FLAG_ADDRESS_CLUSTER: 10,
  RED_FLAG_PHONE_ADJACENT: 10,
  RED_FLAG_EMPLOYEE_MATCH: 10,
  RED_FLAG_SAME_SENDER: 10,
  RELIABILITY_UNRELIABLE: 7,
  CONTROL_FAILURE: 15,
  LOW_REPLY_RATE: 14,
  UNUSUAL_PATTERN: 10,
}

// ─── Composable 主体 ─────────────────────────────────────────────────────────

export interface UseFraudSignalCollectorOptions {
  /** 已收集的舞弊信号（响应式） */
  signals: Ref<FraudSignal[]>
}

export function useFraudSignalCollector(options: UseFraudSignalCollectorOptions) {
  const { signals } = options

  /**
   * 添加舞弊信号（去重：同 confirm_index + signalType 不重复添加）
   */
  function addSignal(input: Omit<FraudSignal, 'targetItemNo' | 'detected_at'>): boolean {
    // 去重检查
    const exists = signals.value.some(
      s => s.confirm_index === input.confirm_index && s.signalType === input.signalType
    )
    if (exists) return false

    const signal: FraudSignal = {
      ...input,
      targetItemNo: SIGNAL_TO_ITEM_MAP[input.signalType],
      detected_at: new Date().toISOString(),
    }
    signals.value.push(signal)
    return true
  }

  /**
   * 批量添加信号（来自 D0-2 红旗检测结果）
   */
  function addD02RedFlags(
    confirmIndex: string,
    flags: { type: FraudSignalType; description: string; severity: FraudSignal['severity'] }[]
  ): number {
    let added = 0
    for (const flag of flags) {
      const success = addSignal({
        source: 'D0-2',
        confirm_index: confirmIndex,
        signalType: flag.type,
        description: flag.description,
        severity: flag.severity,
      })
      if (success) added++
    }
    return added
  }

  /**
   * D0-7 不可靠信号
   */
  function addD07Unreliable(confirmIndex: string, entityName: string): boolean {
    return addSignal({
      source: 'D0-7',
      confirm_index: confirmIndex,
      signalType: 'RELIABILITY_UNRELIABLE',
      description: `${entityName} 电子回函验证为不可靠`,
      severity: 'high',
    })
  }

  /**
   * D0-3 控制失败信号
   */
  function addD03ControlFailure(confirmIndex: string, entityName: string): boolean {
    return addSignal({
      source: 'D0-3',
      confirm_index: confirmIndex,
      signalType: 'CONTROL_FAILURE',
      description: `${entityName} 跟函控制检查存在否定项（串通迹象）`,
      severity: 'high',
    })
  }

  /**
   * D0-1 低回函率信号
   */
  function addD01LowReplyRate(replyRate: number): boolean {
    return addSignal({
      source: 'D0-1',
      confirm_index: '__aggregate__',
      signalType: 'LOW_REPLY_RATE',
      description: `整体回函率 ${replyRate.toFixed(1)}% 异常偏低`,
      severity: replyRate < 50 ? 'high' : 'medium',
    })
  }

  // ─── 按 D0-8 检查项聚合 ───────────────────────────────────────────────────

  /** 按目标检查项分组的信号 */
  const signalsByItem = computed(() => {
    const map = new Map<number, FraudSignal[]>()
    for (const signal of signals.value) {
      const existing = map.get(signal.targetItemNo) ?? []
      existing.push(signal)
      map.set(signal.targetItemNo, existing)
    }
    return map
  })

  /** 按来源分组的信号 */
  const signalsBySource = computed(() => {
    const map = new Map<FraudSignalSource, FraudSignal[]>()
    for (const signal of signals.value) {
      const existing = map.get(signal.source) ?? []
      existing.push(signal)
      map.set(signal.source, existing)
    }
    return map
  })

  /** 是否存在高严重度信号 */
  const hasHighSeverity = computed(() => {
    return signals.value.some(s => s.severity === 'high')
  })

  /** 信号总数 */
  const totalSignals = computed(() => signals.value.length)

  /**
   * 导出为 D0-8 可消费的格式
   * 返回 itemNo → { exists: '是', index_ref, response_note } 预填值
   */
  function exportForD08(): Map<number, { exists: string; index_refs: string[]; note: string }> {
    const result = new Map<number, { exists: string; index_refs: string[]; note: string }>()

    for (const [itemNo, itemSignals] of signalsByItem.value) {
      const indices = itemSignals
        .filter(s => s.confirm_index !== '__aggregate__')
        .map(s => s.confirm_index)
      const descriptions = itemSignals.map(s => s.description)

      result.set(itemNo, {
        exists: '是',
        index_refs: [...new Set(indices)],
        note: descriptions.join('；'),
      })
    }

    return result
  }

  return {
    signals,
    addSignal,
    addD02RedFlags,
    addD07Unreliable,
    addD03ControlFailure,
    addD01LowReplyRate,
    signalsByItem,
    signalsBySource,
    hasHighSeverity,
    totalSignals,
    exportForD08,
  }
}
