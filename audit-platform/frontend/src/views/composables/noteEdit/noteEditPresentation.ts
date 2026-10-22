/**
 * noteEditPresentation — 纯函数模型 presentEntry
 *
 * 即需求 10.11 的模型。组件用它决定每个写入口的 operable / rendered / disabled / tooltip，
 * 性质测试（Property 14）也直接调用它。
 *
 * Feature: partner-manager-edit-permission, Property 14
 * Requirements: 10.3, 10.4, 10.5, 10.11
 */
import type { NoteWriteEntry } from './noteEditWriteEntries'

// ── 输入状态 ─────────────────────────────────────────────────────────────────

export interface NoteEditState {
  /** 查询状态 */
  queryStatus: 'pending' | 'ok' | 'failed'
  /** 查询成功时的结论 */
  canEdit: boolean
  /** 查询返回的原因（不能编辑时非空） */
  reason: string | null
  /** 查询返回的是否 EQCR */
  isEqcr: boolean
  /** 项目是否已归档 */
  isArchived: boolean
  /** 多窗口锁是否强制只读 */
  forcedReadonly: boolean
}

// ── 输出 ─────────────────────────────────────────────────────────────────────

export interface PresentationResult {
  /** 入口可操作（用户可点击并产生效果） */
  operable: boolean
  /** 入口应渲染（false = 不渲染或隐藏） */
  rendered: boolean
  /** 入口应禁用（rendered && disabled = 可见但灰色不可操作） */
  disabled: boolean
  /** 悬停提示（不可操作时显示，恰为一项当前成立的原因） */
  tooltip: string
}

// ── 常量 ─────────────────────────────────────────────────────────────────────

const TIP_PENDING = '正在确认编辑权限…'
const TIP_FAILED = '无法确认编辑权限'
const TIP_ARCHIVED = '项目已归档，无法编辑'
const TIP_FORCED_READONLY = '他人正在编辑，当前为只读'

// ── 纯函数 ───────────────────────────────────────────────────────────────────

/**
 * 对给定编辑器状态和写入口，计算该入口的呈现。
 *
 * 模型（需求 10.11）：
 * - operable ⇔ 查询成功 ∧ canEdit ∧ 未归档 ∧（入口不受锁约束 ∨ 未被强制只读）
 * - 不可操作时：成功且 EQCR ⇒ 隐藏或禁用；否则可见且禁用
 * - tooltip 恰为一项当前成立的原因
 * - 「📋 只读副本」显示 ⇔ 成功 ∧ EQCR
 * - 按 EQCR 隐藏的入口显示 ⇔ 成功 ∧ 非 EQCR
 */
export function presentEntry(state: NoteEditState, entry: NoteWriteEntry): PresentationResult {
  const { queryStatus, canEdit, reason, isEqcr, isArchived, forcedReadonly } = state
  const { lockConstrained, eqcrHidden, coverage } = entry

  // 可编辑态基础判定
  const queryOk = queryStatus === 'ok'
  const baseCanWrite = queryOk && canEdit && !isArchived
  const operable = coverage
    ? baseCanWrite && (!lockConstrained || !forcedReadonly)
    : true // non-coverage entries (EQCR-hidden-only) always operable when visible

  // EQCR-hidden 入口的渲染
  if (eqcrHidden) {
    // 显示 ⇔ 查询成功 ∧ 非 EQCR
    const rendered = queryOk && !isEqcr
    if (!rendered) {
      return { operable: false, rendered: false, disabled: false, tooltip: '' }
    }
    // 渲染了但如果 coverage 且不能写
    if (coverage && !operable) {
      return { operable: false, rendered: true, disabled: true, tooltip: pickTooltip(state) }
    }
    return { operable: true, rendered: true, disabled: false, tooltip: '' }
  }

  // 普通 coverage 入口
  if (!operable) {
    // 查询成功且 EQCR ⇒ 可以选择隐藏或禁用（我们选择禁用以保持可见）
    const tooltip = pickTooltip(state)
    return { operable: false, rendered: true, disabled: true, tooltip }
  }

  return { operable: true, rendered: true, disabled: false, tooltip: '' }
}

/**
 * 按优先级返回一条当前成立的原因：
 * pending → failed → 判定不能编辑(reason) → 归档 → 多窗口锁
 */
function pickTooltip(state: NoteEditState): string {
  if (state.queryStatus === 'pending') return TIP_PENDING
  if (state.queryStatus === 'failed') return TIP_FAILED
  if (state.queryStatus === 'ok' && !state.canEdit && state.reason) return state.reason
  if (state.isArchived) return TIP_ARCHIVED
  if (state.forcedReadonly) return TIP_FORCED_READONLY
  return ''
}
