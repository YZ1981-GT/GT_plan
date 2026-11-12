/**
 * 合并附注保存 CAS 错误的纯函数。
 *
 * 这里提供错误解析、摘要归一化和冲突确认编排；不直接持有页面状态，页面行为通过回调注入。
 * 生产 http 拦截器会把平台信封的 `message` 归一到 `detail`，但测试和部分调用方
 * 可能直接传入原始 Axios 错误，因此这里保留两种信封的兼容读取。
 */

import { fmtDateTime, parseServerTime } from '@/utils/formatters'

export const CONSOL_NOTE_CONFLICT_CODE = 'CONSOL_NOTE_CONFLICT' as const
export const CONSOL_NOTE_DIGEST_REQUIRED_CODE = 'CONSOL_NOTE_DIGEST_REQUIRED' as const

const DEFAULT_LAST_WRITE_SOURCE = 'manual'
const DEFAULT_CONFLICT_MESSAGE = '附注内容已被其他人修改，请重新加载或保留本地修改'
const CONSOL_NOTE_WRITE_SOURCE_LABELS: Record<string, string> = {
  detail_mapping: '明细映射',
  subtree_aggregate: '子树汇总',
  formula: '公式计算',
  manual: '手工保存',
}

type UnknownRecord = Record<string, unknown>

export interface ConsolNoteConflictInfo {
  /** 服务端当前内容摘要；缺失或类型不对时不猜测。 */
  currentDigest: string | null
  /** 服务端最后写入时间；缺失或类型不对时不猜测。 */
  updatedAt: string | null
  /** 最后写入方的内部标识；缺失时按手工保存处理。 */
  lastWriteSource: string
  /** 可直接展示给用户的中文原因。 */
  message: string
}

export interface ConsolNoteConflictResolverOptions<T> {
  confirm: (message: string, title: string, options: Record<string, unknown>) => Promise<unknown>
  isCurrent: () => boolean
  reload: (context: T) => Promise<unknown>
}

function noteConflictSourceLabel(source: string): string {
  return CONSOL_NOTE_WRITE_SOURCE_LABELS[source] || '其他写入方'
}

function noteConflictTimeLabel(updatedAt: string | null): string {
  if (!updatedAt) return '未知时间'
  const parsed = parseServerTime(updatedAt)
  return Number.isNaN(parsed.getTime()) ? updatedAt : fmtDateTime(parsed)
}

/** 服务端摘要缺失或格式不合法时按旧数据兼容处理为 null。 */
export function normalizeNoteDataDigest(value: unknown): string | null {
  return typeof value === 'string' && /^[0-9a-f]{64}$/.test(value) ? value : null
}

/** 冲突只允许显式重读或保留本地编辑，关闭弹窗也保留本地状态。 */
export async function resolveConsolNoteConflict<T>(
  error: unknown,
  context: T,
  options: ConsolNoteConflictResolverOptions<T>,
): Promise<void> {
  const info = extractConsolNoteConflictInfo(error)
  if (!info) return
  const message = [
    info.message,
    `最近写入方：${noteConflictSourceLabel(info.lastWriteSource)}`,
    `写入时间：${noteConflictTimeLabel(info.updatedAt)}`,
  ].join('；')
  try {
    await options.confirm(
      message,
      '检测到合并附注保存冲突',
      {
        confirmButtonText: '重新加载',
        cancelButtonText: '保留本地修改',
        distinguishCancelAndClose: true,
        type: 'warning',
      },
    )
  } catch {
    return
  }
  if (options.isCurrent()) await options.reload(context)
}

function isRecord(value: unknown): value is UnknownRecord {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

/**
 * 取得错误的 HTTP 响应状态。
 * 同时接受 AxiosError（error.response.status）和测试/解包后的 response（status）。
 */
function responseStatus(error: unknown): number | null {
  if (!isRecord(error)) return null
  const response = isRecord(error.response) ? error.response : error
  const raw = response.status
  if (typeof raw === 'number' && Number.isFinite(raw)) return raw
  if (typeof raw === 'string' && /^\d+$/.test(raw)) return Number(raw)
  return null
}

/**
 * 收集可能承载业务错误的对象。
 * 平台错误可能位于 detail、message，或已经被 API 代理解包为 data 本身。
 */
function detailCandidates(error: unknown): UnknownRecord[] {
  if (!isRecord(error)) return []
  const response = isRecord(error.response) ? error.response : null
  const payloads: unknown[] = []
  if (response && 'data' in response) payloads.push(response.data)
  if ('data' in error && error.data !== response?.data) payloads.push(error.data)
  payloads.push(error)

  const candidates: UnknownRecord[] = []
  const seen = new Set<UnknownRecord>()
  const visit = (value: unknown, depth: number) => {
    if (!isRecord(value) || depth > 2 || seen.has(value)) return
    seen.add(value)
    candidates.push(value)
    for (const key of ['detail', 'message', 'error', 'data']) visit(value[key], depth + 1)
  }
  for (const payload of payloads) visit(payload, 0)
  return candidates
}

function errorCode(error: unknown): string | null {
  for (const candidate of detailCandidates(error)) {
    const code = candidate.error_code ?? candidate.code
    if (typeof code === 'string' && code.trim()) return code.trim()
  }
  return null
}

function matches(error: unknown, code: string, status: number): boolean {
  const actualStatus = responseStatus(error)
  // 已有明确 HTTP 状态时必须与业务错误的状态一致；没有状态的已解包业务对象仍可识别。
  return errorCode(error) === code && (actualStatus === null || actualStatus === status)
}

/** 是否为附注内容摘要冲突（HTTP 409）。 */
export function isConsolNoteConflict(error: unknown): boolean {
  return matches(error, CONSOL_NOTE_CONFLICT_CODE, 409)
}

/** 是否为保存请求缺少 expected_digest / force_overwrite（HTTP 428）。 */
export function isConsolNoteDigestRequired(error: unknown): boolean {
  return matches(error, CONSOL_NOTE_DIGEST_REQUIRED_CODE, 428)
}

function conflictDetail(error: unknown): UnknownRecord | null {
  return detailCandidates(error).find((candidate) => {
    const code = candidate.error_code ?? candidate.code
    return code === CONSOL_NOTE_CONFLICT_CODE
  }) || null
}

function stringOrNull(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

/**
 * 提取冲突弹窗所需的信息。
 * 非合并附注冲突返回 null；冲突详情字段缺失时使用安全默认值，不泄露原始异常文本。
 */
export function extractConsolNoteConflictInfo(error: unknown): ConsolNoteConflictInfo | null {
  if (!isConsolNoteConflict(error)) return null
  const detail = conflictDetail(error) || {}
  const message = stringOrNull(detail.message) || DEFAULT_CONFLICT_MESSAGE
  return {
    currentDigest: stringOrNull(detail.current_digest),
    updatedAt: stringOrNull(detail.updated_at),
    lastWriteSource: stringOrNull(detail.last_write_source) || DEFAULT_LAST_WRITE_SOURCE,
    message,
  }
}

/** 与 `extractConsolNoteConflictInfo` 等价的语义化别名，供保存调用方按读取习惯选择。 */
export const getConsolNoteConflictInfo = extractConsolNoteConflictInfo
