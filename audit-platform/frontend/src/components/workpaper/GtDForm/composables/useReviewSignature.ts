/**
 * useReviewSignature — 签字链 composable
 *
 * 包含：onSignClick / canUnsign / signaturesData / signature history / unsign rules
 * 参数：props (schema signature config, htmlData signatures) + currentState ref + emit
 * 返回：signaturesData / onSignClick() / canUnsign() / allRequiredSigned
 */
import { ref, type Ref } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

// ─── Types ───────────────────────────────────────────────────────────────────

interface SignatureDef {
  role: string
  label?: string
  cell?: string
  source?: string
  auto_timestamp?: boolean
  timestamp_cell?: string
  required?: boolean
}

interface SignatureRecord {
  signed_by: string
  signed_at: string
  cell?: string
}

interface AuditLogEntry {
  from: string
  to: string
  trigger: string
  user?: string
  timestamp: string
  reason?: string
}

interface TransitionDef {
  from: string
  to: string
  trigger: string
  description?: string
}

interface FieldChangePayload {
  field_name: string
  old_value?: any
  new_value?: any
  cell?: string
}

interface SignaturePayload {
  role: string
  signed_by: string
  signed_at: string
  cell?: string
  state_transition?: { from: string; to: string }
}

interface StateChangePayload {
  from: string
  to: string
  trigger: string
  reason?: string
  user?: string
  timestamp: string
}

interface UseReviewSignatureParams {
  currentState: Ref<string>
  auditLog: Ref<AuditLogEntry[]>
  getInitialSignatures: () => Record<string, SignatureRecord>
  getCurrentStepSignatures: () => SignatureDef[]
  getTransitions: () => TransitionDef[]
  isReadonly: () => boolean
  emit: {
    sign: (payload: SignaturePayload) => void
    fieldChange: (payload: FieldChangePayload) => void
    stateChange: (payload: StateChangePayload) => void
  }
}

export interface UseReviewSignatureReturn {
  signaturesData: Ref<Record<string, SignatureRecord>>
  onSignClick: (sig: SignatureDef) => Promise<void>
  onUnsignClick: (sig: SignatureDef) => Promise<void>
  canUnsign: (sig: SignatureDef) => boolean
  isSigned: (sig: SignatureDef) => boolean
  initSignatures: (signatures?: Record<string, SignatureRecord>) => void
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useReviewSignature(params: UseReviewSignatureParams): UseReviewSignatureReturn {
  const { currentState, auditLog, getInitialSignatures, getCurrentStepSignatures, getTransitions, isReadonly, emit } = params
  const authStore = useAuthStore()

  // ─── Refs ──────────────────────────────────────────────────────────────────
  const signaturesData = ref<Record<string, SignatureRecord>>(getInitialSignatures())

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function currentUserName(): string {
    const u = authStore.user
    if (!u) return '审计员'
    return u.full_name || u.username || '审计员'
  }

  function isSigned(sig: SignatureDef): boolean {
    const rec = signaturesData.value[sig.role]
    return !!(rec && rec.signed_by && rec.signed_at)
  }

  function canUnsign(_sig: SignatureDef): boolean {
    // 撤销规则：仅在 pending_signature 或 in_progress 状态下允许
    return currentState.value === 'pending_signature' || currentState.value === 'in_progress'
  }

  // ─── Signature handlers ────────────────────────────────────────────────────

  async function onSignClick(sig: SignatureDef): Promise<void> {
    if (isReadonly()) return
    try {
      await ElMessageBox.confirm(
        `确认以「${currentUserName()}」身份完成「${sig.label || sig.role}」电子签字？\n\n签字后将自动写入时间戳，并可能触发状态机推进。`,
        '电子签字确认',
        {
          confirmButtonText: '确认签字',
          cancelButtonText: '取消',
          type: 'info',
        }
      )
    } catch {
      return
    }

    const ts = new Date().toISOString()
    const signedBy = currentUserName()
    signaturesData.value[sig.role] = {
      signed_by: signedBy,
      signed_at: ts,
      cell: sig.cell,
    }

    // 如果签字触发状态机推进（pending_signature → review_passed），自动入栈
    let stateTransition: { from: string; to: string } | undefined
    if (sig.required && currentState.value === 'pending_signature') {
      const allRequiredSigned = getCurrentStepSignatures()
        .filter(s => s.required)
        .every(s => isSigned(s))
      if (allRequiredSigned) {
        const signTrans = getTransitions()
          .find(t => t.from === 'pending_signature' && t.trigger === 'signature_completed')
        if (signTrans) {
          const fromState = currentState.value
          currentState.value = signTrans.to
          auditLog.value.push({
            from: fromState,
            to: signTrans.to,
            trigger: signTrans.trigger,
            user: signedBy,
            timestamp: ts,
            reason: `${sig.label || sig.role} 完成签字`,
          })
          stateTransition = { from: fromState, to: signTrans.to }
          emit.stateChange({
            from: fromState,
            to: signTrans.to,
            trigger: signTrans.trigger,
            user: signedBy,
            timestamp: ts,
            reason: `${sig.label || sig.role} 完成签字`,
          })
        }
      }
    }

    emit.sign({
      role: sig.role,
      signed_by: signedBy,
      signed_at: ts,
      cell: sig.cell,
      state_transition: stateTransition,
    })
    emit.fieldChange({
      field_name: `signatures.${sig.role}`,
      old_value: undefined,
      new_value: { signed_by: signedBy, signed_at: ts },
      cell: sig.cell,
    })
    ElMessage.success(`${sig.label || sig.role} 签字成功`)
  }

  async function onUnsignClick(sig: SignatureDef): Promise<void> {
    if (isReadonly()) return
    if (!canUnsign(sig)) {
      ElMessage.warning('当前状态不允许撤销签字')
      return
    }
    try {
      const result = await ElMessageBox.prompt(
        `确认撤销「${sig.label || sig.role}」的电子签字？\n请说明撤销原因：`,
        '撤销签字',
        {
          confirmButtonText: '确认撤销',
          cancelButtonText: '取消',
          inputType: 'textarea',
          inputValidator: (v: string) => (v && v.trim().length >= 4) || '原因至少 4 个字',
        }
      )
      const reason = (result as { value: string }).value || ''
      const oldRec = signaturesData.value[sig.role]
      delete signaturesData.value[sig.role]
      auditLog.value.push({
        from: currentState.value,
        to: currentState.value,
        trigger: 'unsign',
        user: currentUserName(),
        timestamp: new Date().toISOString(),
        reason: `撤销 ${sig.label || sig.role} 签字：${reason}`,
      })
      emit.fieldChange({
        field_name: `signatures.${sig.role}`,
        old_value: oldRec,
        new_value: undefined,
        cell: sig.cell,
      })
      ElMessage.success('签字已撤销')
    } catch {
      return
    }
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  function initSignatures(signatures?: Record<string, SignatureRecord>) {
    signaturesData.value =
      signatures && typeof signatures === 'object'
        ? { ...signatures }
        : {}
  }

  return {
    signaturesData,
    onSignClick,
    onUnsignClick,
    canUnsign,
    isSigned,
    initSignatures,
  }
}
