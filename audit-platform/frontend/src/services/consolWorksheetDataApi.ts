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

/** 加载某张表的数据 */
export async function loadWorksheetData(
  projectId: string, year: number, sheetKey: string
): Promise<Record<string, any>> {
  try {
    const { data } = await http.get(
      P.get(projectId, year, sheetKey),
      { validateStatus: (s: number) => s < 600 }
    )
    return data?.content || {}
  } catch {
    return {}
  }
}

/** 保存某张表的数据 */
export async function saveWorksheetData(
  projectId: string, year: number, sheetKey: string, sheetData: Record<string, any>
): Promise<boolean> {
  try {
    const resp = await http.put(
      P.get(projectId, year, sheetKey),
      { sheet_key: sheetKey, data: sheetData },
      { validateStatus: (s: number) => s < 600 }
    )
    return resp.status >= 200 && resp.status < 300
  } catch {
    return false
  }
}

/** 批量加载项目所有表的数据 */
export async function loadAllWorksheetData(
  projectId: string, year: number
): Promise<Record<string, Record<string, any>>> {
  try {
    const resp = await http.get(
      P.listAll(projectId, year),
      { validateStatus: (s: number) => s < 600 }
    )
    // resp.data 可能是数组（直接返回）或 { content: 数组 }（被拦截器解包）
    let items = resp.data
    if (items && !Array.isArray(items) && Array.isArray(items.content)) {
      items = items.content
    }
    if (!Array.isArray(items)) items = []
    const result: Record<string, Record<string, any>> = {}
    for (const item of items) {
      if (item?.sheet_key && item?.content) {
        result[item.sheet_key] = item.content
      }
    }
    return result
  } catch {
    return {}
  }
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
