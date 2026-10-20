/**
 * 知识库上传的纯逻辑（从 KnowledgeBase.vue 抽出，便于单测）
 *
 * - 拖拽文件夹：collectFromEntries / entriesFromDataTransfer
 * - 单文件上传结果：parseUploadResponse / extractErrorReason
 * - 没有正文的原因与后台识别状态：isOcrEligible / noTextHint / isOcrInProgress
 * - 结束汇总：buildUploadSummary
 *
 * spec knowledge-upload-robustness-and-consumer-wiring（Requirement 4 / 5）、
 * dsh-kb-ocr-local-first-routing（Requirement 5.7：扫描件后台识别）
 */

// ─── 拖拽文件夹 ───────────────────────────────────────────────────────────────

/** 与 FileSystemEntry 同形的最小接口（浏览器实现与测试替身共用） */
export interface FsEntryLike {
  isFile: boolean
  isDirectory: boolean
  name: string
  /** 从拖拽根开始的绝对路径，如 `/审计资料/函证/回函.pdf` */
  fullPath: string
  file?: (success: (f: File) => void, error?: (e: unknown) => void) => void
  createReader?: () => FsDirectoryReaderLike
}

export interface FsDirectoryReaderLike {
  readEntries: (success: (entries: FsEntryLike[]) => void, error?: (e: unknown) => void) => void
}

export interface DroppedFile {
  file: File
  /** 相对路径 `根目录/子目录/文件名`（无前导 /），与 `<input webkitdirectory>` 的 webkitRelativePath 同形 */
  relativePath: string
}

export interface DropResult {
  files: DroppedFile[]
  /** 读取失败的条目（相对路径；目录以 / 结尾） */
  failed: string[]
  /** 跳过的系统临时文件 / 目录数 */
  skipped: number
}

const JUNK_FILE_NAMES = new Set(['.ds_store', 'thumbs.db', 'desktop.ini'])
const JUNK_DIR_NAMES = new Set(['__macosx'])

/**
 * 系统临时文件：Office 打开文档时生成的 `~$` 锁文件、LibreOffice 的 `.~lock.`、
 * macOS 的 `._` / `.DS_Store`、Windows 的 `Thumbs.db` / `desktop.ini`。
 * 它们混在审计资料文件夹里很常见，上传后是一堆无正文的垃圾文档。
 */
export function isSystemJunkName(name: string): boolean {
  const n = name.toLowerCase()
  return JUNK_FILE_NAMES.has(n) || n.startsWith('~$') || n.startsWith('.~lock.') || n.startsWith('._')
}

/** 相对路径是否指向系统临时文件（或位于 `__MACOSX` 这类系统目录下） */
export function isSystemJunkPath(relativePath: string): boolean {
  const parts = relativePath.split('/').filter(Boolean)
  if (!parts.length) return false
  return parts.slice(0, -1).some((p) => JUNK_DIR_NAMES.has(p.toLowerCase())) || isSystemJunkName(parts[parts.length - 1])
}

/**
 * 读尽一个目录的全部条目。
 *
 * 🔴 Chromium 的 `readEntries()` 每次最多返回 100 条，必须反复调用直到返回空数组（见 MDN）。
 * 旧实现只调一次 ⇒ 超过 100 个文件的目录，其余文件被静默丢弃。
 */
export async function readAllEntries(reader: FsDirectoryReaderLike): Promise<FsEntryLike[]> {
  const all: FsEntryLike[] = []
  for (;;) {
    const batch = await new Promise<FsEntryLike[]>((resolve, reject) => reader.readEntries(resolve, reject))
    if (!batch.length) return all
    all.push(...batch)
  }
}

function fileOf(entry: FsEntryLike): Promise<File> {
  return new Promise((resolve, reject) => {
    if (!entry.file) {
      reject(new Error('not a file entry'))
      return
    }
    entry.file(resolve, reject)
  })
}

/**
 * 递归展开拖入的条目，保留目录层级。
 *
 * 🔴 `FileSystemFileEntry.file()` 得到的 File **没有** webkitRelativePath（只读属性，恒为空串），
 * 层级只能从 `entry.fullPath` 取。旧实现直接用 File ⇒ 拖入的文件夹结构被压平到目标文件夹根部。
 */
export async function collectFromEntries(roots: FsEntryLike[]): Promise<DropResult> {
  const result: DropResult = { files: [], failed: [], skipped: 0 }

  async function walk(entry: FsEntryLike): Promise<void> {
    const rel = entry.fullPath.replace(/^\/+/, '') || entry.name
    if (entry.isDirectory) {
      if (JUNK_DIR_NAMES.has(entry.name.toLowerCase())) {
        result.skipped += 1
        return
      }
      let children: FsEntryLike[]
      try {
        children = entry.createReader ? await readAllEntries(entry.createReader()) : []
      } catch {
        result.failed.push(`${rel}/`)
        return
      }
      for (const child of children) await walk(child)
      return
    }
    if (!entry.isFile) return
    if (isSystemJunkName(entry.name)) {
      result.skipped += 1
      return
    }
    try {
      result.files.push({ file: await fileOf(entry), relativePath: rel })
    } catch {
      result.failed.push(rel)
    }
  }

  for (const root of roots) await walk(root)
  return result
}

/**
 * 从 drop 事件取条目。
 *
 * 🔴 必须在 drop 事件处理函数的**同步**部分调用：处理函数返回后 DataTransferItemList 即失效，
 * 之后再 `webkitGetAsEntry()` 只能拿到 null。取到的条目本身之后可以异步遍历。
 */
export function entriesFromDataTransfer(dt: DataTransfer | null | undefined): FsEntryLike[] {
  const items = dt?.items
  if (!items) return []
  return Array.from(items)
    .map((item) => ((item as any).webkitGetAsEntry?.() ?? null) as FsEntryLike | null)
    .filter((e): e is FsEntryLike => e !== null)
}

// ─── 单文件上传结果 ─────────────────────────────────────────────────────────

export interface UploadOutcome {
  ok: boolean
  /** 失败原因（中文，可直接展示）；成功时为空串 */
  reason: string
  /** 成功入库但未抽到正文（扫描件 / 空文件）⇒ AI 无法引用其内容 */
  textExtracted: boolean
  /** 没抽到正文、已交给后台 OCR 识别（扫描件；spec dsh-kb-ocr-local-first-routing Req 5.1） */
  ocrQueued?: boolean
}

/** 错误响应体 → 中文原因。平台错误体形如 `{code, message}`；FastAPI 原生为 `{detail}`。 */
export function extractErrorReason(responseText: string | null | undefined): string {
  if (!responseText) return ''
  try {
    const body = JSON.parse(responseText)
    if (typeof body?.message === 'string' && body.message.trim()) return body.message.trim()
    const detail = body?.detail
    if (typeof detail === 'string' && detail.trim()) return detail.trim()
    if (detail && typeof detail === 'object' && !Array.isArray(detail) && typeof detail.message === 'string') {
      return detail.message.trim()
    }
  } catch {
    // 非 JSON（网关错误页等）
  }
  return ''
}

/**
 * 单文件上传（`POST /folders/{id}/upload`，每请求一个文件）的结果判定。
 *
 * 后端逐文件容错：单文件写库失败时返回 200 + `failed:[{filename, reason}]`、`files` 为空 ——
 * 不能只看 HTTP 状态码判成功，也不能只报「失败」而不给原因。
 */
export function parseUploadResponse(status: number, responseText: string): UploadOutcome {
  if (status >= 200 && status < 300) {
    let data: any
    try {
      const json = JSON.parse(responseText)
      data = json?.data ?? json
    } catch {
      return { ok: false, reason: '服务器返回了无法识别的响应', textExtracted: false }
    }
    const saved = Array.isArray(data?.files) ? data.files[0] : null
    if (saved?.id) {
      // 字段缺失（旧后端）按「已抽取」/「未排队」处理，不误报
      return {
        ok: true,
        reason: '',
        textExtracted: saved.text_extracted !== false,
        ocrQueued: saved.ocr_queued === true,
      }
    }
    const reason = Array.isArray(data?.failed) ? String(data.failed[0]?.reason || '') : ''
    return { ok: false, reason: reason || '文件未能保存，请重试', textExtracted: false }
  }
  if (status === 401) return { ok: false, reason: '登录已过期，请重新登录后重试', textExtracted: false }
  const reason = extractErrorReason(responseText)
  if (status === 413) return { ok: false, reason: reason || '文件过大，超出上传上限', textExtracted: false }
  return { ok: false, reason: reason || `上传失败（HTTP ${status}）`, textExtracted: false }
}

// ─── 未提取到正文的原因 ─────────────────────────────────────────────────────

/** 文件名的扩展名（小写、不含点）；无扩展名 / 点开头的隐藏文件返回空串 */
function extOf(name: string): string {
  const base = name.split('/').pop() || ''
  const dot = base.lastIndexOf('.')
  return dot > 0 ? base.slice(dot + 1).toLowerCase() : ''
}

/** 后台 OCR 能识别的类型（与后端 `knowledge_ocr_service.OCR_SUFFIXES` 同一份） */
const OCR_EXTS = new Set(['pdf', 'png', 'jpg', 'jpeg', 'bmp', 'tif', 'tiff', 'webp'])

/**
 * 「没抽到正文」能否交给后台 OCR：看 file_type（优先）或扩展名是否为 PDF / 图片。
 *
 * 没有文字层的 PDF 几乎都是扫描件：上传时自动排队、由后台按本机优先 / 服务器兜底识别
 * （spec dsh-kb-ocr-local-first-routing）。其余类型没抽到正文的原因是文件为空、只含图片或该类型
 * 不支持提取文字 —— OCR 也无济于事，不能对空白 txt 也说「扫描件」（knowledge-upload-robustness R4.2）。
 */
export function isOcrEligible(name: string, fileType?: string | null): boolean {
  const ext = fileType ? fileType.toLowerCase().replace(/^\./, '') : extOf(name)
  return OCR_EXTS.has(ext)
}

/** 后台 OCR 状态（V198 `knowledge_documents.ocr_status`；null = 不适用 / 存量未识别） */
export type OcrStatus = 'pending' | 'running' | 'done' | 'empty' | 'failed'

export interface NoTextHint {
  label: string
  title: string
  /** progress = 识别中（会自动刷新）；warning = AI 当前读不到它 */
  tone: 'progress' | 'warning'
  /** 可以点「重新识别」：可 OCR 的类型、且不在排队 / 识别中（后端 request_retry 同一口径） */
  retryable: boolean
}

/** 列表里有这些状态的文档时自动刷新，直到识别结束 */
export function isOcrInProgress(status?: string | null): boolean {
  return status === 'pending' || status === 'running'
}

/** 文档列表里「没有正文」标记的文案：按后台识别状态与文件类型区分原因 */
export function noTextHint(
  name: string,
  fileType?: string | null,
  ocrStatus?: string | null,
  ocrError?: string | null,
): NoTextHint {
  const eligible = isOcrEligible(name, fileType)
  if (ocrStatus === 'pending' || ocrStatus === 'running') {
    return {
      label: ocrStatus === 'running' ? '⏳ 正在识别文字…' : '⏳ 排队识别中…',
      title: '扫描件正在后台识别文字（本机 OCR 优先，不可用时用服务器 OCR）：完成后 AI 检索与对话即可引用其内容，本列表会自动刷新',
      tone: 'progress',
      retryable: false,
    }
  }
  if (ocrStatus === 'failed') {
    return {
      label: '⚠ 识别失败，AI 无法引用',
      title: `识别失败：${(ocrError || '').trim() || '原因未知'}。可点「重新识别」再试`,
      tone: 'warning',
      retryable: eligible,
    }
  }
  if (ocrStatus === 'empty') {
    return {
      label: '⚠ 未识别出文字，AI 无法引用',
      title: '已完成识别，但没有识别出文字（空白页或图像质量过低）：AI 检索与对话无法引用其内容，只能按文件名找到。可点「重新识别」再试',
      tone: 'warning',
      retryable: eligible,
    }
  }
  if (eligible) {
    // 没有识别记录：后台 OCR 上线前上传的存量扫描件（不批量回填，按需识别）
    return {
      label: '⚠ 未提取到正文（扫描件），AI 无法引用',
      title: '这份文件没有文字层（多为扫描件）：可点「重新识别」交给后台识别文字；在此之前 AI 检索与对话无法引用其内容，只能按文件名找到',
      tone: 'warning',
      retryable: true,
    }
  }
  return {
    label: '⚠ 未提取到正文，AI 无法引用',
    title: '未能从该文件提取文字（文件为空、只含图片，或该类型不支持提取文字）：AI 检索与对话无法引用其内容，只能按文件名找到',
    tone: 'warning',
    retryable: false,
  }
}

// ─── 结束汇总 ───────────────────────────────────────────────────────────────

export interface UploadFailure {
  name: string
  reason: string
}

export interface UploadSummary {
  level: 'success' | 'warning'
  title: string
  /** 明细行（为空表示无需展开说明） */
  lines: string[]
}

export interface UploadSummaryInput {
  /** 本批文件数（不叫 total：那是金额类命名，会被 gt-audit/no-amount-arithmetic 误判） */
  fileCount: number
  failures: UploadFailure[]
  /** 已入库但未抽到正文、也没有交给后台识别的文件名 */
  noText: string[]
  /** 已入库、没抽到正文、已交给后台 OCR 识别的文件名（扫描件） */
  ocrQueued?: string[]
  /** 创建失败、其文件已改传到上一级的子文件夹名 */
  folderFailures?: string[]
  /** 跳过的系统临时文件数 */
  skipped?: number
  /** 每类最多列出的条目数 */
  maxItems?: number
}

export function buildUploadSummary(input: UploadSummaryInput): UploadSummary {
  const { fileCount, failures, noText, ocrQueued = [], folderFailures = [], skipped = 0, maxItems = 5 } = input
  const lines: string[] = []

  for (const f of failures.slice(0, maxItems)) lines.push(`✗ ${f.name}：${f.reason}`)
  if (failures.length > maxItems) lines.push(`……另有 ${failures.length - maxItems} 个文件上传失败`)

  const listed = (names: string[]) =>
    names.slice(0, maxItems).join('、') + (names.length > maxItems ? ` 等 ${names.length} 个` : '')
  // 扫描件已在后台排队识别：不是问题，如实告知进度去向
  if (ocrQueued.length) {
    lines.push(`⏳ 扫描件已交给后台识别文字，完成后 AI 即可引用（进度见文档列表）：${listed(ocrQueued)}`)
  }
  // 未提取到正文且没排上队：可 OCR 的类型（旧后端没有回执字段）与其余原因分两行，不能对空白 txt 也说「扫描件」
  const scans = noText.filter((n) => isOcrEligible(n))
  const others = noText.filter((n) => !isOcrEligible(n))
  if (scans.length) {
    lines.push(`⚠ 未提取到正文 · 可在文档列表点「重新识别」交给后台识别（AI 暂无法引用）：${listed(scans)}`)
  }
  if (others.length) {
    lines.push(`⚠ 未提取到正文 · 文件为空、只含图片或该类型不支持提取文字（AI 无法引用）：${listed(others)}`)
  }
  if (folderFailures.length) {
    lines.push(`⚠ 子文件夹创建失败，其中文件已上传到上一级：${folderFailures.slice(0, maxItems).join('、')}`)
  }
  if (skipped > 0) lines.push(`已跳过 ${skipped} 个系统临时文件（如 ~$ 开头的 Office 锁文件）`)

  const title = failures.length
    ? `上传完成：${fileCount - failures.length} 成功，${failures.length} 失败`
    : `上传完成：${fileCount} 个文件`
  const level = failures.length || noText.length || folderFailures.length ? 'warning' : 'success'
  return { level, title, lines }
}
