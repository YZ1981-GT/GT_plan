/**
 * 附件上传互斥门。
 *
 * 同一项目/底稿目标在同一个浏览器上下文内只允许一个写批次，避免多个
 * el-upload、拖拽区或后台文件夹上传同时建立重复附件。调用方必须在 finally
 * 中释放返回的函数；释放函数幂等，便于异常路径安全收口。
 */

export const ATTACHMENT_UPLOAD_BUSY_MESSAGE = '已有附件正在上传，请等待完成'

type ReleaseUploadLock = () => void

const activeUploadKeys = new Set<string>()

function normalizeKey(key: string): string {
  return String(key || '').trim()
}

/** 尝试占用一个上传目标；目标已占用或 key 为空时返回 null。 */
export function acquireAttachmentUpload(key: string): ReleaseUploadLock | null {
  const normalized = normalizeKey(key)
  if (!normalized || activeUploadKeys.has(normalized)) return null

  activeUploadKeys.add(normalized)
  let released = false
  return () => {
    if (released) return
    released = true
    activeUploadKeys.delete(normalized)
  }
}

export function isAttachmentUploadActive(key: string): boolean {
  const normalized = normalizeKey(key)
  return !!normalized && activeUploadKeys.has(normalized)
}

/**
 * 供服务层编排上传时使用的互斥包装器。
 * 任务抛错时也会释放锁，避免一次失败让后续上传永久卡住。
 */
export async function withAttachmentUpload<T>(key: string, task: () => Promise<T>): Promise<T> {
  const release = acquireAttachmentUpload(key)
  if (!release) throw new Error(ATTACHMENT_UPLOAD_BUSY_MESSAGE)
  try {
    return await task()
  } finally {
    release()
  }
}
