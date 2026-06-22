/**
 * useConfirmationDispatch.ts — D0-1 枢纽分发逻辑
 *
 * 从 D0-1 函证汇总表将行分发到下游底稿：
 * - 差异 ≠ 0 → D0-4（差异调节表）
 * - 未回函 → D0-5（合同负债/销售）或 D0-6（应收/销售），按科目大类路由
 * - 电子回函 → D0-7（回函可靠性验证）
 *
 * 与下游"从 D0-1 带入"统一去重逻辑（双向等价）
 *
 * Sprint 4 Tasks 4.1, 4.2
 */
import { computed, type Ref } from 'vue'
import type { ConfirmationRow } from '../confirmationTypes'

// ─── 分发目标定义 ────────────────────────────────────────────────────────────

export type DispatchTarget = 'D0-4' | 'D0-5' | 'D0-6' | 'D0-7'

export interface DispatchEntry {
  /** 目标底稿 */
  target: DispatchTarget
  /** 源函证索引号 */
  confirm_index: string
  /** 被函证单位 */
  entity_name: string
  /** 科目大类 */
  account_type: string
  /** 函证金额 */
  amount: number
  /** 分发原因 */
  reason: string
}

export interface DispatchResult {
  /** 成功分发的条目 */
  dispatched: DispatchEntry[]
  /** 已存在（去重跳过）的条目 */
  skipped: DispatchEntry[]
  /** 分发错误 */
  errors: { confirm_index: string; message: string }[]
}

// ─── 科目→替代程序路由规则 ──────────────────────────────────────────────────

/** D0-5 接收的科目（合同负债类） */
const D05_ACCOUNT_TYPES = new Set([
  '合同负债',
  '预收账款',
])

/** D0-6 接收的科目（应收类，默认兜底） */
const D06_ACCOUNT_TYPES = new Set([
  '应收账款',
  '其他应收款',
])

/**
 * 根据科目大类决定替代程序路由到 D0-5 或 D0-6
 * - 合同负债/预收账款 → D0-5
 * - 应收账款/其他应收款 → D0-6
 * - 其他 → D0-6（兜底）
 */
export function routeAlternative(accountType: string): 'D0-5' | 'D0-6' {
  if (D05_ACCOUNT_TYPES.has(accountType)) return 'D0-5'
  return 'D0-6'
}

// ─── Composable 主体 ─────────────────────────────────────────────────────────

export interface UseConfirmationDispatchOptions {
  /** D0-1 全部行数据 */
  rows: Ref<ConfirmationRow[]>
  /** 已分发记录（confirm_index → target[] 映射） */
  dispatchedMap: Ref<Map<string, Set<DispatchTarget>>>
}

export function useConfirmationDispatch(options: UseConfirmationDispatchOptions) {
  const { rows, dispatchedMap } = options

  // ─── 计算待分发行 ──────────────────────────────────────────────────────────

  /** 差异 ≠ 0 且未分发到 D0-4 的行 */
  const pendingDiffRows = computed(() => {
    return rows.value.filter(row => {
      if (!row.confirm_index) return false
      const diff = (row.amount ?? 0) - (row.reply_amount ?? 0)
      if (diff === 0) return false
      if (row.match_status === '相符') return false
      // 检查是否已分发
      const dispatched = dispatchedMap.value.get(row.confirm_index)
      return !dispatched?.has('D0-4')
    })
  })

  /** 未回函且未分发到 D0-5/D0-6 的行 */
  const pendingAltRows = computed(() => {
    return rows.value.filter(row => {
      if (!row.confirm_index) return false
      if (row.is_replied !== false && row.match_status !== '未回函') return false
      // 积极式未回函才需要替代程序
      if (row.confirmation_method === '消极式') return false
      const dispatched = dispatchedMap.value.get(row.confirm_index)
      const target = routeAlternative(row.account_type ?? '')
      return !dispatched?.has(target)
    })
  })

  /** 电子回函且未分发到 D0-7 的行 */
  const pendingReliabilityRows = computed(() => {
    return rows.value.filter(row => {
      if (!row.confirm_index) return false
      if (!row.electronic_reply) return false
      // 回函方式为传真或电子邮件
      const method = row.reply_method ?? ''
      if (!['传真', '电子邮件'].includes(method)) return false
      const dispatched = dispatchedMap.value.get(row.confirm_index)
      return !dispatched?.has('D0-7')
    })
  })

  // ─── 分发动作 ──────────────────────────────────────────────────────────────

  /**
   * 构建分发清单（预览用，不实际执行）
   */
  function buildDispatchList(): DispatchEntry[] {
    const entries: DispatchEntry[] = []

    for (const row of pendingDiffRows.value) {
      entries.push({
        target: 'D0-4',
        confirm_index: row.confirm_index!,
        entity_name: row.entity_name ?? '',
        account_type: row.account_type ?? '',
        amount: row.amount ?? 0,
        reason: `差异金额 ${((row.amount ?? 0) - (row.reply_amount ?? 0)).toFixed(2)} 元`,
      })
    }

    for (const row of pendingAltRows.value) {
      const target = routeAlternative(row.account_type ?? '')
      entries.push({
        target,
        confirm_index: row.confirm_index!,
        entity_name: row.entity_name ?? '',
        account_type: row.account_type ?? '',
        amount: row.amount ?? 0,
        reason: '未回函需替代程序',
      })
    }

    for (const row of pendingReliabilityRows.value) {
      entries.push({
        target: 'D0-7',
        confirm_index: row.confirm_index!,
        entity_name: row.entity_name ?? '',
        account_type: row.account_type ?? '',
        amount: row.amount ?? 0,
        reason: `电子回函(${row.reply_method})需验证可靠性`,
      })
    }

    return entries
  }

  /**
   * 执行分发（标记已分发）
   * 实际跨底稿写入由 EventBus 事件触发下游组件处理
   */
  function executeDispatch(entries: DispatchEntry[]): DispatchResult {
    const result: DispatchResult = { dispatched: [], skipped: [], errors: [] }

    for (const entry of entries) {
      const existing = dispatchedMap.value.get(entry.confirm_index)
      if (existing?.has(entry.target)) {
        result.skipped.push(entry)
        continue
      }

      // 标记已分发
      if (!dispatchedMap.value.has(entry.confirm_index)) {
        dispatchedMap.value.set(entry.confirm_index, new Set())
      }
      dispatchedMap.value.get(entry.confirm_index)!.add(entry.target)
      result.dispatched.push(entry)
    }

    return result
  }

  /**
   * 去重校验：下游已存在的行不重复分发
   * 与下游"从 D0-1 带入"等价（双向去重）
   */
  function isAlreadyDispatched(confirmIndex: string, target: DispatchTarget): boolean {
    return dispatchedMap.value.get(confirmIndex)?.has(target) ?? false
  }

  /**
   * 下游带入回标（下游组件创建行后回调标记）
   */
  function markDispatched(confirmIndex: string, target: DispatchTarget): void {
    if (!dispatchedMap.value.has(confirmIndex)) {
      dispatchedMap.value.set(confirmIndex, new Set())
    }
    dispatchedMap.value.get(confirmIndex)!.add(target)
  }

  return {
    pendingDiffRows,
    pendingAltRows,
    pendingReliabilityRows,
    buildDispatchList,
    executeDispatch,
    isAlreadyDispatched,
    markDispatched,
    routeAlternative,
  }
}
