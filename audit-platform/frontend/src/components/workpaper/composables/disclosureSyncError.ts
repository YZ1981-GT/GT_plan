/**
 * 披露同步错误处理（共享）
 *
 * 后端 `sync-from-workpaper` 对跨主体类型（listed vs soe）推送返回 409 +
 * `code: "STANDARD_MISMATCH"`（2026-10-09 恢复门控，防串表）。
 * 前端手动同步 catch 应给出精准提示，而非泛化的"同步失败"。
 */
import { ElMessage } from 'element-plus'
import type { AxiosError } from 'axios'

/** 409 STANDARD_MISMATCH 的响应体结构 */
interface StandardMismatchDetail {
  code: 'STANDARD_MISMATCH'
  detail: string
  project_standard: string
  requested_standard: string
  allowed: string[]
}

/**
 * 判断 axios 错误是否为跨主体类型同步被拒（409 STANDARD_MISMATCH）。
 */
function isStandardMismatch(err: unknown): err is AxiosError<{ detail: StandardMismatchDetail }> {
  if (!err || typeof err !== 'object') return false
  const axErr = err as AxiosError
  if (!axErr.response || axErr.response.status !== 409) return false
  const detail = axErr.response.data as any
  return detail?.detail?.code === 'STANDARD_MISMATCH' || detail?.code === 'STANDARD_MISMATCH'
}

/**
 * 披露同步 catch 中的共享错误处理。
 *
 * - 409 STANDARD_MISMATCH → 精准提示（"当前项目准则不适用此附注版本，已跳过同步"）
 * - 其他错误 → 通用提示（"同步附注失败，请稍后重试"）
 *
 * 用法：
 * ```ts
 * } catch (err) {
 *   handleDisclosureSyncError(err)
 * }
 * ```
 */
export function handleDisclosureSyncError(err: unknown): void {
  if (isStandardMismatch(err)) {
    ElMessage.info('当前项目准则不适用此附注版本，已跳过同步')
    return
  }
  ElMessage.warning('同步附注失败，请稍后重试')
}
