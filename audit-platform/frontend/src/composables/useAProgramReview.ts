/**
 * useAProgramReview — A 类程序表复核子码解析 + A17 版本适用性
 *
 * 从 GtAProgramConsole.vue 抽出（spec workpaper-frontend-large-component-split, Req 1）：
 * - A21~A25 复核子码解析（A1 seq15–17 父码 → 适用 -1/-2）：reviewTemplates state
 * - A17-5 核对表版本适用性：a17_5Versions state + a17OtherExpanded 折叠状态
 * - chip 展示值/禁用/badge 解析；加载 review templates / a17_5 versions
 *
 * 铁律：行为零变更、保响应式（ref/computed）；不在 composable 内 emit；依赖单向（composable → util）。
 *
 * @example
 * const review = useAProgramReview({
 *   sheetName: () => props.sheetName,
 *   projectId,
 *   parseLinkedWorkpapers,
 * })
 */
import { ref, computed, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import {
  isReviewRoleRef,
  resolveReviewWpCode as resolveReviewWpCodeUtil,
} from '@/components/workpaper/reviewWpResolve'

interface ReviewLinkedRow {
  linked_workpapers?: string
}

export function useAProgramReview(options: {
  /** 当前底稿 sheetName 取值（getter，保持响应式） */
  sheetName: () => string
  /** 项目 ID */
  projectId: Ref<string>
  /** 解析 linked_workpapers 字符串为 ref 数组（主组件持有，传入复用） */
  parseLinkedWorkpapers: (value: string) => string[]
}) {
  const { projectId, parseLinkedWorkpapers } = options

  /** 从 sheetName 提取 table_code (如 "审计程序A8" → "A8") */
  function extractTableCode(sheetName: string): string {
    // 匹配 A1~A17 格式（防御：a11-bundle 等嵌套渲染场景 sheetName 可能为 undefined）
    const m = sheetName?.match(/[A-S]\d+/)
    return m ? m[0] : ''
  }

  // ─── A17-5 核对表版本适用性 ───
  const a17_5Versions = ref<Record<string, { applicable: boolean; mandatory: boolean }>>({})
  const a17OtherExpanded = ref(false)

  // ─── A21~A25 复核子码解析（A1 seq15–17 父码 → 适用 -1/-2）───
  const reviewTemplates = ref<Record<string, { applicable: boolean; mandatory: boolean; reason?: string }>>({})

  const isA1Table = computed(() => extractTableCode(options.sheetName()) === 'A1')
  const isA17Table = computed(() => extractTableCode(options.sheetName()) === 'A17')

  function resolveReviewWpCode(ref: string): string {
    return resolveReviewWpCodeUtil(ref, reviewTemplates.value)
  }

  function reviewChipDisplayValue(ref: string): string {
    return isReviewRoleRef(ref) ? resolveReviewWpCode(ref) : ref
  }

  function isReviewChipDisabled(ref: string): boolean {
    if (!isReviewRoleRef(ref)) return false
    const code = resolveReviewWpCode(ref)
    const info = reviewTemplates.value[code]
    return info ? !info.applicable : false
  }

  function reviewChipBadge(ref: string): string {
    if (!isReviewRoleRef(ref)) return ''
    const code = resolveReviewWpCode(ref)
    const info = reviewTemplates.value[code]
    if (!info?.applicable) return ''
    return info.mandatory ? '必做' : ''
  }

  function chipCompletionKey(ref: string): string {
    return isReviewRoleRef(ref) ? resolveReviewWpCode(ref) : ref
  }

  async function fetchReviewTemplates() {
    if (!projectId.value) return
    if (!isA1Table.value && !isA17Table.value) return
    try {
      const res = await api.get(
        `/api/projects/${projectId.value}/a21/applicable-review-templates`,
      )
      const list = Array.isArray(res) ? res : (res?.data ?? res ?? [])
      const map: Record<string, { applicable: boolean; mandatory: boolean; reason?: string }> = {}
      for (const v of list) {
        if (v?.wp_code) {
          map[v.wp_code] = {
            applicable: !!v.applicable,
            mandatory: !!v.mandatory,
            reason: v.reason,
          }
        }
      }
      reviewTemplates.value = map
    } catch {
      reviewTemplates.value = {}
    }
  }

  function isA17_5Ref(ref: string): boolean {
    return /^A17-5-\d$/.test(ref)
  }

  function isA17_5ChipDisabled(ref: string): boolean {
    if (!isA17_5Ref(ref)) return false
    const info = a17_5Versions.value[ref]
    return info ? !info.applicable : false
  }

  function a17_5Badge(ref: string): string {
    const info = a17_5Versions.value[ref]
    if (!info || !info.applicable) return ''
    return info.mandatory ? '必做' : '推荐'
  }

  function a17Seq5Refs(row: ReviewLinkedRow): string[] {
    return parseLinkedWorkpapers(row.linked_workpapers || '').filter(r => isA17_5Ref(r))
  }

  function isA17Seq5Row(row: ReviewLinkedRow): boolean {
    if (!isA17Table.value) return false
    return a17Seq5Refs(row).length >= 3
  }

  function a17ApplicableRefs(row: ReviewLinkedRow): string[] {
    return a17Seq5Refs(row).filter(r => {
      const info = a17_5Versions.value[r]
      if (!info) return true
      return info.applicable
    })
  }

  function a17InapplicableRefs(row: ReviewLinkedRow): string[] {
    return a17Seq5Refs(row).filter(r => {
      const info = a17_5Versions.value[r]
      return info ? !info.applicable : false
    })
  }

  async function fetchA17ApplicableVersions() {
    if (!isA17Table.value || !projectId.value) return
    try {
      const res = await api.get('/api/a17/applicable-versions', {
        params: { project_id: projectId.value },
      })
      const list = Array.isArray(res) ? res : (res?.data ?? res ?? [])
      const map: Record<string, { applicable: boolean; mandatory: boolean }> = {}
      for (const v of list) {
        if (v?.wp_code) {
          map[v.wp_code] = {
            applicable: !!v.applicable,
            mandatory: !!v.mandatory,
          }
        }
      }
      a17_5Versions.value = map
    } catch { /* ignore */ }
  }

  return {
    // state
    reviewTemplates,
    a17_5Versions,
    a17OtherExpanded,
    // computed
    isA1Table,
    isA17Table,
    // review chip 解析
    resolveReviewWpCode,
    reviewChipDisplayValue,
    isReviewChipDisabled,
    reviewChipBadge,
    chipCompletionKey,
    // A17-5 版本
    isA17_5Ref,
    isA17_5ChipDisabled,
    a17_5Badge,
    a17Seq5Refs,
    isA17Seq5Row,
    a17ApplicableRefs,
    a17InapplicableRefs,
    // 加载
    fetchReviewTemplates,
    fetchA17ApplicableVersions,
  }
}
