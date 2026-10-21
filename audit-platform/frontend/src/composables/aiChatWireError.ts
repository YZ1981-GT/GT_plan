/**
 * AI 对话写接口（采纳 / 转存笔记）的失败响应解析 —— 单一真源。
 *
 * 这两个接口走原生 `fetch`（不经 axios 拦截器的 `normaliseErrorEnvelope`），后端三种失败形状
 * 并存（2026-10-20 真实环境实测）：
 *
 * - 业务 `HTTPException(detail={code, message})` 经平台 `http_exception_handler` 输出
 *   `{"code": 422, "message": {"code": "no_target", "message": "请选择笔记保存位置"}}`
 *   —— **外层 `code` 是 HTTP 状态数字**，业务码在 `message` 对象里；
 * - 不可枚举 404：`{"code": 404, "message": "资源不存在或不可访问"}`；
 * - 请求体校验失败：`{"code": 422, "message": "请求参数校验失败", "detail": [...]}`。
 *
 * 旧解析 `body.detail ?? body` 会把外层数字当业务码、把 `message` 对象当提示文案
 * （界面显示 `[object Object]` 或兜底文案），这里统一收口。
 */

export interface AiChatWireError {
  /** 业务错误码（如 `no_target`）；只取字符串，HTTP 状态数字不当业务码 */
  code?: string
  /** 可直接展示的中文原因 */
  message?: string
}

function pick(raw: unknown): AiChatWireError | null {
  if (typeof raw === 'string') return raw.trim() ? { message: raw } : null
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const obj = raw as Record<string, unknown>
  const code = typeof obj.code === 'string'
    ? obj.code
    : typeof obj.error_code === 'string' ? obj.error_code : undefined
  const message = typeof obj.message === 'string' && obj.message.trim() ? obj.message : undefined
  return code || message ? { code, message } : null
}

/** 从已解析的 JSON 响应体取 `(业务码, 中文原因)`；取不到的字段为 undefined。 */
export function readAiChatError(body: unknown): AiChatWireError {
  if (!body || typeof body !== 'object') return {}
  const b = body as Record<string, unknown>
  // FastAPI 默认形状 `{detail}` 优先；平台信封把 exc.detail 放在 `message`
  const fromDetail = pick(b.detail)
  if (fromDetail?.code) return fromDetail
  const fromMessage = pick(b.message)
  if (fromMessage?.code) return fromMessage
  return fromDetail ?? fromMessage ?? pick(b.data) ?? {}
}

/** 读取失败响应体（非 JSON 时返回空对象，不抛）。 */
export async function readAiChatErrorResponse(res: { json: () => Promise<unknown> }): Promise<AiChatWireError> {
  try {
    return readAiChatError(await res.json())
  } catch {
    return {}
  }
}
