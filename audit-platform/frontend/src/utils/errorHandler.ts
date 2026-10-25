/**
 * errorHandler.ts — 统一 API 错误处理 [P0-4]
 *
 * 提供 handleApiError(e, context) 替代各视图手搓 ElMessage.error。
 * 按 HTTP 状态码分级处理：网络错误/401/403/404/409/5xx。
 *
 * 错误分类（四类）：
 * - permission: 403/401 权限相关
 * - network: 无 status（网络不通）
 * - backend_detail: 400/404/409/422/423 带后端 detail
 * - degraded: 503 服务降级 / 5xx 服务端错误
 *
 * @example
 * try { await api.post(...) }
 * catch (e) { handleApiError(e, '保存底稿') }
 */
import { ElMessage, ElNotification } from 'element-plus'
import { getLastTraceId } from '@/utils/http'

/** 错误分类枚举 */
export type ApiErrorCategory = 'permission' | 'network' | 'backend_detail' | 'degraded'

/**
 * 解析错误的分类（不弹提示，仅返回分类）
 * 适用于需要程序化处理错误的场景
 */
export function classifyApiError(e: any): ApiErrorCategory {
  const status = e?.response?.status || e?.status || 0
  if (!status) return 'network'
  if (status === 401 || status === 403) return 'permission'
  if (status >= 500) return 'degraded'
  return 'backend_detail'
}

/**
 * 后端错误详情 → 可展示文本（取不到返回空串，由调用方给兜底文案）。
 *
 * 🔴 两种形态都要认：业务 `HTTPException("中文原因")` 经 `http.ts` 的
 * `normaliseErrorEnvelope` 归一后 `detail` 是**字符串**；只有 dict 形态才有 `.message`。
 * 旧实现只读 `detail?.message` ⇒ 所有字符串 detail 的 409/422/503 都被兜底文案吞掉
 * （2026-09-29 实测：知识库「项目组须包含你参与的项目」422 只显示「请求参数有误」）。
 * FastAPI 字段校验 422 的 `detail` 是数组（英文字段错误）→ 仍走兜底文案。
 */
function detailText(detail: any): string {
  if (typeof detail === 'string') return detail.trim()
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    return String(detail.message || detail.msg || detail.error || '').trim()
  }
  return ''
}

/**
 * 统一 API 错误处理
 * @param e - catch 到的错误对象
 * @param context - 操作上下文描述（如"保存底稿"、"加载项目"）
 */
export function handleApiError(e: any, context: string): void {
  const status = e?.response?.status || e?.status || 0
  const detail = e?.response?.data?.detail || e?.data?.detail

  // 网络错误（无 status）
  if (!status) {
    ElMessage.error(`${context}：网络不通，请检查连接`)
    return
  }

  // 401 — http.ts 已处理 token 刷新，此处静默
  if (status === 401) return

  // 403 — 无权限
  if (status === 403) {
    ElMessage.warning(`${context}：无权操作`)
    return
  }

  // 404 — 资源不存在
  if (status === 404) {
    ElMessage.warning(`${context}：资源不存在`)
    return
  }

  // 409 — 冲突（版本冲突/重复操作）
  if (status === 409) {
    const msg = detailText(detail) || '数据冲突，请刷新后重试'
    ElNotification({ title: '操作冲突', message: msg, type: 'warning', duration: 6000 })
    return
  }

  // 423 — 项目已归档（只读）
  if (status === 423) {
    ElMessage.warning(`${context}：项目已归档（只读），无法执行此操作`)
    return
  }

  // 422 — 参数校验失败 / 业务规则拦截
  if (status === 422) {
    const errorCode = detail?.error_code || e?.response?.data?.error_code
    if (errorCode === 'AI_CONTENT_NOT_CONFIRMED') {
      ElMessage.warning(`${context}：存在未确认的 AI 内容，请先确认后再操作`)
      return
    }
    if (errorCode === 'CROSS_MODULE_CONFLICT_UNRESOLVED') {
      ElMessage.warning(`${context}：存在未调解的跨模块冲突，请先调解后再操作`)
      return
    }
    const msg = detailText(detail) || '请求参数有误，请检查输入'
    ElMessage.warning(`${context}：${msg}`)
    return
  }

  // 503 — 服务降级
  if (status === 503) {
    ElNotification({
      title: `${context}：服务降级`,
      message: detailText(detail) || '服务暂时不可用，请稍后重试',
      type: 'warning',
      duration: 8000,
    })
    return
  }

  // 400 — 请求错误（含后端 detail）
  if (status === 400) {
    const msg = detailText(detail) || '请求参数错误'
    ElMessage.warning(`${context}：${msg}`)
    return
  }

  // 5xx — 服务端错误
  const traceId = getLastTraceId()
  ElNotification({
    title: `${context}失败`,
    dangerouslyUseHTMLString: true,
    message: traceId
      ? `系统错误，请联系管理员<br/><small style="cursor:pointer;color:var(--gt-color-primary)" onclick="navigator.clipboard.writeText('${traceId}').then(()=>this.textContent='已复制!')">trace: ${traceId} 📋</small>`
      : '系统错误，请联系管理员',
    type: 'error',
    duration: 10000,
  })
}
