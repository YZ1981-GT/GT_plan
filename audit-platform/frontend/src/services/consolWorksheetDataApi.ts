/**
 * 合并工作底稿数据存储 API
 * 通用 JSON 存储，支持所有 16 张表的保存/加载
 */
import http from '@/utils/http'
import { consolWorksheetData as P } from '@/services/apiPaths'

export interface WorksheetDataResponse {
  project_id: string
  year: number
  sheet_key: string
  content: Record<string, any>
  updated_at?: string
}

export interface G7LinkageCompany {
  company_code: string
  company_name: string
  parent_code?: string
}

export interface G7LinkageFieldDiff {
  sheet_key: string
  identity: string
  company_name?: string
  field: string
  old_value: unknown
  new_value: unknown
  status: 'added' | 'changed' | 'conflict' | 'unchanged'
  selected: boolean
}

export interface G7LinkageSuggestion {
  id: string
  type: string
  source_sheet: string
  company_code: string
  company_name: string
  acquisition_date?: string | null
  acquisition_cost?: number | null
  identifiable_net_assets_fv?: number | null
  parent_share_ratio?: number | null
  goodwill_amount?: number | null
  non_controlling_interest_share?: number | null
  change_type?: string
  before_ratio?: number | null
  after_ratio?: number | null
  amount?: number | null
  equity_adjustment?: number | null
  entry_type?: string
  account_code?: string
  account_name?: string
  debit_amount?: number | null
  credit_amount?: number | null
  description?: string
  selected_default?: boolean
  note?: string
}

export interface G7LinkagePreview {
  source_wp_id?: string | null
  source_updated_at?: string | null
  item_versions?: Record<string, string>
  sources_used: string[]
  unresolved_companies: string[]
  ambiguous_companies?: string[]
  available_companies: G7LinkageCompany[]
  counts: Record<string, { candidate: number; importable: number }>
  targets: Record<string, Record<string, any>[]>
  importable: Record<string, Record<string, any>[]>
  field_diffs?: G7LinkageFieldDiff[]
  diff_summary?: {
    added: number
    changed: number
    conflict: number
    unchanged: number
  }
  suggestions?: G7LinkageSuggestion[]
  skipped_net_asset_fields?: Array<{
    investee_name: string
    company_code?: string
    field: string
    reason: string
  }>
  linkage_stale?: boolean
  stale_sheets?: string[]
}

export interface PriorYearWorksheetResult {
  found: boolean
  source_year?: number
  source_key?: string
  content: Record<string, any>
  message?: string
  updated_at?: string | null
}

export type WorksheetLoadStatus = 'loaded' | 'empty' | 'error'

export interface WorksheetLoadResult<T extends Record<string, any> = Record<string, any>> {
  status: WorksheetLoadStatus
  data: T
  /** 各表当前版本号映射（sheet_key → version），用于后续 CAS 保存。 */
  versions: Record<string, number>
  errorMessage?: string
}

function isRecord(value: unknown): value is Record<string, any> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function errorMessage(error: any, fallback: string): string {
  const detail = error?.response?.data?.detail ?? error?.response?.data?.message
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail && typeof detail === 'object' && typeof detail.message === 'string') return detail.message
  if (typeof error?.message === 'string' && error.message.trim()) return error.message
  return fallback
}

function loadError<T extends Record<string, any>>(message: string): WorksheetLoadResult<T> {
  return { status: 'error', data: {} as T, versions: {}, errorMessage: message }
}

/** 加载某张表的数据；成功空表与 HTTP/解析错误保持可区分。 */
export async function loadWorksheetData(
  projectId: string, year: number, sheetKey: string
): Promise<WorksheetLoadResult> {
  try {
    const response = await http.get(P.get(projectId, year, sheetKey))
    const payload = response.data
    if (!isRecord(payload) || !isRecord(payload.content)) {
      return loadError('工作底稿响应格式无法识别')
    }
    const content = payload.content
    const version = typeof payload.version === 'number' ? payload.version : 0
    return {
      status: Object.keys(content).length ? 'loaded' : 'empty',
      data: content,
      versions: { [sheetKey]: version },
    }
  } catch (error) {
    return loadError(errorMessage(error, '工作底稿加载失败'))
  }
}

/** 工作底稿版本冲突错误（后端 409 worksheet_version_conflict）。 */
export class WorksheetVersionConflictError extends Error {
  readonly code = 'worksheet_version_conflict' as const
  readonly expectedVersion: number | null
  readonly actualVersion: number | null

  constructor(expectedVersion: number | null, actualVersion: number | null, message?: string) {
    super(message || '工作底稿已被其他操作修改，请重新加载后再保存')
    this.name = 'WorksheetVersionConflictError'
    this.expectedVersion = expectedVersion
    this.actualVersion = actualVersion
  }
}

export interface WorksheetSaveResult {
  ok: boolean
  version: number
}

/**
 * 保存某张表的数据；返回保存后的新版本号。
 *
 * - `expectedVersion` 传入时启用 CAS：后端校验当前版本 == expectedVersion，
 *   不匹配返回 409（抛 WorksheetVersionConflictError）。
 * - `expectedVersion` 省略时走兼容 upsert（首次创建或无版本保护覆盖）。
 */
export async function saveWorksheetData(
  projectId: string,
  year: number,
  sheetKey: string,
  sheetData: Record<string, any>,
  expectedVersion?: number,
): Promise<WorksheetSaveResult> {
  const body: Record<string, any> = { sheet_key: sheetKey, data: sheetData }
  if (expectedVersion !== undefined) {
    body.expected_version = expectedVersion
  }
  try {
    const response = await http.put(P.get(projectId, year, sheetKey), body)
    if (typeof response.status === 'number' && (response.status < 200 || response.status >= 300)) {
      throw new Error(`工作底稿保存失败（HTTP ${response.status}）`)
    }
    const version = typeof response.data?.version === 'number' ? response.data.version : 0
    return { ok: true, version }
  } catch (err: any) {
    const status = err?.response?.status
    const detail = err?.response?.data?.detail
    if (status === 409 && detail?.code === 'worksheet_version_conflict') {
      throw new WorksheetVersionConflictError(
        detail.expected_version ?? null,
        detail.actual_version ?? null,
        detail.message,
      )
    }
    throw err
  }
}

/** 批量加载项目所有表的数据；成功零行返回 empty，异常返回 error。 */
export async function loadAllWorksheetData(
  projectId: string, year: number
): Promise<WorksheetLoadResult<Record<string, Record<string, any>>>> {
  try {
    const response = await http.get(P.listAll(projectId, year))
    // resp.data 可能是数组（直接返回）或 { content: 数组 }（统一信封已解包前的兼容形状）
    const payload = response.data
    const items = Array.isArray(payload)
      ? payload
      : isRecord(payload) && Array.isArray(payload.content)
        ? payload.content
        : null
    if (!items) return loadError('工作底稿批量响应格式无法识别')

    const result: Record<string, Record<string, any>> = {}
    const versions: Record<string, number> = {}
    for (const item of items) {
      if (!isRecord(item) || typeof item.sheet_key !== 'string' || !isRecord(item.content)) {
        return loadError('工作底稿批量响应包含无法解析的表数据')
      }
      result[item.sheet_key] = item.content
      versions[item.sheet_key] = typeof item.version === 'number' ? item.version : 0
    }
    const hasContent = Object.values(result).some((content) => Object.keys(content).length > 0)
    return { status: hasContent ? 'loaded' : 'empty', data: result, versions }
  } catch (error) {
    return loadError(errorMessage(error, '工作底稿批量加载失败'))
  }
}

export async function loadPriorYearWorksheetData(
  projectId: string, year: number, sheetKey: string,
): Promise<PriorYearWorksheetResult> {
  const { data } = await http.get(
    `/api/consol-worksheet-data/${projectId}/${year}/prior-year/${sheetKey}`,
  )
  if (!isRecord(data) || typeof data.found !== 'boolean' || !isRecord(data.content)) {
    throw new Error('上年工作底稿响应格式无法识别')
  }
  return data as PriorYearWorksheetResult
}

/** 预览 G7 到合并工作底稿的字段映射，不产生写入。 */
export async function previewG7Linkage(
  projectId: string, year: number
): Promise<G7LinkagePreview> {
  const { data } = await http.get(
    `/api/consol-worksheet-data/g7-linkage/${projectId}/${year}/preview`
  )
  return data
}

/** 按用户确认的主体映射导入；默认只填充目标空值。 */
export async function importG7Linkage(
  projectId: string,
  year: number,
  payload: {
    company_mappings: Record<string, string>
    sheet_keys?: string[]
    overwrite?: boolean
    expected_versions?: Record<string, string>
    selected_diffs?: Array<{ sheet_key: string; identity: string; field: string }>
    apply_suggestion_ids?: string[]
  },
): Promise<{
  imported: Record<string, number>
  scope_synced?: number
  suggestions_applied?: number
  unresolved_companies: string[]
  ambiguous_companies?: string[]
  source_wp_id?: string
  item_versions?: Record<string, string>
}> {
  const { data } = await http.post(
    `/api/consol-worksheet-data/g7-linkage/${projectId}/${year}/import`,
    payload,
  )
  return data
}
