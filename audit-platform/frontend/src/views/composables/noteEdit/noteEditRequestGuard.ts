/**
 * noteEditRequestGuard — 请求级守卫：编辑器挂载时装拦截器，卸载时拆除
 *
 * 当不可写时，拦截覆盖集合内的写请求并以 axios.Cancel 拒绝，请求不发出。
 * 当可写时，在 config 上挂 _forbiddenHandler——后端返回 403 时由 http.ts 调用它。
 *
 * Feature: partner-manager-edit-permission
 * Requirements: 10.7, 10.10
 */
import axios, { type InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { matchesCoverage } from './noteEditCoverage'
import type { UseNoteEditPermissionReturn } from './useNoteEditPermission'

/** 解析后端拒绝原因文本 */
function extractReason(response: any): string {
  if (!response) return ''
  const d = response.data
  if (typeof d === 'string') return d
  if (d?.message) return d.message
  if (d?.detail && typeof d.detail === 'string') return d.detail
  if (d?.detail?.message) return d.detail.message
  if (d?.data && typeof d.data === 'string') return d.data
  return ''
}

/** 判断请求是否属于覆盖集合内的写方法 */
function isWriteInCoverage(config: InternalAxiosRequestConfig): boolean {
  const method = (config.method || '').toUpperCase()
  if (!['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) return false
  const url = config.url || ''
  return matchesCoverage(method, url)
}

export interface NoteEditRequestGuardReturn {
  install: () => void
  uninstall: () => void
}

/**
 * 判断错误是否由守卫拦截或后端门禁拒绝引起。
 * 用于 catch 块跳过本地降级——这类错误已由拦截器处理过。
 */
export function isNoteEditGuardError(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false
  const e = err as any
  if (e.__CANCEL__ || e.message === 'note-edit-readonly') return true
  const status = e?.response?.status
  return status === 403 || status === 423
}

/**
 * autoSave 的 shouldRetry 回调：守卫取消 / 403 / 423 不重试。
 */
export function noteEditShouldRetry(err: unknown): boolean {
  return !isNoteEditGuardError(err)
}

/**
 * 创建请求级守卫。调用 install() 装上拦截器，uninstall() 拆除。
 *
 * @param noteEdit useNoteEditPermission 的返回值（canWrite 、 markRejected 、 refresh）
 */
export function createNoteEditRequestGuard(
  noteEdit: Pick<UseNoteEditPermissionReturn, 'canWrite' | 'markRejected' | 'refresh'>,
): NoteEditRequestGuardReturn {
  let requestInterceptorId: number | null = null
  let responseInterceptorId: number | null = null

  function install() {
    // 请求拦截器：后装先执行，先于 http.ts 自己的去重拦截器
    requestInterceptorId = http.interceptors.request.use(
      (config: InternalAxiosRequestConfig) => {
        if (!isWriteInCoverage(config)) return config
        // 不可写：以 Cancel 拒绝，请求不发出
        if (!noteEdit.canWrite.value) {
          throw new axios.Cancel('note-edit-readonly')
        }
        // 可写：挂 _forbiddenHandler 供 403 时调用
        ;(config as any)._forbiddenHandler = (error: any) => {
          noteEdit.markRejected()
          const reason = extractReason(error?.response)
          ElMessage.error(reason || '权限不足')
          noteEdit.refresh()
        }
        return config
      },
    )
    // 响应拦截器：处理 423 — markRejected + refresh，不另弹提示（现有 toast 保留）
    responseInterceptorId = http.interceptors.response.use(
      undefined,
      (error: any) => {
        if (error?.response?.status === 423 && error?.config && isWriteInCoverage(error.config)) {
          noteEdit.markRejected()
          noteEdit.refresh()
        }
        return Promise.reject(error)
      },
    )
  }

  function uninstall() {
    if (requestInterceptorId !== null) {
      http.interceptors.request.eject(requestInterceptorId)
      requestInterceptorId = null
    }
    if (responseInterceptorId !== null) {
      http.interceptors.response.eject(responseInterceptorId)
      responseInterceptorId = null
    }
  }

  return { install, uninstall }
}
