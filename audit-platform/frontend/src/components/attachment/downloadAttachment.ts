/**
 * 附件下载（已鉴权）
 *
 * `<a :href="/api/attachments/{id}/download" target="_blank">`、`window.open(...)` 这类
 * 浏览器原生跳转不经 axios，带不上 Bearer 头，后端恒 401（新标签页里只有
 * {"code":401,...}）。下载一律经 http 取 blob 再保存（utils/http 的 downloadFile）。
 * spec attachment-security-baseline 任务 12。
 */
import { attachments as P_att } from '@/services/apiPaths'
import { downloadFile } from '@/utils/http'
import { handleApiError } from '@/utils/errorHandler'

export async function downloadAttachment(attachmentId: string, fileName?: string): Promise<void> {
  if (!attachmentId) return
  try {
    await downloadFile(P_att.download(attachmentId), { fileName: fileName || undefined, silent: true })
  } catch (e) {
    handleApiError(e, '下载附件')
  }
}
