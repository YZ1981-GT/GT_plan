/**
 * G7 底稿侧发起合并联动（R1）—— 只复用既有 preview/import 端点，不新造后端口径。
 *
 * - `openPreview()` → `previewG7Linkage`（`GET .../g7-linkage/{pid}/{year}/preview`）
 * - `confirmImport()` → `importG7Linkage`（`POST .../import`），透传最近一次 preview 的
 *   `item_versions` 作为 `expected_versions`（乐观锁）
 * - 409（源数据已变更）→ 提示 + 自动重新 preview，**绝不自动重试写入**（Property 11）
 * - 422（配置错误/多实例/年度不一致）→ 显示后端 `detail` 原文，禁用确认导入
 * - `/stale` 只读薄端点（Wave 5 落地）失败时静默降级（Property 12）
 * - `gotoConsolidation()` 跳合并工作底稿供核对写入结果
 */
import { ref, computed, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import {
  previewG7Linkage,
  importG7Linkage,
  type G7LinkagePreview,
} from '@/services/consolWorksheetDataApi'

/** 后端返回的错误细节（axios error.response.data.detail 原文） */
function extractDetail(err: unknown): string {
  const anyErr = err as any
  const detail = anyErr?.response?.data?.detail ?? anyErr?.response?.data?.message
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d: any) => d?.msg || String(d)).join('；')
  }
  return anyErr?.message || '联动失败'
}

function statusOf(err: unknown): number {
  return Number((err as any)?.response?.status ?? 0)
}

export interface G7ConsolLinkageEntry {
  preview: Ref<G7LinkagePreview | null>
  loading: Ref<boolean>
  importing: Ref<boolean>
  configError: Ref<string>
  stale: Ref<boolean>
  staleSheets: Ref<string[]>
  suggestionCount: Ref<number>
  unresolvedCount: Ref<number>
  openPreview: () => Promise<boolean>
  confirmImport: (opts?: { overwrite?: boolean }) => Promise<boolean>
  refreshStale: () => Promise<void>
  gotoConsolidation: () => void
  reset: () => void
}

export function useG7ConsolLinkageEntry(
  projectId: Ref<string>,
  year: Ref<number>,
): G7ConsolLinkageEntry {
  const router = useRouter()
  const preview = ref<G7LinkagePreview | null>(null)
  const loading = ref(false)
  const importing = ref(false)
  const configError = ref('')
  const stale = ref(false)
  const staleSheets = ref<string[]>([])

  const suggestionCount = computed(() => preview.value?.suggestions?.length ?? 0)
  const unresolvedCount = computed(() => preview.value?.unresolved_companies?.length ?? 0)

  async function openPreview(): Promise<boolean> {
    if (!projectId.value || !year.value) {
      configError.value = '缺少项目或年度上下文'
      return false
    }
    loading.value = true
    configError.value = ''
    try {
      const data = await previewG7Linkage(projectId.value, year.value)
      preview.value = data
      stale.value = !!data.linkage_stale
      staleSheets.value = data.stale_sheets ?? []
      return true
    } catch (err) {
      const status = statusOf(err)
      if (status === 422) {
        // 配置错误（多实例/未生成/年度不一致）：显示后端原文，禁用导入
        configError.value = extractDetail(err)
      } else {
        configError.value = extractDetail(err)
      }
      preview.value = null
      return false
    } finally {
      loading.value = false
    }
  }

  async function confirmImport(opts?: { overwrite?: boolean }): Promise<boolean> {
    const pv = preview.value
    if (!pv) return false
    importing.value = true
    try {
      // 默认导入全部可映射主体（未匹配主体由后端跳过）
      const companyMappings: Record<string, string> = {}
      for (const c of pv.available_companies ?? []) {
        companyMappings[c.company_code] = c.company_code
      }
      const applyIds = (pv.suggestions ?? [])
        .filter((s) => s.selected_default)
        .map((s) => s.id)
      const result = await importG7Linkage(projectId.value, year.value, {
        company_mappings: companyMappings,
        overwrite: !!opts?.overwrite,
        // 透传最近一次 preview 的版本号作为乐观锁
        expected_versions: pv.item_versions ?? {},
        apply_suggestion_ids: applyIds,
      })
      const total = Object.values(result.imported ?? {}).reduce((a, b) => a + Number(b || 0), 0)
      ElMessage.success(
        `已联动到合并工作底稿：写入 ${total} 行` +
        (result.suggestions_applied ? `，建议草稿 ${result.suggestions_applied} 条` : ''),
      )
      stale.value = false
      staleSheets.value = []
      // 导入成功后刷新预览（反映最新版本号）
      await openPreview()
      return true
    } catch (err) {
      const status = statusOf(err)
      if (status === 409) {
        // 源数据已变更：提示 + 自动重新 preview，不自动重试写入（Property 11）
        ElMessage.warning('G7 源数据已变更，已为你重新预览，请核对后再导入')
        await openPreview()
      } else if (status === 422) {
        configError.value = extractDetail(err)
        ElMessage.error(configError.value)
      } else {
        ElMessage.error(extractDetail(err))
      }
      return false
    } finally {
      importing.value = false
    }
  }

  async function refreshStale(): Promise<void> {
    if (!projectId.value || !year.value) return
    try {
      const { data } = await http.get(
        `/api/consol-worksheet-data/g7-linkage/${projectId.value}/${year.value}/stale`,
        { _silent: true } as any,
      )
      const body = data?.data ?? data ?? {}
      stale.value = !!body.linkage_stale
      staleSheets.value = Array.isArray(body.stale_sheets) ? body.stale_sheets : []
    } catch {
      // 静默降级：不显示提示、不抛错（Property 12）
    }
  }

  function gotoConsolidation(): void {
    if (!projectId.value) return
    router.push({
      name: 'ConsolidationIndex',
      params: { projectId: projectId.value },
      query: { year: String(year.value) },
    }).catch(() => {
      // 路由名不同环境可能不同，兜底跳 URL
      window.location.href = `/projects/${projectId.value}/consolidation?year=${year.value}`
    })
  }

  function reset(): void {
    preview.value = null
    configError.value = ''
  }

  return {
    preview,
    loading,
    importing,
    configError,
    stale,
    staleSheets,
    suggestionCount,
    unresolvedCount,
    openPreview,
    confirmImport,
    refreshStale,
    gotoConsolidation,
    reset,
  }
}
