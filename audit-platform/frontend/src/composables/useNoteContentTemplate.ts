/**
 * useNoteContentTemplate — 附注内容模板目录 / 版本 / 保存 composable
 *
 * spec: disclosure-note-doc-upload-and-batch-fill Task 46 / 47（第二轮复盘：对齐后端契约）
 * 不采集浏览器快照：预检与保存只发 {year, name, description, owner_scope}（+ digest），
 * 快照由后端按 project_id + year 生成；列表只载元数据，正文只在预览阶段由后端读取。
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { notifyBatchError, silent, type BatchError } from '@/composables/useNoteTextBatch'

export type OwnerScope = 'personal' | 'group'

export interface ContentTemplateVersion {
  id: string
  version_no: number
  source_project_id?: string
  source_project_name: string
  source_year: number
  template_type: string
  report_scope: string
  quality_summary: Record<string, number>
  content_hash: string
  byte_size: number
  created_by?: string | null
  created_at: string | null
}

export interface ContentTemplateItem {
  id: string
  name: string
  description: string | null
  owner_scope: OwnerScope
  current_version_id: string | null
  current_version?: ContentTemplateVersion | null
  created_by: string | null
  created_at: string | null
  updated_at: string | null
}

export interface SnapshotPreviewResult {
  snapshot_digest: string
  content_hash: string
  byte_size: number
  source_project_name: string
  source_year: number
  template_type: string
  report_scope: string
  quality_summary: Record<string, number>
  owner_scope: OwnerScope
  section_count: number
  group_root_project_id?: string
  group_root_project_name?: string | null
}

export interface SaveTemplateResult {
  template_id: string
  version_id: string
  version_no: number
  content_hash: string
  reused: boolean
}

export interface SaveTemplateInput {
  year: number
  name: string
  description: string | null
  ownerScope: OwnerScope
}

export const NOTE_CONTENT_TEMPLATE_PATHS = {
  list: (pid: string) => `/api/projects/${pid}/note-content-templates`,
  detail: (pid: string, tid: string) => `/api/projects/${pid}/note-content-templates/${tid}`,
  versions: (pid: string, tid: string) => `/api/projects/${pid}/note-content-templates/${tid}/versions`,
  snapshotPreview: (pid: string) => `/api/projects/${pid}/note-content-templates/snapshot-preview`,
  save: (pid: string) => `/api/projects/${pid}/note-content-templates`,
  delete: (pid: string, tid: string) => `/api/projects/${pid}/note-content-templates/${tid}`,
}

function body(input: SaveTemplateInput) {
  return { year: input.year, name: input.name.trim(), description: input.description || null,
    owner_scope: input.ownerScope }
}

export function useNoteContentTemplate(options: { projectId: Ref<string> }) {
  const { projectId } = options

  const loading = ref(false)
  const saveLoading = ref(false)
  const templates = ref<ContentTemplateItem[]>([])
  const total = ref(0)
  const versions = ref<ContentTemplateVersion[]>([])
  const snapshotPreview = ref<SnapshotPreviewResult | null>(null)
  const lastError = ref<BatchError | null>(null)

  function fail(e: unknown, fallback: string, notify = true): BatchError {
    lastError.value = notifyBatchError(e, fallback, projectId.value, notify)
    return lastError.value
  }

  /** 只有最后一发列表请求能落状态：被去重取消 / 迟到的旧请求不得覆盖新结果或提前结束加载态 */
  let listSeq = 0

  /** append：「加载更多」追加下一页；失败保留已载条目。非 append 失败清空，避免把旧列表当成现状 */
  async function fetchTemplates(limit = 50, offset = 0, opts: { append?: boolean } = {}): Promise<void> {
    const seq = ++listSeq
    loading.value = true
    lastError.value = null
    try {
      const result = await api.get<{ items: ContentTemplateItem[]; total: number }>(
        NOTE_CONTENT_TEMPLATE_PATHS.list(projectId.value), silent({ params: { limit, offset } }))
      if (seq !== listSeq) return
      const items = result.items || []
      templates.value = opts.append ? [...templates.value, ...items] : items
      total.value = result.total ?? templates.value.length
    } catch (e) {
      if (seq !== listSeq) return  // 含 http 去重取消：取消只发生在同键新请求发出时
      if (!opts.append) {
        templates.value = []
        total.value = 0
      }
      fail(e, '模板列表加载失败')
    } finally {
      if (seq === listSeq) loading.value = false
    }
  }

  async function fetchVersions(templateId: string): Promise<ContentTemplateVersion[]> {
    lastError.value = null
    try {
      const result = await api.get<{ items: ContentTemplateVersion[] }>(
        NOTE_CONTENT_TEMPLATE_PATHS.versions(projectId.value, templateId), silent())
      versions.value = result.items || []
    } catch (e) {
      versions.value = []
      fail(e, '加载版本列表失败')
    }
    return versions.value
  }

  /** 保存前预检：后端生成快照摘要与 digest；集团归属在此即校验发布权限（403 不弹两次） */
  async function previewSnapshot(input: SaveTemplateInput): Promise<SnapshotPreviewResult | null> {
    loading.value = true
    lastError.value = null
    try {
      snapshotPreview.value = await api.post<SnapshotPreviewResult>(
        NOTE_CONTENT_TEMPLATE_PATHS.snapshotPreview(projectId.value), body(input), silent())
      return snapshotPreview.value
    } catch (e) {
      snapshotPreview.value = null
      fail(e, '预检失败')
      return null
    } finally {
      loading.value = false
    }
  }

  /** 携预检 digest 正式保存；来源在预检后变化 ⇒ STALE_SNAPSHOT，由调用方要求重新预检 */
  async function saveTemplate(input: SaveTemplateInput, digest: string): Promise<SaveTemplateResult | null> {
    saveLoading.value = true
    lastError.value = null
    try {
      return await api.post<SaveTemplateResult>(NOTE_CONTENT_TEMPLATE_PATHS.save(projectId.value),
        { ...body(input), snapshot_digest: digest }, silent())
    } catch (e) {
      const err = fail(e, '保存失败', false)
      if (err.code === 'STALE_SNAPSHOT') ElMessage.warning('来源附注在预检后已变化，请重新预检')
      else if (err.code !== 'CANCELED') ElMessage.error(err.message)
      return null
    } finally {
      saveLoading.value = false
    }
  }

  /** 调用方必须先在 UI 二次确认 */
  async function deleteTemplate(templateId: string): Promise<boolean> {
    try {
      await api.delete(NOTE_CONTENT_TEMPLATE_PATHS.delete(projectId.value, templateId), silent()) // eslint-disable-line gt-audit/no-delete-without-confirm
      ElMessage.success('模板已删除')
      await fetchTemplates()
      return true
    } catch (e) {
      fail(e, '删除失败')
      return false
    }
  }

  function reset() {
    templates.value = []
    total.value = 0
    versions.value = []
    snapshotPreview.value = null
    lastError.value = null
  }

  return {
    loading, saveLoading, templates, total, versions, snapshotPreview, lastError,
    fetchTemplates, fetchVersions, previewSnapshot, saveTemplate, deleteTemplate, reset,
  }
}
