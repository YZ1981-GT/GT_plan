/**
 * 程序表控制台「程序行委派」对话框（从 GtAProgramConsole.vue 原样抽出 —— 该组件有行数守卫 ≤1900）。
 *
 * 管理者给已物化的程序行指定执行人 / 复核人：服务端 preview（一次性凭证 + TTL）→ apply。
 * spec procedure-trim-generation-delegation-chain 任务 13：
 * - 预览计数在嵌套的 summary 里，`scope_gaps` 提示执行人 / 复核人看不到的循环；
 * - 应用遇 400 out_of_scope ⇒ 填写理由后同一凭证 / 请求号带 expand_scope 重试（需求 4.4）；
 * - 其他错误交给 handleApiError 取中文原因（错误体 message 可能是对象，原先直接显示成 [object Object]）。
 */
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { applyProcedureDelegation, ensureProgramRowTask, previewProcedureDelegation } from '@/services/commonApi'
import { listAssignments } from '@/services/staffApi'
import { handleApiError } from '@/utils/errorHandler'
import { describeScopeGaps, withScopeExpansionRetry } from '@/composables/useScopeExpansionRetry'
import { newRequestId, type OverlayRow } from '@/components/workpaper/composables/procedureConsoleOverlay'

export interface DelegateTeamMember { staff_id: string; staff_name: string; role_label?: string }

export interface DelegateDialogState {
  visible: boolean; row: OverlayRow | null; assigneeId: string; reviewerId: string;
  previewStats: any | null; previewId: string; reqId: string; ttl: string | null; loading: boolean;
}

const ROLE_LABELS: Record<string, string> = {
  partner: '合伙人', signing_partner: '签字合伙人', manager: '项目经理',
  auditor: '审计员', reviewer: '复核', eqcr: 'EQCR',
}

export function useProgramRowDelegate(ctx: {
  projectId: () => string
  onApplied: () => unknown
  /** 逐行委派（行上没有任务字段时）按需建任务用 */
  wpId?: () => string
  sheetName?: () => string
}) {
  const delegateDialog = ref<DelegateDialogState>({
    visible: false, row: null, assigneeId: '', reviewerId: '', previewStats: null, previewId: '', reqId: '', ttl: null, loading: false,
  })
  /** 预览的 scope_gaps：执行人 / 复核人看不到的循环，应用时需填写理由扩大可见范围（空串 = 无缺口） */
  const delegateScopeGapText = computed(() => describeScopeGaps(delegateDialog.value.previewStats?.scope_gaps))
  const teamMembers = ref<DelegateTeamMember[]>([])

  async function loadTeamMembers() {
    if (!ctx.projectId()) return
    try {
      const list = await listAssignments(ctx.projectId())
      teamMembers.value = (Array.isArray(list) ? list : [])
        .filter((a: any) => a.staff_id)
        .map((a: any) => ({ staff_id: a.staff_id, staff_name: a.staff_name || a.staff_id.slice(0, 8), role_label: ROLE_LABELS[a.role] || a.role || '' }))
    } catch { teamMembers.value = [] }
  }

  function openDelegate(row: object) {
    const o = row as unknown as OverlayRow
    delegateDialog.value = {
      visible: true, row: o, assigneeId: o.assignee_staff_id || '', reviewerId: o.reviewer_staff_id || '',
      previewStats: null, previewId: '', reqId: '', ttl: null, loading: false,
    }
    if (!teamMembers.value.length) loadTeamMembers()
  }

  /**
   * 逐行委派（spec procedure-chain-followup-closure R2.2）：程序行任务开关关闭时行上没有 task_id，
   * 先请服务端取 / 建这一行的任务（同一程序号的新旧定义任务一起委派），再进同一个预览 → 应用对话框。
   */
  async function openDelegateForProgramRow(row: { program_no: number | string }) {
    if (!ctx.wpId?.()) return
    try {
      const ref = await ensureProgramRowTask(ctx.projectId(), ctx.wpId(), ctx.sheetName?.() || '', row.program_no)
      openDelegate({
        ...row, task_id: ref.task_ids[0], task_ids: ref.task_ids,
        assignee_staff_id: ref.assignee_staff_id, reviewer_staff_id: ref.reviewer_staff_id,
      })
    } catch (e) {
      handleApiError(e, '委派')
    }
  }

  function delegationBody(taskId: string) {
    const ids = (delegateDialog.value.row as { task_ids?: string[] } | null)?.task_ids
    return {
      selector: { kind: 'row' as const, task_ids: ids?.length ? ids : [taskId] },
      assignee_staff_id: delegateDialog.value.assigneeId,
      reviewer_staff_id: delegateDialog.value.reviewerId || null,
    }
  }

  async function runDelegatePreview() {
    const o = delegateDialog.value.row
    if (!o?.task_id || !delegateDialog.value.assigneeId) {
      ElMessage.warning('请选择程序执行人')
      return
    }
    delegateDialog.value.loading = true
    try {
      const res = await previewProcedureDelegation(ctx.projectId(), delegationBody(o.task_id), { silent: true })
      delegateDialog.value.previewStats = res
      delegateDialog.value.previewId = res?.preview_id || res?.preview?.id || ''
      delegateDialog.value.reqId = newRequestId()
      delegateDialog.value.ttl = res?.expires_at || res?.preview?.expires_at || null
      // 前置（导入程序行定义 / 生成行任务 / 绑定底稿）没成功：预览照常返回，但目标数可能不全（spec procedure-chain-hardening R13）
      if (res?.preparation_ready === false) {
        ElMessage.warning(`${res?.materialization?.error || '程序行任务没有准备好'}，预览的目标数可能不全，请稍后重新预览`)
      }
    } catch (e: any) {
      // 请求静默、这里提示一次：422 写明原因与处理办法（如所选人员没有关联登录账号，spec procedure-chain-hardening R12.3）
      handleApiError(e, '委派预览')
    } finally {
      delegateDialog.value.loading = false
    }
  }

  async function runDelegateApply() {
    const o = delegateDialog.value.row
    if (!o?.task_id || !delegateDialog.value.previewId) return
    const targetCount = delegateDialog.value.previewStats?.summary?.targets
    if (targetCount === 0) {
      ElMessage.warning(delegateDialog.value.previewStats?.hint || '没有可委派的程序行')
      return
    }
    delegateDialog.value.loading = true
    try {
      const body = delegationBody(o.task_id)
      const out = await withScopeExpansionRetry((exp) => applyProcedureDelegation(
        ctx.projectId(), delegateDialog.value.previewId, delegateDialog.value.reqId, body, { ...exp, silent: true }))
      if (out.status === 'cancelled') { ElMessage.info('已取消委派，预览仍可使用'); return }
      const res = out.result
      const applied = res?.applied ?? res?.changed ?? 0
      ElMessage.success(`委派完成：应用 ${applied} 项`)
      delegateDialog.value.visible = false
      await ctx.onApplied()
    } catch (e: any) {
      if (e?.response?.status === 409) {
        ElMessage.warning('预览已失效（过期/一次消费/目标版本变化），请重新预览')
        delegateDialog.value.previewId = ''
        delegateDialog.value.previewStats = null
      } else {
        handleApiError(e, '委派')
      }
    } finally {
      delegateDialog.value.loading = false
    }
  }

  return {
    delegateDialog, delegateScopeGapText, teamMembers, loadTeamMembers,
    openDelegate, openDelegateForProgramRow, runDelegatePreview, runDelegateApply,
  }
}
