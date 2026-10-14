/**
 * useNoteContentTemplate — 附注内容模板目录/版本/保存 composable
 *
 * spec: disclosure-note-doc-upload-and-batch-fill Phase 8 Task 46
 * 不采集浏览器快照；模板列表只载元数据，正文仅在 preview 阶段加载。
 */
import { ref, computed, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import { ElMessage } from 'element-plus'

export interface ContentTemplateItem {
  id: string
  name: string
  description: string | null
  owner_scope: 'personal' | 'group'
  current_version_id: string | null
  created_by: string | null
  created_at: string | null
  updated_at: string | null
  current_version?: ContentTemplateVersion | null
}

export interface ContentTemplateVersion {
  id: string
  version_no: number
  source_project_name: string
  source_year: number
  template_type: string
  report_scope: string
  quality_summary: Record<string, number>
  content_hash: string
  byte_size: number
  created_at: string | null
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
}

const PATHS = {
  list: (pid: string) => `/api/projects/${pid}/note-content-templates`,
  detail: (pid: string, tid: string) => `/api/projects/${pid}/note-content-templates/${tid}`,
  versions: (pid: string, tid: string) => `/api/projects/${pid}/note-content-templates/${tid}/versions`,
  snapshotPreview: (pid: string) => `/api/projects/${pid}/note-content-templates/snapshot-preview`,
  save: (pid: string) => `/api/projects/${pid}/note-content-templates`,
  delete: (pid: string, tid: string) => `/api/projects/${pid}/note-content-templates/${tid}`,
}

export function useNoteContentTemplate(options: { projectId: Ref<string> }) {
  const { projectId } = options

  const loading = ref(false)
  const templates = ref<ContentTemplateItem[]>([])
  const selectedTemplate = ref<ContentTemplateItem | null>(null)
  const selectedVersion = ref<ContentTemplateVersion | null>(null)
  const versions = ref<ContentTemplateVersion[]>([])
  const snapshotPreview = ref<SnapshotPreviewResult | null>(null)
  const saveLoading = ref(false)

  async function fetchTemplates(): Promise<void> {
    loading.value = true
    try {
      const result = await api.get<{ items: ContentTemplateItem[] }>(PATHS.list(projectId.value))
      templates.value = result.items || []
    } catch {
      ElMessage.error('加载模板列表失败')
    } finally {
      loading.value = false
    }
  }

  async function fetchDetail(templateId: string): Promise<ContentTemplateItem | null> {
    try {
      const detail = await api.get<ContentTemplateItem>(PATHS.detail(projectId.value, templateId))
      selectedTemplate.value = detail
      return detail
    } catch {
      ElMessage.error('加载模板详情失败')
      return null
    }
  }

  async function fetchVersions(templateId: string): Promise<void> {
    try {
      const result = await api.get<{ items: ContentTemplateVersion[] }>(PATHS.versions(projectId.value, templateId))
      versions.value = result.items || []
      if (versions.value.length) {
        selectedVersion.value = versions.value[0] // 默认最新
      }
    } catch {
      ElMessage.error('加载版本列表失败')
    }
  }

  async function previewSnapshot(year: number, name: string, description: string | null, ownerScope: string): Promise<SnapshotPreviewResult | null> {
    loading.value = true
    try {
      const result = await api.post<SnapshotPreviewResult>(
        PATHS.snapshotPreview(projectId.value),
        null,
        { params: { year } },
      )
      snapshotPreview.value = result
      return result
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || '预检失败')
      return null
    } finally {
      loading.value = false
    }
  }

  async function saveTemplate(year: number, name: string, description: string | null, ownerScope: string, digest: string): Promise<boolean> {
    saveLoading.value = true
    try {
      await api.post(PATHS.save(projectId.value), {
        year, name, description, owner_scope: ownerScope, snapshot_digest: digest,
      })
      ElMessage.success('模板保存成功')
      await fetchTemplates()
      return true
    } catch (e: any) {
      const detail = e?.response?.data?.detail || ''
      if (detail.includes('STALE')) {
        ElMessage.warning('来源附注已变化，请重新预检')
      } else {
        ElMessage.error(detail || '保存失败')
      }
      return false
    } finally {
      saveLoading.value = false
    }
  }

  async function deleteTemplate(templateId: string): Promise<boolean> {
    // ESLint gt-audit/no-delete-without-confirm: 调用方必须在 UI 层二次确认后才调用
    try {
      await api.delete(PATHS.delete(projectId.value, templateId)) // eslint-disable-line gt-audit/no-delete-without-confirm
      ElMessage.success('模板已删除')
      await fetchTemplates()
      return true
    } catch {
      ElMessage.error('删除失败')
      return false
    }
  }

  function reset() {
    templates.value = []
    selectedTemplate.value = null
    selectedVersion.value = null
    versions.value = []
    snapshotPreview.value = null
  }

  return {
    loading, saveLoading,
    templates, selectedTemplate, selectedVersion, versions, snapshotPreview,
    fetchTemplates, fetchDetail, fetchVersions,
    previewSnapshot, saveTemplate, deleteTemplate, reset,
  }
}
