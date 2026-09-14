/**
 * useOcrAttachmentCache — C 循环控制测试弹窗附件 OCR 上下文缓存 composable
 *
 * 职责：
 * - 维护附件列表缓存（dialog session 内有效，关闭 dialog 时清除）
 * - 维护 OCR 结果缓存（组件生命周期持久，attachment_id → full_text）
 * - 提供 loadAttachments / runOcr / resetListCache 三个动作
 * - 提供 isOcrEligible 纯函数判断文件是否可 OCR 识别
 *
 * 数据来源（复用真实端点，走 http/axios 携带 Authorization，禁用原生 fetch）：
 * - 附件列表：GET /api/working-papers/{wpId}/attachments（底稿关联附件，见 attachments.py）
 * - OCR 识别：POST /api/workpapers/{wpId}/d4/contract-ocr（multipart，返回 extracted_fields.full_text）
 *
 * Validates: Requirements 6.1, 6.2, 6.3, 6.4, 4.2, 4.3
 */
import { ref, type Ref } from 'vue'
import http from '@/utils/http'
import { appendOcrLinkageFields } from '@/components/workpaper/composables/ocrAttachmentLinkage'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AttachmentItem {
  /** attachment_id */
  id: string
  file_name: string
  /** MIME type 或后端 file_type 字段 */
  file_type: string
  file_size: number
  created_at: string
  /** 前端根据 file_name 后缀计算，是否支持 OCR 识别 */
  ocrEligible: boolean
}

export interface UseOcrAttachmentCacheReturn {
  /** OCR 结果缓存 (attachment_id → extracted full_text)，组件生命周期持久 */
  ocrCache: Ref<Map<string, string>>
  /** 附件列表缓存（dialog session 内有效） */
  attachmentList: Ref<AttachmentItem[]>
  /** 附件列表是否已加载（用于跳过重复请求 / 强制刷新） */
  attachmentListLoaded: Ref<boolean>
  /** 加载附件列表（已加载则跳过） */
  loadAttachments: (wpId: string) => Promise<void>
  /** 执行 OCR 并缓存（已缓存则直接返回，不发起 HTTP；forceReocr 可强制重识别） */
  runOcr: (wpId: string, attachmentId: string, file: File | Blob, forceReocr?: boolean) => Promise<string>
  /** 清除附件列表缓存（dialog 关闭时调用），不清除 ocrCache */
  resetListCache: () => void
}

// ─── OCR 可识别性判定（纯函数） ────────────────────────────────────────────────

/** 支持 OCR 识别的文件扩展名（小写，含点） */
const OCR_EXTENSIONS = new Set(['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif'])

/**
 * 判断文件名是否为 OCR 可识别格式（扩展名大小写不敏感）。
 *
 * @param fileName 文件名（可含路径 / 多个点）
 * @returns 当且仅当扩展名属于 .pdf/.png/.jpg/.jpeg/.tiff/.bmp/.gif 时返回 true
 *
 * Validates: Requirements 4.2 (Property 3)
 */
export function isOcrEligible(fileName: string): boolean {
  if (!fileName || typeof fileName !== 'string') return false
  const parts = fileName.split('.')
  // 无扩展名（无点或以点结尾产生空段）时不可识别
  if (parts.length < 2) return false
  const ext = '.' + (parts.pop()?.toLowerCase() ?? '')
  return OCR_EXTENSIONS.has(ext)
}

// ─── OCR 文本拼接/截断规则（design §7） ─────────────────────────────────────────

/** OCR 上下文文本总长上限（字符） */
export const MAX_OCR_CONTEXT_LENGTH = 3000

/** OCR 文本并入 AI context 时使用的固定 key（design §Interfaces） */
export const OCR_CONTEXT_KEY = '参考资料（OCR识别）'

/**
 * 拼接多段 OCR 文本并按上限截断（纯函数）。
 * - joined = texts.join('\n---\n')
 * - 长度 ≤ 3000：返回完整拼接
 * - 长度 > 3000：返回前 3000 字符 + '…（已截断）'
 *
 * Validates: Requirements 4.4, 5.3 (Property 5)
 */
export function truncateOcrText(texts: string[]): string {
  const joined = texts.join('\n---\n')
  if (joined.length <= MAX_OCR_CONTEXT_LENGTH) return joined
  return joined.slice(0, MAX_OCR_CONTEXT_LENGTH) + '…（已截断）'
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useOcrAttachmentCache(): UseOcrAttachmentCacheReturn {
  const ocrCache: Ref<Map<string, string>> = ref(new Map<string, string>())
  const attachmentList: Ref<AttachmentItem[]> = ref<AttachmentItem[]>([])
  const attachmentListLoaded = ref(false)

  /**
   * 加载底稿关联附件列表。已加载（attachmentListLoaded=true）则跳过，避免重复请求。
   * 每项计算 ocrEligible。加载失败时保持空列表，不抛异常（不阻塞 AI 生成）。
   */
  async function loadAttachments(wpId: string): Promise<void> {
    if (attachmentListLoaded.value) return
    if (!wpId) return
    try {
      // 复用真实端点：底稿关联附件（http 拦截器已解包 ApiResponse 信封）
      const res = await http.get(`/api/working-papers/${wpId}/attachments`)
      const raw = (res?.data?.data ?? res?.data) as any
      const rows: any[] = Array.isArray(raw) ? raw : raw?.items ?? []
      attachmentList.value = rows.map((a) => {
        const fileName = String(a?.file_name ?? '')
        return {
          id: String(a?.id ?? ''),
          file_name: fileName,
          file_type: String(a?.file_type ?? ''),
          file_size: Number(a?.file_size ?? 0),
          created_at: String(a?.created_at ?? ''),
          ocrEligible: isOcrEligible(fileName),
        } as AttachmentItem
      })
      attachmentListLoaded.value = true
    } catch {
      // 附件列表获取失败：保持空列表，不阻塞后续流程
      attachmentList.value = []
      attachmentListLoaded.value = false
    }
  }

  /**
   * 对单个附件执行 OCR 并缓存。
   * 若 ocrCache 已有该 attachmentId，则直接返回缓存文本，不发起任何 HTTP 请求。
   * 否则 POST 到 /d4/contract-ocr，从 extracted_fields.full_text 提取文本并缓存。
   *
   * Validates: Requirements 4.3, 6.3 (Property 4)
   */
  async function runOcr(wpId: string, attachmentId: string, file: File | Blob, forceReocr = false): Promise<string> {
    // 命中缓存：不发 HTTP（除非强制重识别）
    if (!forceReocr && ocrCache.value.has(attachmentId)) {
      return ocrCache.value.get(attachmentId) as string
    }

    const formData = new FormData()
    formData.append('file', file)
    appendOcrLinkageFields(formData, {
      attachmentId,
      forceReocr,
    })
    const res = await http.post(
      `/api/workpapers/${wpId}/d4/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    // http 拦截器已解包一层；OCR 端点可能再嵌一层 data，双重兜底
    const payload = (res?.data?.data ?? res?.data) as any
    const fields = payload?.extracted_fields || {}
    const text =
      payload?.ocr_text ||
      fields.full_text ||
      fields.summary ||
      fields.content ||
      Object.values(fields).filter(Boolean).join('\n') ||
      ''
    const result = String(text)
    ocrCache.value.set(attachmentId, result)
    return result
  }

  /**
   * 清除附件列表缓存（dialog 关闭时调用）。
   * 仅清列表 + 重置 loaded 标志；ocrCache 保留（组件生命周期持久）。
   */
  function resetListCache(): void {
    attachmentList.value = []
    attachmentListLoaded.value = false
  }

  return {
    ocrCache,
    attachmentList,
    attachmentListLoaded,
    loadAttachments,
    runOcr,
    resetListCache,
  }
}

export default useOcrAttachmentCache
