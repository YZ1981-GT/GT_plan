/**
 * useChainExecution — 全链路一键刷新编排 composable
 *
 * 职责：
 * - 调用 execute-full-chain API 触发全链路执行
 * - 通过 SSE 订阅实时进度
 * - 管理各步骤状态（pending → running → completed/failed）
 * - 暴露 loading / executing / stepStatuses 给 UI 层
 *
 * 对应需求：11.1-11.7
 *
 * @module composables/useChainExecution
 */
import { ref, computed, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import { chainWorkflow } from '@/services/apiPaths'
import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'

export type StepKey = 'recalc_tb' | 'generate_workpapers' | 'generate_reports' | 'generate_notes'
export type StepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped'

export interface StepState {
  key: StepKey
  label: string
  status: StepStatus
  durationMs?: number
  error?: string
  summary?: string
}

export interface ChainExecutionResult {
  execution_id: string
  status: string
  steps: Record<string, any>
  total_duration_ms?: number
}

const STEP_LABELS: Record<StepKey, string> = {
  recalc_tb: '重算试算表',
  generate_workpapers: '生成底稿',
  generate_reports: '生成报表',
  generate_notes: '生成附注',
}

const STEP_ORDER: StepKey[] = ['recalc_tb', 'generate_workpapers', 'generate_reports', 'generate_notes']

export function useChainExecution(projectId: Ref<string>) {
  const executing = ref(false)
  const executionId = ref<string | null>(null)
  const stepStates = ref<StepState[]>(buildInitialSteps())
  const totalDurationMs = ref<number | null>(null)
  const executionStatus = ref<string>('')
  const conflictMessage = ref('')

  // SSE 相关
  let eventSource: EventSource | null = null

  function buildInitialSteps(): StepState[] {
    return STEP_ORDER.map(key => ({
      key,
      label: STEP_LABELS[key],
      status: 'pending' as StepStatus,
    }))
  }

  function resetSteps() {
    stepStates.value = buildInitialSteps()
    totalDurationMs.value = null
    executionStatus.value = ''
    conflictMessage.value = ''
  }

  /** 获取步骤状态的 computed 快捷方式 */
  const completedCount = computed(() =>
    stepStates.value.filter(s => s.status === 'completed').length
  )
  const failedCount = computed(() =>
    stepStates.value.filter(s => s.status === 'failed').length
  )
  const isAllDone = computed(() =>
    stepStates.value.every(s => s.status === 'completed' || s.status === 'skipped' || s.status === 'failed')
  )

  /**
   * 执行全链路
   * @param year 审计年度
   * @param steps 可选指定步骤（默认全部）
   * @param force 是否强制执行
   */
  async function executeFullChain(year: number, steps?: StepKey[], force = false) {
    if (!projectId.value) return
    if (executing.value) return

    executing.value = true
    resetSteps()

    try {
      const body: Record<string, any> = { year, force }
      if (steps && steps.length > 0) {
        body.steps = steps
      }

      const result = await api.post<ChainExecutionResult>(
        chainWorkflow.executeFullChain(projectId.value),
        body,
      )

      executionId.value = result.execution_id
      executionStatus.value = result.status

      // 订阅 SSE 进度
      subscribeProgress(result.execution_id)
    } catch (err: any) {
      executing.value = false
      // 处理 409 冲突（项目正在执行中）
      const status = err?.response?.status
      if (status === 409) {
        const detail = err?.response?.data?.detail || err?.response?.data?.message
        const msg = typeof detail === 'object' ? detail.message || detail.error : detail
        conflictMessage.value = msg || '项目正在执行中，请稍后再试'
        ElMessage.warning(conflictMessage.value)
      } else {
        handleApiError(err, '全链路执行')
      }
    }
  }

  /** 订阅 SSE 进度流 */
  function subscribeProgress(execId: string) {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }

    const url = chainWorkflow.progress(projectId.value, execId)
    // 获取 token 用于 SSE 认证（通过 query param）
    const token = sessionStorage.getItem('token') || localStorage.getItem('token') || ''
    const sseUrl = `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`

    eventSource = new EventSource(sseUrl)

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        handleSSEEvent(data)
      } catch {
        // 忽略解析错误
      }
    }

    eventSource.onerror = () => {
      // SSE 连接断开，标记执行完成（可能已完成或网络问题）
      if (eventSource) {
        eventSource.close()
        eventSource = null
      }
      // 如果还在执行中，延迟检查最终状态
      if (executing.value) {
        setTimeout(() => checkFinalStatus(execId), 2000)
      }
    }
  }

  /** 处理 SSE 事件 */
  function handleSSEEvent(data: any) {
    const { step, status, type, duration_ms, error_message, summary, total_duration_ms, results } = data

    // 终止事件：全链路完成
    if (type === 'chain_completed') {
      totalDurationMs.value = total_duration_ms || null
      executionStatus.value = 'completed'
      finishExecution(results)
      return
    }

    // 步骤状态更新
    if (step && status) {
      const stepState = stepStates.value.find(s => s.key === step)
      if (stepState) {
        stepState.status = status as StepStatus
        if (duration_ms) stepState.durationMs = duration_ms
        if (error_message) stepState.error = error_message
        if (summary) stepState.summary = summary
      }
    }
  }

  /** 执行完成后的处理 */
  function finishExecution(results?: any) {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    executing.value = false

    // 显示摘要通知
    showCompletionMessage()
  }

  /** 显示完成摘要 */
  function showCompletionMessage() {
    const completed = completedCount.value
    const failed = failedCount.value
    const total = stepStates.value.length

    if (failed === 0) {
      ElMessage.success(`全链路执行完成：${completed}/${total} 步骤成功`)
    } else if (completed > 0) {
      ElMessage.warning(`全链路部分完成：${completed} 成功，${failed} 失败`)
    } else {
      ElMessage.error(`全链路执行失败：${failed} 步骤失败`)
    }
  }

  /** SSE 断开后检查最终状态 */
  async function checkFinalStatus(execId: string) {
    if (!executing.value) return
    try {
      const executions = await api.get<any[]>(chainWorkflow.executions(projectId.value))
      const exec = Array.isArray(executions)
        ? executions.find((e: any) => e.id === execId || e.execution_id === execId)
        : null
      if (exec && (exec.status === 'completed' || exec.status === 'failed' || exec.status === 'partially_failed')) {
        // 从执行记录更新步骤状态
        if (exec.steps) {
          for (const [key, info] of Object.entries(exec.steps as Record<string, any>)) {
            const stepState = stepStates.value.find(s => s.key === key)
            if (stepState && info) {
              stepState.status = (info as any).status || stepState.status
              stepState.durationMs = (info as any).duration_ms
              stepState.error = (info as any).error
            }
          }
        }
        executionStatus.value = exec.status
        totalDurationMs.value = exec.total_duration_ms || null
        finishExecution()
      } else {
        // 仍在执行中，继续等待
        executing.value = false
      }
    } catch {
      executing.value = false
    }
  }

  /** 清理 SSE 连接 */
  function cleanup() {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
  }

  return {
    executing,
    executionId,
    stepStates,
    totalDurationMs,
    executionStatus,
    conflictMessage,
    completedCount,
    failedCount,
    isAllDone,
    executeFullChain,
    resetSteps,
    cleanup,
  }
}
