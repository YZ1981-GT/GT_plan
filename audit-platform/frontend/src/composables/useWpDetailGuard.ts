/**
 * useWpDetailGuard — 底稿详情加载三态守卫 composable
 *
 * 锚定 spec workpaper-editor-refactor Req 1
 *
 * 处理 5 种状态：
 * - 'loading'      初始加载中
 * - 'invalid_id'   wpId 格式不合法（不是 UUID）
 * - 'no_index'     后端无 WpIndex 记录（项目内无该编码）
 * - 'no_file'      有 WpIndex 但无 WorkingPaper 文件记录（需先在生命周期生成）
 * - 'ready'        完整加载成功
 * - 'error'        其他错误
 *
 * @example
 * const guard = useWpDetailGuard(projectId, wpId)
 * if (guard.state.value === 'ready') {
 *   // 安全使用 guard.wpDetail.value
 * } else if (guard.state.value === 'no_file') {
 *   // 显示"请先在生命周期生成"引导
 * }
 */
import { ref, computed, watch, type Ref } from 'vue'
import http from '@/utils/http'

export type WpDetailGuardState =
  | 'loading'
  | 'invalid_id'
  | 'no_index'
  | 'no_file'
  | 'ready'
  | 'error'

export interface WorkingPaperDetail {
  id: string
  project_id: string
  wp_index_id: string
  file_path: string | null
  source_type: string
  status: string
  review_status?: string
  assigned_to: string | null
  reviewer: string | null
  file_version: number
  last_parsed_at: string | null
  wp_code?: string
  wp_name?: string
  parsed_data?: any
  [key: string]: any
}

export interface WpIndexInfo {
  id: string
  wp_code: string
  wp_name: string
  audit_cycle: string | null
  status: string | null
}

const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function useWpDetailGuard(
  projectId: Ref<string> | (() => string),
  wpId: Ref<string> | (() => string),
) {
  const state = ref<WpDetailGuardState>('loading')
  const wpDetail = ref<WorkingPaperDetail | null>(null)
  const wpIndex = ref<WpIndexInfo | null>(null)
  const errorMessage = ref('')

  const loading = computed(() => state.value === 'loading')
  const ready = computed(() => state.value === 'ready')

  function _readId(src: Ref<string> | (() => string)): string {
    return typeof src === 'function' ? src() : src.value
  }

  async function refresh() {
    const pid = _readId(projectId)
    const wid = _readId(wpId)

    state.value = 'loading'
    errorMessage.value = ''
    wpDetail.value = null
    wpIndex.value = null

    // ① 校验 wpId 格式
    if (!wid || !UUID_REGEX.test(wid)) {
      state.value = 'invalid_id'
      errorMessage.value = '底稿 ID 格式不合法'
      return
    }

    // ② 尝试加载 working_paper.id 对应的底稿详情
    try {
      const res = await http.get(`/api/projects/${pid}/working-papers/${wid}`, {
        validateStatus: (s: number) => s < 600,
      })

      if (res.status === 200 && res.data) {
        // 加载成功
        wpDetail.value = res.data
        // 文件未生成（file_path 为空）→ no_file
        if (!res.data.file_path) {
          state.value = 'no_file'
          errorMessage.value = '底稿文件尚未生成，请先在生命周期中执行"一键生成底稿"'
          return
        }
        state.value = 'ready'
        return
      }

      // ③ 404 → 检查是否是 wp_index.id 而非 working_paper.id
      if (res.status === 404) {
        const indexRes = await http.get(`/api/projects/${pid}/wp-index`, {
          validateStatus: (s: number) => s < 600,
        })
        if (indexRes.status === 200 && Array.isArray(indexRes.data)) {
          const matched = indexRes.data.find((i: any) => i.id === wid)
          if (matched) {
            // 是 wp_index.id 但没有 working_paper 文件
            wpIndex.value = matched
            state.value = 'no_file'
            errorMessage.value = `底稿 ${matched.wp_code} 索引存在但文件尚未生成，请先在生命周期中执行"一键生成底稿"`
            return
          }
        }
        // 既不是 working_paper 也不是 wp_index
        state.value = 'no_index'
        errorMessage.value = '该底稿不在当前项目中（可能编码已变更或被删除）'
        return
      }

      // 其他错误
      state.value = 'error'
      errorMessage.value = `加载底稿失败（HTTP ${res.status}）`
    } catch (e: any) {
      state.value = 'error'
      errorMessage.value = e?.message || '加载底稿时发生网络错误'
    }
  }

  // 监听 wpId 变化自动刷新
  if (typeof wpId !== 'function') {
    watch(wpId, () => {
      refresh()
    }, { immediate: true })
  } else {
    refresh()
  }

  return {
    state,
    wpDetail,
    wpIndex,
    loading,
    ready,
    errorMessage,
    refresh,
  }
}
