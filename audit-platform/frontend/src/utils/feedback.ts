/**
 * 统一反馈工具（R8-S1-05）
 *
 * 三层规范：
 * - 第一层 success/info/warning/error：轻量 Toast（2-4 秒自动消失）
 * - 第二层 notify：持续性通知卡片（5-8 秒，可关闭，可点击）
 * - 第三层：中断性确认 → 走 utils/confirm.ts
 */
import { ElMessage, ElNotification } from 'element-plus'

export const feedback = {
  /** 成功提示（2 秒自动消失） */
  success(msg: string) {
    ElMessage.success(msg)
  },

  /** 普通信息（2 秒自动消失） */
  info(msg: string) {
    ElMessage.info(msg)
  },

  /** 警告提示（3 秒自动消失） */
  warning(msg: string) {
    ElMessage.warning({ message: msg, duration: 3000 })
  },

  /** 错误提示（4 秒，可关闭） */
  error(msg: string, detail?: string) {
    ElMessage.error({ message: msg, duration: 4000, showClose: true })
    if (detail) console.warn('[feedback.error]', detail)
  },

  /** 持续性通知卡片（右上角，5 秒默认，可关闭） */
  notify(opts: {
    title: string
    message: string
    type?: 'success' | 'warning' | 'info' | 'error'
    duration?: number
    onClick?: () => void
  }) {
    ElNotification({
      duration: 5000,
      ...opts,
    })
  },
}

export default feedback
