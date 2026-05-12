/**
 * errorHandler.ts — 统一 API 错误处理 [R7-S2-10]
 *
 * 提供 handleApiError(e, context) 替代各视图手搓 ElMessage.error。
 * 按 HTTP 状态码分级处理：网络错误/401/403/404/409/5xx。
 *
 * @example
 * try { await api.post(...) }
 * catch (e) { handleApiError(e, '保存底稿') }
 */
import { ElMessage, ElNotification } from 'element-plus'
import { getLastTraceId } from '@/utils/http'

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
    const msg = detail?.message || detail?.error || '数据冲突，请刷新后重试'
    ElNotification({ title: '操作冲突', message: msg, type: 'warning', duration: 6000 })
    return
  }

  // 422 — 参数校验失败
  if (status === 422) {
    const msg = detail?.message || '请求参数有误，请检查输入'
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
