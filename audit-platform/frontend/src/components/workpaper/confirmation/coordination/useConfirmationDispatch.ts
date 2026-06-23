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
 * Feature: cross-workpaper-dispatch-persistence — 后端持久化接入
 */
import { computed, ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { ConfirmationRow } from '../confirmationTypes'
import {
  dispatchApi,
  type DispatchEntry as ApiDispatchEntry,
  type DispatchRecord,
  type BatchDispatchResponse,
} from '@/services/dispatchApi'

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
  /** 当前项目 ID */
  projectId: Ref<string>
}

export function useConfirmationDispatch(options: UseConfirmationDispatchOptions) {
  const { rows, dispatchedMap, projectId } = options

  /** 是否正在从后端加载分发记录 */
  const loading = ref(false)
  /** 是否正在执行分发操作 */
  const dispatching = ref(false)

  // ─── 从后端加载分发记录初始化 Map ─────────────────────────────────────────

  /**
   * 从后端加载分发记录填充 dispatchedMap
   * 在组件 onMounted 时调用
   */
  async function loadDispatchRecords(): Promise<void> {
    if (!projectId.value) return
    loading.value = true
    try {
      const response = await dispatchApi.list(projectId.value)
      // 重建 dispatchedMap
      const newMap = new Map<string, Set<DispatchTarget>>()
      for (const record of response.items) {
        const existing = newMap.get(record.confirm_index)
        if (existing) {
          existing.add(record.target as DispatchTarget)
        } else {
          newMap.set(record.confirm_index, new Set([record.target as DispatchTarget]))
        }
      }
      dispatchedMap.value = newMap
    } catch (e: any) {
      ElMessage.warning('加载分发记录失败，分发状态可能不完整')
      // 保持 dispatchedMap 为空，不阻断使用
    } finally {
      loading.value = false
    }
  }

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
   * 执行分发 — 调用后端 API 持久化 + 更新本地 Map
   */
  async function executeDispatch(entries: DispatchEntry[]): Promise<DispatchResult> {
    const result: DispatchResult = { dispatched: [], skipped: [], errors: [] }

    if (!entries.length || !projectId.value) return result

    dispatching.value = true
    try {
      const apiEntries: ApiDispatchEntry[] = entries.map(e => ({
        confirm_index: e.confirm_index,
        target: e.target,
        entity_name: e.entity_name,
        account_type: e.account_type,
        amount: e.amount,
        reason: e.reason,
      }))

      const response: BatchDispatchResponse = await dispatchApi.batchCreate(
        projectId.value,
        apiEntries,
      )

      // 更新本地 dispatchedMap：dispatched + skipped 都标记为已分发
      for (const record of response.dispatched) {
        const existing = dispatchedMap.value.get(record.confirm_index)
        if (existing) {
          existing.add(record.target as DispatchTarget)
        } else {
          dispatchedMap.value.set(record.confirm_index, new Set([record.target as DispatchTarget]))
        }
        // 构建 DispatchEntry 返回
        result.dispatched.push({
          target: record.target as DispatchTarget,
          confirm_index: record.confirm_index,
          entity_name: record.entity_name ?? '',
          account_type: record.account_type ?? '',
          amount: record.amount ?? 0,
          reason: record.reason ?? '',
        })
      }

      for (const item of response.skipped) {
        const target = item.target as DispatchTarget
        const existing = dispatchedMap.value.get(item.confirm_index)
        if (existing) {
          existing.add(target)
        } else {
          dispatchedMap.value.set(item.confirm_index, new Set([target]))
        }
        result.skipped.push({
          target,
          confirm_index: item.confirm_index,
          entity_name: '',
          account_type: '',
          amount: 0,
          reason: item.reason,
        })
      }
    } catch (e: any) {
      ElMessage.warning('分发操作失败，请稍后重试')
      // dispatchedMap 保持不变
    } finally {
      dispatching.value = false
    }

    return result
  }

  /**
   * 撤回分发记录 — 调用后端 API + 从本地 Map 移除
   */
  async function revokeDispatch(
    recordId: string,
    confirmIndex: string,
    target: DispatchTarget,
  ): Promise<boolean> {
    if (!projectId.value) return false

    try {
      await dispatchApi.revoke(projectId.value, recordId)

      // 从 dispatchedMap 移除
      const existing = dispatchedMap.value.get(confirmIndex)
      if (existing) {
        existing.delete(target)
        if (existing.size === 0) {
          dispatchedMap.value.delete(confirmIndex)
        }
      }
      return true
    } catch (e: any) {
      ElMessage.error('撤回失败：' + (e?.response?.data?.detail ?? '请稍后重试'))
      return false
    }
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
    loading,
    dispatching,
    pendingDiffRows,
    pendingAltRows,
    pendingReliabilityRows,
    buildDispatchList,
    executeDispatch,
    revokeDispatch,
    loadDispatchRecords,
    isAlreadyDispatched,
    markDispatched,
    routeAlternative,
  }
}
