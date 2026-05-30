/**
 * useReviewStateMachine — 状态机流转 composable
 *
 * 包含：onTransitionClick / canTransition / getAvailableTransitions / 审计日志
 * 参数：props (schema state_machine config, htmlData initial state) + emit
 * 返回：currentState / availableTransitions / isFinalState / auditLog / transition() / onTransitionClick()
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

// ─── Types ───────────────────────────────────────────────────────────────────

interface StateDef {
  id: string
  label: string
  class?: 'info' | 'warning' | 'success' | 'danger'
}

interface TransitionDef {
  from: string
  to: string
  trigger: string
  description?: string
}

interface StateMachineDef {
  states?: StateDef[]
  transitions?: TransitionDef[]
  initial?: string
  final?: string[]
  cell?: string
  audit_log?: boolean
}

interface AuditLogEntry {
  from: string
  to: string
  trigger: string
  user?: string
  timestamp: string
  reason?: string
}

interface StateChangePayload {
  from: string
  to: string
  trigger: string
  reason?: string
  user?: string
  timestamp: string
}

interface FieldChangePayload {
  field_name: string
  old_value?: any
  new_value?: any
  cell?: string
}

interface UseReviewStateMachineParams {
  getStateMachine: () => StateMachineDef | null
  getInitialState: () => string
  getInitialAuditLog: () => AuditLogEntry[]
  isReadonly: () => boolean
  emit: {
    stateChange: (payload: StateChangePayload) => void
    fieldChange: (payload: FieldChangePayload) => void
  }
}

export interface UseReviewStateMachineReturn {
  currentState: Ref<string>
  auditLog: Ref<AuditLogEntry[]>
  availableTransitions: ComputedRef<TransitionDef[]>
  isFinalState: ComputedRef<boolean>
  hasStateMachine: ComputedRef<boolean>
  auditLogEnabled: ComputedRef<boolean>
  currentStateDef: ComputedRef<StateDef | null>
  currentStateLabel: ComputedRef<string>
  currentStateTagType: ComputedRef<'info' | 'warning' | 'success' | 'danger' | 'primary'>
  stateLabelOf: (stateId: string) => string
  transitionButtonType: (t: TransitionDef) => 'primary' | 'success' | 'warning' | 'danger' | 'info'
  transitionButtonLabel: (t: TransitionDef) => string
  auditLogItemType: (log: AuditLogEntry) => 'primary' | 'success' | 'warning' | 'danger' | 'info'
  onTransitionClick: (t: TransitionDef) => Promise<void>
  initStateMachine: (state?: string, log?: AuditLogEntry[]) => void
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useReviewStateMachine(params: UseReviewStateMachineParams): UseReviewStateMachineReturn {
  const { getStateMachine, getInitialState, getInitialAuditLog, isReadonly, emit } = params
  const authStore = useAuthStore()

  // ─── Refs ──────────────────────────────────────────────────────────────────
  const currentState = ref<string>(getInitialState())
  const auditLog = ref<AuditLogEntry[]>(getInitialAuditLog())

  // ─── Computed ──────────────────────────────────────────────────────────────
  const stateMachine = computed<StateMachineDef | null>(() => getStateMachine())

  const hasStateMachine = computed(
    () => !!(stateMachine.value && (stateMachine.value.states?.length || 0) > 0)
  )

  const auditLogEnabled = computed(() => !!stateMachine.value?.audit_log)

  const currentStateDef = computed<StateDef | null>(() => {
    const states = stateMachine.value?.states || []
    return states.find(s => s.id === currentState.value) ?? null
  })

  const currentStateLabel = computed(
    () => currentStateDef.value?.label || currentState.value || '—'
  )

  const currentStateTagType = computed<'info' | 'warning' | 'success' | 'danger' | 'primary'>(() => {
    const cls = currentStateDef.value?.class
    if (cls === 'info' || cls === 'warning' || cls === 'success' || cls === 'danger') return cls
    return 'info'
  })

  const isFinalState = computed(() => {
    const finals = stateMachine.value?.final || []
    return finals.includes(currentState.value)
  })

  const availableTransitions = computed<TransitionDef[]>(() => {
    const trans = stateMachine.value?.transitions || []
    return trans.filter(t => t.from === currentState.value)
  })

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function currentUserName(): string {
    const u = authStore.user
    if (!u) return '审计员'
    return u.full_name || u.username || '审计员'
  }

  function stateLabelOf(stateId: string): string {
    if (!stateId) return ''
    const states = stateMachine.value?.states || []
    return states.find(s => s.id === stateId)?.label || stateId
  }

  function transitionButtonType(t: TransitionDef): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
    const states = stateMachine.value?.states || []
    const target = states.find(s => s.id === t.to)
    const cls = target?.class
    if (cls === 'success') return 'success'
    if (cls === 'warning') return 'warning'
    if (cls === 'danger') return 'danger'
    if (cls === 'info') return 'info'
    return 'primary'
  }

  function transitionButtonLabel(t: TransitionDef): string {
    if (t.description) {
      const m = t.description.match(/→\s*(.+)$/)
      if (m) return m[1].trim()
      return t.description
    }
    return t.trigger
  }

  function auditLogItemType(log: AuditLogEntry): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
    const states = stateMachine.value?.states || []
    const target = states.find(s => s.id === log.to)
    const cls = target?.class
    if (cls === 'success') return 'success'
    if (cls === 'warning') return 'warning'
    if (cls === 'danger') return 'danger'
    if (cls === 'info') return 'info'
    return 'primary'
  }

  // ─── State machine handler ─────────────────────────────────────────────────

  async function onTransitionClick(t: TransitionDef): Promise<void> {
    if (isReadonly()) return
    const requireReason =
      t.to === 'review_returned' ||
      t.trigger === 'unsign' ||
      t.to === 'pending_response'
    let reason = ''
    if (requireReason) {
      try {
        const result = await ElMessageBox.prompt(
          `${t.description || t.trigger}\n\n请输入触发原因：`,
          '状态变更',
          {
            confirmButtonText: '确认',
            cancelButtonText: '取消',
            inputType: 'textarea',
            inputValidator: (v: string) => (v && v.trim().length >= 4) || '原因至少 4 个字',
          }
        )
        reason = (result as { value: string }).value || ''
      } catch {
        return
      }
    } else {
      try {
        await ElMessageBox.confirm(
          t.description || `确认推进至「${stateLabelOf(t.to)}」？`,
          '状态变更',
          {
            confirmButtonText: '确认',
            cancelButtonText: '取消',
            type: 'warning',
          }
        )
      } catch {
        return
      }
    }

    const ts = new Date().toISOString()
    const logEntry: AuditLogEntry = {
      from: t.from,
      to: t.to,
      trigger: t.trigger,
      user: currentUserName(),
      timestamp: ts,
      reason: reason || undefined,
    }
    auditLog.value.push(logEntry)
    currentState.value = t.to

    emit.stateChange({
      from: t.from,
      to: t.to,
      trigger: t.trigger,
      reason: reason || undefined,
      user: currentUserName(),
      timestamp: ts,
    })
    emit.fieldChange({
      field_name: 'state_machine',
      old_value: t.from,
      new_value: t.to,
      cell: stateMachine.value?.cell,
    })
    ElMessage.success(`已推进至「${stateLabelOf(t.to)}」`)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  function initStateMachine(state?: string, log?: AuditLogEntry[]) {
    const initial = stateMachine.value?.initial || (stateMachine.value?.states?.[0]?.id ?? '')
    currentState.value = (state && typeof state === 'string') ? state : initial
    auditLog.value = Array.isArray(log) ? [...log] : []
  }

  return {
    currentState,
    auditLog,
    availableTransitions,
    isFinalState,
    hasStateMachine,
    auditLogEnabled,
    currentStateDef,
    currentStateLabel,
    currentStateTagType,
    stateLabelOf,
    transitionButtonType,
    transitionButtonLabel,
    auditLogItemType,
    onTransitionClick,
    initStateMachine,
  }
}
