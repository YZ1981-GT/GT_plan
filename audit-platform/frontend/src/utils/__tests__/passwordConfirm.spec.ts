/**
 * 编程式二次确认（spec attachment-archive-and-a-class-evidence 需求 4.2）。
 * 对话框换成桩：只验证「确认 ⇒ 令牌、取消 ⇒ null、结束后卸载」这条接线。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h } from 'vue'

const dialogState: { emit?: (event: string, ...args: any[]) => void; props?: any } = {}

vi.mock('@/components/PasswordConfirmDialog.vue', () => ({
  default: defineComponent({
    name: 'PasswordConfirmDialogStub',
    props: { visible: Boolean, title: String },
    emits: ['confirmed', 'cancelled', 'update:visible'],
    setup(props, { emit }) {
      dialogState.emit = emit as any
      dialogState.props = props
      return () => h('div', { class: 'pcd-stub' }, props.visible ? props.title : '')
    },
  }),
}))

import { confirmationHeaders, CONFIRMATION_TOKEN_HEADER, requestConfirmationToken } from '../passwordConfirm'

describe('requestConfirmationToken', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    document.body.innerHTML = ''
    dialogState.emit = undefined
  })

  it('确认后返回令牌，并在动画结束后卸载', async () => {
    const pending = requestConfirmationToken('归档确认')
    expect(document.querySelector('.pcd-stub')?.textContent).toBe('归档确认')
    dialogState.emit!('confirmed', 'tok-123')
    dialogState.emit!('update:visible', false)
    dialogState.emit!('cancelled') // el-dialog 关闭时对话框还会再发一次取消：不得覆盖已确认的结果
    await expect(pending).resolves.toBe('tok-123')
    vi.advanceTimersByTime(1000)
    expect(document.querySelector('.pcd-stub')).toBeNull()
  })

  it('取消返回 null', async () => {
    const pending = requestConfirmationToken()
    expect(dialogState.props.title).toBe('安全验证')
    dialogState.emit!('cancelled')
    await expect(pending).resolves.toBeNull()
    vi.advanceTimersByTime(1000)
    expect(document.body.children.length).toBe(0)
  })

  it('请求头名与后端 require_confirmation_token 一致', () => {
    expect(CONFIRMATION_TOKEN_HEADER).toBe('X-Confirmation-Token')
    expect(confirmationHeaders('t')).toEqual({ 'X-Confirmation-Token': 't' })
  })
})
