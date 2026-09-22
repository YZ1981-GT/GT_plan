/**
 * `forcesave_frozen` 必须可重试 —— 不得把用户关在 OnlyOffice 里。
 *
 * 2026-09-22 真栈实测的死角（浏览器端复现）：
 *   用户进 OO 什么都没改就点「保存并回到表单模式」
 *     → Command Service 返 `no_changes`
 *     → 202 带 `callback_expected=false`
 *     → 桥落 `forcesave_frozen`，界面显示
 *       「文档没有检测到改动，本次无需保存（Command Service 返回码 4）。若确实改过，
 *         请在编辑器内先点一下单元格外的空白处让改动生效，**再重新保存**。」
 *     → 但 `canForcesave` 只认 `oo_editing`，于是 `:disabled="!canForcesave"` 的保存按钮
 *       永久灰掉；room 开着时结构化视图的切换入口也是禁用的 ⇒ 无路可走。
 *
 * 状态机与文案本来就承诺可重试（`forcesave_frozen --forcesave_started-->
 * forcesave_requesting`、hint「请重新发送强制保存命令」），缺的只是那道门。
 */
import { describe, expect, it } from 'vitest'

import {
  WP_BRIDGE_FORCESAVE_READY_STATES,
  WP_BRIDGE_IN_FLIGHT_STATES,
} from '../useWorkpaperSyncBridge'
import { transitionBridgeState } from '../workpaperSyncBridgeMachine'
import { WP_SYNC_ACTION_HINT } from '../workpaperSyncPresentation'

describe('forcesave_frozen 可重试', () => {
  it('canForcesave 的状态集合包含 forcesave_frozen', () => {
    expect(WP_BRIDGE_FORCESAVE_READY_STATES).toContain('forcesave_frozen')
    expect(WP_BRIDGE_FORCESAVE_READY_STATES).toContain('oo_editing')
  })

  it('集合里每个状态都真的能接 forcesave_started（不是写了个空承诺）', () => {
    for (const state of WP_BRIDGE_FORCESAVE_READY_STATES) {
      const next = transitionBridgeState(state, 'forcesave_started', 'oo', {})
      expect(
        next.to,
        `${state} 不接受 forcesave_started —— 放进 ready 集合会让按钮亮起后点了就抛`,
      ).toBe('forcesave_requesting')
      expect(next.terminal, `${state} 被判成 terminal，重试不可能成立`).toBe(false)
    }
  })

  it('集合只含 mode=oo 的状态（HTML 侧不得出现强制保存入口）', () => {
    for (const state of WP_BRIDGE_FORCESAVE_READY_STATES) {
      expect(
        WP_BRIDGE_IN_FLIGHT_STATES.includes(state) || state === 'oo_editing',
        `${state} 既不在 in-flight 集合也不是 oo_editing —— 状态归属存疑`,
      ).toBe(true)
    }
  })

  it('凡是提示用户「重新发送强制保存」的状态，都必须在 ready 集合里', () => {
    const promisesRetry = Object.entries(WP_SYNC_ACTION_HINT).filter(([, hint]) =>
      /重新发送强制保存|再重新保存|重新保存/.test(String(hint ?? '')),
    )
    expect(
      promisesRetry.length,
      '没有任何状态提示重试 —— 判据会恒真（假绿）',
    ).toBeGreaterThan(0)
    for (const [state] of promisesRetry) {
      expect(
        WP_BRIDGE_FORCESAVE_READY_STATES,
        `状态 ${state} 的提示语让用户重新保存，但它不在 canForcesave 的放行集合里 ⇒ ` +
          '按钮是灰的，提示语在骗用户',
      ).toContain(state as (typeof WP_BRIDGE_FORCESAVE_READY_STATES)[number])
    }
  })
})
