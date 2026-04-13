/**
 * Phase 8 扩展功能 API 服务层
 * 封装所有扩展模块的后端 API 调用
 */
import http from '@/utils/http'

// ─── 会计准则 ───

export interface AccountingStandard {
  id: string
  standard_code: string
  standard_name: string
  standard_description?: string
  is_active: boolean
}

export async function getAccountingStandards(): Promise<AccountingStandard[]> {
  const { data } = await http.get('/api/accounting-standards')
  return data.data ?? data ?? []
}

export async function getAccountingStandard(id: string): Promise<AccountingStandard> {
  const { data } = await http.get(`/api/accounting-standards/${id}`)
  return data.data ?? data
}

export async function switchProjectStandard(projectId: string, standardId: string) {
  const { data } = await http.put(`/api/projects/${projectId}/accounting-standard`, {
    accounting_standard_id: standardId,
  })
  return data.data ?? data
}

// ─── 多语言 ───

export async function getLanguages() {
  const { data } = await http.get('/api/i18n/languages')
  return data.data ?? data ?? []
}

export async function getTranslations(lang: string) {
  const { data } = await http.get(`/api/i18n/translations/${lang}`)
  return data.data ?? data
}

export async function setUserLanguage(userId: string, language: string) {
  const { data } = await http.put(`/api/users/${userId}/language`, { language })
  return data.data ?? data
}

// ─── 审计类型 ───

export async function getAuditTypeRecommendation(type: string) {
  const { data } = await http.get(`/api/audit-types/${type}/recommendation`)
  return data.data ?? data
}

// ─── 自定义模板 ───

export interface CustomTemplate {
  id: string
  template_name: string
  category: string
  version: string
  description?: string
  is_published: boolean
  created_at: string
  updated_at: string
}

export async function getCustomTemplates(params?: {
  category?: string
  published?: boolean
  search?: string
}): Promise<CustomTemplate[]> {
  const { data } = await http.get('/api/custom-templates', { params })
  return data.data ?? data ?? []
}

export async function getCustomTemplate(id: string): Promise<CustomTemplate> {
  const { data } = await http.get(`/api/custom-templates/${id}`)
  return data.data ?? data
}

export async function createCustomTemplate(formData: FormData) {
  const { data } = await http.post('/api/custom-templates', formData)
  return data.data ?? data
}

export async function updateCustomTemplate(id: string, formData: FormData) {
  const { data } = await http.put(`/api/custom-templates/${id}`, formData)
  return data.data ?? data
}

export async function validateCustomTemplate(id: string) {
  const { data } = await http.post(`/api/custom-templates/${id}/validate`)
  return data.data ?? data
}

export async function publishCustomTemplate(id: string) {
  const { data } = await http.post(`/api/custom-templates/${id}/publish`)
  return data.data ?? data
}

export async function copyCustomTemplate(id: string) {
  const { data } = await http.post(`/api/custom-templates/${id}/copy`)
  return data.data ?? data
}

export async function deleteCustomTemplate(id: string) {
  const { data } = await http.delete(`/api/custom-templates/${id}`)
  return data.data ?? data
}

// ─── 电子签名 ───

export interface SignatureRecord {
  id: string
  object_type: string
  object_id: string
  signer_id: string
  signer_name?: string
  signature_level: string
  ip_address?: string
  created_at: string
}

export async function signDocument(payload: {
  object_type: string
  object_id: string
  signature_level: string
  password?: string
  signature_data?: any
}): Promise<SignatureRecord> {
  const { data } = await http.post('/api/signatures/sign', payload)
  return data.data ?? data
}

export async function getSignatureRecords(
  objectType: string,
  objectId: string
): Promise<SignatureRecord[]> {
  const { data } = await http.get(`/api/signatures/${objectType}/${objectId}`)
  return data.data ?? data ?? []
}

export async function verifySignature(id: string) {
  const { data } = await http.post(`/api/signatures/${id}/verify`)
  return data.data ?? data
}

export async function revokeSignature(id: string) {
  const { data } = await http.post(`/api/signatures/${id}/revoke`)
  return data.data ?? data
}

// ─── 监管备案 ───

export interface RegulatoryFiling {
  id: string
  project_id: string
  filing_type: string
  filing_status: string
  submitted_at?: string
  responded_at?: string
  error_message?: string
}

export async function getFilings(params?: {
  filing_type?: string
  filing_status?: string
}): Promise<RegulatoryFiling[]> {
  const { data } = await http.get('/api/regulatory/filings', { params })
  return data.data ?? data ?? []
}

export async function submitCICPAReport(payload: any) {
  const { data } = await http.post('/api/regulatory/cicpa-report', payload)
  return data.data ?? data
}

export async function submitArchivalStandard(payload: any) {
  const { data } = await http.post('/api/regulatory/archival-standard', payload)
  return data.data ?? data
}

export async function retryFiling(id: string) {
  const { data } = await http.post(`/api/regulatory/filings/${id}/retry`)
  return data.data ?? data
}

export async function getFilingStatus(id: string) {
  const { data } = await http.get(`/api/regulatory/filings/${id}/status`)
  return data.data ?? data
}

// ─── 致同编码体系 ───

export interface GTWPCoding {
  id: string
  code_prefix: string
  code_range: string
  cycle_name: string
  wp_type: string
  description?: string
  sort_order: number
}

export async function getGTCoding(): Promise<GTWPCoding[]> {
  const { data } = await http.get('/api/gt-coding')
  return data.data ?? data ?? []
}

export async function getGTCodingDetail(id: string): Promise<GTWPCoding> {
  const { data } = await http.get(`/api/gt-coding/${id}`)
  return data.data ?? data
}

export async function generateWPIndex(projectId: string) {
  const { data } = await http.post(`/api/projects/${projectId}/generate-index`)
  return data.data ?? data ?? []
}

// ─── T型账户 ───

export interface TAccount {
  id: string
  account_code: string
  account_name: string
  opening_balance: number
  entry_count?: number
  net_change?: number
}

export async function getTAccounts(projectId: string): Promise<TAccount[]> {
  const { data } = await http.get(`/api/projects/${projectId}/t-accounts`)
  return data.data ?? data ?? []
}

export async function getTAccount(projectId: string, id: string) {
  const { data } = await http.get(`/api/projects/${projectId}/t-accounts/${id}`)
  return data.data ?? data
}

export async function createTAccount(projectId: string, payload: any) {
  const { data } = await http.post(`/api/projects/${projectId}/t-accounts`, payload)
  return data.data ?? data
}

export async function addTAccountEntry(projectId: string, accountId: string, entry: any) {
  const { data } = await http.post(
    `/api/projects/${projectId}/t-accounts/${accountId}/entries`,
    entry
  )
  return data.data ?? data
}

export async function calculateTAccount(projectId: string, accountId: string) {
  const { data } = await http.post(
    `/api/projects/${projectId}/t-accounts/${accountId}/calculate`
  )
  return data.data ?? data
}

export async function integrateTAccount(projectId: string, accountId: string) {
  const { data } = await http.post(
    `/api/projects/${projectId}/t-accounts/${accountId}/integrate`
  )
  return data.data ?? data
}

// ─── AI插件 ───

export interface AIPlugin {
  id: string
  plugin_name: string
  version: string
  description?: string
  is_enabled: boolean
  config?: any
}

export async function getAIPlugins(): Promise<AIPlugin[]> {
  const { data } = await http.get('/api/ai-plugins')
  return data.data ?? data ?? []
}

export async function enablePlugin(id: string) {
  const { data } = await http.post(`/api/ai-plugins/${id}/enable`)
  return data.data ?? data
}

export async function disablePlugin(id: string) {
  const { data } = await http.post(`/api/ai-plugins/${id}/disable`)
  return data.data ?? data
}

export async function updatePluginConfig(id: string, config: any) {
  const { data } = await http.put(`/api/ai-plugins/${id}/config`, { config })
  return data.data ?? data
}

// ─── Metabase 下钻 ───

export interface DrilldownPath {
  id: string
  name: string
  source: string
  source_field: string
  target_level: string
  description: string
}

export async function getDrilldownConfig(): Promise<DrilldownPath[]> {
  const { data } = await http.get('/api/metabase/drilldown-config')
  return data.data ?? data ?? []
}

export async function buildDrilldownUrl(params: {
  project_id: string
  year: number
  target_level: string
  account_code?: string
  voucher_no?: string
  voucher_date?: string
  aux_code?: string
  aux_type?: string
}): Promise<{ drilldown_url: string; target_level: string }> {
  const { data } = await http.get('/api/metabase/drilldown-url', { params })
  return data.data ?? data
}
