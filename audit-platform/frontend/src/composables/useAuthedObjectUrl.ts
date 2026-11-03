/**
 * useAuthedObjectUrl — 给 iframe / img 用的「已鉴权」原件地址
 *
 * 浏览器原生加载（iframe / img 的 src、a 的 href、window.open）不经 axios，带不上
 * Authorization 头；后端 HTTPBearer 一律 401，预览区里显示的是
 * {"code":401,"message":"Not authenticated"}（2026-10-27 附件 OCR 确认弹窗走查实测）。
 * 这里经 api.get 取字节（走全局令牌与刷新链），换成 blob: 地址再交给元素。
 *
 * - 源地址变化 / 置空 / 所在作用域销毁：中止在途请求并释放旧地址
 * - 晚到的旧响应不覆盖新地址（序号判定）
 * - 预览端点对不可预览类型回 JSON（previewable:false）：按失败处理，不当文件显示
 * - options.type：强制 blob 类型（iframe 显示 PDF 时传 application/pdf，避免浏览器按
 *   octet-stream / 其他类型处理）；不传则沿用响应类型
 *
 * 下载类场景（a 链接 / 新窗口）不用本函数，直接用 utils/http 的 downloadFile。
 */
import { getCurrentScope, onScopeDispose, ref, watch, type WatchSource } from 'vue'
import { api } from '@/services/apiProxy'

export type AuthedObjectUrlState = 'idle' | 'loading' | 'ready' | 'forbidden' | 'not_found' | 'failed'

/** 预览区的失败提示（与状态一一对应，组件直接取用） */
export const AUTHED_OBJECT_URL_FAILURE_TEXT: Record<'forbidden' | 'not_found' | 'failed', string> = {
  forbidden: '无权查看该文件',
  not_found: '文件不存在或已删除',
  failed: '文件加载失败，请稍后重试',
}

export function authedObjectUrlFailureText(state: AuthedObjectUrlState): string {
  return state === 'forbidden' || state === 'not_found' || state === 'failed'
    ? AUTHED_OBJECT_URL_FAILURE_TEXT[state]
    : ''
}

export function useAuthedObjectUrl(
  source: WatchSource<string | null | undefined>,
  options: { type?: () => string | undefined } = {},
) {
  const url = ref('')
  const state = ref<AuthedObjectUrlState>('idle')
  let controller: AbortController | null = null
  let seq = 0

  function release(): void {
    controller?.abort()
    controller = null
    if (url.value) URL.revokeObjectURL(url.value)
    url.value = ''
  }

  async function load(path: string): Promise<void> {
    const mine = ++seq
    release()
    if (!path) {
      state.value = 'idle'
      return
    }
    const ctl = new AbortController()
    controller = ctl
    state.value = 'loading'
    try {
      const data = await api.get(path, {
        responseType: 'blob',
        _silent: true,
        _dedupe: false,
        signal: ctl.signal,
      } as any)
      if (mine !== seq) return
      if (!(data instanceof Blob) || /json/i.test(data.type)) {
        state.value = 'failed'
        return
      }
      const forced = options.type?.()
      const blob = forced && forced !== data.type ? new Blob([data], { type: forced }) : data
      url.value = URL.createObjectURL(blob)
      state.value = 'ready'
    } catch (e: any) {
      if (mine !== seq) return
      const status = e?.response?.status
      state.value = status === 403 ? 'forbidden' : status === 404 ? 'not_found' : 'failed'
    } finally {
      if (mine === seq) controller = null
    }
  }

  watch(source, (path) => { void load(path || '') }, { immediate: true })
  if (getCurrentScope()) {
    onScopeDispose(() => {
      seq++
      release()
    })
  }
  return { url, state }
}
