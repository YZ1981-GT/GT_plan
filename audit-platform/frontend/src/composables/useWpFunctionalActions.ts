/**
 * useWpFunctionalActions — 底稿功能行为动作 composable
 *
 * 职责：
 *  1. 根据底稿 functional_type 获取可用动作列表
 *  2. 渲染工具栏动作按钮
 *  3. 执行动作（调后端取数 → 填回 parsed_data → 触发定位）
 *
 * @example
 *   const { actions, loading, executeAction, loadActions } = useWpFunctionalActions(projectId, wpId)
 *   await loadActions()
 *   // actions.value = [{ label: '截止测试取数', icon: '📅', ... }]
 *   await executeAction('截止测试取数', { account_codes: ['6001'], year: 2025 })
 */
import { ref, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import { ElMessage } from 'element-plus'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ActionInfo {
  label: string
  description: string
  endpoint: string
  method: string
  params_schema: Record<string, any>
  fill_strategy: string
  requires_llm: boolean
  icon: string
}

export interface ActionsResponse {
  functional_type: string | null
  actions: ActionInfo[]
}

export interface ExecuteActionResult {
  success: boolean
  message: string
  data: Record<string, any> | null
  rows_affected: number
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useWpFunctionalActions(projectId: Ref<string>, wpId: Ref<string>) {
  const actions = ref<ActionInfo[]>([])
  const functionalType = ref<string | null>(null)
  const loading = ref(false)
  const executing = ref(false)
  const lastResult = ref<ExecuteActionResult | null>(null)

  /**
   * 加载底稿可用动作列表
   */
  async function loadActions(): Promise<void> {
    if (!projectId.value || !wpId.value) return

    loading.value = true
    try {
      const resp = await api.get<ActionsResponse>(
        `/api/projects/${projectId.value}/workpapers/${wpId.value}/actions`
      )
      functionalType.value = resp.functional_type
      actions.value = resp.actions
    } catch (e: any) {
      console.warn('[useWpFunctionalActions] 加载动作失败:', e?.message)
      actions.value = []
      functionalType.value = null
    } finally {
      loading.value = false
    }
  }

  /**
   * 执行指定动作
   */
  async function executeAction(
    actionLabel: string,
    params: Record<string, any>
  ): Promise<ExecuteActionResult | null> {
    if (!projectId.value || !wpId.value) return null

    executing.value = true
    try {
      const result = await api.post<ExecuteActionResult>(
        `/api/projects/${projectId.value}/workpapers/${wpId.value}/actions/execute`,
        { action_label: actionLabel, params }
      )
      lastResult.value = result

      if (result.success) {
        ElMessage.success(`${actionLabel} 完成，影响 ${result.rows_affected} 行`)
        // 触发 locate-cell 事件定位到新数据（通过 eventBus）
        _emitLocateAfterFill()
      } else {
        ElMessage.warning(result.message)
      }

      return result
    } catch (e: any) {
      const msg = e?.response?.data?.detail?.message || e?.message || '执行失败'
      ElMessage.error(msg)
      lastResult.value = { success: false, message: msg, data: null, rows_affected: 0 }
      return null
    } finally {
      executing.value = false
    }
  }

  /**
   * 填充后触发定位到新数据区域
   */
  function _emitLocateAfterFill() {
    // 通过 eventBus 发送 locate-cell 事件
    // 定位到 action_data 区域的第一行
    try {
      import('@/utils/eventBus').then(({ eventBus }) => {
        eventBus.emit('workpaper:locate-cell', {
          wpId: wpId.value,
          sheetName: undefined, // 当前 sheet
          cellRef: 'A1',        // 滚动到顶部新数据区
        })
      })
    } catch {
      // eventBus 不可用时静默
    }
  }

  /**
   * 检查是否有可用动作
   */
  function hasActions(): boolean {
    return actions.value.length > 0
  }

  return {
    actions,
    functionalType,
    loading,
    executing,
    lastResult,
    loadActions,
    executeAction,
    hasActions,
  }
}
