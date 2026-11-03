/**
 * 编程式二次密码确认（spec attachment-archive-and-a-class-evidence 需求 4.2，ADR-AE-08）。
 *
 * 后端高危端点（启动 / 重试归档、签字）要求 `X-Confirmation-Token`：先 POST `/api/auth/verify-password`
 * 换一次性令牌（5 分钟、用一次即失效）。改造前 `PasswordConfirmDialog` 没有任何挂载点、前端没有一处带令牌，
 * 这些端点恒 403。
 *
 * 用法：`const token = await requestConfirmationToken('归档确认'); if (!token) return`，再把
 * `confirmationHeaders(token)` 放进请求配置。取消 ⇒ 返回 null（调用方不发请求）。
 */
import { createApp, h, ref } from 'vue'
import PasswordConfirmDialog from '@/components/PasswordConfirmDialog.vue'

export const CONFIRMATION_TOKEN_HEADER = 'X-Confirmation-Token'

export function confirmationHeaders(token: string): Record<string, string> {
  return { [CONFIRMATION_TOKEN_HEADER]: token }
}

/** 关闭动画结束后再卸载（el-dialog 默认动画约 300ms）。 */
const UNMOUNT_DELAY_MS = 400

export function requestConfirmationToken(title = '安全验证'): Promise<string | null> {
  return new Promise((resolve) => {
    const host = document.createElement('div')
    document.body.appendChild(host)
    const visible = ref(true)
    let settled = false

    const app = createApp({
      setup() {
        return () => h(PasswordConfirmDialog, {
          visible: visible.value,
          title,
          'onUpdate:visible': (v: boolean) => { visible.value = v },
          onConfirmed: (token: string) => finish(token),
          onCancelled: () => finish(null),
        })
      },
    })

    // 确认后对话框关闭还会再发一次「取消」：只认第一次（Promise 本身也只认第一次 resolve，
    // app.unmount() 重复调用无副作用 —— 这条守卫只让收尾流程走一遍，变异记为等价）
    function finish(token: string | null) {
      if (settled) return
      settled = true
      visible.value = false
      resolve(token || null)
      setTimeout(() => {
        app.unmount()
        host.remove()
      }, UNMOUNT_DELAY_MS)
    }

    app.mount(host)
  })
}
