/**
 * useA111Signing — A1-11 签发流转控制表 签字流转状态管理
 *
 * Spec: .kiro/specs/a1-11-signing-control-form/
 * Task: 2.2
 *
 * 职责：
 * - SIGN_SLOTS 配置常量（6 个签字槽位定义）
 * - requiredSlots 计算（基于 businessCategory 过滤必填槽位）
 * - progress 计算（signed/total）
 * - isAllSigned / isReadonly 计算
 * - signAction(slotId, userName) 方法
 * - getSlotState(slotId) 辅助方法
 */
import { computed, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface SignSlot {
  id: string          // item_id 后缀，如 'pm'
  label: string       // 中文标签
  requiredFor: ('A' | 'B' | 'C')[]  // 哪些业务分类必填
  optional: boolean   // 是否可选填（如 IT/税务专家）
}

export interface SignState {
  conclusion: string | null
  remark: string | null
  wp_ref: string | null
}

// ─── Configuration ───────────────────────────────────────────────────────────

export const SIGN_SLOTS: SignSlot[] = [
  { id: 'pm',      label: '项目负责经理',       requiredFor: ['A', 'B', 'C'], optional: false },
  { id: 'partner', label: '项目合伙人',         requiredFor: ['A', 'B', 'C'], optional: false },
  { id: 'qc',      label: '质量控制复核合伙人', requiredFor: ['A'],           optional: false },
  { id: 'eqcr',    label: '技术复核人(EQCR)',   requiredFor: ['A'],           optional: false },
  { id: 'it',      label: 'IT专家',             requiredFor: [],              optional: true },
  { id: 'tax',     label: '税务专家',           requiredFor: [],              optional: true },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA111Signing(
  businessCategory: Ref<string>,
  signStates: Ref<Record<string, { conclusion: string | null; remark: string | null; wp_ref: string | null }>>,
  externalReadonly?: Ref<boolean>
) {
  // ─── requiredSlots ─────────────────────────────────────────────────────────

  /** 当前业务分类下的必填签字槽位 */
  const requiredSlots = computed<SignSlot[]>(() => {
    const cat = businessCategory.value as 'A' | 'B' | 'C'
    if (!cat) return []
    return SIGN_SLOTS.filter(slot => slot.requiredFor.includes(cat))
  })

  // ─── progress ──────────────────────────────────────────────────────────────

  /** 签字进度：{ signed, total } */
  const progress = computed<{ signed: number; total: number }>(() => {
    const slots = requiredSlots.value
    const total = slots.length
    const signed = slots.filter(slot => {
      const state = signStates.value[slot.id]
      return state?.conclusion === 'Y'
    }).length
    return { signed, total }
  })

  // ─── isAllSigned ───────────────────────────────────────────────────────────

  /** 所有必填签字槽位是否均已签字 */
  const isAllSigned = computed<boolean>(() => {
    const slots = requiredSlots.value
    if (slots.length === 0) return false
    return slots.every(slot => {
      const state = signStates.value[slot.id]
      return state?.conclusion === 'Y'
    })
  })

  // ─── isReadonly ────────────────────────────────────────────────────────────

  /** 只读判定：所有必填签字完成 OR 外部 readonly prop */
  const isReadonly = computed<boolean>(() => {
    if (externalReadonly?.value) return true
    return isAllSigned.value
  })

  // ─── signAction ────────────────────────────────────────────────────────────

  /** 执行签字操作：设置 conclusion='Y', remark=userName, wp_ref=today */
  function signAction(slotId: string, userName: string): void {
    const today = formatDate(new Date())
    signStates.value[slotId] = {
      conclusion: 'Y',
      remark: userName,
      wp_ref: today,
    }
  }

  // ─── getSlotState ──────────────────────────────────────────────────────────

  /** 获取某槽位的签字状态 */
  function getSlotState(slotId: string): SignState {
    return signStates.value[slotId] || { conclusion: null, remark: null, wp_ref: null }
  }

  return {
    SIGN_SLOTS,
    requiredSlots,
    progress,
    isAllSigned,
    isReadonly,
    signAction,
    getSlotState,
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 格式化日期为 YYYY-MM-DD */
function formatDate(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export default useA111Signing
