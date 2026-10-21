import type { OpenFormulaManagerPayload } from '@/utils/eventBus'

import {
  onLocationChangedWhileOpen,
  type FormulaManagerSession,
} from './openFormulaManagerCommand'

export interface FormulaManagerContextOwnerState {
  active?: OpenFormulaManagerPayload
  pending?: OpenFormulaManagerPayload
}

const SCOPE_CHANGE_BANNER = '公式目标已变化，草稿仍固定在原位置。保存或丢弃草稿后再切换到最新目标。'

/**
 * 公式管理器唯一 owner 的 open-event reducer。
 *
 * clean 会话跟随最新上下文；dirty 会话只更新 latest/banner，并保留完整活动 payload，
 * 防止旧草稿被新的 project/wp/year/scope props 重新解释后写错实例。
 */
export function receiveFormulaManagerOpen(
  state: FormulaManagerContextOwnerState,
  incoming?: OpenFormulaManagerPayload,
): FormulaManagerContextOwnerState {
  if (!incoming) return { active: undefined, pending: undefined }

  const session = state.active?.formulaSession
  if (!session?.dirty) return { active: incoming, pending: undefined }

  const nextSession = incoming.canonicalLocation
    ? onLocationChangedWhileOpen(session, incoming.canonicalLocation)
    : { ...session, banner: SCOPE_CHANGE_BANNER }

  return {
    active: { ...state.active, formulaSession: nextSession },
    pending: incoming,
  }
}

/**
 * 接收 FormulaManagerDialog 的会话变化。dirty 清除后，若期间收到新目标，则原子切换
 * 到 pending payload；否则只更新活动会话。
 */
export function receiveFormulaManagerSession(
  state: FormulaManagerContextOwnerState,
  session: FormulaManagerSession,
): FormulaManagerContextOwnerState {
  if (!state.active) return state
  if (!session.dirty && state.pending) {
    return { active: state.pending, pending: undefined }
  }
  return {
    active: { ...state.active, formulaSession: session },
    pending: state.pending,
  }
}
