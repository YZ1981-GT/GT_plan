/**
 * 共享配置模板 API
 * 支持5类配置的三层共享：system/group/personal
 */
import http from '@/utils/http'
import { sharedConfig as P } from '@/services/apiPaths'

export interface SharedConfigTemplate {
  id: string
  name: string
  description?: string
  config_type: string
  owner_type: string  // system / group / personal
  owner_user_id?: string
  owner_project_id?: string
  owner_project_name?: string
  config_version: number
  applicable_standard?: string
  is_public: boolean
  reference_count: number
  created_at?: string
  updated_at?: string
  config_data?: Record<string, any>
}

export interface ConfigReference {
  id: string
  template_name: string
  config_type: string
  applied_at?: string
  is_customized: boolean
}

const OWNER_TYPE_LABELS: Record<string, string> = {
  system: '🏢 事务所默认',
  group: '🏗️ 集团模板',
  personal: '👤 个人模板',
}

export function getOwnerTypeLabel(type: string): string {
  return OWNER_TYPE_LABELS[type] || type
}

const CONFIG_TYPE_LABELS: Record<string, string> = {
  report_mapping: '国企/上市转换规则',
  account_mapping: '科目映射',
  formula_config: '公式审核配置',
  report_template: '报告模板',
  workpaper_template: '底稿模板',
}

export function getConfigTypeLabel(type: string): string {
  return CONFIG_TYPE_LABELS[type] || type
}

/** 查询可用模板列表 */
export async function listSharedTemplates(configType: string, projectId?: string) {
  const params: any = { config_type: configType }
  if (projectId) params.project_id = projectId
  const { data } = await http.get(P.templates, { params })
  return (data ?? []) as SharedConfigTemplate[]
}

/** 保存为模板 */
export async function saveAsTemplate(body: {
  name: string
  config_type: string
  config_data: Record<string, any>
  owner_type?: string
  owner_project_id?: string
  description?: string
  applicable_standard?: string
  is_public?: boolean
}) {
  const { data } = await http.post(P.templates, body)
  return data as SharedConfigTemplate
}

/** 获取模板详情 */
export async function getTemplateDetail(templateId: string) {
  const { data } = await http.get(P.detail(templateId))
  return data as SharedConfigTemplate
}

/** 更新模板 */
export async function updateTemplate(templateId: string, body: Record<string, any>) {
  const { data } = await http.put(P.detail(templateId), body)
  return data as SharedConfigTemplate
}

/** 删除模板 */
export async function deleteTemplate(templateId: string) {
  const { data } = await http.delete(P.detail(templateId))
  return data
}

/** 引用模板到项目 */
export async function applyTemplate(templateId: string, projectId: string) {
  const { data } = await http.post(P.apply, {
    template_id: templateId,
    project_id: projectId,
  })
  return data as { success: boolean; message: string; config_type: string }
}

/** 查询项目引用历史 */
export async function listReferences(projectId: string) {
  const { data } = await http.get(P.references(projectId))
  return (data ?? []) as ConfigReference[]
}
