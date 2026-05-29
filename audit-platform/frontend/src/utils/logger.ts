/**
 * logger — 统一日志 wrapper [V3 Req 12.4.3]
 *
 * 生产环境：warn/error 仍输出（便于线上排查），log 完全静默
 * 开发环境：全部输出，带 [Audit] 前缀便于过滤
 *
 * @example
 * import { logger } from '@/utils/logger'
 * logger.log('调试信息', data)   // 仅 DEV 输出
 * logger.warn('警告', msg)       // 始终输出
 * logger.error('错误', err)      // 始终输出
 */

const PREFIX = '[Audit]'

export const logger = {
  /** 仅开发环境输出（生产构建 tree-shake 后无副作用） */
  log: (...args: any[]) => {
    if (import.meta.env.DEV) {
      // eslint-disable-next-line no-console
      console.log(PREFIX, ...args)
    }
  },

  /** 警告：始终输出（生产环境也需要可见） */
  warn: (...args: any[]) => {
    // eslint-disable-next-line no-console
    console.warn(PREFIX, ...args)
  },

  /** 错误：始终输出 + 未来可接入 Sentry 上报 */
  error: (...args: any[]) => {
    // eslint-disable-next-line no-console
    console.error(PREFIX, ...args)
  },
}
