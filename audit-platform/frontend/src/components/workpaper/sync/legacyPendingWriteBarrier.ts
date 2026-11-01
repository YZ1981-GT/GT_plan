import { ElMessage } from 'element-plus'

import { flushPendingWrites, runWithPendingWriteBarrier } from './pendingWrites'

/**
 * legacy OnlyOffice 入口的完整过渡屏障。
 *
 * active lease 从 flush 前同步取得，直到调用方完成 config / 结构化→Word 同步 / 模式切换后
 * 才释放。保存失败时不执行 transition，保留结构化视图并显示中文提示；transition 自己的
 * 配置错误仍按原调用方逻辑处理，不会被误报成“内容保存失败”。
 */
export async function runLegacyOnlyOfficeTransition(
  transition: () => Promise<void>,
): Promise<boolean> {
  return runWithPendingWriteBarrier(async () => {
    try {
      await flushPendingWrites()
    } catch (error) {
      const message = error instanceof Error && error.message
        ? error.message
        : '切换在线编辑前内容保存失败，请重试'
      ElMessage.error(message)
      return false
    }
    await transition()
    return true
  })
}
