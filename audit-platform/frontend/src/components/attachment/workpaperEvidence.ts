/**
 * 底稿内上传证据的唯一写法（spec attachment-evidence-intake ADR-AEI-08）
 *
 * 后端 `POST /api/projects/{pid}/workpapers/{wpId}/evidence/upload`：
 * - 不带表页 / 单元格 ⇒ 整稿关联（在「本底稿关联附件」里可见）；
 * - 带表页或单元格 ⇒ 只写行级证据链接（不再额外挂整稿关联），统一视图里来源为「行级证据」；
 * - 证据类型不传时后端按底稿编码的证据声明取缺省（恰好声明一类 ⇒ 该类，否则「审计证据」）；
 * - 回执 `{ attachment, evidence_link }`；http 拦截器已解包 `{code, message, data}` 信封。
 *
 * 上传成功后让本底稿的共享链接仓失效重取，同一底稿上的所有行级附件组件立即看到新文件。
 * 旧写法（`/api/projects/{pid}/attachments/upload` + `title` 过滤 / 再 associate）只留给附件管理页与函证附件抽屉。
 */
import http from '@/utils/http'
import { attachments as P_att } from '@/services/apiPaths'
import { invalidateWpEvidenceLinks, type WpEvidenceLink } from '@/composables/useWpEvidenceLinks'

/** 证据类型（与后端 `workpaper_evidence_intake.EVIDENCE_TYPES` 逐项一致，守卫钉住）。 */
export const EVIDENCE_TYPE_OPTIONS = [
  { value: 'evidence', label: '审计证据' },
  { value: 'support', label: '支持文件' },
  { value: 'voucher', label: '凭证 / 原始单据' },
  { value: 'contract', label: '合同 / 协议' },
  { value: 'bank_statement', label: '银行对账单' },
  { value: 'stocktake', label: '盘点 / 监盘记录' },
  { value: 'note', label: '票据影像' },
  { value: 'confirmation', label: '函证回函' },
] as const

export type EvidenceType = (typeof EVIDENCE_TYPE_OPTIONS)[number]['value']

export const EVIDENCE_TYPE_LABEL: Record<string, string> = Object.fromEntries(
  EVIDENCE_TYPE_OPTIONS.map((opt) => [opt.value, opt.label]),
)

/** 单个附件上传上限（与后端 `ATTACHMENT_MAX_UPLOAD_MB` 缺省 50MB 一致；超限后端回 413）。 */
export const EVIDENCE_MAX_UPLOAD_BYTES = 50 * 1024 * 1024

/** ItemAttachment 槽位的位置键：表页 = sheetKey，单元格 = `item:{序号}`。 */
export function itemCellRef(itemIndex: number | string): string {
  return `item:${itemIndex}`
}

/** 位置的中文标签（统一视图「行级证据」位置、证据链接列表用）。 */
export function evidencePositionLabel(pos: { sheet_name?: string | null; cell_ref?: string | null; page_ref?: string | null }): string {
  const parts: string[] = []
  if (pos.sheet_name) parts.push(pos.sheet_name)
  const cell = pos.cell_ref || ''
  if (cell.startsWith('item:')) parts.push(`第 ${cell.slice(5)} 项`)
  else if (cell.startsWith('row:')) parts.push(`行 ${cell.slice(4)}`)
  else if (cell) parts.push(cell)
  if (pos.page_ref) parts.push(`第 ${pos.page_ref} 页`)
  return parts.join(' · ') || '整张底稿'
}

export interface WorkpaperEvidenceAttachment {
  id: string
  file_name?: string
  file_size?: number
  attachment_type?: string
  [key: string]: unknown
}

export interface UploadWorkpaperEvidenceResult {
  attachment: WorkpaperEvidenceAttachment
  evidenceLink: WpEvidenceLink | Record<string, unknown> | null
}

export interface UploadWorkpaperEvidenceOptions {
  projectId: string
  wpId: string
  file: File | Blob
  /** 文件名（Blob 时必填；File 时缺省取 file.name） */
  fileName?: string
  evidenceType?: string | null
  /** 行级位置：表页键（与单元格任一非空即只写证据链接） */
  sheetName?: string | null
  cellRef?: string | null
  pageRef?: string | null
  /** 上传进度（0-100） */
  onProgress?: (percent: number) => void
}

function unwrap(body: any): any {
  if (body && typeof body === 'object' && 'code' in body && 'data' in body) return body.data
  return body
}

/**
 * 上传一份底稿证据。失败抛出（调用方 `handleApiError` 提示：413 超限 / 422 类型或文件被拒 / 423 已归档 / 404 底稿不存在）。
 */
export async function uploadWorkpaperEvidence(opts: UploadWorkpaperEvidenceOptions): Promise<UploadWorkpaperEvidenceResult> {
  const { projectId, wpId, file } = opts
  if (!projectId || !wpId) throw new Error('缺少项目或底稿，无法上传证据')
  const form = new FormData()
  const name = opts.fileName || (file as File).name || 'attachment.bin'
  form.append('file', file, name)
  if (opts.evidenceType) form.append('evidence_type', opts.evidenceType)
  if (opts.sheetName) form.append('sheet_name', opts.sheetName)
  if (opts.cellRef) form.append('cell_ref', opts.cellRef)
  if (opts.pageRef) form.append('page_ref', opts.pageRef)
  const onProgress = opts.onProgress
  const res = await http.post(P_att.evidenceUpload(projectId, wpId), form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    _silent: true,
    onUploadProgress: onProgress
      ? (e: { loaded: number; total?: number }) => onProgress(e.total ? Math.round((e.loaded / e.total) * 100) : 0)
      : undefined,
  } as any)
  const body = unwrap(res?.data)
  const attachment = body?.attachment
  if (!attachment?.id) throw new Error('上传成功但未返回附件编号')
  void invalidateWpEvidenceLinks(projectId, wpId).catch(() => [])
  return { attachment, evidenceLink: body?.evidence_link ?? null }
}

/** 附件管理「关联到底稿」的候选项：值是底稿（working_paper）id。 */
export interface AssociateCandidate {
  wpId: string
  wpCode: string
  wpName: string
}

/**
 * 从底稿索引（`GET /api/projects/{pid}/wp-index`）里挑「关联到底稿」的候选。
 *
 * 索引条目的 `id` 是索引 id，`wp_id` 才是底稿 id；关联端点要底稿 id。原先选项值取 `id`，
 * 任何底稿都关联失败（门禁按底稿 id 查不到 ⇒ 404「资源不存在或不可访问」，走查中发现）。
 * 只建了索引、还没生成底稿（无 `wp_id`）的条目不能关联，不列出。
 */
export function associateCandidates(items: unknown, query: string, limit = 20): AssociateCandidate[] {
  const q = (query || '').trim().toLowerCase()
  if (!q || !Array.isArray(items)) return []
  const out: AssociateCandidate[] = []
  for (const it of items as Array<Record<string, unknown>>) {
    const wpId = it?.wp_id ? String(it.wp_id) : ''
    if (!wpId) continue
    const wpCode = String(it.wp_code ?? '')
    const wpName = String(it.wp_name ?? '')
    if (!wpCode.toLowerCase().includes(q) && !wpName.toLowerCase().includes(q)) continue
    out.push({ wpId, wpCode, wpName })
    if (out.length >= limit) break
  }
  return out
}
